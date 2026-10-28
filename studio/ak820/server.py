"""Loopback-only application service. Browser requests cannot specify HID commands."""
import argparse
import base64
import binascii
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from . import imaging
from .protocol import build_payload
from .transport import NativeTransport
from .rgb import normalize_rgb, DEFAULT_RGB_SETTINGS
from .live_bridge import LiveBridge

ROOT = Path(__file__).resolve().parent.parent
CAPABILITIES = {
    'screen': {'available': True, 'size': [128,128], 'max_frames':140, 'physical_still_verified':True,
               'physical_animation_verified':False},
    'rgb': {'available':True, 'physical_verified':False, 'reason':'Kaynak doğrulandı; LED görünümü kullanıcı tarafından kontrol edilir.'},
    'integrations': {'codex':False, 'claude_code':False},
}
ID_PATTERN = re.compile(r'^[a-f0-9]{24}$')
# GIF upload to QMK writes external flash at 0xCE0000 and has not been run on
# the keyboard yet. It stays off, as it was on live-v1, until a separate
# hardware test; showing/hiding an already stored GIF is unaffected.
QMK_MEDIA_UPLOAD_ENABLED = False
QMK_MEDIA_REASON = 'QMK görsel yükleme donanımda henüz doğrulanmadı; ayrı test adımıyla açılacak.'



class App:
    def __init__(self, state_dir, simulation=None, *, live=False):
        self.path = Path(state_dir)
        self.path.mkdir(parents=True, exist_ok=True, mode=0o700)
        for name in ('assets','renders','presets','transfers'):
            (self.path/name).mkdir(exist_ok=True, mode=0o700)
        self.token = secrets.token_urlsafe(32)
        self.simulation = simulation
        self.transport = NativeTransport()
        self.lock = threading.Lock()
        self.render_lock = threading.Semaphore(1)
        self.live = LiveBridge(enabled=live and not simulation)
        self.job = {'state':'idle','progress':0,'message':'Göndermeye hazır.'}
        self.device_cache = (0, {})
        self.device_lock = threading.Lock()
        self.rgb = {'last_settings':dict(DEFAULT_RGB_SETTINGS),'last_enabled':None,
                    'last_applied':None,'source':'local'}
        try:
            record = json.loads((self.path/'rgb-settings.json').read_text())
            saved = normalize_rgb(record['last_settings'])
            if saved['mode'] != 0:
                self.rgb['last_settings'] = saved
            self.rgb['last_applied'] = record.get('last_applied')
            # Restart never asserts a measured LED state.
        except (OSError, ValueError, KeyError, TypeError):
            pass

    def device(self):
        if self.simulation:
            return {'connected':self.simulation != 'disconnected', 'name':'AK820 Pro · TEST',
                    'message':'TEST MODU · USB’ye yazılmaz.', 'simulated':True}
        # hidapi's macOS manager is bound to its initializing run loop. Calling
        # enumerate from disposable HTTP threads caused native CFRunLoop crashes.
        # Probe once on a short-lived process's MAIN thread; never load hid here.
        with self.device_lock:
            if time.monotonic()-self.device_cache[0] > 2:
                try:
                    result = subprocess.run([sys.executable, '-m', 'ak820.worker', '--detect'],
                                            cwd=ROOT, env=os.environ.copy(), capture_output=True,
                                            text=True, timeout=3, check=True)
                    value = json.loads(result.stdout)
                    if not isinstance(value, dict) or not isinstance(value.get('connected'), bool):
                        raise ValueError('Invalid device probe response')
                    value['name'] = 'AJAZZ AK820 Pro'
                except Exception:
                    value = {'connected':False,'name':'AJAZZ AK820 Pro',
                             'message':'USB bağlantısı kontrol edilemiyor. Bağlantı yeniden denenecek.'}
                self.device_cache = (time.monotonic(), value)
            return dict(self.device_cache[1])

    def valid_path(self, folder, ident, suffix):
        if not isinstance(ident,str) or not ID_PATTERN.fullmatch(ident):
            raise ValueError('Geçersiz kayıt kimliği.')
        return self.path/folder/(ident+suffix)

    def state(self):
        presets = []
        for file in (self.path/'presets').glob('*.json'):
            try:
                data = json.loads(file.read_text())
                presets.append({'id':data['id'],'name':data['name']})
            except (OSError,ValueError,KeyError):
                continue
        with self.lock:
            job = dict(self.job)
            rgb = json.loads(json.dumps(self.rgb))
        device=self.device()
        capabilities=json.loads(json.dumps(CAPABILITIES))
        stock=bool(device.get('firmware')=='stock' or self.simulation)
        modern=bool(device.get('firmware')=='qmk' and self.live.supports_v2())
        for feature in ('screen','rgb'):
            capabilities[feature]['hardware_send_available']=stock or modern
            capabilities[feature]['available']=stock or modern
            if not stock and not modern:capabilities[feature]['reason']='Bu işlem için yeni Studio firmware gerekli; önizleme kullanılabilir.'
        if device.get('firmware')=='qmk':
            capabilities['screen'].update(max_frames=96,min_frame_ms=100,physical_still_verified=False,physical_animation_verified=False)
            if modern and not QMK_MEDIA_UPLOAD_ENABLED:
                capabilities['screen'].update(available=False,hardware_send_available=False,reason=QMK_MEDIA_REASON)
            capabilities['rgb']['physical_verified']=False
            if modern:
                from .qmk_rgb import capabilities as rgb_capabilities
                capabilities['rgb'].update(rgb_capabilities())
                rgb['measured']=self.live.rgb_state()
                rgb['source']='device'
        capabilities['integrations']={'codex':True,'claude_code':True}
        return {'token':self.token,'device':device,'job':job,'capabilities':capabilities,
                'presets':sorted(presets,key=lambda p:p['name'].casefold()),'rgb':rgb}

    def connections(self):
        from .ai_sources import get_connections_snapshot
        return get_connections_snapshot()

    def connection_action(self, provider, action, body):
        if body:
            raise ValueError('Bağlantı isteği ek alan içermemeli.')
        from .ai_sources import connection_action
        result = connection_action(provider, action)
        # Clear stopped providers from the bridge immediately. The next regular
        # heartbeat propagates this state without starting an extra HID writer.
        if self.live.enabled:
            self.live._sources()
        return result

    def close(self):
        self.live.close()
        from .ai_sources import shutdown_ai_sources
        shutdown_ai_sources()

    def import_image(self, body):
        try:
            data = base64.b64decode(body['data'], validate=True)
        except (KeyError, ValueError, binascii.Error, TypeError):
            raise ValueError('Dosya verisi okunamadı.')
        meta = imaging.inspect_image(data)
        ident = hashlib.sha256(data).hexdigest()[:24]
        name = str(body.get('name','Görsel'))[:160]
        self.valid_path('assets',ident,'.bin').write_bytes(data)
        meta.update(asset_id=ident,name=name)
        self.valid_path('assets',ident,'.json').write_text(json.dumps(meta,ensure_ascii=False))
        return meta

    def asset(self, ident):
        if ident is None:
            return None, {'name':'Studio / Orbit'}
        return self.valid_path('assets',ident,'.bin').read_bytes(), json.loads(self.valid_path('assets',ident,'.json').read_text())

    def preview(self, body):
        if not self.render_lock.acquire(timeout=10):
            raise RuntimeError('Önizleme hazırlanıyor. Biraz sonra yeniden deneyin.')
        try:
            s = imaging.normalize_settings(body.get('settings',{}))
            ident = imaging.render_key(body.get('asset_id'),s)
            manifest = self.valid_path('renders',ident,'.json')
            if manifest.exists():
                return json.loads(manifest.read_text())
            data, asset = self.asset(body.get('asset_id'))
            frames, delays, warnings = imaging.render(data,s)
            payload = build_payload(frames,delays)
            self.valid_path('renders',ident,'.bin').write_bytes(payload)
            frames[0].save(self.valid_path('renders',ident,'.png'))
            animated = len(frames)>1
            if animated:
                frames[0].save(self.valid_path('renders',ident,'.webp'),save_all=True,append_images=frames[1:],
                               duration=delays,loop=0,lossless=True,method=0)
            meta = dict(render_id=ident,preview_url=f'/media/{ident}'+('.webp' if animated else '.png'),
                        still_url=f'/media/{ident}.png',frame_count=len(frames),duration_ms=sum(delays),
                        blocks=len(payload)//4096,bytes=len(payload),name=asset['name'],warnings=warnings)
            manifest.write_text(json.dumps(meta,ensure_ascii=False))
            # Cache only the most recent 60 renders. Presets retain their original asset.
            manifests = sorted((self.path/'renders').glob('*.json'),key=lambda p:p.stat().st_mtime,reverse=True)
            for old in manifests[60:]:
                for part in old.parent.glob(old.stem+'.*'):
                    part.unlink(missing_ok=True)
            return meta
        finally:
            self.render_lock.release()

    def save_preset(self, body):
        name = str(body.get('name','')).strip()
        if not name or len(name)>60:
            raise ValueError('Kayıt adı 1–60 karakter olmalı.')
        settings = imaging.normalize_settings(body.get('settings',{}))
        self.asset(body.get('asset_id'))
        ident = secrets.token_hex(12)
        record = dict(id=ident,name=name,asset_id=body.get('asset_id'),settings=settings)
        self.valid_path('presets',ident,'.json').write_text(json.dumps(record,ensure_ascii=False))
        return record

    def send(self, body):
        # Immutable server-generated bytes only. No arbitrary host paths, opcodes or selectors.
        ident = body.get('render_id')
        with self.render_lock:
            payload = self.valid_path('renders',ident,'.bin').read_bytes()
        with self.lock:
            if self.job['state']=='sending':
                raise BlockingIOError('Bir aktarım zaten sürüyor.')
            device=self.device()
            if not device.get('connected'):
                raise ConnectionError('Klavyeyi USB ile bağlayın ve kablolu moda alın.')
            modern=device.get('firmware')=='qmk' and self.live.supports_v2()
            if not self.simulation and device.get('firmware')!='stock' and not modern:
                raise ConnectionError('Görsel aktarımı için yeni Studio firmware gerekli.')
            if modern and not QMK_MEDIA_UPLOAD_ENABLED:
                raise ConnectionError(QMK_MEDIA_REASON)
            if modern:
                from .qmk_media import convert_payload
                convert_payload(payload)
            transfer_id = secrets.token_hex(12)
            snapshot = self.valid_path('transfers',transfer_id,'.bin')
            snapshot.write_bytes(payload)
            self.job = {'id':transfer_id,'state':'sending','progress':0,'message':'Aktarım başlıyor…',
                        'render_id':ident,'visual_confirmation':False,'kind':'image'}
            threading.Thread(target=self._send_qmk_worker if modern else self._send_worker,args=(snapshot,),daemon=True).start()
            return dict(self.job)

    def apply_media(self,body):
        self.require_idle()
        return self.live.apply_media(body)

    def require_idle(self):
        with self.lock:
            if self.job['state']=='sending':raise BlockingIOError('Görsel aktarımı tamamlanana kadar bekleyin.')

    def _send_qmk_worker(self,snapshot):
        process=None;timer=None
        try:
            with self.live.io_lock:
                command=[sys.executable,'-m','ak820.media_worker',str(snapshot)]
                process=subprocess.Popen(command,cwd=ROOT,env=os.environ.copy(),stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,bufsize=1)
                process.stdin.write(json.dumps(self.live.operation_context()));process.stdin.close()
                timer=threading.Timer(910,process.kill);timer.daemon=True;timer.start()
                completed=False
                with snapshot.with_suffix('.jsonl').open('w') as log:
                    for line in process.stdout:
                        log.write(line);log.flush()
                        try:event=json.loads(line)
                        except ValueError:continue
                        self.live.accept_operation_event(event)
                        if event.get('event')=='complete':completed=True
                        elif event.get('event')=='error':raise RuntimeError(event.get('message','Görsel aktarımı başarısız.'))
                        if 'progress' in event:self.update_job(progress=event['progress'],message=event.get('message','Aktarılıyor…'))
                if process.wait()!=0 or not completed:raise RuntimeError('Görsel aktarımı tamamlanmadı; otomatik tekrar yapılmadı.')
            self.update_job(state='sent',progress=1,acknowledged=True,visual_confirmation=False,finished_at=time.time(),
                message='Görsel belleğe yazıldı, checksum doğrulandı ve ekranda etkinleştirildi.')
        except Exception as exc:
            self.live.operation_failed()
            self.update_job(state='error',acknowledged=False,progress=0,message=str(exc),finished_at=time.time())
        finally:
            if timer:timer.cancel()
            if process and process.poll() is None:process.kill();process.wait()
            snapshot.unlink(missing_ok=True)

    def _save_rgb(self):
        # Caller holds the shared state lock; atomically replace local selection.
        target = self.path/'rgb-settings.json'
        temp = self.path/'rgb-settings.tmp'
        temp.write_text(json.dumps(self.rgb,ensure_ascii=False))
        temp.replace(target)

    def apply_rgb(self, body):
        settings = normalize_rgb(body.get('settings',{}))
        return self._submit_rgb(settings)

    def power_rgb(self, body):
        enabled = body.get('enabled')
        if not isinstance(enabled,bool):
            raise ValueError('Aydınlatma seçimi açık veya kapalı olmalı.')
        with self.lock:
            settings = dict(self.rgb['last_settings']) if enabled else {'mode':0}
        return self._submit_rgb(normalize_rgb(settings))

    def _submit_rgb(self, settings):
        with self.lock:
            if self.job['state']=='sending':
                raise BlockingIOError('Bir USB aktarımı zaten sürüyor.')
            device=self.device()
            if not device.get('connected'):
                raise ConnectionError('Klavyeyi USB ile bağlayın ve kablolu moda alın.')
            if not self.simulation and device.get('firmware')!='stock':
                raise ConnectionError('Stok aktarım yolu QMK firmware üzerinde kullanılamaz.')
            transfer_id = secrets.token_hex(12)
            snapshot = self.valid_path('transfers',transfer_id,'.rgb')
            snapshot.write_text(json.dumps(settings))
            if settings['mode'] != 0:
                self.rgb['last_settings'] = dict(settings)
                self._save_rgb()
            self.job = {'id':transfer_id,'kind':'rgb','state':'sending','progress':0,
                        'message':'Aydınlatma uygulanıyor…','rgb_settings':dict(settings),
                        'visual_confirmation':False}
            threading.Thread(target=self._send_worker,args=(snapshot,'rgb',dict(settings)),daemon=True).start()
            return dict(self.job)

    def update_job(self, **fields):
        with self.lock:
            self.job.update(fields)

    def _send_worker(self, snapshot, kind="image", rgb_settings=None):
        log_path = snapshot.with_suffix('.jsonl')
        timer = None
        process = None
        terminal = None
        try:
            if self.simulation:
                for index in range(12):
                    time.sleep(.25)
                    if self.simulation=='error' and index==5:
                        raise RuntimeError('TEST: Klavye yanıt vermedi. Otomatik tekrar yapılmadı.')
                    self.update_job(progress=(index+1)/13,message=f'TEST · {index+1}/12 blok aktarılıyor…')
            else:
                command = [sys.executable,'-m','ak820.worker'] + (['--rgb'] if kind=='rgb' else []) + [str(snapshot)]
                process = subprocess.Popen(command,cwd=ROOT,
                                           env=os.environ.copy(),stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                                           text=True,bufsize=1)
                deadline_hit = threading.Event()
                def expire():
                    deadline_hit.set()
                    process.kill()
                timer = threading.Timer(15 if kind=="rgb" else 300,expire)
                timer.daemon=True
                timer.start()
                completed = False
                with log_path.open('w') as log:
                    for line in process.stdout:
                        log.write(line)
                        log.flush()
                        try:
                            event = json.loads(line)
                        except ValueError:
                            continue
                        if event.get('event')=='complete':
                            completed=True
                        elif event.get('event')=='error':
                            raise RuntimeError(event.get('message','USB aktarımı başarısız.'))
                        if 'progress' in event:
                            self.update_job(progress=event['progress'],message=event.get('message','Aktarılıyor…'))
                    code=process.wait()
                if deadline_hit.is_set():
                    raise TimeoutError('Aktarım zaman aşımına uğradı. Otomatik tekrar yapılmadı.')
                if code!=0 or not completed:
                    raise RuntimeError('USB aktarımı tamamlanmadı. Bağlantıyı kontrol edip yeniden deneyin.')
            terminal = dict(state='sent',progress=1,message=('TEST · ' if self.simulation else '')+
                            ('USB komutları iletildi. LED’leri kontrol edin.' if kind=='rgb' else 'Aktarım tamamlandı. Görüntüyü klavye ekranından kontrol edin.'),
                            acknowledged=True,visual_confirmation=False,finished_at=time.time())
        except Exception as e:
            terminal = dict(state='error',message=str(e),acknowledged=False,visual_confirmation=False)
        finally:
            if timer:
                timer.cancel()
            if process and process.poll() is None:
                process.kill()
                process.wait()
            snapshot.unlink(missing_ok=True)
            if terminal:
                with self.lock:
                    if kind=='rgb':
                        self.rgb['last_enabled'] = bool(rgb_settings['mode']) if terminal['state']=='sent' else None
                        if terminal['state']=='sent':
                            self.rgb['last_applied'] = {'settings':rgb_settings,'applied_at':terminal['finished_at'],
                                                       'acknowledged':True,'visual_confirmation':False}
                        try:
                            self._save_rgb()
                        except OSError:
                            terminal['message'] += ' Yerel seçim kaydedilemedi.'
                    self.job.update(terminal)


class Handler(BaseHTTPRequestHandler):
    server_version='AK820Studio/1.0'
    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith(('POST','DELETE')):
            super().log_message(fmt,*args)

    def reply(self, status, data, content_type='application/json; charset=utf-8'):
        if not isinstance(data,bytes):
            data=json.dumps(data,ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(data)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; img-src 'self' blob: data:; style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError,ConnectionResetError):
            pass

    def guard(self, mutation=False):
        expected={f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}'}
        host=self.headers.get('Host','')
        if host not in expected:
            raise PermissionError('Yalnızca yerel bağlantılara izin verilir.')
        origin=self.headers.get('Origin')
        if origin and origin not in {f'http://{h}' for h in expected}:
            raise PermissionError('Bu sayfadan istek kabul edilmedi.')
        if mutation and not secrets.compare_digest(self.headers.get('X-AK820-Token',''),self.server.app.token):
            raise PermissionError('Oturum yenilendi. Sayfayı yenileyin.')

    def do_GET(self): self.handle_route('GET')
    def do_POST(self): self.handle_route('POST')
    def do_DELETE(self): self.handle_route('DELETE')

    def handle_route(self, method):
        try:
            self.guard(method!='GET')
            app=self.server.app
            path=urlparse(self.path).path
            body={}
            if method=='POST':
                length=int(self.headers.get('Content-Length','0'))
                if not 0 < length <= 17*1024*1024:
                    raise ValueError('İstek çok büyük veya boş.')
                if self.headers.get_content_type()!='application/json':
                    raise ValueError('JSON biçiminde istek gerekli.')
                body=json.loads(self.rfile.read(length))
                if not isinstance(body,dict):
                    raise ValueError('Geçersiz istek.')
            if method=='GET' and path=='/api/state':
                return self.reply(200,app.state())
            if method=='GET' and path=='/api/host-link':
                return self.reply(200,app.live.state(app.device()))
            if method=='GET' and path=='/api/connections':
                return self.reply(200,app.connections())
            connection_route=re.fullmatch(r'/api/connections/(codex|claude_code)/(connect|disconnect|refresh|setup)',path)
            if method=='POST' and connection_route:
                return self.reply(200,app.connection_action(*connection_route.groups(),body))
            if method=='GET' and path=='/api/settings':
                return self.reply(200,app.live.settings())
            if method=='POST' and path=='/api/settings':
                app.require_idle()
                return self.reply(200,app.live.apply_settings(body))
            if method=='GET' and path=='/api/media/state':
                return self.reply(200,app.live.media_state())
            if method=='POST' and path=='/api/media/display':
                return self.reply(200,app.apply_media(body))
            routes={'/api/import':app.import_image,'/api/preview':app.preview,'/api/presets':app.save_preset,'/api/send':app.send,'/api/rgb/apply':app.apply_rgb,'/api/rgb/power':app.power_rgb}
            if method=='POST' and path in routes:
                return self.reply(202 if path in ('/api/send','/api/rgb/apply','/api/rgb/power') else 200,routes[path](body))
            if path.startswith('/api/presets/'):
                file=app.valid_path('presets',path.rsplit('/',1)[-1],'.json')
                if method=='GET':
                    return self.reply(200,json.loads(file.read_text()))
                if method=='DELETE':
                    file.unlink()
                    return self.reply(200,{'deleted':True})
            if method=='GET' and path.startswith('/media/'):
                match=re.fullmatch(r'/media/([a-f0-9]{24})\.(png|webp)',path)
                if not match: raise FileNotFoundError()
                file=app.valid_path('renders',match[1],'.'+match[2])
                return self.reply(200,file.read_bytes(),'image/'+match[2])
            if method=='GET' and path in ('/','/index.html','/style.css','/app.js'):
                file=ROOT/'web'/('index.html' if path=='/' else path[1:])
                mime={'.html':'text/html; charset=utf-8','.css':'text/css; charset=utf-8','.js':'text/javascript; charset=utf-8'}[file.suffix]
                return self.reply(200,file.read_bytes(),mime)
            self.reply(404,{'error':'Kayıt bulunamadı.'})
        except PermissionError as e: self.reply(403,{'error':str(e)})
        except (BlockingIOError,ConnectionError) as e: self.reply(409,{'error':str(e)})
        except FileNotFoundError: self.reply(404,{'error':'Kayıt bulunamadı. Görseli yeniden hazırlayın.'})
        except (ValueError,TypeError,KeyError) as e: self.reply(400,{'error':str(e)})
        except Exception as e:
            print(f'Error: {type(e).__name__}: {e}',file=sys.stderr,flush=True)
            self.reply(500,{'error':'İşlem tamamlanamadı. Görseli veya bağlantıyı kontrol edin.'})


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--port',type=int,default=8765)
    p.add_argument('--state-dir',default=str(ROOT/'work'/'state'))
    p.add_argument('--simulate',choices=['connected','disconnected','error'])
    args=p.parse_args()
    server=ThreadingHTTPServer(('127.0.0.1',args.port),Handler)
    server.app=App(args.state_dir,args.simulate,live=True)
    print(f'AK820 Studio http://127.0.0.1:{args.port}'+(' TEST MODE' if args.simulate else ''),flush=True)
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        server.app.close()

if __name__=='__main__': main()
