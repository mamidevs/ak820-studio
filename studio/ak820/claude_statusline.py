#!/usr/bin/env python3
"""Capture quota fields, then exec the unchanged original Claude status line.

No HTTP, credential, transcript or model access. Original stdin/stdout/exit status
are preserved; exec replaces this process so cancellation cannot orphan a child.
"""
import argparse
import datetime
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import time

MAX_CAPTURE = 1024 * 1024


def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def sanitized_usage(payload, now):
    if not isinstance(payload, dict):
        raise ValueError('Invalid status-line payload')
    limits = payload.get('rate_limits')
    if limits is not None and not isinstance(limits, dict):
        raise ValueError('Invalid quota envelope')
    result = {'updated_at': now, 'origin': 'claude_code_statusline'}
    for key in ('five_hour', 'seven_day'):
        window = (limits or {}).get(key)
        if not isinstance(window, dict):
            continue
        used = _number(window.get('used_percentage'))
        reset = _number(window.get('resets_at'))
        if used is None or not 0 <= used <= 100:
            continue
        # Native documented schema is Unix seconds. Never import a stale HUD file.
        if reset is not None and reset <= now:
            continue
        result[key] = {'used_percentage': used, 'resets_at': reset if reset and reset > 0 else None}
    return result


def atomic_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'.', dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(value, stream, allow_nan=False)
            stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--binding', required=True)
    parser.add_argument('--refresh', default='0')
    args = parser.parse_args()
    binding = json.loads(Path(args.binding).read_text())
    original = binding.get('original_command')
    # Spool exactly once; the prior command receives every original byte.
    with tempfile.TemporaryFile() as incoming:
        captured = bytearray()
        while True:
            chunk = sys.stdin.buffer.read(65536)
            if not chunk:
                break
            incoming.write(chunk)
            if len(captured) <= MAX_CAPTURE:
                captured.extend(chunk)
        now = time.time()
        try:
            if len(captured) > MAX_CAPTURE:
                raise ValueError('Payload exceeds capture limit')
            usage = sanitized_usage(json.loads(captured), now)
            atomic_json(binding['export_path'], usage)
            atomic_json(binding['health_path'], {'received_at': now, 'valid_payload': True,
                'quota_windows': sum(key in usage for key in ('five_hour', 'seven_day'))})
        except (OSError, ValueError, TypeError):
            # Never turn invalid input into a fresh quota, or change terminal output.
            pass
        if not original:
            return 0
        incoming.seek(0)
        os.dup2(incoming.fileno(), 0)
        os.set_inheritable(0, True)
        os.execv('/bin/sh', ['/bin/sh', '-c', original])
    return 0


if __name__ == '__main__':
    sys.exit(main())
