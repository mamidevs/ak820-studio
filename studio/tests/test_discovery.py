from concurrent.futures import ThreadPoolExecutor
import json
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch
from ak820.server import App

class DiscoveryTests(unittest.TestCase):
    def test_http_threads_share_one_isolated_readonly_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            app=App(temp)
            def result(*args,**kwargs):
                self.assertEqual(args[0][-1],'--detect')
                self.assertEqual(kwargs['timeout'],3)
                time.sleep(.03)
                return subprocess.CompletedProcess(args[0],0,json.dumps({'connected':True,'message':'USB'}),'')
            with patch('ak820.server.subprocess.run',side_effect=result) as run:
                with ThreadPoolExecutor(8) as pool: values=list(pool.map(lambda _:app.device(),range(8)))
                self.assertEqual(run.call_count,1)
                self.assertTrue(all(x['connected'] for x in values))
                self.assertEqual(app.job['state'],'idle')
    def test_native_probe_crash_or_timeout_does_not_crash_service(self):
        for failure in (subprocess.CalledProcessError(-5,['probe']),subprocess.TimeoutExpired(['probe'],3)):
            with self.subTest(failure=type(failure).__name__),tempfile.TemporaryDirectory() as temp:
                app=App(temp)
                with patch('ak820.server.subprocess.run',side_effect=failure):
                    state=app.state()
                    self.assertFalse(state['device']['connected'])
                    self.assertEqual(state['job']['state'],'idle')

if __name__=='__main__': unittest.main()
