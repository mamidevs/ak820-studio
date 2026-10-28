import json
from pathlib import Path
import tempfile
import threading
import time
import unittest

from ak820.ai_sources import (AISourceCache, normalize_codex, normalize_claude,
                              read_claude_export, read_codex_limits)

NOW = 1800000000


def codex(used=24):
    return {'rateLimitsByLimitId': {'codex': {'primary': {
        'usedPercent': used, 'windowDurationMins': 10080, 'resetsAt': NOW+2000}, 'secondary': None}}}


class NormalizeTests(unittest.TestCase):
    def test_multibucket_preferred_and_missing_is_not_zero(self):
        raw = codex()
        raw['rateLimits'] = {'primary': {'usedPercent': 99}}
        raw['rateLimitsByLimitId']['another'] = {'secondary': {
            'usedPercent': 0, 'windowDurationMins': 300, 'resetsAt': NOW+100}}
        source = normalize_codex(raw, NOW, NOW)
        self.assertEqual(source['status'], 'available')
        self.assertEqual(len(source['windows']), 2)
        self.assertEqual(source['windows'][0]['remaining_percent'], 76)
        self.assertEqual(source['windows'][1]['remaining_percent'], 100)
        self.assertEqual(source['windows'][1]['limit_id'], 'another')

    def test_notification_and_legacy(self):
        source = normalize_codex({'method': 'account/rateLimits/updated', 'params': {
            'rateLimits': {'limitId': 'codex', 'primary': {'usedPercent': 32,
             'windowDurationMins': 300, 'resetsAt': NOW+100}}}}, NOW, NOW)
        self.assertEqual(source['windows'][0]['remaining_percent'], 68)
        self.assertEqual(source['windows'][0]['label'], '5 saat')

    def test_malformed_percent_is_never_fabricated(self):
        for invalid in (None, True, '24', float('nan'), float('inf'), -1):
            with self.subTest(invalid=invalid):
                source = normalize_codex(codex(invalid), NOW, NOW)
                self.assertEqual(source['windows'], [])
                self.assertEqual(source['status'], 'not_connected')
        with self.assertRaises(ValueError):
            normalize_codex([], NOW, NOW)

    def test_stale_by_age_reset_or_future_timestamp(self):
        self.assertEqual(normalize_codex(codex(), NOW-181, NOW)['status'], 'stale')
        raw = codex();raw['rateLimitsByLimitId']['codex']['primary']['resetsAt'] = NOW-1
        source = normalize_codex(raw, NOW, NOW)
        self.assertEqual(source['status'], 'stale')
        self.assertEqual(source['windows'][0]['status'], 'stale')
        self.assertEqual(normalize_codex(codex(), NOW+31, NOW)['status'], 'stale')

    def test_unknown_reset_and_duration_stay_null(self):
        raw={'rateLimits': {'primary': {'usedPercent': 100}}}
        window=normalize_codex(raw, NOW, NOW)['windows'][0]
        self.assertIsNone(window['resets_at'])
        self.assertIsNone(window['duration_minutes'])
        self.assertEqual(window['remaining_percent'], 0)

    def test_claude_export_optional_windows_and_iso_time(self):
        data={'updated_at': '2027-01-15T08:00:00Z', 'five_hour': {
            'used_percentage': 12.5, 'resets_at': NOW+100}, 'seven_day': {'used_percentage': None},
            'email': 'not-copied', 'token': 'not-copied', 'context_window': {'used_percentage': 88}}
        source=normalize_claude(data, NOW)
        self.assertEqual(len(source['windows']), 1)
        self.assertEqual(source['windows'][0]['remaining_percent'], 87.5)
        self.assertEqual(source['windows'][0]['duration_minutes'], 300)
        self.assertNotIn('not-copied', json.dumps(source))
        self.assertNotIn('context_window', source)

    def test_claude_missing_bad_and_stale_file(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'usage.json'
            self.assertEqual(read_claude_export(path, NOW)['status'], 'not_connected')
            path.write_text('{')
            self.assertEqual(read_claude_export(path, NOW)['status'], 'error')
            path.write_text(json.dumps({'updated_at': NOW-301, 'seven_day': {
                'used_percentage': 80, 'resets_at': NOW+100}}))
            self.assertEqual(read_claude_export(path, NOW)['status'], 'stale')
            path.write_text(' ' * 16385)
            self.assertEqual(read_claude_export(path, NOW)['status'], 'error')
        with self.assertRaises(ValueError):
            normalize_claude({'five_hour': {'used_percentage': 50}}, NOW)


class AdapterTests(unittest.TestCase):
    def test_single_nonblocking_worker_and_failure_keeps_stale(self):
        calls=[];started=threading.Event();release=threading.Event();clock=[NOW]
        def reader():
            calls.append(True);started.set();release.wait(2)
            if len(calls)>1:raise RuntimeError('sensitive raw error must not escape')
            return codex()
        with tempfile.TemporaryDirectory() as folder:
            cache=AISourceCache(Path(folder)/'none',reader,lambda:clock[0])
            first=cache.get_snapshot()
            self.assertTrue(first['refreshing']);self.assertTrue(started.wait(.5))
            for _ in range(10):cache.get_snapshot()
            self.assertEqual(len(calls),1)
            release.set()
            deadline=time.monotonic()+2
            while cache._busy and time.monotonic()<deadline:time.sleep(.01)
            self.assertEqual(cache.get_snapshot()['sources']['codex']['status'],'available')
            clock[0]+=61
            cache.get_snapshot()
            deadline=time.monotonic()+2
            while cache._busy and time.monotonic()<deadline:time.sleep(.01)
            result=cache.get_snapshot()
            self.assertEqual(result['sources']['codex']['status'],'stale')
            self.assertEqual(result['sources']['codex']['windows'][0]['status'],'stale')
            self.assertNotIn('sensitive',json.dumps(result))
            self.assertEqual(result['sources']['codex']['windows'][0]['remaining_percent'],76)

    def test_stdio_protocol_only_reads_metadata_and_cleans_up(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=Path(folder)/'codex'
            fake.write_text('''#!/usr/bin/env python3
import json,sys
first=json.loads(sys.stdin.readline())
assert first['method']=='initialize'
print(json.dumps({'id':1,'result':{}}),flush=True)
assert json.loads(sys.stdin.readline())['method']=='initialized'
assert json.loads(sys.stdin.readline())['method']=='account/rateLimits/read'
print(json.dumps({'id':2,'result':{'rateLimits':{'primary':{'usedPercent':8}}}}),flush=True)
import time;time.sleep(30)
''')
            fake.chmod(0o700)
            result=read_codex_limits(timeout=1,binary=str(fake))
            self.assertEqual(result['rateLimits']['primary']['usedPercent'],8)

    def test_stdio_timeout_is_bounded(self):
        with tempfile.TemporaryDirectory() as folder:
            fake=Path(folder)/'codex'
            fake.write_text('#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n')
            fake.chmod(0o700)
            started=time.monotonic()
            with self.assertRaises(TimeoutError):read_codex_limits(timeout=.05,binary=str(fake))
            self.assertLess(time.monotonic()-started,2)


if __name__=='__main__':unittest.main()
