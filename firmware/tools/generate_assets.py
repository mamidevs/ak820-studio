#!/usr/bin/env python3
"""Generate the AK820 LCD fonts and icons as const C data (4-bit alpha).

Run from the project root with a Python that has Pillow:
    python3 firmware/tools/generate_assets.py

Fonts: Open Sans (Apache-2.0), historical 2011 Google font release; obtain separately.
Icons: Material Design Icons (Pictogrammers, Apache-2.0) as patched into
JetBrains Mono Nerd Font (OFL-1.1 / MIT). Glyphs are rasterised here on the
host; the firmware only blends the stored coverage values.
"""
from pathlib import Path
import os
import hashlib
import json

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).resolve().parent
OUT = ROOT / 'overlay/keyboards/a_jazz/ak820pro/app_menu'
FONTS = Path(os.environ.get('AK820_FONT_DIR', HERE / 'fonts'))
NERD = Path(os.environ.get('AK820_ICON_FONT', HERE / 'fonts/JetBrainsMonoNLNerdFont-Regular.ttf'))

TEXT = ''.join(chr(i) for i in range(32, 127)) + 'ÇÖÜçöüĞğİıŞş·°—…'
FONT_SPECS = [  # enum name, file, pixel size, charset
    ('SMALL', 'OpenSans-Semibold.ttf', 9, TEXT),
    ('BODY', 'OpenSans-Semibold.ttf', 11, TEXT),
    ('TITLE', 'OpenSans-ExtraBold.ttf', 13, TEXT),
    ('BIG', 'OpenSans-ExtraBold.ttf', 21, TEXT),
    ('CLOCK', 'OpenSans-ExtraBold.ttf', 38, ' 0123456789:-'),
]

ICON_SPECS = [  # enum name, MDI name, codepoint, sizes
    ('HOME', 'home', 0xF02DC, (16, 28)),
    ('CODEX', 'console', 0xF018D, (12, 16, 28)),
    ('CLAUDE', 'star-four-points', 0xF0AE2, (12, 16, 28)),
    ('LIGHT', 'lightbulb-on', 0xF06E8, (12, 16, 28)),
    ('KNOB', 'rotate-right', 0xF0467, (12, 16, 28)),
    ('DISPLAY', 'monitor', 0xF0379, (16, 28)),
    ('DEVICE', 'keyboard', 0xF030C, (16, 28)),
    ('HELP', 'help-circle-outline', 0xF0625, (16, 28)),
    ('USB', 'usb', 0xF0553, (12, 16)),
    ('BT', 'bluetooth', 0xF00AF, (12, 16)),
    ('RF', 'access-point', 0xF0003, (12, 16)),
    ('APPLE', 'apple', 0xF0035, (12, 16)),
    ('WINDOWS', 'microsoft-windows', 0xF05B3, (12, 16)),
    ('CAPS', 'apple-keyboard-caps', 0xF0632, (12, 16)),
    ('BOLT', 'lightning-bolt', 0xF140B, (9, 12, 16)),
    ('LINK', 'link-variant', 0xF0339, (12, 16)),
    ('LINK_OFF', 'link-variant-off', 0xF033A, (12, 16)),
    ('VOLUME', 'volume-high', 0xF057E, (12, 16)),
    ('MUTE', 'volume-off', 0xF0581, (12, 16)),
    ('MEDIA', 'play-pause', 0xF040E, (12, 16)),
    ('NEXT', 'skip-next', 0xF04AD, (16,)),
    ('PREV', 'skip-previous', 0xF04AE, (16,)),
    ('BRIGHT', 'brightness-6', 0xF00DF, (12, 16)),
    ('ZOOM', 'magnify-plus-outline', 0xF06ED, (12, 16)),
    ('RESET', 'update', 0xF06B0, (10, 12)),
    ('SLEEP', 'sleep', 0xF04B2, (16,)),
    ('IMAGE', 'image-multiple', 0xF02F9, (16,)),
    ('POWER', 'power', 0xF0425, (16,)),
    ('PALETTE', 'palette', 0xF03D8, (16,)),
    ('SPEED', 'speedometer', 0xF04C5, (16,)),
    ('EFFECT', 'auto-fix', 0xF0068, (16,)),
    ('CHECK', 'check', 0xF012C, (12, 16)),
    ('BACK', 'chevron-left', 0xF0141, (12, 16)),
    ('CHEVRON', 'chevron-right', 0xF0142, (12,)),
    ('CLOCK', 'clock-outline', 0xF0150, (16,)),
    ('FACE', 'view-dashboard-outline', 0xF0A1D, (16,)),
    ('SYSTEM', 'laptop', 0xF0322, (16,)),
    ('ALERT', 'alert-circle-outline', 0xF05D6, (12, 16)),
    ('SYNC', 'sync', 0xF04E6, (12, 16)),
    ('SAT', 'water-percent', 0xF058E, (16,)),
    ('LINKS', 'swap-horizontal-bold', 0xF0BCD, (16, 28)),
    ('PAIR', 'link-plus', 0xF0C94, (16,)),
]


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def quant(values):
    return [(v * 15 + 127) // 255 for v in values]


def pack(alpha):
    out = []
    for i in range(0, len(alpha), 2):
        hi = alpha[i]
        lo = alpha[i + 1] if i + 1 < len(alpha) else 0
        out.append((hi << 4) | lo)
    return out


def c_bytes(name, data):
    lines = [f'static const uint8_t {name}[{len(data)}]={{']
    for i in range(0, len(data), 24):
        lines.append(','.join(str(b) for b in data[i:i + 24]) + ',')
    lines.append('};')
    return '\n'.join(lines)


def render_font(file, size, chars):
    font = ImageFont.truetype(str(FONTS / file), size)
    ascent, descent = font.getmetrics()
    top = min(font.getbbox(c)[1] for c in chars if c.strip())
    bottom = max(font.getbbox(c)[3] for c in chars if c.strip())
    height = bottom - top
    pad = 4
    glyphs, data = [], []
    for ch in chars:
        advance = round(font.getlength(ch))
        box = font.getbbox(ch)
        width = max(advance, box[2]) + pad * 2
        im = Image.new('L', (max(1, width), height))
        ImageDraw.Draw(im).text((pad, -top), ch, font=font, fill=255)
        bbox = im.getbbox()
        if bbox is None:
            glyphs.append((ord(ch), 0, 0, 0, 0, 0, advance))
            continue
        x0, y0, x1, y1 = bbox
        crop = im.crop(bbox)
        alpha = quant(list(crop.tobytes()))
        offset = len(data)
        data += pack(alpha)
        glyphs.append((ord(ch), offset, x1 - x0, y1 - y0, x0 - pad, y0, advance))
    cap = font.getbbox('H')
    digit = font.getbbox('0')
    metrics = {'height': height, 'baseline': ascent - top,
               'cap_top': (cap if 'H' in chars else digit)[1] - top,
               'cap_bottom': (cap if 'H' in chars else digit)[3] - top}
    return glyphs, data, metrics


def render_icon(codepoint, size):
    big = 512
    font = ImageFont.truetype(str(NERD), big)
    im = Image.new('L', (big * 2, big * 2))
    ImageDraw.Draw(im).text((big // 2, big // 2), chr(codepoint), font=font, fill=255)
    bbox = im.getbbox()
    if bbox is None:
        raise SystemExit(f'icon U+{codepoint:X} is empty')
    crop = im.crop(bbox)
    w, h = crop.size
    scale = size / max(w, h)
    tw, th = max(1, round(w * scale)), max(1, round(h * scale))
    small = crop.resize((tw, th), Image.Resampling.BOX)
    canvas = Image.new('L', (size, size))
    canvas.paste(small, ((size - tw) // 2, (size - th) // 2))
    return quant(list(canvas.tobytes()))


def write_fonts():
    header = ['// Generated by firmware/tools/generate_assets.py. Do not edit.',
              '// Open Sans, Copyright 2011 Google Corporation, Apache License 2.0.',
              '#pragma once', '#include <stdint.h>', '#include <stddef.h>', '',
              'enum {']
    header += [f'    APP_FONT_{name},' for name, *_ in FONT_SPECS]
    header += ['    APP_FONT_COUNT', '};', '',
               'typedef struct { uint16_t offset; uint8_t width, height; int8_t x; uint8_t y, advance; } app_font_glyph_t;',
               '/* Never NULL: unknown code points map to the font space glyph. */',
               'const app_font_glyph_t *app_font_glyph(uint32_t codepoint, uint8_t font);',
               'const uint8_t *app_font_pixels(uint8_t font);',
               'uint8_t app_font_height(uint8_t font);   /* line box */',
               'uint8_t app_font_baseline(uint8_t font); /* baseline y inside line box */',
               'uint8_t app_font_cap_top(uint8_t font);  /* top of capitals/digits */',
               'uint8_t app_font_cap_bottom(uint8_t font);',
               '/* 0..15 coverage of a pixel inside the glyph bitmap. */',
               'static inline uint8_t app_font_alpha(const uint8_t *pixels, const app_font_glyph_t *g, uint8_t row, uint8_t col) {',
               '    const uint16_t index = (uint16_t)(row * g->width + col);',
               '    const uint8_t byte = pixels[g->offset + index / 2u];',
               '    return (index & 1u) ? (byte & 15u) : (byte >> 4);',
               '}',
               'uint32_t app_font_next(const char **text);',
               'uint16_t app_font_width(const char *text, uint8_t font);', '']
    (OUT / 'app_font.h').write_text('\n'.join(header))

    src = ['// Generated by firmware/tools/generate_assets.py. Do not edit.',
           '// Open Sans, Copyright 2011 Google Corporation, Apache License 2.0.',
           '#include "app_font.h"', '']
    table, meta = [], []
    for index, (name, file, size, chars) in enumerate(FONT_SPECS):
        glyphs, data, metrics = render_font(file, size, chars)
        glyphs.sort(key=lambda g: g[0])
        assert len(data) < 65536
        src.append(c_bytes(f'pixels_{index}', data))
        src.append(f'static const uint16_t codes_{index}[{len(glyphs)}]={{' + ','.join(str(g[0]) for g in glyphs) + '};')
        src.append(f'static const app_font_glyph_t glyphs_{index}[{len(glyphs)}]={{' +
                   ','.join('{%d,%d,%d,%d,%d,%d}' % g[1:] for g in glyphs) + '};')
        space = [g[0] for g in glyphs].index(32)
        table.append(f'    {{pixels_{index},codes_{index},glyphs_{index},{len(glyphs)},{space},'
                     f'{metrics["height"]},{metrics["baseline"]},{metrics["cap_top"]},{metrics["cap_bottom"]}}},')
        meta.append({'enum': name, 'file': file, 'size_px': size, 'glyphs': len(glyphs),
                     'bytes': len(data), **metrics, 'sha256': sha(FONTS / file)})
    src += ['', 'typedef struct {', '    const uint8_t *pixels; const uint16_t *codes; const app_font_glyph_t *glyphs;',
            '    uint8_t count, space, height, baseline, cap_top, cap_bottom;', '} font_t;',
            'static const font_t fonts[APP_FONT_COUNT]={'] + table + ['};', '']
    src.append('''static const font_t *font_of(uint8_t font) { return &fonts[font < APP_FONT_COUNT ? font : APP_FONT_BODY]; }
const uint8_t *app_font_pixels(uint8_t font) { return font_of(font)->pixels; }
uint8_t app_font_height(uint8_t font) { return font_of(font)->height; }
uint8_t app_font_baseline(uint8_t font) { return font_of(font)->baseline; }
uint8_t app_font_cap_top(uint8_t font) { return font_of(font)->cap_top; }
uint8_t app_font_cap_bottom(uint8_t font) { return font_of(font)->cap_bottom; }

const app_font_glyph_t *app_font_glyph(uint32_t cp, uint8_t font) {
    const font_t *f = font_of(font);
    uint8_t low = 0, high = f->count;
    while (low < high) {
        const uint8_t mid = (uint8_t)((low + high) / 2u);
        if (f->codes[mid] == cp) return &f->glyphs[mid];
        if (f->codes[mid] < cp) low = (uint8_t)(mid + 1u);
        else high = mid;
    }
    return &f->glyphs[f->space];
}

uint32_t app_font_next(const char **text) {
    const uint8_t *p = (const uint8_t *)*text;
    uint32_t cp = *p++;
    if (cp >= 0xC2 && cp <= 0xDF && (p[0] & 0xC0) == 0x80) {
        cp = ((cp & 31u) << 6) | (p[0] & 63u);
        p += 1;
    } else if (cp >= 0xE0 && cp <= 0xEF && (p[0] & 0xC0) == 0x80 && (p[1] & 0xC0) == 0x80) {
        cp = ((cp & 15u) << 12) | ((uint32_t)(p[0] & 63u) << 6) | (p[1] & 63u);
        p += 2;
    } else if (cp >= 128) {
        cp = '?';
    }
    *text = (const char *)p;
    return cp;
}

uint16_t app_font_width(const char *text, uint8_t font) {
    if (!text) return 0;
    uint32_t width = 0;
    for (unsigned n = 0; *text && n < 64u; n++) width += app_font_glyph(app_font_next(&text), font)->advance;
    return width > 65535u ? 65535u : (uint16_t)width;
}
''')
    (OUT / 'app_font.c').write_text('\n'.join(src))
    return meta


def write_icons():
    header = ['// Generated by firmware/tools/generate_assets.py. Do not edit.',
              '// Material Design Icons (Pictogrammers), Apache License 2.0.',
              '#pragma once', '#include <stdint.h>', '', 'enum {']
    header += [f'    APP_ICON_{name},' for name, *_ in ICON_SPECS]
    header += ['    APP_ICON_COUNT', '};', '',
               'typedef struct { uint16_t offset; uint8_t id, size; } app_icon_t;',
               '/* NULL when the icon was not generated at this size. */',
               'const app_icon_t *app_icon_find(uint8_t id, uint8_t size);',
               'extern const uint8_t app_icon_pixels[];',
               'static inline uint8_t app_icon_alpha(const app_icon_t *icon, uint8_t row, uint8_t col) {',
               '    const uint16_t index = (uint16_t)(row * icon->size + col);',
               '    const uint8_t byte = app_icon_pixels[icon->offset + index / 2u];',
               '    return (index & 1u) ? (byte & 15u) : (byte >> 4);',
               '}', '']
    (OUT / 'app_icons.h').write_text('\n'.join(header))
    data, entries, meta = [], [], []
    for index, (name, mdi, cp, sizes) in enumerate(ICON_SPECS):
        for size in sizes:
            entries.append((len(data), index, size))
            data += pack(render_icon(cp, size))
        meta.append({'enum': name, 'mdi': mdi, 'codepoint': f'U+{cp:X}', 'sizes': list(sizes)})
    assert len(data) < 65536
    src = ['// Generated by firmware/tools/generate_assets.py. Do not edit.',
           '// Material Design Icons (Pictogrammers), Apache License 2.0.',
           '#include "app_icons.h"', '#include <stddef.h>', '',
           c_bytes('icon_pixels_data', data).replace('static const uint8_t icon_pixels_data', 'const uint8_t app_icon_pixels'),
           f'static const app_icon_t icons[{len(entries)}]={{' + ','.join('{%d,%d,%d}' % e for e in entries) + '};',
           '''const app_icon_t *app_icon_find(uint8_t id, uint8_t size) {
    for (size_t i = 0; i < sizeof(icons) / sizeof(icons[0]); i++)
        if (icons[i].id == id && icons[i].size == size) return &icons[i];
    return NULL;
}
''']
    (OUT / 'app_icons.c').write_text('\n'.join(src))
    return meta, len(data)


def main():
    fonts = write_fonts()
    icons, icon_bytes = write_icons()
    provenance = {
        'generator': 'firmware/tools/generate_assets.py',
        'alpha_bits': 4,
        'fonts': fonts,
        'font_license': 'Open Sans, Copyright 2011 Google Corporation, Apache License 2.0',
        'icons': icons,
        'icon_bytes': icon_bytes,
        'icon_source': {'file': NERD.name, 'sha256': sha(NERD),
                        'license': 'Material Design Icons (Pictogrammers) Apache-2.0; '
                                   'Nerd Fonts patcher MIT; JetBrains Mono OFL-1.1'},
    }
    (ROOT / 'asset-provenance.json').write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + '\n')
    total = sum(f['bytes'] for f in fonts) + icon_bytes
    print('fonts', [(f['enum'], f['bytes'], f['height']) for f in fonts])
    print('icons', icon_bytes, 'bytes; total pixel data', total)


if __name__ == '__main__':
    main()
