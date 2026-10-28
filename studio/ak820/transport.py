"""Strict, one-attempt HID transfer for the physically verified AK820 Pro.

Run sends in a separate process with a hard watchdog: some platform HID
feature calls have no cancellable timeout. The application's worker provides
that bound. This module also enforces an elapsed deadline and 300 ms data ACKs.
"""
from __future__ import annotations

import fcntl
import importlib
import os
from pathlib import Path
import tempfile
import threading
import time

from .protocol import BLOCK_BYTES, control_packets, payload_metadata
from .rgb import normalize_rgb, rgb_packets, RGB_ACKS, RGB_STAGES, RGB_DELAY_SECONDS

VID, PID = 0x0C45, 0x8009
REVISION = 0x0114  # USB descriptor revision, not a firmware-version assertion.
CONTROL_DESCRIPTOR = bytes.fromhex("0613ff0901a101150026ff007508954009028102090391020a00ffb102c0")
DATA_DESCRIPTOR = bytes.fromhex("0668ff0961a1010962150026ff009540750881020963150026ff0096001075089102c0")
_SEND_LOCK = threading.Lock()


class DeviceError(RuntimeError):
    pass


class BusyError(DeviceError):
    pass


class TransferError(DeviceError):
    pass


def _exact_pair(entries):
    selected = []
    for label, page, usage, interface in (("kontrol", 0xFF13, 1, 3), ("görüntü", 0xFF68, 0x61, 2)):
        matches = [d for d in entries if d.get("usage_page") == page and d.get("usage") == usage]
        if len(matches) != 1:
            raise DeviceError(f"AK820 Pro {label} bağlantısı bulunamadı veya birden fazla aygıt bağlı.")
        item = matches[0]
        expected = {
            "vendor_id": VID, "product_id": PID,
            "manufacturer_string": "SONiX", "product_string": "AK820",
            "interface_number": interface, "release_number": REVISION, "bus_type": 1,
        }
        if any(item.get(key) != value for key, value in expected.items()):
            raise DeviceError("Bağlı aygıt bu sürümde doğrulanan AK820 Pro USB kimliğiyle eşleşmiyor.")
        if not item.get("path"):
            raise DeviceError("Aygıt yolu eksik.")
        selected.append(item)
    control, data = selected
    if control["path"] == data["path"]:
        raise DeviceError("Kontrol ve görüntü bağlantıları ayrı olmalı.")
    if control.get("serial_number") != data.get("serial_number"):
        raise DeviceError("Kontrol ve görüntü aygıt kimlikleri eşleşmiyor.")
    return control, data


class NativeTransport:
    def __init__(self, hid_backend=None, *, timeout_seconds=300, lock_path=None):
        self._backend = hid_backend
        self.timeout_seconds = max(1, min(float(timeout_seconds), 300))
        self.lock_path = Path(lock_path) if lock_path else Path(tempfile.gettempdir()) / f"ak820-0c45-8009-{os.getuid()}.lock"

    def _hid(self):
        return self._backend if self._backend is not None else importlib.import_module("hid")

    def detect(self) -> dict:
        """Read-only enumeration. Does not open a device or send a HID report."""
        try:
            entries = self._hid().enumerate(VID, PID)
            control, _data = _exact_pair(entries)
            return {
                "connected": True, "supported": True,
                "message": "AK820 Pro USB ile bağlı",
                "device": "AJAZZ AK820 Pro", "manufacturer": "SONiX", "product": "AK820",
                "vendor_id": VID, "product_id": PID, "connection": "USB",
                "descriptor_revision": f"0x{control['release_number']:04X}",
                "firmware_version": None, "descriptor_checked_on_send": True,
            }
        except ImportError:
            return {"connected": False, "supported": False, "message": "USB köprüsü yüklenemedi; uygulamayı başlangıç dosyasıyla açın."}
        except Exception as exc:
            return {"connected": False, "supported": False, "message": str(exc)}

    def send(self, payload: bytes, progress=None) -> dict:
        """One serialized transfer. No retries, implicit sends or unknown commands."""
        meta = payload_metadata(payload)
        if not _SEND_LOCK.acquire(blocking=False):
            raise BusyError("Başka bir ekran aktarımı sürüyor.")
        lock_file = None
        handles = []
        started = time.monotonic()
        sent = 0
        def emit(stage, message, percent):
            if progress:
                progress({"stage": stage, "message": message, "progress": percent / 100,
                          "completed_blocks": sent, "total_blocks": meta["blocks"]})
        def deadline():
            if time.monotonic() - started > self.timeout_seconds:
                raise TransferError("Aktarım süresi aşıldı; otomatik tekrar yapılmadı.")
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = os.fdopen(os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a")
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BusyError("Başka bir ekran aktarımı sürüyor.") from exc
            hid = self._hid()
            control_info, data_info = _exact_pair(hid.enumerate(VID, PID))
            emit("opening", "USB bağlantısı doğrulanıyor…", 0)
            for info, expected in ((control_info, CONTROL_DESCRIPTOR), (data_info, DATA_DESCRIPTOR)):
                handle = hid.device()
                handles.append(handle)
                handle.open_path(info["path"])
                if bytes(handle.get_report_descriptor()) != expected:
                    raise DeviceError("Aygıt rapor yapısı doğrulanmış sürümle eşleşmiyor; aktarım yapılmadı.")
            control, data = handles
            packets = control_packets(payload)
            def send_control(stage, packet, percent):
                deadline()
                time.sleep(.010)
                count = control.send_feature_report(bytes([0]) + packet)
                if count not in (64, 65):
                    raise TransferError(f"Kontrol verisi eksik yazıldı ({stage}).")
                time.sleep(.010)
                response = bytes(control.get_feature_report(0, 65))
                raw = response[1:] if len(response) == 65 and response[0] == 0 else response
                if len(raw) != 64 or raw[:2] != packet[:2] or raw[3] != 1:
                    raise TransferError(f"Aygıt kontrol onayı alınamadı ({stage}).")
                emit(stage, "Aktarım hazırlanıyor…" if stage != "finish" else "Son aygıt onayı alındı.", percent)
            send_control("start", packets[0], 1)
            send_control("image_config", packets[1], 2)
            for index in range(meta["blocks"]):
                deadline()
                block = payload[index * BLOCK_BYTES:(index + 1) * BLOCK_BYTES]
                count = data.write(bytes([0]) + block)
                if count not in (BLOCK_BYTES, BLOCK_BYTES + 1):
                    raise TransferError(f"Görüntü verisi eksik yazıldı ({index + 1}/{meta['blocks']}).")
                response = bytes(data.read(64, 300))
                if len(response) != 64:
                    raise TransferError(f"Görüntü bloğu onayı alınamadı ({index + 1}/{meta['blocks']}); tekrar yapılmadı.")
                # No speculative interpretation of the data-reply bytes: the
                # proven sender checked receipt, while control ACK status=1.
                sent = index + 1
                emit("data", f"Görüntü aktarılıyor · {sent}/{meta['blocks']}", round(2 + sent / meta["blocks"] * 95))
            send_control("finish", packets[2], 99)
            deadline()
            result = {
                "status": "transfer_acknowledged", "acknowledged": True,
                "visual_confirmation": False, "bytes": meta["bytes"],
                "blocks": meta["blocks"], "frame_count": meta["frame_count"],
                "sha256": meta["sha256"], "elapsed_seconds": round(time.monotonic() - started, 3),
            }
            emit("complete", "Aygıt aktarımı onayladı. Görüntüyü klavye ekranından kontrol edin.", 100)
            return result
        except (DeviceError, ValueError):
            raise
        except Exception as exc:
            raise TransferError(f"USB aktarımı durdu: {exc}. Otomatik tekrar yapılmadı.") from exc
        finally:
            for handle in reversed(handles):
                try:
                    handle.close()
                except Exception:
                    pass
            if lock_file is not None:
                lock_file.close()
            _SEND_LOCK.release()

    def send_rgb(self, settings: dict, progress=None) -> dict:
        """One explicit stock RGB transfer; shares the image transfer locks.

        A supervising subprocess must enforce the hard 15-second timeout.
        No feature read is attempted for the two source-marked no-ACK writes.
        """
        settings = normalize_rgb(settings)
        packets = rgb_packets(settings)
        if not _SEND_LOCK.acquire(blocking=False):
            raise BusyError("Başka bir klavye aktarımı sürüyor.")
        lock_file = None
        handles = []
        started = time.monotonic()
        completed = 0
        def deadline():
            if time.monotonic() - started > min(self.timeout_seconds, 15):
                raise TransferError("RGB aktarım süresi aşıldı; otomatik tekrar yapılmadı.")
        try:
            self.lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_file = os.fdopen(os.open(self.lock_path, os.O_WRONLY | os.O_CREAT | os.O_NOFOLLOW, 0o600), "a")
            try:
                fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise BusyError("Başka bir klavye aktarımı sürüyor.") from exc
            hid = self._hid()
            control_info, data_info = _exact_pair(hid.enumerate(VID, PID))
            for info, expected in ((control_info, CONTROL_DESCRIPTOR), (data_info, DATA_DESCRIPTOR)):
                handle = hid.device()
                handles.append(handle)
                handle.open_path(info['path'])
                if bytes(handle.get_report_descriptor()) != expected:
                    raise DeviceError("Aygıt rapor yapısı doğrulanmış sürümle eşleşmiyor; RGB aktarımı yapılmadı.")
            control = handles[0]
            for packet, requires_ack, stage in zip(packets, RGB_ACKS, RGB_STAGES):
                deadline()
                time.sleep(RGB_DELAY_SECONDS)
                count = control.send_feature_report(bytes([0]) + packet)
                if count not in (64, 65):
                    raise TransferError(f"RGB kontrol verisi eksik yazıldı ({stage}).")
                if requires_ack:
                    time.sleep(RGB_DELAY_SECONDS)
                    response = bytes(control.get_feature_report(0, 65))
                    raw = response[1:] if len(response) == 65 and response[0] == 0 else response
                    if len(raw) != 64 or raw[:2] != packet[:2] or raw[3] != 1:
                        raise TransferError(f"RGB aygıt onayı alınamadı ({stage}); tekrar yapılmadı.")
                completed += 1
                if progress:
                    progress({'stage': stage, 'progress': completed / len(packets),
                              'completed_commands': completed, 'total_commands': len(packets),
                              'message': f"Aydınlatma uygulanıyor · {completed}/{len(packets)}"})
            deadline()
            return {'status': 'transfer_acknowledged', 'kind': 'rgb', 'acknowledged': True,
                    'visual_confirmation': False, 'settings': settings,
                    'commands': completed, 'acknowledged_commands': 3,
                    'elapsed_seconds': round(time.monotonic() - started, 3)}
        except (DeviceError, ValueError):
            raise
        except Exception as exc:
            raise TransferError(f"RGB aktarımı durdu: {exc}. Otomatik tekrar yapılmadı.") from exc
        finally:
            for handle in reversed(handles):
                try:
                    handle.close()
                except Exception:
                    pass
            if lock_file is not None:
                lock_file.close()
            _SEND_LOCK.release()
