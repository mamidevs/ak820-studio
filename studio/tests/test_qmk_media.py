import struct
import unittest
import zlib
from ak820.protocol import build_payload
from ak820.qmk_media import *
from ak820.qmk_transport import clock_packet, CLOCK, telemetry, BridgeError

class MemoryTransport:
    def __init__(self):
        self.handle=self;self.memory=bytearray(b'\xff'*(0x1000000-BASE));self.packets=[];self.pointer=0;self.ready=False;self.show=False
        self.crc_bad=False;self.last=None
    def exchange(self,p):
        r=bytearray(p);r[6]=1
        if p[2]==HELLO:
            r[12:]=bytes(20);r[12]=100;r[13]=2;r[17]=1;r[18]=3;r[24:28]=b'AST2'
        return r
    def write(self,p):self.last=bytes(p[1:]);self.packets.append(self.last);return len(p)
    def read(self,*unused):
        p=self.last;r=bytearray(p)
        if p[1]==0x14:
            if p[2]==0x91:self.ready=False;self.show=False
            if p[2]==0x92:self.ready=True;self.show=True
            if p[2]==0x93:self.show=bool(p[12])
            if p[2]==0x94:self.show=False
            r[6]=1;r[12:]=bytes(20);r[12]=self.ready;r[13]=self.show;r[15]=96
            if self.ready:
                r[16:18]=self.memory[6:8];r[18:22]=self.memory[8:12];r[22:26]=self.memory[12:16]
            struct.pack_into('<H',r,26,100);r[28:]=b'MED2';return r
        assert p[1]==0x11
        command=p[2];address=int.from_bytes(p[3:6],'big');r[3]=0
        if command==1:r[4:10]=bytes.fromhex('856018')+BASE.to_bytes(3,'big')
        elif command==7:r[4]=0
        elif command==2:
            assert BASE<=address<0x1000000
            self.memory[address-BASE:address-BASE+4096]=b'\xff'*4096
        elif command==3:self.pointer=address
        elif command==4:
            n=p[3];offset=self.pointer-BASE;self.memory[offset:offset+n]=p[4:4+n];self.pointer+=n
        elif command==6:
            n=int.from_bytes(p[6:9],'big');crc=zlib.crc32(self.memory[address-BASE:address-BASE+n])
            if self.crc_bad:crc^=1
            r[4:8]=crc.to_bytes(4,'big')
        return r

class MediaTests(unittest.TestCase):
    def payload(self):return build_payload([bytes([255,0,0])*16384,bytes([0,255,0])*16384],[20,250])
    def test_native_endianness_timing_and_bounds(self):
        h,d,delays=convert_payload(self.payload())
        self.assertEqual(d[:2],b'\xf8\x00');self.assertEqual(d[32768:32770],b'\x07\xe0')
        self.assertEqual(delays,[100,250]);self.assertEqual(h[:4],b'AKM2')
        self.assertEqual(struct.unpack_from('<I',h,12)[0],zlib.crc32(d))
        p=bytearray(self.payload());p[0]=97
        with self.assertRaises(ValueError):convert_payload(bytes(p))
    def test_commit_follows_verify_and_never_writes_stock_region(self):
        fake=MemoryTransport();events=[]
        result=AssetSender(fake,{'session':42,'sequence':0,'new_session':True,'sources':{}},events.append).send(self.payload())
        self.assertTrue(result['verified']);self.assertEqual(result['media']['frame_count'],2)
        operations=[p for p in fake.packets if p[1]==0x11]
        begins=[(i,int.from_bytes(p[3:6],'big')) for i,p in enumerate(operations) if p[2]==3]
        self.assertEqual([address for _,address in begins],[BASE+4096,BASE])
        self.assertTrue(any(p[2]==6 for p in operations[:begins[1][0]]))
        self.assertTrue(events[0]['event']=='bridge');self.assertEqual(events[-1]['event'],'bridge')
    def test_crc_failure_cancels_without_header_commit(self):
        fake=MemoryTransport();fake.crc_bad=True
        with self.assertRaises(BridgeError):AssetSender(fake,{'session':42,'sequence':0,'sources':{}},lambda _:None).send(self.payload())
        self.assertEqual(fake.memory[:4],b'\xff'*4);self.assertFalse(fake.show)
        self.assertFalse(any(p[1]==0x14 and p[2]==0x92 for p in fake.packets))
    def test_malformed_payload_causes_no_write(self):
        fake=MemoryTransport()
        with self.assertRaises(ValueError):AssetSender(fake,{},lambda _:None).send(b'bad')
        self.assertEqual(fake.packets,[])
    def test_clock_encoding_and_rejection(self):
        p=clock_packet(42,2,1791740000,-330)
        self.assertEqual(p[2],CLOCK);self.assertEqual(struct.unpack_from('<Ih',p,12),(1791740000,-330));self.assertEqual(p[18:],bytes(14))
        for epoch,offset in ((0,0),(True,0),(1,841),(1,-841)):
            with self.assertRaises(ValueError):clock_packet(1,1,epoch,offset)

if __name__=='__main__':unittest.main()
