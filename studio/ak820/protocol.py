"""Stock AK820 Pro LCD image format; no device I/O.

Derived from the locally verified official-driver sender. See
provenance/protocol-provenance.txt in the distributed app for evidence and the byte-equivalence fixture.
"""
from __future__ import annotations

import hashlib
import math
import struct

WIDTH = HEIGHT = 128
MAX_FRAMES = 140
HEADER_BYTES = 256
FRAME_BYTES = WIDTH * HEIGHT * 2
BLOCK_BYTES = 4096


def rgb565(frame) -> bytes:
    """Pack a 128×128 Pillow image or packed RGB bytes as little-endian RGB565."""
    if isinstance(frame, (bytes, bytearray, memoryview)):
        rgb = bytes(frame)
    else:
        if frame.size != (WIDTH, HEIGHT):
            raise ValueError("Her kare tam olarak 128 × 128 piksel olmalı.")
        rgb = frame.convert("RGB").tobytes()
    if len(rgb) != WIDTH * HEIGHT * 3:
        raise ValueError("RGB kare uzunluğu 128 × 128 × 3 bayt olmalı.")
    packed = bytearray(FRAME_BYTES)
    for index in range(WIDTH * HEIGHT):
        r, g, b = rgb[index * 3:index * 3 + 3]
        value = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
        struct.pack_into("<H", packed, index * 2, value)
    return bytes(packed)


def build_payload(frames, delays_ms=None) -> bytes:
    """Build the complete FF-padded payload, accepting 1–140 RGB frames.

    Delay resolution is 2 ms and the on-device header stores one byte per
    frame. Durations are clamped to 2–510 ms instead of reproducing the
    official driver's byte overflow for larger durations. The caller should
    disclose this normalization in its animation summary.
    """
    frames = list(frames)
    if not 1 <= len(frames) <= MAX_FRAMES:
        raise ValueError("Ekran aktarımı 1–140 kare içermeli.")
    delays = [50] * len(frames) if delays_ms is None else list(delays_ms)
    if len(delays) != len(frames):
        raise ValueError("Kare ve süre sayıları aynı olmalı.")
    header = bytearray(b"\xff" * HEADER_BYTES)
    header[0] = len(frames)
    for index, delay in enumerate(delays, 1):
        if isinstance(delay, bool) or not isinstance(delay, (int, float)) or not math.isfinite(delay):
            raise ValueError("Kare süresi sonlu bir sayı olmalı.")
        header[index] = max(1, min(255, int(delay) // 2))
    payload = bytes(header) + b"".join(rgb565(frame) for frame in frames)
    return payload + b"\xff" * (-len(payload) % BLOCK_BYTES)


def validate_payload(payload: bytes) -> None:
    """Reject malformed data before any control command can be emitted."""
    if not isinstance(payload, bytes) or len(payload) < BLOCK_BYTES:
        raise ValueError("Ekran verisi eksik veya geçersiz.")
    count = payload[0]
    if not 1 <= count <= MAX_FRAMES:
        raise ValueError("Geçersiz kare sayısı.")
    unpadded = HEADER_BYTES + count * FRAME_BYTES
    expected = ((unpadded + BLOCK_BYTES - 1) // BLOCK_BYTES) * BLOCK_BYTES
    if len(payload) != expected:
        raise ValueError("Ekran verisi uzunluğu kare sayısıyla eşleşmiyor.")
    if 0 in payload[1:count + 1]:
        raise ValueError("Kare süresi sıfır olamaz.")
    if payload[count + 1:HEADER_BYTES] != b"\xff" * (HEADER_BYTES - count - 1):
        raise ValueError("Ekran başlığı geçersiz.")
    if payload[unpadded:] != b"\xff" * (len(payload) - unpadded):
        raise ValueError("Ekran dolgu verisi geçersiz.")


def payload_metadata(payload: bytes) -> dict:
    validate_payload(payload)
    return {
        "frame_count": payload[0],
        "frames": payload[0],
        "delays_ms": [value * 2 for value in payload[1:payload[0] + 1]],
        "bytes": len(payload),
        "blocks": len(payload) // BLOCK_BYTES,
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def control_packets(payload: bytes) -> tuple[bytes, bytes, bytes]:
    validate_payload(payload)
    start = bytes([4, 0x18]) + bytes(62)
    config = bytearray(64)
    config[:3] = bytes([4, 0x72, 1])  # Official first LCD item: index 0 + 1.
    struct.pack_into("<H", config, 8, len(payload) // BLOCK_BYTES)
    finish = bytes([4, 0x02]) + bytes(62)
    return start, bytes(config), finish
