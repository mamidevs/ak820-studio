"""Bounded QMK asset provisioning into the dedicated external-flash region."""
import secrets
import struct
import time
import zlib
from .protocol import validate_payload, FRAME_BYTES
from .qmk_transport import BridgeError, decode_reply, HELLO, CODEX, CLAUDE, request, telemetry, usage_packet, clock_packet

BASE=0xCE0000
HEADER=4096
MAX_FRAMES=96
MIN_DELAY=100

def convert_payload(stock):
    validate_payload(stock)
    count=stock[0]
    if count>MAX_FRAMES:raise ValueError('Bu QMK sürümü en fazla 96 kare destekliyor. GIF’i kısaltın.')
    data=bytearray(stock[256:256+count*FRAME_BYTES])
    data[0::2],data[1::2]=data[1::2],data[0::2] # panel stream: RGB565 MSB first
    header=bytearray(b'\xff'*HEADER)
    header[:16]=struct.pack('<4sBBHII',b'AKM2',2,0,count,len(data),zlib.crc32(data))
    delays=[max(MIN_DELAY,v*2) for v in stock[1:count+1]]
    for i,value in enumerate(delays):struct.pack_into('<H',header,16+i*2,value)
    return bytes(header),bytes(data),delays

def raw_exchange(transport,packet):
    if len(packet)!=32:raise ValueError('Invalid packet length')
    if transport.handle.write(bytes([0])+bytes(packet)) not in (32,33):raise BridgeError('USB paketi eksik gönderildi.')
    reply=bytes(transport.handle.read(32,800))
    if len(reply)==33 and reply[0]==0:reply=reply[1:]
    if len(reply)!=32:raise BridgeError('USB yanıtı gelmedi; yazma otomatik tekrarlanmadı.')
    return reply

def media_control(transport,command=0x90,show=None):
    p=bytearray(32);p[:4]=bytes([7,0x14,command,1])
    struct.pack_into('<H',p,4,secrets.randbelow(65536))
    struct.pack_into('<I',p,8,secrets.randbelow(0xffffffff)+1)
    if show is not None:
        if type(show) is not bool:raise ValueError('Görsel seçimi açık veya kapalı olmalı.')
        p[12]=int(show)
    r=decode_reply(raw_exchange(transport,p),p)
    count=struct.unpack_from('<H',r,16)[0]
    if r[28:32]!=b'MED2' or r[12]>1 or r[13]>1 or r[14]>1 or r[15]!=MAX_FRAMES or count>MAX_FRAMES:
        raise BridgeError('Görsel durum yanıtı doğrulanamadı.')
    return {'available':bool(r[12]),'show':bool(r[13]),'uploading':bool(r[14]),
            'frame_count':count,'max_frames':r[15],'min_frame_ms':struct.unpack_from('<H',r,26)[0],
            'crc32':struct.unpack_from('<I',r,22)[0]}

class AssetSender:
    def __init__(self,transport,context,progress):
        self.t=transport;self.context=dict(context);self.progress=progress;self.last_heartbeat=0;self.deadline=time.monotonic()+900
    def heartbeat(self,force=False):
        now=time.monotonic()
        if now>self.deadline:raise TimeoutError('Görsel aktarımı süre sınırına ulaştı; otomatik tekrar yok.')
        if not force and now-self.last_heartbeat<5:return
        c=self.context
        def next_seq():c['sequence']=(c['sequence']+1)&65535;return c['sequence']
        r=self.t.exchange(request(HELLO,c['session'],next_seq(),int(c.get('new_session',False))))
        state=telemetry(r)
        if state['bridge_version']<2:raise BridgeError('Görsel aktarımı için yeni Studio firmware gerekli.')
        c['new_session']=False
        self.t.exchange(clock_packet(c['session'],next_seq()))
        for cmd,key in ((CODEX,'codex'),(CLAUDE,'claude_code')):
            self.t.exchange(usage_packet(cmd,c['session'],next_seq(),c.get('sources',{}).get(key,{})))
        self.last_heartbeat=now
        self.progress({'event':'bridge','session':c['session'],'sequence':c['sequence'],'telemetry':state,'acknowledged_at':time.time()})
    def flash(self,command,payload=b'',allow_more=False):
        if len(payload)>29:raise ValueError('Flash packet too long')
        p=bytes([7,0x11,command])+payload+bytes(29-len(payload))
        deadline=time.monotonic()+3
        while True:
            self.heartbeat()
            r=raw_exchange(self.t,p)
            if r[:3]!=p[:3]:raise BridgeError('Flash yanıtı istekle eşleşmiyor.')
            if r[3]==1: # explicitly refused BUSY means this packet consumed no bytes
                if time.monotonic()>deadline:raise TimeoutError('Klavye belleği hazır olmadı.')
                time.sleep(.005);continue
            if r[3] not in ((0,4) if allow_more else (0,)):raise BridgeError(f'Klavye görsel işlemini reddetti ({r[3]}).')
            return r
    def wait_idle(self):
        deadline=time.monotonic()+3
        while self.flash(7)[4]:
            if time.monotonic()>deadline:raise TimeoutError('Bellek yazması tamamlanmadı.')
            time.sleep(.005)
    @staticmethod
    def addr(value):return value.to_bytes(3,'big')
    def write(self,address,data,report=True):
        if address<BASE or address+len(data)>0x1000000 or address%256:raise ValueError('Görsel bölgesi dışında yazma reddedildi.')
        self.wait_idle();self.flash(3,self.addr(address))
        total=len(data)
        for offset in range(0,total,28):
            chunk=data[offset:offset+28];self.flash(4,bytes([len(chunk)])+chunk)
            if report and offset%7168==0:self.progress({'event':'progress','progress':.15+.65*offset/max(total,1),'message':f'Görsel yazılıyor · %{round(100*offset/max(total,1))}'})
        self.flash(5);self.wait_idle()
    def verify(self,address,data):
        r=self.flash(6,self.addr(address)+self.addr(len(data)),True)
        while r[3]==4:r=self.flash(9,allow_more=True)
        actual=int.from_bytes(r[4:8],'big')
        if actual!=zlib.crc32(data):raise BridgeError('Görsel checksum doğrulaması başarısız; görüntü etkinleştirilmedi.')
    def send(self,stock):
        header,data,delays=convert_payload(stock) # all validation before hardware writes
        self.heartbeat(True)
        info=self.flash(1)
        if info[6]!=0x18 or int.from_bytes(info[7:10],'big')!=BASE:raise BridgeError('Harici belleğin kapasitesi veya görsel bölgesi beklenenle eşleşmiyor.')
        media_control(self.t,0x91)
        try:
            sectors=(HEADER+len(data))//4096
            for index in range(sectors):
                self.wait_idle();self.flash(2,self.addr(BASE+index*4096))
                if index%8==0:self.progress({'event':'progress','progress':.15*index/sectors,'message':'Görsel alanı hazırlanıyor…'})
            self.write(BASE+HEADER,data)
            self.progress({'event':'progress','progress':.85,'message':'Klavye belleğindeki görsel doğrulanıyor…'})
            self.verify(BASE+HEADER,data)
            # Commit a valid header only after the entire payload verifies.
            self.write(BASE,header,False);self.verify(BASE,header)
            state=media_control(self.t,0x92)
            if state['crc32']!=zlib.crc32(data) or state['frame_count']!=len(delays) or not state['show']:
                raise BridgeError('Görsel etkinleştirme onayı doğrulanamadı.')
            self.heartbeat(True)
            return {'verified':True,'media':state,'bytes':len(data),'delays_ms':delays}
        except Exception:
            try:media_control(self.t,0x94)
            except Exception:pass
            raise
