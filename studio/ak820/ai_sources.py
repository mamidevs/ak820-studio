"""Read-only, bounded local quota adapters; never read credentials or transcripts.

Codex: official app-server account/rateLimits/read and /updated schema.
Claude Code: official statusLine rate_limits, exported by the existing Claude HUD.
get_ai_snapshot() returns immediately and refreshes Codex in one finite worker.
"""
from __future__ import annotations

import copy
import datetime as dt
import json
import math
import os
from pathlib import Path
import selectors
import signal
import shutil
import subprocess
import threading
import time

CODEX_DOC = 'https://learn.chatgpt.com/docs/app-server#6-rate-limits-chatgpt'
CLAUDE_DOC = 'https://code.claude.com/docs/en/statusline#available-data'
APP_ROOT = Path(__file__).resolve().parents[1]
CLAUDE_EXPORT = APP_ROOT / 'work/state/claude-native-usage.json'
REFRESH_SECONDS = 60
STALE_SECONDS = 180
CLAUDE_STALE_SECONDS = 300
MAX_JSON_BYTES = 16384


def _number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def _epoch(value):
    number = _number(value)
    if number is not None:
        return number if number > 0 else None
    if isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                return None
            return parsed.timestamp() if parsed.timestamp() > 0 else None
        except (ValueError, OverflowError):
            pass
    return None


def _source(kind, description, doc, ttl, status='not_connected', message='Veri bekleniyor.'):
    return dict(status=status, message=message, observed_at=None,
                source_age_seconds=None, ttl_seconds=ttl,
                source=dict(kind=kind, description=description, documentation_url=doc),
                windows=[])


def _window(identifier, label, used, reset, duration, limit_id=None):
    used = _number(used)
    reset = _epoch(reset)
    duration = _number(duration)
    if used is None or used < 0:
        return None
    window = dict(id=identifier, label=label, used_percent=used,
                  remaining_percent=max(0.0, min(100.0, 100.0-used)),
                  resets_at=reset, duration_minutes=duration if duration and duration > 0 else None)
    if limit_id is not None:
        window['limit_id'] = limit_id
    return window


def _age(source, now):
    result = copy.deepcopy(source)
    observed = result.get('observed_at')
    if observed is None:
        return result
    age = max(0, now-observed)
    result['source_age_seconds'] = round(age, 1)
    expired = False
    for window in result['windows']:
        window['status'] = 'stale' if window['resets_at'] is not None and now >= window['resets_at'] else 'available'
        expired |= window['status'] == 'stale'
    if result['status'] in ('available', 'stale'):
        if age > result['ttl_seconds'] or observed > now+30 or expired:
            result['status'] = 'stale'
            result['message'] = 'Son ölçüm güncel değil; yeni veri bekleniyor.'
            for window in result['windows']:
                window['status'] = 'stale'
        else:
            result['status'] = 'available'
    return result


def normalize_codex(payload, observed_at=None, now=None):
    now = time.time() if now is None else now
    observed_at = now if observed_at is None else observed_at
    result = _source('codex_app_server', 'Codex · yerel app-server', CODEX_DOC, STALE_SECONDS)
    if not isinstance(payload, dict):
        raise ValueError('Codex response is not an object')
    # /updated notifications use the same rateLimits envelope as /read results.
    if payload.get('method') == 'account/rateLimits/updated':
        payload = payload.get('params', {})
    buckets = payload.get('rateLimitsByLimitId')
    if not isinstance(buckets, dict) or not buckets:
        legacy = payload.get('rateLimits')
        buckets = {legacy.get('limitId') or 'codex': legacy} if isinstance(legacy, dict) else {}
    for limit_id, bucket in buckets.items():
        if not isinstance(limit_id, str) or not isinstance(bucket, dict):
            continue
        for name in ('primary', 'secondary'):
            raw = bucket.get(name)
            if not isinstance(raw, dict):
                continue
            duration = _number(raw.get('windowDurationMins'))
            label = '5 saat' if duration == 300 else '7 gün' if duration == 10080 else name
            item = _window(f'{limit_id}:{name}', label, raw.get('usedPercent'), raw.get('resetsAt'), duration, limit_id)
            if item:
                result['windows'].append(item)
    result['observed_at'] = observed_at
    if result['windows']:
        result.update(status='available', message='Codex hesabından okundu.')
    else:
        result['message'] = 'Codex kullanım penceresi paylaşmadı; eksik değer sıfır değildir.'
    return _age(result, now)


def normalize_claude(payload, now=None):
    now = time.time() if now is None else now
    result = _source('claude_code_statusline', 'Claude Code · durum satırı dışa aktarımı', CLAUDE_DOC, CLAUDE_STALE_SECONDS)
    if not isinstance(payload, dict):
        raise ValueError('Claude usage export is not an object')
    observed_at = _epoch(payload.get('updated_at'))
    if observed_at is None:
        raise ValueError('Claude usage export needs a timestamp')
    raw_windows = payload.get('rate_limits', payload)
    if not isinstance(raw_windows, dict):
        raise ValueError('Claude rate_limits is not an object')
    for name, label, duration in (('five_hour', '5 saat', 300), ('seven_day', '7 gün', 10080)):
        raw = raw_windows.get(name)
        if isinstance(raw, dict):
            item = _window(name, label, raw.get('used_percentage'), raw.get('resets_at'), duration)
            if item:
                result['windows'].append(item)
    result['observed_at'] = observed_at
    if result['windows']:
        result.update(status='available', message='Claude Code durum satırından okundu.')
    else:
        result['message'] = 'Claude Code kullanım penceresi paylaşmadı; bir sonraki yanıt bekleniyor.'
    return _age(result, now)


def read_claude_export(path=CLAUDE_EXPORT, now=None):
    path = Path(path)
    empty = _source('claude_code_statusline', 'Claude Code · durum satırı dışa aktarımı', CLAUDE_DOC, CLAUDE_STALE_SECONDS)
    try:
        with path.open('rb') as handle:
            raw = handle.read(MAX_JSON_BYTES+1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError('Usage export exceeds size bound')
        return normalize_claude(json.loads(raw), now=now)
    except FileNotFoundError:
        empty['message'] = 'Claude Code bekleniyor; açık bir oturumun durum satırı güncellenmeli.'
    except (OSError, ValueError, TypeError, OverflowError):
        empty.update(status='error', message='Claude Code kullanım dışa aktarımı okunamadı.')
    return empty


def _codex_binary():
    # Common installed CLI locations; no credentials/config files are opened here.
    choices = [shutil.which('codex'), str(Path.home()/'.local/bin/codex'),
               '/Applications/Codex.app/Contents/Resources/codex']
    for choice in choices:
        if choice and Path(choice).is_file() and os.access(choice, os.X_OK):
            return choice
    raise FileNotFoundError('Codex CLI unavailable')


def read_codex_limits(timeout=12, binary=None, cancel_event=None):
    """One finite authenticated metadata read; no login, refresh, thread or turn."""
    binary = binary or _codex_binary()
    proc = subprocess.Popen([binary, 'app-server', '--listen', 'stdio://'],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                            stderr=subprocess.DEVNULL, bufsize=0, cwd=APP_ROOT, start_new_session=True)
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    buffer = b''
    update = None
    initialized = False
    def send(message):
        proc.stdin.write((json.dumps(message)+'\n').encode())
        proc.stdin.flush()
    try:
        send({'id': 1, 'method': 'initialize', 'params': {
            'clientInfo': {'name': 'ak820_studio_usage', 'version': '1.0.0'}}})
        deadline = time.monotonic()+timeout
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                raise InterruptedError('Codex read cancelled')
            if not selector.select(min(.25, max(0, deadline-time.monotonic()))):
                if proc.poll() is not None:
                    raise RuntimeError('Codex app-server stopped')
                continue
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError('Codex app-server closed')
            buffer += chunk
            if len(buffer) > 1024*1024:
                raise ValueError('Codex response exceeds bound')
            while b'\n' in buffer:
                line, buffer = buffer.split(b'\n', 1)
                message = json.loads(line)
                if not isinstance(message, dict):
                    continue
                if message.get('method') == 'account/rateLimits/updated':
                    update = message.get('params')
                if message.get('id') == 1:
                    if initialized or 'error' in message:
                        raise RuntimeError('Codex initialization failed')
                    initialized = True
                    send({'method': 'initialized', 'params': {}})
                    send({'id': 2, 'method': 'account/rateLimits/read'})
                elif message.get('id') == 2:
                    if 'error' in message:
                        raise RuntimeError('Codex usage read failed')
                    return message.get('result')
        if isinstance(update, dict):
            return update
        raise TimeoutError('Codex usage read timed out')
    finally:
        selector.close()
        # Include any app-server helpers in cleanup; this process owns the group.
        try: os.killpg(proc.pid, signal.SIGTERM)
        except ProcessLookupError: pass
        try:
            proc.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            proc.wait(timeout=1)
        finally:
            try: os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError: pass
        for stream in (proc.stdin, proc.stdout):
            if stream:
                stream.close()


class AISourceCache:
    """At most one finite refresh worker; UI reads never wait for the CLI."""
    def __init__(self, claude_path=CLAUDE_EXPORT, codex_reader=read_codex_limits, clock=time.time):
        self.claude_path = Path(claude_path)
        self.codex_reader = codex_reader
        self.clock = clock
        self._lock = threading.Lock()
        self._busy = False
        self._closed = False
        self._generation = 0
        self._cancel = threading.Event()
        self._thread = None
        self._next_refresh = 0
        self._codex = _source('codex_app_server', 'Codex · yerel app-server', CODEX_DOC, STALE_SECONDS,
                              message='Codex kullanım verisi okunuyor.')

    def _refresh(self, generation, cancel):
        try:
            raw = self.codex_reader(cancel_event=cancel) if self.codex_reader is read_codex_limits else self.codex_reader()
            normalized = normalize_codex(raw, observed_at=self.clock(), now=self.clock())
        except FileNotFoundError:
            normalized = _source('codex_app_server', 'Codex · yerel app-server', CODEX_DOC, STALE_SECONDS,
                                 message='Codex yerel aracı bulunamadı.')
        except Exception:
            # Never forward raw subprocess/network errors: they can contain identity.
            normalized = _source('codex_app_server', 'Codex · yerel app-server', CODEX_DOC, STALE_SECONDS,
                                 status='error', message='Codex kullanım bilgisi alınamadı; bağlantı veya oturum kontrol edilmeli.')
        with self._lock:
            if generation != self._generation or self._closed:
                self._busy = False
                return
            if normalized['status'] == 'error' and self._codex['windows']:
                previous = copy.deepcopy(self._codex)
                previous.update(status='stale', message='Güncelleme başarısız; son ölçüm gösteriliyor.')
                normalized = previous
            self._codex = normalized
            self._next_refresh = self.clock()+REFRESH_SECONDS
            self._busy = False

    def request_refresh(self):
        with self._lock:
            self._next_refresh = 0

    def disconnect_codex(self):
        with self._lock:
            self._generation += 1
            self._cancel.set()
            self._next_refresh = 0
            self._codex = _source('codex_app_server', 'Codex · yerel app-server', CODEX_DOC, STALE_SECONDS,
                                  message='Studio bağlantısı kapalı.')

    def close(self):
        with self._lock:
            self._closed = True
            self._generation += 1
            self._cancel.set()
            thread = self._thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=3)

    def get_snapshot(self, enabled=None):
        enabled = enabled or {'codex': True, 'claude_code': True}
        now = self.clock()
        with self._lock:
            if enabled.get('codex') and not self._closed and not self._busy and now >= self._next_refresh:
                self._busy = True
                self._cancel = threading.Event()
                self._thread = threading.Thread(target=self._refresh, args=(self._generation,self._cancel), name='ak820-ai-usage', daemon=True)
                self._thread.start()
            codex = _age(self._codex, now)
            # A failed read must remain stale even when the last value is recent.
            if self._codex['status'] == 'stale':
                codex['status'] = 'stale'
                codex['message'] = self._codex['message']
                for window in codex['windows']:
                    window['status'] = 'stale'
            refreshing = self._busy
        claude = read_claude_export(self.claude_path, now) if enabled.get('claude_code') else _source(
            'claude_code_statusline', 'Claude Code · durum satırı dışa aktarımı', CLAUDE_DOC, CLAUDE_STALE_SECONDS,
            message='Studio bağlantısı kapalı.')
        if not enabled.get('codex'):
            codex = _source('codex_app_server', 'Codex · yerel app-server', CODEX_DOC, STALE_SECONDS,
                            message='Studio bağlantısı kapalı.')
        return dict(schema_version=1, updated_at=now, refresh_interval_seconds=REFRESH_SECONDS,
                    refreshing=refreshing, sources=dict(codex=codex, claude_code=claude))



def get_ai_snapshot():
    """Immediate view respecting persistent per-provider forwarding preferences."""
    from .connections import get_manager
    return get_manager().ai_snapshot()


def get_connections_snapshot():
    from .connections import get_manager
    return get_manager().snapshot()


def connection_action(provider, action):
    from .connections import get_manager
    return get_manager().action(provider, action)


def shutdown_ai_sources():
    from .connections import shutdown_manager
    shutdown_manager()
