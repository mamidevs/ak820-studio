"""Studio v1 Raw HID bridge. Only fixed telemetry/settings commands; no stock writes."""
from __future__ import annotations
import contextlib
from datetime import datetime
import fcntl
import importlib
import math
import os
from pathlib import Path
import struct
import tempfile
import time

VID, PID = 0x0C45, 0x8009
DESCRIPTOR = bytes.fromhex('0660ff0961a1010962150026ff009520750881020963150026ff00952075089102c0')
CHANNEL, VERSION = 0x13, 1
HELLO, CODEX, CLAUDE, SETTINGS, CLOCK = 0x80, 0x81, 0x82, 0x83, 0x84
UNKNOWN = 0xFFFFFFFF
LOCK_PATH = Path(tempfile.gettempdir()) / f'ak820-0c45-8009-{os.getuid()}.lock'

class BridgeError(RuntimeError): pass
class BridgeUnsupported(BridgeError): pass

def exact_device(entries):
    matches = [x for x in entries if x.get('usage_page')==0xff60 and x.get('usage')==0x61]
    if len(matches)!=1: raise BridgeError('Tek QMK Raw HID aygıtı bulunamadı.')
    d=matches[0]
    expected={'vendor_id':VID,'product_id':PID,'manufacturer_string':'AJAZZ','product_string':'AK820 PRO',
              'release_number':0x0100,'interface_number':1,'bus_type':1}
    if any(d.get(k)!=v for k,v in expected.items()) or not d.get('path'):
        raise BridgeError('QMK aygıt kimliği beklenen firmware ile eşleşmiyor.')
    return d

def detect(backend=None):
    try:
        hid=backend or importlib.import_module('hid')
        exact_device(hid.enumerate(VID,PID))
        return {'connected':True,'supported':True,'firmware':'qmk','name':'AJAZZ AK820 PRO',
                'message':'QMK USB ile bağlı','connection':'USB','descriptor_revision':'0x0100',
                'stock_controls_available':False}
    except Exception as exc:
        return {'connected':False,'supported':False,'firmware':'unknown','message':str(exc)}

def request(command,session,sequence,flags=0):
    if command not in (HELLO,CODEX,CLAUDE,SETTINGS,CLOCK) or not 0<session<=0xffffffff or not 0<=sequence<=65535:
        raise ValueError('Invalid bridge header')
    p=bytearray(32);p[:4]=bytes([7,CHANNEL,command,VERSION]);struct.pack_into('<H',p,4,sequence)
    p[7]=flags;struct.pack_into('<I',p,8,session);return p

def usage_packet(command,session,sequence,source,now=None):
    p=request(command,session,sequence);p[12]=p[13]=255
    now=time.time() if now is None else now
    stamp=source.get('observed_at')
    age=UNKNOWN
    if isinstance(stamp,(float,int)) and not isinstance(stamp,bool) and math.isfinite(stamp) and 0<=now-stamp<UNKNOWN:
        age=int(now-stamp)
    if source.get('status') in ('error','not_connected'):
        age=UNKNOWN
    elif source.get('status')=='stale' and age!=UNKNOWN:
        age=max(301,age)
    windows=source.get('windows',[])
    if isinstance(windows,list) and any(w.get('limit_id')=='codex' for w in windows if isinstance(w,dict)):
        windows=[w for w in windows if isinstance(w,dict) and w.get('limit_id')=='codex']
    for w in windows if isinstance(windows,list) else []:
        duration=w.get('duration_minutes');ident=w.get('id')
        slot=12 if duration==10080 or ident in ('weekly','seven_day') else 13 if duration==300 or ident in ('short','five_hour') else None
        used=w.get('used_percent')
        if slot is None or not isinstance(used,(int,float)) or isinstance(used,bool) or not math.isfinite(used) or not 0<=used<=100:continue
        if age==UNKNOWN:continue
        p[slot]=int(round(used));p[7]|=1 if slot==12 else 2
        reset=w.get('resets_at')
        if isinstance(reset,(int,float)) and not isinstance(reset,bool) and math.isfinite(reset) and 0<reset<=0xffffffff:
            struct.pack_into('<I',p,14 if slot==12 else 18,int(reset))
    struct.pack_into('<I',p,22,age)
    return p

def settings_packet(session,sequence,settings):
    if not isinstance(settings,dict) or set(settings)-{'screen_on','sleep_minutes'} or not settings:raise ValueError('Geçersiz ekran ayarı.')
    p=request(SETTINGS,session,sequence);p[12]=p[13]=255
    if 'screen_on' in settings:
        if not isinstance(settings['screen_on'],bool):raise ValueError('Ekran açık/kapalı olmalı.')
        p[12]=int(settings['screen_on'])
    if 'sleep_minutes' in settings:
        value=settings['sleep_minutes']
        if isinstance(value,bool) or value not in (0,1,5,15,30):raise ValueError('Geçersiz uyku süresi.')
        p[13]=value
    return p

def clock_packet(session,sequence,epoch=None,offset_minutes=None):
    epoch=int(time.time()) if epoch is None else epoch
    offset_minutes=int(datetime.now().astimezone().utcoffset().total_seconds()//60) if offset_minutes is None else offset_minutes
    if isinstance(epoch,bool) or not isinstance(epoch,int) or not 0<epoch<=0xffffffff:
        raise ValueError('Geçersiz saat.')
    if isinstance(offset_minutes,bool) or not isinstance(offset_minutes,int) or not -840<=offset_minutes<=840:
        raise ValueError('Geçersiz saat dilimi.')
    p=request(CLOCK,session,sequence)
    struct.pack_into('<Ih',p,12,epoch,offset_minutes)
    return p

def decode_reply(reply,sent):
    r=bytes(reply)
    if len(r)==33 and r[0]==0:r=r[1:]
    if len(r)!=32:raise BridgeError('Klavye yanıtı eksik veya zaman aşımı.')
    # VIA reports an unsupported command by replacing only byte0 with FF.
    # Correlate even that rejection before classifying the running firmware.
    if r[1:6]!=bytes(sent[1:6]) or r[8:12]!=bytes(sent[8:12]):raise BridgeError('Klavye yanıt kimliği veya sıra numarası uyuşmuyor.')
    if r[0]==0xff:raise BridgeUnsupported('Bu QMK sürümünde canlı Studio köprüsü yok; firmware güncellemesi gerekli.')
    if r[0]!=sent[0]:raise BridgeError('Klavye yanıt kimliği veya sıra numarası uyuşmuyor.')
    if r[6]!=1:raise BridgeError(f'Klavye isteği reddetti (durum {r[6]}).')
    return r

def telemetry(reply):
    r=bytes(reply)
    if r[24:28] not in (b'AST1',b'AST2'):raise BridgeUnsupported('Studio protokol imzası doğrulanamadı.')
    if (r[12]>100 and r[12]!=255) or r[13]&~3 or r[14]>3 or r[17]>1 or r[18] not in (0,1,3,5,15,30) or r[19] or any(r[28:32]):
        raise BridgeError('Klavye durum verisi geçersiz.')
    return {'battery_percent':r[12] if r[12]<=100 else None,'charging':bool(r[13]&1),
            'usb_active':bool(r[13]&2),'connection':{0:'usb',1:'bluetooth',2:'2.4ghz'}.get(r[14]),
            'radio_slot':r[15],'radio_state':r[16],'screen_on':bool(r[17]),'sleep_minutes':r[18],
            'uptime_seconds':struct.unpack_from('<I',r,20)[0],'bridge_version':2 if r[24:28]==b'AST2' else 1}

class QmkTransport:
    def __init__(self,backend=None,lock_path=LOCK_PATH):self.backend=backend;self.lock_path=Path(lock_path);self.handle=None
    @contextlib.contextmanager
    def connected(self):
        fd=os.open(self.lock_path,os.O_WRONLY|os.O_CREAT|os.O_NOFOLLOW,0o600)
        try:
            try:fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise BridgeError('Başka bir klavye aktarımı sürüyor.')
            hid=self.backend or importlib.import_module('hid')
            info=exact_device(hid.enumerate(VID,PID));self.handle=hid.device();self.handle.open_path(info['path'])
            if bytes(self.handle.get_report_descriptor())!=DESCRIPTOR:raise BridgeError('QMK Raw HID rapor yapısı uyuşmuyor.')
            yield self
        finally:
            if self.handle is not None:self.handle.close();self.handle=None
            os.close(fd)
    def exchange(self,p):
        if len(p)!=32 or p[:2]!=bytes([7,CHANNEL]):raise ValueError('Invalid Studio packet')
        count=self.handle.write(bytes([0])+bytes(p))
        if count not in (32,33):raise BridgeError('Klavye paketi tam gönderilemedi.')
        return decode_reply(self.handle.read(32,400),p)
    def cycle(self,session,sequence,new_session,sources,settings=None,media_show=None,rgb_settings=None):
        with self.connected():
            sequence=(sequence+1)&65535
            r=self.exchange(request(HELLO,session,sequence,int(new_session)))
            state=telemetry(r)
            extra={}
            if settings is not None:
                sequence=(sequence+1)&65535
                state=telemetry(self.exchange(settings_packet(session,sequence,settings)))
            else:
                # Older AST1 firmware keeps its original three-packet cycle.
                if state['bridge_version']>=2:
                    sequence=(sequence+1)&65535
                    self.exchange(clock_packet(session,sequence))
                for cmd,key in ((CODEX,'codex'),(CLAUDE,'claude_code')):
                    sequence=(sequence+1)&65535
                    self.exchange(usage_packet(cmd,session,sequence,sources.get(key,{ })))
            if state['bridge_version']>=2:
                from .qmk_media import media_control
                extra['media']=media_control(self,0x93 if media_show is not None else 0x90,media_show)
                from .qmk_rgb import rgb_exchange
                extra['rgb']=rgb_exchange(self,rgb_settings)
            elif media_show is not None or rgb_settings is not None:
                raise BridgeUnsupported('Bu işlem için yeni Studio firmware gerekli.')
        return {'connected':True,'telemetry':state,'sequence':sequence,'acknowledged_at':time.time(),**extra}
