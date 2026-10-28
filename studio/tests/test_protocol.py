import hashlib
from pathlib import Path
import unittest

from PIL import Image

from ak820.protocol import build_payload, control_packets, payload_metadata, rgb565, validate_payload


class ProtocolTests(unittest.TestCase):
    def test_exact_verified_physical_transfer_bytes(self):
        fixtures = Path(__file__).parent / "fixtures"
        with Image.open(fixtures / "verified-test.png") as image:
            payload = build_payload([image], [50])
        self.assertEqual(payload, (fixtures / "verified-payload.bin").read_bytes())
        self.assertEqual(hashlib.sha256(payload).hexdigest(), "a08a01dea47b4706705816972484cf5b6d03f85ce878d48c4fa74d47604c8958")
        start, config, finish = control_packets(payload)
        self.assertEqual(start, bytes.fromhex("0418") + bytes(62))
        self.assertEqual(config, bytes.fromhex("04720100000000000900") + bytes(54))
        self.assertEqual(finish, bytes.fromhex("0402") + bytes(62))
        self.assertEqual(payload_metadata(payload)["blocks"], 9)

    def test_rgb565_endianness_and_channel_order(self):
        rgb = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255]) + bytes(128 * 128 * 3 - 12)
        self.assertEqual(rgb565(rgb)[:8], bytes.fromhex("00f8e0071f00ffff"))

    def test_animation_header_count_delay_bounds_and_padding(self):
        frame = bytes(128 * 128 * 3)
        payload = build_payload([frame] * 4, [0, 51, 510, 99999])
        self.assertEqual(payload[:5], bytes([4, 1, 25, 255, 255]))
        self.assertEqual(payload[5:256], b"\xff" * 251)
        self.assertEqual(payload[256:256 + 4 * 32768], bytes(4 * 32768))
        self.assertEqual(payload_metadata(payload)["delays_ms"], [2, 50, 510, 510])
        self.assertEqual(payload_metadata(payload)["blocks"], 33)
        self.assertEqual(payload[256 + 4 * 32768:], b"\xff" * 3840)

    def test_invalid_input_and_malformed_payloads_rejected(self):
        frame = bytes(128 * 128 * 3)
        for frames, delays in [([], []), ([frame] * 141, [50] * 141), ([frame], []), ([frame], [float("nan")]), ([frame], ["50"])]:
            with self.subTest(delays=str(delays)[:20]), self.assertRaises(ValueError):
                build_payload(frames, delays)
        with self.assertRaises(ValueError):
            build_payload([bytes(10)])
        with self.assertRaises(ValueError):
            build_payload([Image.new("RGB", (64, 64))])
        valid = build_payload([frame])
        mutations = [valid[:-1], bytes([0]) + valid[1:], valid[:1] + bytes([0]) + valid[2:], valid[:2] + bytes([0]) + valid[3:], valid[:-1] + bytes([0])]
        for mutation in mutations:
            with self.assertRaises(ValueError):
                validate_payload(mutation)

    def test_official_frame_cap_and_uint16_block_count(self):
        payload = build_payload([bytes(128 * 128 * 3)] * 140)
        self.assertEqual(payload[0], 140)
        self.assertEqual(payload_metadata(payload)["blocks"], 1121)
        self.assertEqual(control_packets(payload)[1][8:10], bytes.fromhex("6104"))


if __name__ == "__main__":
    unittest.main()
