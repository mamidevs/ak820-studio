"""Local Studio forwarding preferences and an idempotent Claude status-line tap.

This module never logs out, reads credentials, or starts model turns. Connection
setup is explicit. GETs only read state and schedule finite usage metadata reads.
"""
from __future__ import annotations
import copy
import fcntl
import json
import os
from pathlib import Path
import shlex
import sys
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
PROVIDERS = ('codex', 'claude_code')
ACTIONS = ('connect', 'disconnect', 'refresh', 'setup')


def _atomic(path, value, mode=0o600):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, indent=2, allow_nan=False); stream.write('\n')
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def _json(path, limit=1024*1024):
    with Path(path).open('rb') as stream: data=stream.read(limit+1)
    if len(data)>limit: raise ValueError('Local configuration exceeds size limit')
    parsed=json.loads(data)
    if not isinstance(parsed,dict): raise ValueError('Local configuration must be an object')
    return parsed


class ClaudeStatuslineInstaller:
    def __init__(self, state_dir, settings_path=None, python=None):
        self.state_dir=Path(state_dir)
        config_dir=Path(os.environ.get('CLAUDE_CONFIG_DIR',str(Path.home()/'.claude'))).expanduser()
        self.settings_path=Path(settings_path) if settings_path else config_dir/'settings.json'
        self.binding_path=self.state_dir/'claude-statusline-binding.json'
        self.receiver=Path(__file__).with_name('claude_statusline.py')
        self.export_path=self.state_dir/'claude-native-usage.json'
        self.health_path=self.state_dir/'claude-statusline-health.json'
        self.python=python or sys.executable

    def installed(self):
        try:
            binding=_json(self.binding_path)
            current=_json(self.settings_path).get('statusLine',{})
            return self.receiver.is_file() and isinstance(current,dict) and current.get('command')==binding.get('installed_command')
        except (OSError,ValueError,TypeError): return False

    def setup(self, refresh=False):
        self.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
        lock_path=self.state_dir/'claude-setup.lock'
        fd=os.open(lock_path,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            fcntl.flock(fd,fcntl.LOCK_EX)
            existed=self.settings_path.exists()
            original=self.settings_path.read_bytes() if existed else None
            settings=_json(self.settings_path) if existed else {}
            current=settings.get('statusLine')
            if current is not None and (not isinstance(current,dict) or current.get('type')!='command' or not isinstance(current.get('command'),str)):
                raise ValueError('Mevcut Claude durum satırı biçimi desteklenmiyor; ayar değiştirilmedi.')
            installed=self.installed()
            if installed and not refresh: return False
            if installed:
                binding=_json(self.binding_path)
                binding['export_path']=str(self.export_path)
            else:
                if current and str(self.receiver) in current['command']:
                    raise ValueError('Claude köprü kaydı eksik; mevcut durum satırına dokunulmadı.')
                binding={'original_command':current.get('command') if current else None,
                         'original_statusline':copy.deepcopy(current), 'created_at':time.time(),
                         'export_path':str(self.export_path), 'health_path':str(self.health_path)}
                # Back up only the field being changed, never unrelated env/auth settings.
                _atomic(self.state_dir/f'claude-statusline-before-{time.time_ns()}.json',
                        {'statusLine':copy.deepcopy(current),'settings_existed':existed})
            revision=str(time.time_ns()) if refresh else '0'
            command=shlex.join([self.python,str(self.receiver),'--binding',str(self.binding_path),'--refresh',revision])
            binding['installed_command']=command
            patched=copy.deepcopy(current) if current else {'type':'command'}
            patched['command']=command
            settings['statusLine']=patched
            # Persist binding first; a newly triggered status-line process can read it.
            old_binding=self.binding_path.read_bytes() if self.binding_path.exists() else None
            _atomic(self.binding_path,binding)
            try:
                latest=self.settings_path.read_bytes() if self.settings_path.exists() else None
                if latest!=original: raise ValueError('Claude ayarları eşzamanlı değişti; yeniden deneyin.')
                mode=(self.settings_path.stat().st_mode & 0o777) if existed else 0o600
                _atomic(self.settings_path,settings,mode)
            except BaseException:
                if old_binding is None:
                    self.binding_path.unlink(missing_ok=True)
                else:
                    _atomic(self.binding_path,json.loads(old_binding))
                raise
            return True
        finally:
            os.close(fd)

    def seen(self):
        try:
            health=_json(self.health_path,16384)
            value=health.get('received_at')
            return value if isinstance(value,(int,float)) and not isinstance(value,bool) else None
        except (OSError,ValueError,TypeError): return None


class ConnectionsManager:
    def __init__(self,state_dir=None,settings_path=None,cache=None,clock=time.time):
        from .ai_sources import AISourceCache
        self.state_dir=Path(state_dir) if state_dir else ROOT/'work/state'
        self.config_path=self.state_dir/'connections.json'
        self.clock=clock; self._lock=threading.RLock(); self._closed=False
        self.installer=ClaudeStatuslineInstaller(self.state_dir,settings_path)
        self.cache=cache or AISourceCache(claude_path=self.installer.export_path)
        self._errors={}

    def _load(self):
        # Migration preserves the already enabled live bridge; explicit choices persist.
        defaults={'version':1,'providers':{p:{'enabled':True,'last_attempt_at':None} for p in PROVIDERS}}
        try:
            data=_json(self.config_path,16384)
            providers=data.get('providers',{})
            if not isinstance(providers,dict): raise ValueError('Invalid provider preferences')
            for provider in PROVIDERS:
                saved=providers.get(provider,{})
                if not isinstance(saved,dict): raise ValueError('Invalid provider preference')
                defaults['providers'][provider]={'enabled':saved.get('enabled') is True,
                    'last_attempt_at':saved.get('last_attempt_at')}
        except FileNotFoundError: pass
        except (OSError,ValueError,TypeError):
            for item in defaults['providers'].values():item['enabled']=False
        return defaults

    def ai_snapshot(self):
        with self._lock:
            config=self._load()
            enabled={p:config['providers'][p]['enabled'] and not self._closed for p in PROVIDERS}
            errors=copy.deepcopy(self._errors)
        result=self.cache.get_snapshot(enabled=enabled)
        for provider,message in errors.items():
            if enabled.get(provider):
                source=result['sources'][provider]
                source.update(status='error',message=message,windows=[])
        return result

    def snapshot(self):
        from .ai_sources import _codex_binary
        with self._lock:
            config=self._load(); ai=self.ai_snapshot(); now=self.clock()
            installed=self.installer.installed(); seen=self.installer.seen()
            providers={}
            for provider in PROVIDERS:
                preference=config['providers'][provider]; enabled=preference['enabled'] and not self._closed
                source=ai['sources'][provider]; state=source['status']
                message=source['message']; required=False; user_action=None
                ready=installed if provider=='claude_code' else True
                if provider=='codex':
                    try:_codex_binary()
                    except FileNotFoundError:ready=False;user_action='Codex uygulamasını veya CLI aracını açıp normal hesabınıza giriş yapın.'
                else:
                    required=not installed
                    if not seen:
                        user_action='Açık Claude Code terminalinde Esc ile yardım/menü ekranını kapatın. Gerekirse aynı oturumu kapatıp claude --continue ile yeniden açın; Studio model isteği göndermez.'
                    elif state=='not_connected':
                        user_action='Claude Code veri gönderdi ancak kullanım pencereleri yok. Pro/Max oturumunda normal bir yanıt geldikten sonra tekrar kontrol edin; API veya kurumsal sağlayıcı kota alanını paylaşmayabilir.'
                if not enabled:
                    state='disconnected';message='Studio aktarımı kapalı. Hesap oturumu açık kalır.'
                elif provider in self._errors:
                    state='error';message=self._errors[provider]
                elif state=='not_connected':
                    state='connecting' if provider=='codex' and ai.get('refreshing') else 'waiting'
                    if provider=='claude_code' and not installed:message='Claude Code bağlantısının kurulması gerekiyor.'
                providers[provider]={'enabled':enabled,'state':state,'message':message,
                    'observed_at':source.get('observed_at'),'last_attempt_at':preference.get('last_attempt_at'),
                    'source_age_seconds':source.get('source_age_seconds'),'ttl_seconds':source.get('ttl_seconds'),
                    'source':source.get('source'),'windows':source.get('windows',[]) if enabled else [],
                    'actions':{'connect':not enabled or not ready,'disconnect':enabled,
                        'refresh':enabled and ready,'setup':provider=='claude_code' and required},
                    'setup':{'installed':ready,'required':required,'user_action':user_action,
                             'last_receiver_at':seen if provider=='claude_code' else None}}
            return {'updated_at':now,'providers':providers}

    def action(self,provider,action):
        if provider not in PROVIDERS or action not in ACTIONS:
            raise ValueError('Geçersiz bağlantı işlemi.')
        with self._lock:
            if self._closed:raise ValueError('Bağlantı servisi kapalı.')
            self.state_dir.mkdir(parents=True,exist_ok=True,mode=0o700)
            fd=os.open(self.state_dir/'connections.lock',os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
            try:
                fcntl.flock(fd,fcntl.LOCK_EX)
                config=self._load(); entry=config['providers'][provider]
                if action=='disconnect':
                    entry['enabled']=False
                    _atomic(self.config_path,config)
                    if provider=='codex':self.cache.disconnect_codex()
                    self._errors.pop(provider,None)
                    return self.snapshot()
                if action=='refresh' and not entry['enabled']:
                    raise ValueError('Önce Studio bağlantısını açın.')
                entry['last_attempt_at']=self.clock()
                try:
                    if provider=='claude_code':
                        if action=='refresh' and not self.installer.installed():
                            raise ValueError('Önce Claude Code bağlantısını kurun.')
                        self.installer.setup(refresh=action=='refresh')
                    else:
                        from .ai_sources import _codex_binary
                        _codex_binary()
                        self.cache.request_refresh()
                    entry['enabled']=True
                    self._errors.pop(provider,None)
                except PermissionError:
                    self._errors[provider]='Claude Code ayarını güncelleme izni yok. Bağlantı kurulmadı.'
                except (OSError,ValueError):
                    self._errors[provider]='Yerel bağlantı kurulamadı; mevcut durum satırı veya uygulama kurulumu kontrol edilmeli.'
                _atomic(self.config_path,config)
                return self.snapshot()
            finally:
                os.close(fd)

    def close(self):
        with self._lock:self._closed=True
        self.cache.close()


_manager=None
_manager_lock=threading.Lock()

def get_manager():
    global _manager
    with _manager_lock:
        if _manager is None:_manager=ConnectionsManager()
        return _manager

def shutdown_manager():
    with _manager_lock: manager=_manager
    if manager is not None:manager.close()
