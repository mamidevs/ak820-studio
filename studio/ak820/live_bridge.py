"""Live companion coordination. HID stays on a subprocess main thread."""
import copy,json,os,secrets,subprocess,sys,threading,time
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

def empty_source(label):
    return {'status':'not_connected','message':label+' verisi bekleniyor.','observed_at':None,'source':None,'windows':[]}

def browser_source(s,now):
    import math
    def finite(value):
        return isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value)
    stamp=s.get('observed_at')
    stamp=stamp if finite(stamp) else None
    age=now-stamp if stamp is not None else None
    ttl=s.get('ttl_seconds',300)
    ttl=ttl if finite(ttl) and ttl>0 else 300
    status=s.get('status','not_connected')
    stale=status=='stale' or (status=='available' and (age is None or age<0 or age>ttl))
    out={'status':status,'source':(s.get('source',{}).get('description') if isinstance(s.get('source'),dict) else s.get('source')),'observed_at':stamp,
         'stale':stale,'message':s.get('message',''),'short':None,'weekly':None}
    # On source failure, retained diagnostic snapshots must not look like live quotas.
    if status in ('error','not_connected'):
        return out
    windows=s.get('windows',[])
    windows=[w for w in windows if isinstance(w,dict)] if isinstance(windows,list) else []
    if any(w.get('limit_id')=='codex' for w in windows):windows=[w for w in windows if w.get('limit_id')=='codex']
    for w in windows:
        key='weekly' if w.get('duration_minutes')==10080 or w.get('id') in ('weekly','seven_day') else 'short' if w.get('duration_minutes')==300 or w.get('id') in ('short','five_hour') else None
        remaining=w.get('remaining_percent');reset=w.get('resets_at')
        reset=reset if finite(reset) and reset>0 else None
        if w.get('status')=='stale' or (reset is not None and now>=reset):out['stale']=True
        if key:out[key]={'remaining_percent':remaining if finite(remaining) and 0<=remaining<=100 else None,'reset_at':reset}
    if out['stale'] and out['status']=='available':out['status']='stale'
    return out

class LiveBridge:
    def __init__(self,enabled=True):
        self.enabled=enabled;self.stop_event=threading.Event();self.lock=threading.Lock();self.io_lock=threading.Lock()
        self.session=secrets.randbelow(0xffffffff)+1;self.sequence=0;self.established=False
        self.sources={'codex':empty_source('Codex'),'claude_code':empty_source('Claude Code')}
        self.link={'state':'disconnected','last_success_at':None,'message':'Klavye bağlantısı bekleniyor.'}
        self.telemetry={}
        self.media={};self.rgb={}
        self.thread=None
        if enabled:
            self.thread=threading.Thread(target=self._loop,name='ak820-live-bridge',daemon=True)
            self.thread.start()
    def close(self):
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
    def _sources(self):
        try:
            from .ai_sources import get_ai_snapshot
            snapshot=get_ai_snapshot()
            sources=snapshot.get('sources',{})
            with self.lock:
                self.sources={k:sources.get(k,empty_source(k)) for k in ('codex','claude_code')}
        except (ImportError,AttributeError):pass
        except Exception:
            with self.lock:
                for source in self.sources.values():
                    source['status']='error';source['message']='Yerel kullanım verisi okunamadı.'
    def _cycle(self,settings=None,media_show=None,rgb_settings=None):
        with self.io_lock:
            with self.lock:sources=copy.deepcopy(self.sources)
            payload={'session':self.session,'sequence':self.sequence,'new_session':not self.established,'sources':sources}
            if settings is not None:payload['settings']=settings
            if media_show is not None:payload['media_show']=media_show
            if rgb_settings is not None:payload['rgb_settings']=rgb_settings
            try:
                process=subprocess.run([sys.executable,'-m','ak820.bridge_worker'],input=json.dumps(payload),cwd=ROOT,
                    env=os.environ.copy(),capture_output=True,text=True,timeout=4,check=True)
                result=json.loads(process.stdout)
                if not isinstance(result,dict):raise ValueError()
            except Exception:result={'connected':False,'message':'Klavye canlı bağlantısı yanıt vermedi.'}
            with self.lock:
                if result.get('connected'):
                    self.sequence=result['sequence'];self.established=True;self.telemetry=result['telemetry']
                    if 'media' in result:self.media=result['media']
                    if 'rgb' in result:self.rgb=result['rgb']
                    self.link={'state':'connected','last_success_at':result['acknowledged_at'],'message':'Studio canlı verisi klavyede onaylandı.'}
                else:
                    self.established=False;self.session=secrets.randbelow(0xffffffff)+1;self.sequence=0
                    self.link.update(state='unsupported' if result.get('unsupported') else 'disconnected',message=result.get('message','Bağlantı yok.'))
            return result
    def operation_context(self):
        # Caller holds io_lock across the full child operation.
        with self.lock:
            return {'session':self.session,'sequence':self.sequence,'new_session':not self.established,'sources':copy.deepcopy(self.sources)}
    def accept_operation_event(self,event):
        if event.get('event')=='bridge':
            with self.lock:
                self.session=event['session'];self.sequence=event['sequence'];self.established=True
                self.telemetry=event['telemetry']
                self.link={'state':'connected','last_success_at':event['acknowledged_at'],'message':'Studio canlı verisi klavyede onaylandı.'}
        elif event.get('event')=='complete' and 'media' in event.get('result',{}):
            with self.lock:self.media=event['result']['media']
    def operation_failed(self):
        with self.lock:
            self.established=False;self.session=secrets.randbelow(0xffffffff)+1;self.sequence=0
    def supports_v2(self):
        with self.lock:
            return self.link['state']=='connected' and time.time()-(self.link.get('last_success_at') or 0)<=15 and self.telemetry.get('bridge_version',0)>=2
    def media_state(self):
        with self.lock:value=dict(self.media)
        if not self.supports_v2():value.update(available=False,show=False,uploading=False)
        return value
    def rgb_state(self):
        with self.lock:return copy.deepcopy(self.rgb) if self.telemetry.get('bridge_version',0)>=2 else {}
    def apply_media(self,body):
        if not isinstance(body,dict) or set(body)!={'show'} or type(body['show']) is not bool:
            raise ValueError('Geçersiz görsel gösterimi seçimi.')
        if not self.enabled:raise ValueError('Önizleme modunda klavye ayarı uygulanmaz.')
        result=self._cycle(media_show=body['show'])
        if not result.get('connected'):raise ConnectionError(result.get('message','Klavye görsel seçimini onaylamadı.'))
        return self.media_state()
    def apply_rgb(self,settings):
        if not self.enabled:raise ValueError('Önizleme modunda klavye ayarı uygulanmaz.')
        result=self._cycle(rgb_settings=settings)
        if not result.get('connected'):raise ConnectionError(result.get('message','Klavye ışık ayarını onaylamadı.'))
        return self.rgb_state()
    def _loop(self):
        while not self.stop_event.is_set():
            self._sources();self._cycle();self.stop_event.wait(5)
    def state(self,device=None):
        now=time.time()
        with self.lock:sources=copy.deepcopy(self.sources);link=dict(self.link);telemetry=dict(self.telemetry)
        stamp=link.get('last_success_at');fresh=link['state']=='connected' and isinstance(stamp,(int,float)) and now-stamp<=15
        if not self.enabled:link={'state':'disconnected','last_success_at':None,'message':'Önizleme modu · USB canlı bağlantısı kapalı.'}
        dev={'connected':fresh,'firmware':(device or {}).get('firmware','qmk' if stamp else 'unknown'),
             'battery_percent':telemetry.get('battery_percent') if fresh else None,
             'charging':telemetry.get('charging') if fresh else None,
             'connection':telemetry.get('connection') if fresh else None,
             'observed_at':stamp,'stale':bool(stamp and not fresh),'message':link['message']}
        return {'device':dev,'codex':browser_source(sources['codex'],now),'claude':browser_source(sources['claude_code'],now),'sync':link}
    def settings(self):
        with self.lock:
            ready=self.link['state']=='connected' and time.time()-(self.link.get('last_success_at') or 0)<=15
            return {'available':ready,'screen_on':self.telemetry.get('screen_on') if ready else None,
                    'sleep_minutes':self.telemetry.get('sleep_minutes') if ready else None,
                    'sleep_choices':[0,1,5,15,30],'persistent':False,'message':'Ayarlar klavye yeniden başlayana kadar geçerlidir.'}
    def apply_settings(self,settings):
        from .qmk_transport import settings_packet
        settings_packet(1,1,settings) # validate before any child/HID access
        if not self.enabled:raise ValueError('Önizleme modunda klavye ayarı uygulanmaz.')
        result=self._cycle(settings=settings)
        if not result.get('connected'):raise ConnectionError(result.get('message','Klavye ayarı onaylamadı.'))
        return self.settings()
