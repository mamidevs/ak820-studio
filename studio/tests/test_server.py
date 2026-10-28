import base64
from concurrent.futures import ThreadPoolExecutor
import io
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer
from PIL import Image
from ak820.server import App, Handler

class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.app=App(self.temp.name,'connected')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True); self.thread.start()
        self.url=f'http://127.0.0.1:{self.server.server_port}'
        self.token=self.server.app.token
    def tearDown(self):
        deadline=time.monotonic()+6
        while self.server.app.job['state']=='sending' and time.monotonic()<deadline: time.sleep(.05)
        self.server.shutdown(); self.server.server_close(); self.temp.cleanup()
    def request(self,path,body=None,headers=None):
        h={'Content-Type':'application/json','X-AK820-Token':self.token}; h.update(headers or {})
        req=urllib.request.Request(self.url+path,data=json.dumps(body).encode() if body is not None else None,headers=h)
        try:
            with urllib.request.urlopen(req) as r: return r.status,json.load(r)
        except urllib.error.HTTPError as r: return r.code,json.load(r)
    def test_origin_and_token_guard(self):
        self.assertEqual(self.request('/api/preview',{}, {'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.request('/api/preview',{}, {'X-AK820-Token':''})[0],403)
        self.assertEqual(self.request('/api/state',headers={'Host':'evil.example'})[0],403)
        self.assertEqual(self.server.app.job['state'],'idle')
    def test_upload_preview_and_preset_roundtrip_no_writes(self):
        b=io.BytesIO(); Image.new('RGB',(80,60),'red').save(b,format='PNG')
        code,asset=self.request('/api/import',{'name':'Kırmızı.png','data':base64.b64encode(b.getvalue()).decode()})
        self.assertEqual(code,200)
        s={'effect':'mono','fit':'contain'}
        code,preview=self.request('/api/preview',{'asset_id':asset['asset_id'],'settings':s})
        self.assertEqual(code,200); self.assertEqual(preview['blocks'],9)
        code,preset=self.request('/api/presets',{'name':'Deneme','asset_id':asset['asset_id'],'settings':s})
        self.assertEqual(code,200)
        code,loaded=self.request('/api/presets/'+preset['id'])
        self.assertEqual(loaded['settings']['effect'],'mono')
        self.assertEqual(self.server.app.job['state'],'idle')
        self.assertEqual(list((Path(self.temp.name)/'transfers').iterdir()),[])
    def test_single_active_job_and_ack_not_visual(self):
        _,preview=self.request('/api/preview',{})
        with ThreadPoolExecutor(2) as pool:
            results=list(pool.map(lambda _:self.request('/api/send',{'render_id':preview['render_id']}),range(2)))
        self.assertEqual(sorted(x[0] for x in results),[202,409])
        deadline=time.monotonic()+5
        while self.server.app.job['state']=='sending' and time.monotonic()<deadline: time.sleep(.05)
        self.assertEqual(self.server.app.job['state'],'sent')
        self.assertFalse(self.server.app.job['visual_confirmation'])
        self.assertTrue(self.server.app.job['acknowledged'])
    def test_disconnected_send_and_arbitrary_path_rejected(self):
        _,preview=self.request('/api/preview',{})
        self.server.app.simulation='disconnected'
        self.assertEqual(self.request('/api/send',{'render_id':preview['render_id']})[0],409)
        self.assertEqual(self.request('/api/send',{'render_id':'../../etc/passwd'})[0],400)
    def test_error_never_success(self):
        self.server.app.simulation='error'
        _,preview=self.request('/api/preview',{})
        self.request('/api/send',{'render_id':preview['render_id']})
        deadline=time.monotonic()+5
        while self.server.app.job['state']=='sending' and time.monotonic()<deadline: time.sleep(.05)
        self.assertEqual(self.server.app.job['state'],'error')
        self.assertFalse(self.server.app.job['acknowledged'])

    def wait_job(self):
        deadline=time.monotonic()+5
        while self.server.app.job['state']=='sending' and time.monotonic()<deadline: time.sleep(.05)
        self.assertNotEqual(self.server.app.job['state'],'sending')

    def test_rgb_off_and_on_preserve_only_local_selection(self):
        initial=self.request('/api/state')[1]
        self.assertIsNone(initial['rgb']['last_enabled'])
        self.assertIsNone(initial['rgb']['last_applied'])
        settings={'mode':1,'color':'#123456','brightness':4,'speed':3,'multicolor':False,'direction':0}
        code,job=self.request('/api/rgb/apply',{'settings':settings})
        self.assertEqual(code,202); self.assertEqual(job['kind'],'rgb')
        self.wait_job()
        state=self.request('/api/state')[1]
        self.assertTrue(state['rgb']['last_enabled'])
        self.assertFalse(state['rgb']['last_applied']['visual_confirmation'])
        saved=state['rgb']['last_settings']
        code,job=self.request('/api/rgb/power',{'enabled':False})
        self.assertEqual(code,202);self.assertEqual(job['rgb_settings']['mode'],0)
        self.wait_job()
        state=self.request('/api/state')[1]
        self.assertFalse(state['rgb']['last_enabled'])
        self.assertEqual(state['rgb']['last_settings'],saved)
        code,job=self.request('/api/rgb/power',{'enabled':True})
        self.assertEqual(code,202);self.assertEqual(job['rgb_settings'],saved)
        self.wait_job()
        restarted=App(self.temp.name,'connected')
        self.assertEqual(restarted.rgb['last_settings'],saved)
        self.assertIsNone(restarted.rgb['last_enabled'])
        self.assertTrue(restarted.rgb['last_applied']['acknowledged'])

    def test_image_and_rgb_share_one_job_lock(self):
        _,preview=self.request('/api/preview',{})
        with ThreadPoolExecutor(2) as pool:
            a=pool.submit(self.request,'/api/send',{'render_id':preview['render_id']})
            b=pool.submit(self.request,'/api/rgb/power',{'enabled':False})
            self.assertEqual(sorted([a.result()[0],b.result()[0]]),[202,409])
        self.wait_job()

    def test_rgb_guards_error_and_no_startup_write(self):
        self.assertEqual(list((Path(self.temp.name)/'transfers').iterdir()),[])
        self.assertEqual(self.request('/api/rgb/power',{'enabled':False},{'X-AK820-Token':''})[0],403)
        self.assertEqual(self.request('/api/rgb/power',{'enabled':'off'})[0],400)
        self.assertEqual(self.request('/api/rgb/apply',{'settings':{'mode':255}})[0],400)
        self.server.app.simulation='disconnected'
        self.assertEqual(self.request('/api/rgb/power',{'enabled':False})[0],409)
        self.server.app.simulation='error'
        self.assertEqual(self.request('/api/rgb/power',{'enabled':False})[0],202)
        self.wait_job()
        self.assertEqual(self.server.app.job['state'],'error')
        self.assertIsNone(self.server.app.rgb['last_enabled'])
        self.assertIsNone(self.server.app.rgb['last_applied'])

if __name__=='__main__': unittest.main()


class QmkMediaGateTests(unittest.TestCase):
    def test_unverified_qmk_upload_stays_off(self):
        import ak820.server as server
        self.assertFalse(server.QMK_MEDIA_UPLOAD_ENABLED)
        with tempfile.TemporaryDirectory() as d:
            app=server.App(d)
            app.device=lambda:{'connected':True,'firmware':'qmk'}
            app.live.supports_v2=lambda:True
            state=app.state()
            self.assertFalse(state['capabilities']['screen']['available'])
            self.assertIn('doğrulanmadı',state['capabilities']['screen']['reason'])
            (app.path/'renders'/('a'*24+'.bin')).write_bytes(b'x')
            with self.assertRaises(ConnectionError):app.send({'render_id':'a'*24})
            self.assertEqual(list((app.path/'transfers').iterdir()),[])
