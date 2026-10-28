import contextlib,struct,tempfile,unittest
from pathlib import Path
from ak820.qmk_transport import *
from ak820.live_bridge import browser_source

class Fake:
    def __init__(self):self.writes=[];self.closed=False;self.descriptor=DESCRIPTOR;self.mutate=lambda p:p
    def enumerate(self,*args):return [dict(vendor_id=VID,product_id=PID,manufacturer_string='AJAZZ',product_string='AK820 PRO',release_number=0x100,interface_number=1,bus_type=1,usage_page=0xff60,usage=0x61,path=b'fake')]
    def device(self):return self
    def open_path(self,p):pass
    def get_report_descriptor(self):return self.descriptor
    def write(self,p):self.writes.append(bytes(p));return len(p)
    def read(self,*args):
        r=bytearray(self.writes[-1][1:]);r[6]=1
        if r[2] in (HELLO,SETTINGS):
            r[12:]=bytes(20);r[12]=255;r[13]=2;r[14]=0;r[17]=1;r[18]=3;r[24:28]=b'AST1'
        return self.mutate(r)
    def close(self):self.closed=True

class BridgeTests(unittest.TestCase):
    def source(self,**more):
        s={'status':'available','observed_at':1000,'windows':[{'id':'weekly','duration_minutes':10080,'used_percent':24,'resets_at':5000}]};s.update(more);return s
    def test_weekly_primary_not_five_hour(self):
        p=usage_packet(CODEX,8,2,self.source(),now=1010)
        self.assertEqual((p[7],p[12],p[13]),(1,24,255));self.assertEqual(struct.unpack_from('<I',p,22)[0],10)
    def test_codex_bucket_has_priority(self):
        s=self.source(windows=[{'limit_id':'codex','duration_minutes':10080,'used_percent':26}, {'limit_id':'other','duration_minutes':10080,'used_percent':99}])
        p=usage_packet(CODEX,8,2,s,now=1010);self.assertEqual(p[12],26)
    def test_missing_and_future_never_zero(self):
        for s in ({},self.source(observed_at=2000),self.source(status='error'),self.source(status='not_connected')):
            p=usage_packet(CODEX,8,2,s,now=1010);self.assertEqual(p[7],0);self.assertEqual(p[12:14],b'\xff\xff')
    def test_stale_remains_stale(self):
        p=usage_packet(CODEX,8,2,self.source(status='stale'),now=1010);self.assertGreater(struct.unpack_from('<I',p,22)[0],300)
    def test_malformed_percent(self):
        for n in (-1,101,float('nan'),float('inf'),True,'4'):
            p=usage_packet(CODEX,8,2,self.source(windows=[{'id':'weekly','used_percent':n}]),now=1010);self.assertEqual(p[7],0)
    def test_roundtrip_three_packets_no_stock_writes(self):
        f=Fake()
        with tempfile.TemporaryDirectory() as d:
            out=QmkTransport(f,Path(d)/'lock').cycle(22,65534,True,{'codex':self.source()})
        self.assertEqual(out['sequence'],1);self.assertEqual(len(f.writes),3);self.assertTrue(f.closed)
        self.assertEqual([p[3] for p in f.writes],[HELLO,CODEX,CLAUDE]);self.assertIsNone(out['telemetry']['battery_percent'])
    def test_bad_descriptor_no_writes(self):
        f=Fake();f.descriptor=b'wrong'
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(BridgeError):QmkTransport(f,Path(d)/'lock').cycle(22,0,True,{})
        self.assertEqual(f.writes,[])
    def test_old_firmware_stops_before_snapshots(self):
        f=Fake();f.mutate=lambda p:bytes([255])+bytes(p[1:])
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(BridgeUnsupported):QmkTransport(f,Path(d)/'lock').cycle(22,0,True,{})
        self.assertEqual(len(f.writes),1)
    def test_bad_ack_and_missing_reply(self):
        for mutate in (lambda p:p[:4],lambda p:bytes(p[:4])+b'\x66\x00'+bytes(p[6:]),lambda p:bytes(p[:8])+b'xxxx'+bytes(p[12:])):
            f=Fake();f.mutate=mutate
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(BridgeError):QmkTransport(f,Path(d)/'lock').cycle(22,0,True,{})
            self.assertEqual(len(f.writes),1)
    def test_settings_only_valid_choices(self):
        for settings in ({},{'screen_on':1},{'sleep_minutes':2},{'opcode':1}):
            with self.assertRaises(ValueError):settings_packet(1,1,settings)
        p=settings_packet(1,2,{'screen_on':False,'sleep_minutes':5});self.assertEqual(p[12:14],bytes([0,5]))
    def test_settings_one_write_no_retry(self):
        f=Fake()
        with tempfile.TemporaryDirectory() as d:QmkTransport(f,Path(d)/'lock').cycle(1,0,True,{},settings={'screen_on':False})
        self.assertEqual(len(f.writes),2);self.assertEqual(f.writes[-1][3],SETTINGS)
    def test_ui_mapping_age(self):
        s=browser_source(self.source(),1400);self.assertIsNone(s['short']);self.assertTrue(s['stale']);self.assertEqual(s['status'],'stale')

    def test_unrelated_ff_response_is_not_firmware_classification(self):
        sent=request(HELLO,17,42,1)
        for index in (1,2,3,4,8):
            reply=bytearray(sent);reply[0]=255;reply[index]^=1
            with self.assertRaises(BridgeError) as caught:decode_reply(reply,sent)
            self.assertNotIsInstance(caught.exception,BridgeUnsupported)
        reply=bytearray(sent);reply[0]=255
        with self.assertRaises(BridgeUnsupported):decode_reply(reply,sent)

    def test_ui_mapping_respects_source_stale_and_ttl(self):
        for raw in (self.source(status='stale'),self.source(ttl_seconds=5)):
            source=browser_source(raw,1010)
            self.assertEqual(source['status'],'stale');self.assertTrue(source['stale'])
        raw=self.source(windows=[{'id':'weekly','remaining_percent':76,'resets_at':1005}])
        self.assertTrue(browser_source(raw,1010)['stale'])

    def test_ui_source_error_hides_retained_quotas(self):
        for state in ('error','not_connected'):
            raw=self.source(status=state,windows=[{'id':'weekly','remaining_percent':76}])
            source=browser_source(raw,1010)
            self.assertEqual(source['status'],state);self.assertIsNone(source['weekly'])

    def test_ui_mapping_keeps_codex_bucket_and_ignores_malformed_windows(self):
        raw=self.source(windows=[None,{'limit_id':'other','id':'weekly','remaining_percent':1},
            {'limit_id':'codex','id':'weekly','remaining_percent':76}])
        self.assertEqual(browser_source(raw,1010)['weekly']['remaining_percent'],76)
        raw=self.source(windows=[{'id':'weekly','remaining_percent':float('nan')}])
        self.assertIsNone(browser_source(raw,1010)['weekly']['remaining_percent'])

if __name__=='__main__':unittest.main()

class StudioV2Tests(unittest.TestCase):
    """AST2 firmware: clock is sent, RGB stays on the keyboard's own screen."""
    def fake(self):
        f=Fake();base=f.read
        def read(*args):
            r=bytearray(base(*args))
            if r[1]==0x14:  # media status, as app_media_command answers
                r[12:]=bytes(20);r[15]=96;struct.pack_into('<H',r,26,100);r[28:32]=b'MED2'
            elif r[2] in (HELLO,SETTINGS):r[24:28]=b'AST2'
            return bytes(r)
        f.read=read;return f
    def test_cycle_sends_clock_and_survives_without_host_rgb(self):
        f=self.fake()
        with tempfile.TemporaryDirectory() as d:
            out=QmkTransport(f,Path(d)/'lock').cycle(22,0,True,{})
        self.assertEqual(out['telemetry']['bridge_version'],2)
        self.assertEqual([p[3] for p in f.writes[:4]],[HELLO,CLOCK,CODEX,CLAUDE])
        self.assertEqual(out['rgb'],{})
        self.assertFalse(any(p[3]>=0xA0 for p in f.writes))
    def test_host_rgb_request_is_refused_not_faked(self):
        f=self.fake()
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(BridgeUnsupported):
                QmkTransport(f,Path(d)/'lock').cycle(22,0,True,{},rgb_settings={'mode':1})
    def test_rgb_capability_points_to_the_keyboard(self):
        from ak820.qmk_rgb import capabilities
        c=capabilities();self.assertFalse(c['available']);self.assertIn('Işık',c['reason'])
