import fcntl
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from ak820.protocol import build_payload
from ak820.rgb import DEFAULT_RGB_SETTINGS, MODE_MASKS, RGB_ACKS, normalize_rgb, rgb_packets
from ak820.transport import BusyError, DeviceError, NativeTransport, TransferError
from test_transport import FakeHID, FakeHandle


class RGBProtocolTests(unittest.TestCase):
    def test_off_packet_exact_source_sequence(self):
        packets = rgb_packets({'mode': 0})
        self.assertEqual(len(packets), 5)
        self.assertEqual(packets[0], bytes.fromhex('0418') + bytes(62))
        self.assertEqual(packets[1], bytes.fromhex('041300000000000001') + bytes(55))
        self.assertEqual(packets[2], bytes(14) + bytes.fromhex('aa55') + bytes(48))
        self.assertEqual(packets[3], bytes.fromhex('0402') + bytes(62))
        self.assertEqual(packets[4], bytes.fromhex('04f0') + bytes(62))
        self.assertEqual(RGB_ACKS, (True, True, False, True, False))

    def test_custom_color_order_and_no_opcode_prefix(self):
        settings = {'mode': 11, 'color': '#123456', 'brightness': 2, 'speed': 4,
                    'multicolor': False, 'direction': 1}
        expected = bytearray(64)
        expected[:4] = bytes.fromhex('0b123456')
        expected[8:12] = bytes([0, 2, 4, 1])
        expected[14:16] = bytes.fromhex('aa55')
        self.assertEqual(rgb_packets(settings)[2], bytes(expected))

    def test_verified_boundaries_and_direction_groups(self):
        for level in (1, 5):
            self.assertEqual(normalize_rgb({'mode': 11, 'brightness': level, 'speed': level})['speed'], level)
        for value in (0, 6, -1, 1.5, True, '3'):
            for field in ('brightness', 'speed'):
                with self.subTest(field=field,value=value), self.assertRaises(ValueError):
                    normalize_rgb({'mode': 11, field: value})
        for mode in (11, 12, 16, 18):
            for direction in (0, 1):
                self.assertEqual(normalize_rgb({'mode': mode, 'direction': direction})['direction'], direction)
            for invalid in (2, 3, True):
                with self.assertRaises(ValueError):
                    normalize_rgb({'mode': mode, 'direction': invalid})
        for direction in (2, 3):
            self.assertEqual(normalize_rgb({'mode': 10, 'direction': direction})['direction'], direction)
        with self.assertRaises(ValueError):
            normalize_rgb({'mode': 10, 'direction': 0})
        self.assertEqual(normalize_rgb({'mode': 10})['direction'], 2)

    def test_mode_mask_canonicalizes_disabled_fields(self):
        static = normalize_rgb({'mode': 1, 'speed': 255, 'direction': 255})
        self.assertEqual((static['speed'], static['direction']), (3, 0))
        for mode in (6, 8):
            result = normalize_rgb({'mode': mode, 'color': '#00ffff', 'multicolor': False, 'direction': 255})
            self.assertEqual((result['color'], result['multicolor'], result['direction']), ('#ff0000', True, 0))
        for mode,mask in enumerate(MODE_MASKS):
            result = normalize_rgb({'mode': mode})
            self.assertEqual(result, normalize_rgb(result))
            self.assertTrue(all(len(p) == 64 for p in rgb_packets(result)))
        self.assertEqual(normalize_rgb({}), DEFAULT_RGB_SETTINGS)

    def test_invalid_settings_rejected(self):
        for raw in ([], None, {'mode':20}, {'mode':-1}, {'mode':True}, {'opcode':0xF0},
                    {'mode':1,'color':'red'}, {'mode':1,'color':'#12345g'},
                    {'mode':1,'multicolor':1}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                normalize_rgb(raw)


class RGBFakeHandle(FakeHandle):
    def send_feature_report(self, packet):
        value = super().send_feature_report(packet)
        count = len(self.backend.features)
        if self.backend.block_feature and count == 1:
            self.backend.feature_entered.set()
            if not self.backend.feature_release.wait(3):
                raise RuntimeError('Fake RGB transport was not released')
        if self.backend.fail_write == count:
            return 4
        return value

    def get_feature_report(self, report_id, length):
        self.backend.ack_reads += 1
        if self.backend.fail_ack == self.backend.ack_reads:
            return bytes(65)
        return super().get_feature_report(report_id, length)


class RGBFakeHID(FakeHID):
    def __init__(self):
        super().__init__()
        self.ack_reads = 0
        self.fail_write = self.fail_ack = None
        self.block_feature = False
        self.feature_entered, self.feature_release = threading.Event(), threading.Event()

    def device(self):
        handle = RGBFakeHandle(self)
        self.handles.append(handle)
        return handle


class RGBTransportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.lock_path = Path(self.temp.name) / 'shared.lock'
        self.hid = RGBFakeHID()
        self.transport = NativeTransport(self.hid, lock_path=self.lock_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_exact_five_writes_three_reads_and_35ms_pacing(self):
        progress = []
        with patch('ak820.transport.time.sleep') as sleep:
            result = self.transport.send_rgb({'mode': 1, 'color': '#00ff00'}, progress.append)
        self.assertEqual(self.hid.features, [b'\0' + p for p in rgb_packets({'mode': 1, 'color': '#00ff00'})])
        self.assertEqual(self.hid.ack_reads, 3)
        self.assertEqual(self.hid.writes, [])
        self.assertEqual([call.args[0] for call in sleep.call_args_list], [.035] * 8)
        self.assertEqual(progress[-1]['progress'], 1)
        self.assertTrue(result['acknowledged'])
        self.assertFalse(result['visual_confirmation'])
        self.assertTrue(all(h.closed for h in self.hid.handles))

    def test_wrong_identity_or_descriptor_refused_before_write(self):
        self.hid.entries[0]['product_string'] = 'Other'
        with self.assertRaises(DeviceError):
            self.transport.send_rgb({'mode': 0})
        self.assertEqual(self.hid.features, [])
        self.hid.entries[0]['product_string'] = 'AK820'
        self.hid.wrong_descriptor = True
        with self.assertRaises(DeviceError):
            self.transport.send_rgb({'mode': 0})
        self.assertEqual(self.hid.features, [])
        self.assertTrue(all(h.closed for h in self.hid.handles))

    def test_any_write_or_ack_failure_stops_without_retry(self):
        for field,values in [('fail_write', range(1, 6)), ('fail_ack', range(1, 4))]:
            for failure in values:
                with self.subTest(field=field,failure=failure):
                    hid = RGBFakeHID()
                    setattr(hid, field, failure)
                    with patch('ak820.transport.time.sleep'), self.assertRaises(TransferError):
                        NativeTransport(hid, lock_path=self.lock_path).send_rgb({'mode': 0})
                    expected_writes = failure if field == 'fail_write' else (1, 2, 4)[failure - 1]
                    self.assertEqual(len(hid.features), expected_writes)
                    self.assertTrue(all(h.closed for h in hid.handles))

    def test_image_and_rgb_share_same_concurrency_lock_both_directions(self):
        payload = build_payload([bytes(128 * 128 * 3)])
        for first in ('rgb', 'image'):
            with self.subTest(first=first):
                hid = RGBFakeHID()
                transport = NativeTransport(hid, lock_path=self.lock_path)
                hid.block_feature = True
                errors = []
                def send_first():
                    try:
                        if first == 'rgb': transport.send_rgb({'mode': 1})
                        else: transport.send(payload)
                    except Exception as exc: errors.append(exc)
                thread = threading.Thread(target=send_first)
                thread.start()
                try:
                    self.assertTrue(hid.feature_entered.wait(2))
                    with self.assertRaises(BusyError):
                        if first == 'rgb': transport.send(payload)
                        else: transport.send_rgb({'mode': 0})
                    self.assertEqual(len(hid.handles), 2)
                finally:
                    hid.feature_release.set()
                    thread.join(3)
                self.assertFalse(thread.is_alive())
                self.assertEqual(errors, [])

    def test_same_os_lock_and_invalid_settings_open_no_devices(self):
        with self.lock_path.open('w') as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BusyError):
                self.transport.send_rgb({'mode': 0})
        with self.assertRaises(ValueError):
            self.transport.send_rgb({'mode': 1, 'brightness': 0})
        self.assertEqual(self.hid.handles, [])


if __name__ == '__main__':
    unittest.main()
