import json
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import unittest

from ak820.ai_sources import AISourceCache, read_codex_limits
from ak820.claude_statusline import sanitized_usage
from ak820.connections import ClaudeStatuslineInstaller, ConnectionsManager

class Cache:
    def __init__(self):self.refreshes=0;self.disconnected=0;self.closed=False
    def get_snapshot(self,enabled=None):
        return {'refreshing':False,'sources':{p:{'status':'not_connected','message':'Waiting',
            'windows':[],'observed_at':None} for p in ('codex','claude_code')}}
    def request_refresh(self):self.refreshes+=1
    def disconnect_codex(self):self.disconnected+=1
    def close(self):self.closed=True

class ConnectionTests(unittest.TestCase):
    def test_disconnect_persists_without_changing_claude_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);settings=root/'settings.json';settings.write_text('{"statusLine":{"type":"command","command":"cat"},"env":{"keep":"private"}}')
            original=settings.read_bytes();cache=Cache()
            manager=ConnectionsManager(root/'state',settings,cache)
            result=manager.action('codex','disconnect')
            self.assertEqual(result['providers']['codex']['state'],'disconnected')
            self.assertEqual(cache.disconnected,1)
            restarted=ConnectionsManager(root/'state',settings,Cache())
            self.assertFalse(restarted.snapshot()['providers']['codex']['enabled'])
            self.assertEqual(settings.read_bytes(),original)
            with self.assertRaises(ValueError):manager.action('codex','refresh')
            manager.close();self.assertTrue(cache.closed)

    def test_atomic_setup_idempotence_preserves_other_settings_and_statusline_options(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);settings=root/'settings.json'
            prior={'statusLine':{'type':'command','command':'cat; exit 7','padding':3},
                   'hooks':{'SessionStart':['existing']},'env':{'keep':'private'}}
            settings.write_text(json.dumps(prior));installer=ClaudeStatuslineInstaller(root/'state',settings)
            self.assertTrue(installer.setup());after=settings.read_bytes()
            self.assertFalse(installer.setup());self.assertEqual(settings.read_bytes(),after)
            changed=json.loads(after)
            self.assertEqual(changed['hooks'],prior['hooks']);self.assertEqual(changed['env'],prior['env'])
            self.assertEqual(changed['statusLine']['padding'],3)
            binding=json.loads(installer.binding_path.read_text())
            self.assertEqual(binding['original_command'],'cat; exit 7')
            backups=list((root/'state').glob('claude-statusline-before-*.json'))
            self.assertEqual(len(backups),1);self.assertNotIn('env',json.loads(backups[0].read_text()))
            installer.setup(refresh=True)
            fresh=json.loads(settings.read_text())
            self.assertNotEqual(fresh['statusLine']['command'],changed['statusLine']['command'])
            self.assertEqual(json.loads(installer.binding_path.read_text())['original_command'],'cat; exit 7')
            self.assertTrue(installer.installed())

    def test_receiver_preserves_stdin_stdout_exit_and_stores_only_quota(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);settings=root/'settings.json'
            settings.write_text(json.dumps({'statusLine':{'type':'command','command':'cat; exit 7'}}))
            installer=ClaudeStatuslineInstaller(root/'state',settings);installer.setup()
            data={'rate_limits':{'five_hour':{'used_percentage':33.5,'resets_at':time.time()+3600}},
                  'transcript_path':'private-path','model':{'id':'not-persisted'},'token':'not-persisted'}
            raw=json.dumps(data).encode()+b'\n'
            result=subprocess.run(json.loads(settings.read_text())['statusLine']['command'],
                shell=True,input=raw,capture_output=True,timeout=3)
            self.assertEqual(result.returncode,7);self.assertEqual(result.stdout,raw)
            saved=json.loads(installer.export_path.read_text())
            self.assertEqual(saved['five_hour']['used_percentage'],33.5)
            self.assertEqual(set(saved),{'updated_at','origin','five_hour'})
            self.assertNotIn('not-persisted',installer.export_path.read_text())
            stamp=saved['updated_at']
            subprocess.run(json.loads(settings.read_text())['statusLine']['command'],
                shell=True,input=b'not json',capture_output=True,timeout=3)
            self.assertEqual(json.loads(installer.export_path.read_text())['updated_at'],stamp)
            self.assertGreater(installer.seen(),0)

    def test_valid_no_quota_payload_clears_old_windows(self):
        self.assertEqual(set(sanitized_usage({'rate_limits':{}},100)),{'updated_at','origin'})
        data={'rate_limits':{'five_hour':{'used_percentage':0,'resets_at':99},
            'seven_day':{'used_percentage':True,'resets_at':200}}}
        self.assertNotIn('five_hour',sanitized_usage(data,100))
        self.assertNotIn('seven_day',sanitized_usage(data,100))

    def test_setup_failure_does_not_report_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);settings=root/'settings.json'
            settings.write_text('{"statusLine":{"type":"unsupported"}}')
            manager=ConnectionsManager(root/'state',settings,Cache())
            result=manager.action('claude_code','setup')['providers']['claude_code']
            self.assertEqual(result['state'],'error');self.assertFalse(result['setup']['installed'])
            self.assertTrue(result['actions']['setup'])
            self.assertEqual(json.loads(settings.read_text())['statusLine']['type'],'unsupported')

    def test_disconnect_cancels_and_discards_late_codex_results(self):
        release=threading.Event();started=threading.Event()
        def reader():started.set();release.wait(2);return {'rateLimits':{'primary':{'usedPercent':4}}}
        with tempfile.TemporaryDirectory() as directory:
            cache=AISourceCache(Path(directory)/'none',reader)
            cache.get_snapshot();self.assertTrue(started.wait(.5))
            cache.disconnect_codex();release.set()
            deadline=time.monotonic()+2
            while cache._busy and time.monotonic()<deadline:time.sleep(.01)
            result=cache.get_snapshot(enabled={'codex':False,'claude_code':False})
            self.assertEqual(result['sources']['codex']['windows'],[])
            cache.close()

    def test_codex_cancel_stops_finite_process(self):
        with tempfile.TemporaryDirectory() as directory:
            fake=Path(directory)/'codex';fake.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n');fake.chmod(0o700)
            cancel=threading.Event();threading.Timer(.05,cancel.set).start()
            started=time.monotonic()
            with self.assertRaises(InterruptedError):read_codex_limits(binary=str(fake),cancel_event=cancel)
            self.assertLess(time.monotonic()-started,2)

if __name__=='__main__':unittest.main()
