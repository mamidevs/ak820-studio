#!/usr/bin/env python3
"""Render every screen through the real firmware C core + raster renderer.

    python3 firmware/tools/make_previews.py [output-dir]

Builds firmware/tools/build/sim.dylib, drives scenes via ctypes and writes
<name>.png (128x128), <name>@4x.png and overview.png. The fixture data is
illustrative and only exists in sim.c; firmware starts with nothing known.
"""
from pathlib import Path
import ctypes
import json
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
CORE = ROOT / 'overlay/keyboards/a_jazz/ak820pro/app_menu'
BUILD = HERE / 'build'
SOURCES = ['app_menu.c', 'app_raster.c', 'app_font.c', 'app_icons.c']

TICK, FN, PRESS, ROTATE, BACK = range(5)
PAGES = {'boot': 0, 'home': 1, 'menu': 2, 'codex': 3, 'claude': 4, 'light': 5,
         'knob': 6, 'display': 7, 'device': 8, 'shortcuts': 9, 'link': 10}


def build():
    BUILD.mkdir(exist_ok=True)
    lib = BUILD / ('sim.dylib' if sys.platform == 'darwin' else 'sim.so')
    subprocess.run(['cc', '-std=c99', '-O2', '-Wall', '-Wextra', '-Werror', '-pedantic', '-shared', '-fPIC',
                    f'-I{CORE}', str(HERE / 'sim.c'), *[str(CORE / s) for s in SOURCES], '-o', str(lib)], check=True)
    sim = ctypes.CDLL(str(lib))
    sim.sim_state.restype = ctypes.c_char_p
    sim.sim_set.argtypes = [ctypes.c_char_p, ctypes.c_int]
    return sim


def frame(sim):
    buf = (ctypes.c_uint8 * 32768)()
    sim.sim_frame(buf)
    raw = bytes(buf)
    pixels = []
    for i in range(0, len(raw), 2):
        v = (raw[i] << 8) | raw[i + 1]
        pixels.append((((v >> 11) & 31) * 255 // 31, ((v >> 5) & 63) * 255 // 63, (v & 31) * 255 // 31))
    im = Image.new('RGB', (128, 128))
    im.putdata(pixels)
    return im


# name, preset, pokes (key, value) applied after boot
SCENES = [
    ('home', 1, []),
    ('home-single-window', 4, []),
    ('home-bt-unplugged', 5, []),
    ('home-clock', 1, [('face', 1)]),
    ('home-clock-single-window', 4, [('face', 1)]),
    ('home-toast', 3, [('toast', 9)]),
    ('home-stale', 2, []),
    ('home-empty', 0, []),
    ('menu', 1, [('menu', 1), ('page', PAGES['menu']), ('selected', 3)]),
    ('menu-codex', 1, [('menu', 1), ('page', PAGES['menu']), ('selected', 1)]),
    ('codex', 1, [('menu', 1), ('page', PAGES['codex'])]),
    ('claude-stale', 2, [('menu', 1), ('page', PAGES['claude'])]),
    ('light', 1, [('menu', 1), ('page', PAGES['light']), ('focus', 4)]),
    ('light-edit', 1, [('menu', 1), ('page', PAGES['light']), ('focus', 3), ('editing', 1)]),
    ('knob', 1, [('menu', 1), ('page', PAGES['knob']), ('focus', 2)]),
    ('display', 1, [('menu', 1), ('page', PAGES['display']), ('focus', 1), ('editing', 1)]),
    ('link', 5, [('menu', 1), ('page', PAGES['link']), ('focus', 3)]),
    ('link-system', 5, [('menu', 1), ('page', PAGES['link']), ('focus', 7)]),
    ('device', 1, [('menu', 1), ('page', PAGES['device']), ('uptime', 8040000)]),
    ('device-bt', 5, [('menu', 1), ('page', PAGES['device']), ('uptime', 8040000)]),
    ('shortcuts', 1, [('menu', 1), ('page', PAGES['shortcuts'])]),
    ('boot', 0, [('page', 0), ('boot', 600)]),
]


def main():
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'previews'
    out.mkdir(parents=True, exist_ok=True)
    sim = build()
    images = []
    for name, preset, pokes in SCENES:
        sim.sim_init(preset)
        sim.sim_event(TICK, 900)
        for key, value in pokes:
            sim.sim_set(key.encode(), value)
        im = frame(sim)
        im.save(out / f'{name}.png')
        im.resize((512, 512), Image.Resampling.NEAREST).save(out / f'{name}@4x.png')
        images.append((name, im))
    cols, scale, pad, label = 4, 3, 18, 22
    cell = 128 * scale
    rows = (len(images) + cols - 1) // cols
    sheet = Image.new('RGB', (pad + cols * (cell + pad), pad + rows * (cell + pad + label)), '#e5e7eb')
    draw = ImageDraw.Draw(sheet)
    try:
        font = ImageFont.truetype(str(HERE / 'fonts/OpenSans-Semibold.ttf'), 15)
    except OSError:
        font = None
    for i, (name, im) in enumerate(images):
        x = pad + (i % cols) * (cell + pad)
        y = pad + (i // cols) * (cell + pad + label)
        sheet.paste(im.resize((cell, cell), Image.Resampling.NEAREST), (x, y))
        draw.text((x, y + cell + 3), name, fill='#111827', font=font)
    sheet.save(out / 'overview.png')
    (out / 'preview-data.json').write_text(json.dumps({
        'renderer': 'Firmware C app_menu + app_raster + app_font + app_icons, 16 bands of 128x8',
        'data': 'Illustrative host fixtures from firmware/tools/sim.c; never compiled into firmware.',
        'scenes': [s[0] for s in SCENES]}, indent=2) + '\n')
    print('wrote', len(images), 'scenes to', out)


if __name__ == '__main__':
    main()
