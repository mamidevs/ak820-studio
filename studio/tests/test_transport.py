import copy
import fcntl
from pathlib import Path
import tempfile
import threading
import unittest

from ak820.protocol import build_payload, control_packets
from ak820.transport import BusyError, CONTROL_DESCRIPTOR, DATA_DESCRIPTOR, DeviceError, NativeTransport, TransferError


def device_entries():
    base = {"vendor_id": 0x0C45, "product_id": 0x8009, "manufacturer_string": "SONiX", "product_string": "AK820", "release_number": 0x0114, "bus_type": 1, "serial_number": ""}
    return [dict(base, path=b"control", usage_page=0xFF13, usage=1, interface_number=3), dict(base, path=b"data", usage_page=0xFF68, usage=0x61, interface_number=2)]


class FakeHandle:
    def __init__(self, backend):
        self.backend = backend
        self.path = None
        self.closed = False
        self.last = None

    def open_path(self, path):
        self.path = path

    def get_report_descriptor(self):
        if self.backend.wrong_descriptor:
            return bytes([0])
        return CONTROL_DESCRIPTOR if self.path == b"control" else DATA_DESCRIPTOR

    def send_feature_report(self, packet):
        self.last = packet
        self.backend.features.append(packet)
        return len(packet)

    def get_feature_report(self, report_id, length):
        packet = bytearray(self.last)
        packet[4] = 0 if self.backend.bad_control_ack else 1
        return packet

    def write(self, packet):
        self.backend.writes.append(packet)
        if self.backend.entered:
            self.backend.entered.set()
            if not self.backend.release.wait(3):
                raise RuntimeError("Test did not release fake transport")
        if self.backend.disconnect:
            raise OSError("device disconnected")
        return 42 if self.backend.short_write else len(packet)

    def read(self, length, timeout):
        self.backend.read_timeouts.append(timeout)
        return [] if self.backend.missing_ack else bytes.fromhex("015a02") + bytes(61)

    def close(self):
        self.closed = True


class FakeHID:
    def __init__(self):
        self.entries = device_entries()
        self.features, self.writes, self.handles, self.read_timeouts = [], [], [], []
        self.wrong_descriptor = self.bad_control_ack = self.missing_ack = self.disconnect = self.short_write = False
        self.entered = self.release = None

    def enumerate(self, vid, pid):
        assert (vid, pid) == (0x0C45, 0x8009)
        return copy.deepcopy(self.entries)

    def device(self):
        handle = FakeHandle(self)
        self.handles.append(handle)
        return handle


class TransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = build_payload([bytes([255, 0, 0]) * 128 * 128])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.hid = FakeHID()
        self.lock_path = Path(self.temp.name) / "transfer.lock"
        self.transport = NativeTransport(self.hid, lock_path=self.lock_path)

    def tearDown(self):
        self.temp.cleanup()

    def test_detection_is_read_only_and_disconnect_is_truthful(self):
        status = self.transport.detect()
        self.assertTrue(status["connected"])
        self.assertEqual(status["descriptor_revision"], "0x0114")
        self.assertIsNone(status["firmware_version"])
        self.assertEqual(self.hid.handles, [])
        self.hid.entries = []
        self.assertFalse(self.transport.detect()["connected"])

    def test_wrong_identity_ambiguous_or_mixed_devices_never_write(self):
        changes = {"vendor_id": 1, "product_id": 1, "manufacturer_string": "Other", "product_string": "Other", "release_number": 0x0107, "bus_type": 2, "interface_number": 0, "usage_page": 1, "usage": 6, "path": b"", "serial_number": "other"}
        for key, value in changes.items():
            with self.subTest(key=key):
                self.hid.entries = device_entries()
                self.hid.entries[0][key] = value
                self.assertFalse(self.transport.detect()["connected"])
                with self.assertRaises(DeviceError):
                    self.transport.send(self.payload)
                self.assertEqual(self.hid.features + self.hid.writes, [])
        self.hid.entries = device_entries() * 2
        with self.assertRaises(DeviceError):
            self.transport.send(self.payload)
        self.hid.entries = device_entries()
        self.hid.entries[1]["path"] = b"control"
        with self.assertRaises(DeviceError):
            self.transport.send(self.payload)

    def test_unrecognized_descriptor_refuses_before_first_write(self):
        self.hid.wrong_descriptor = True
        with self.assertRaises(DeviceError):
            self.transport.send(self.payload)
        self.assertEqual(self.hid.features + self.hid.writes, [])
        self.assertTrue(all(h.closed for h in self.hid.handles))

    def test_packets_match_proven_sender_and_progress_ack_is_not_visual(self):
        progress = []
        result = self.transport.send(self.payload, progress.append)
        self.assertEqual(self.hid.features, [b"\x00" + packet for packet in control_packets(self.payload)])
        self.assertEqual(b"".join(packet[1:] for packet in self.hid.writes), self.payload)
        self.assertEqual(len(self.hid.writes), 9)
        self.assertTrue(all(packet[0] == 0 and len(packet) == 4097 for packet in self.hid.writes))
        self.assertEqual(self.hid.read_timeouts, [300] * 9)
        self.assertTrue(result["acknowledged"])
        self.assertFalse(result["visual_confirmation"])
        self.assertEqual(progress[-1]["progress"], 1)
        self.assertEqual(progress[-1]["completed_blocks"], 9)
        self.assertTrue(all(h.closed for h in self.hid.handles))

    def test_failure_stops_without_retry_or_finish_and_closes_handles(self):
        for failure in ("bad_control_ack", "missing_ack", "disconnect", "short_write"):
            with self.subTest(failure=failure):
                hid = FakeHID()
                setattr(hid, failure, True)
                with self.assertRaises(TransferError):
                    NativeTransport(hid, lock_path=self.lock_path).send(self.payload)
                self.assertLessEqual(len(hid.writes), 1)
                self.assertTrue(all(h.closed for h in hid.handles))
                self.assertFalse(any(packet[1:3] == bytes([4, 2]) for packet in hid.features))

    def test_concurrent_call_rejected_without_new_device_handles(self):
        self.hid.entered, self.hid.release = threading.Event(), threading.Event()
        failures = []
        def send():
            try:
                self.transport.send(self.payload)
            except Exception as exc:
                failures.append(exc)
        thread = threading.Thread(target=send)
        thread.start()
        try:
            self.assertTrue(self.hid.entered.wait(2))
            with self.assertRaises(BusyError):
                NativeTransport(self.hid, lock_path=self.lock_path).send(self.payload)
            self.assertEqual(len(self.hid.handles), 2)
        finally:
            self.hid.release.set()
            thread.join(3)
        self.assertFalse(thread.is_alive())
        self.assertEqual(failures, [])

    def test_existing_os_lock_rejects_new_sender(self):
        with self.lock_path.open("w") as owner:
            fcntl.flock(owner, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BusyError):
                self.transport.send(self.payload)
        self.assertEqual(self.hid.handles, [])

    def test_malformed_payload_never_opens_device(self):
        with self.assertRaises(ValueError):
            self.transport.send(bytes(4096))
        self.assertEqual(self.hid.handles, [])


if __name__ == "__main__":
    unittest.main()
