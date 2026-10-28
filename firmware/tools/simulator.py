#!/usr/bin/env python3
"""Interactive AK820 screen simulator: the firmware's own C core and raster
renderer run on this Mac; the browser only shows the 128x128 RGB565 frames.

    python3 firmware/tools/simulator.py [--port 8770]

No USB, no keyboard access, nothing is flashed. Needs only a C compiler.
"""
import argparse
import ctypes
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import secrets
import subprocess
import sys
import threading

HERE = Path(__file__).resolve().parent
CORE = HERE.parent / 'overlay/keyboards/a_jazz/ak820pro/app_menu'
SOURCES = ['app_menu.c', 'app_raster.c', 'app_font.c', 'app_icons.c']
ACTIONS = ['', 'Ses +', 'Ses −', 'Sessiz', 'Sonraki parça', 'Önceki parça', 'Oynat/duraklat',
           'Parlaklık +', 'Parlaklık −', 'Yakınlaştır', 'Uzaklaştır', 'Zoom sıfırla', 'Işık aç/kapat',
           'Sonraki efekt', 'Önceki efekt', 'Işık +', 'Işık −', 'Renk +', 'Renk −', 'Doygunluk +',
           'Doygunluk −', 'Hız +', 'Hız −', 'Görsel aç/kapat', 'Ekranı kapat', 'USB kabloya geç',
           'Bluetooth yuvasına geç', '2.4 GHz alıcıya geç', 'Bluetooth eşleştirme başlat',
           'macOS düzenine geç', 'Windows düzenine geç']


def build():
    out = HERE / 'build'
    out.mkdir(exist_ok=True)
    lib = out / ('sim.dylib' if sys.platform == 'darwin' else 'sim.so')
    subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-shared', '-fPIC', f'-I{CORE}',
                    str(HERE / 'sim.c'), *[str(CORE / s) for s in SOURCES], '-o', str(lib)], check=True)
    sim = ctypes.CDLL(str(lib))
    sim.sim_state.restype = ctypes.c_char_p
    sim.sim_set.argtypes = [ctypes.c_char_p, ctypes.c_int]
    return sim


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8770)
    args = parser.parse_args()
    sim = build()
    lock = threading.Lock()
    token = secrets.token_urlsafe(18)
    with lock:
        sim.sim_init(1)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, code, body, kind='application/json'):
            if not isinstance(body, bytes):
                body = json.dumps(body).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind)
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def state(self):
            s = json.loads(sim.sim_state())
            s['action_label'] = ACTIONS[s['action']] if 0 <= s['action'] < len(ACTIONS) else ''
            return s

        def do_GET(self):
            if self.path in ('/', '/index.html'):
                html = (HERE / 'simulator.html').read_text().replace('__TOKEN__', token)
                return self.reply(200, html.encode(), 'text/html; charset=utf-8')
            if self.path == '/frame':
                buf = (ctypes.c_uint8 * 32768)()
                with lock:
                    sim.sim_frame(buf)
                return self.reply(200, bytes(buf), 'application/octet-stream')
            self.reply(404, {'error': 'not found'})

        def do_POST(self):
            if self.headers.get('X-Token') != token:
                return self.reply(403, {'error': 'token'})
            try:
                length = int(self.headers.get('Content-Length', '0'))
                if not 0 < length <= 512:
                    raise ValueError('length')
                body = json.loads(self.rfile.read(length))
                with lock:
                    if self.path == '/event':
                        events = body['events']
                        if not 1 <= len(events) <= 4:
                            raise ValueError('events')
                        for kind, value in events:
                            if type(kind) is not int or type(value) is not int or not 0 <= kind <= 4 or not -5000 <= value <= 5000:
                                raise ValueError('event')
                        for kind, value in events:
                            sim.sim_event(kind, value)
                    elif self.path == '/reset':
                        preset = body['preset']
                        if preset not in (0, 1, 2, 3, 4, 5):
                            raise ValueError('preset')
                        sim.sim_init(preset)
                    else:
                        return self.reply(404, {'error': 'not found'})
                    return self.reply(200, self.state())
            except (ValueError, KeyError, TypeError) as error:
                self.reply(400, {'error': str(error)})

    url = f'http://127.0.0.1:{args.port}'
    print(f'AK820 ekran simülatörü: {url}  (klavyeye dokunmaz)', flush=True)
    ThreadingHTTPServer(('127.0.0.1', args.port), Handler).serve_forever()


if __name__ == '__main__':
    main()
