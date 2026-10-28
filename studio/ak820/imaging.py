"""Local image decoding and deterministic 128px screen rendering."""
import hashlib
import io
import json
import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageOps, UnidentifiedImageError

Image.MAX_IMAGE_PIXELS = 25_000_000
MAX_FILE = 12 * 1024 * 1024
MAX_FRAMES = 140
DEFAULTS = dict(fit='cover', zoom=1, x=0, y=0, brightness=1, contrast=1,
                saturation=1, rotation=0, effect='none', background='#0b0e12',
                layout='image', title='MERHABA', subtitle='KENDİ EKRANIN', color='#bcf26d')


def normalize_settings(raw):
    if not isinstance(raw, dict):
        raise ValueError('Görüntü ayarları geçersiz.')
    s = dict(DEFAULTS)
    for key, allowed in {'fit': ['cover', 'contain'], 'effect': ['none', 'mono', 'warm', 'cool', 'invert', 'pixel'],
                         'layout': ['image', 'card', 'poster'], 'rotation': [0, 90, 180, 270]}.items():
        value = raw.get(key, s[key])
        if value not in allowed:
            raise ValueError(f'Geçersiz ayar: {key}')
        s[key] = value
    for key, low, high in [('zoom', 1, 3), ('x', -1, 1), ('y', -1, 1),
                            ('brightness', 0, 2), ('contrast', 0, 2), ('saturation', 0, 2)]:
        value = float(raw.get(key, s[key]))
        if not math.isfinite(value) or not low <= value <= high:
            raise ValueError(f'Geçersiz ayar: {key}')
        s[key] = value
    for key in ('color', 'background'):
        value = raw.get(key, s[key])
        if not isinstance(value, str) or not re.fullmatch(r'#[a-fA-F0-9]{6}', value):
            raise ValueError('Geçersiz renk.')
        s[key] = value
    for key in ('title', 'subtitle'):
        value = raw.get(key, s[key])
        if not isinstance(value, str) or len(value) > 40:
            raise ValueError('Yazılar en fazla 40 karakter olabilir.')
        s[key] = value
    return s


def inspect_image(data):
    if len(data) > MAX_FILE:
        raise ValueError('Dosya en fazla 12 MB olabilir.')
    try:
        with Image.open(io.BytesIO(data)) as im:
            if im.format not in ('PNG', 'JPEG', 'GIF', 'WEBP'):
                raise ValueError('PNG, JPG, WebP veya GIF seçin.')
            count = getattr(im, 'n_frames', 1)
            if count > MAX_FRAMES:
                raise ValueError('Animasyon en fazla 140 kare olabilir. GIF’i kısaltıp yeniden seçin.')
            if im.width * im.height > 25_000_000 or im.width * im.height * count > 80_000_000:
                raise ValueError('Görsel çok büyük. Boyutunu küçültüp yeniden seçin.')
            # Validate the complete animation before accepting an asset.
            for i in range(count):
                im.seek(i)
                im.load()
            return dict(width=im.width, height=im.height, frame_count=count, format=im.format)
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError('Görsel okunamadı. Geçerli bir PNG, JPG, WebP veya GIF seçin.') from exc


def default_image():
    image = Image.new('RGB', (256, 256))
    values = []
    for y in range(256):
        for x in range(256):
            glow = math.exp(-(((x-153)/95)**2 + ((y-112)/88)**2))
            band = (math.sin((x+y*.43)/21)+1)/2
            values.append((int(13+glow*61+band*5), int(22+glow*112), int(31+glow*70)))
    image.putdata(values)
    d = ImageDraw.Draw(image)
    for i in range(6):
        r = 44+i*15
        d.arc((128-r, 116-r, 128+r, 116+r), 215, 500, fill=(158+i*10, 224+i*4, 109+i*4), width=2)
    d.rounded_rectangle((30, 177, 226, 222), radius=8, fill=(13, 22, 22))
    d.text((128, 199), 'MAKE IT YOURS', font=font(19), fill='#d7f4aa', anchor='mm')
    return image


def font(size):
    for path in ['/System/Library/Fonts/Supplemental/Arial Bold.ttf', '/System/Library/Fonts/Supplemental/Arial.ttf']:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size=size)


def text_fit(draw, value, max_size, width):
    # Both template slots are single-line; never let a long label spill outside
    # the 128px screen after the minimum readable font size has been reached.
    value = ' '.join(value.splitlines())
    for size in range(max_size, 6, -1):
        f = font(size)
        if draw.textlength(value, font=f) <= width:
            return value, f
    f = font(7)
    ellipsis = '…'
    if draw.textlength(ellipsis, font=f) > width:
        return '', f
    while value and draw.textlength(value + ellipsis, font=f) > width:
        value = value[:-1]
    return value.rstrip() + ellipsis, f


def quantize565(image):
    # Expand exact 5/6/5 channel values for preview, preserving their packed value.
    return Image.merge('RGB', tuple(channel.point(lambda v, bits=bits: (v >> (8-bits))*255//((1<<bits)-1))
                                    for channel, bits in zip(image.split(), (5, 6, 5))))


def render_frame(source, s):
    source = ImageOps.exif_transpose(source).convert('RGBA')
    source = source.rotate(-s['rotation'], expand=True)
    bg = Image.new('RGBA', source.size, s['background'])
    bg.alpha_composite(source)
    source = bg.convert('RGB')
    scale = (max if s['fit'] == 'cover' else min)(128/source.width, 128/source.height) * s['zoom']
    w, h = source.width*scale, source.height*scale
    left = (128-w)/2 - s['x']*abs(128-w)/2
    top = (128-h)/2 - s['y']*abs(128-h)/2
    image = source.transform((128, 128), Image.Transform.AFFINE,
                             (1/scale, 0, -left/scale, 0, 1/scale, -top/scale),
                             resample=Image.Resampling.BICUBIC, fillcolor=s['background'])
    image = ImageEnhance.Brightness(image).enhance(s['brightness'])
    image = ImageEnhance.Contrast(image).enhance(s['contrast'])
    image = ImageEnhance.Color(image).enhance(s['saturation'])
    if s['effect'] == 'mono':
        image = ImageOps.grayscale(image).convert('RGB')
    elif s['effect'] in ('warm', 'cool'):
        tint = '#ffac67' if s['effect'] == 'warm' else '#65aeff'
        image = Image.blend(image, Image.new('RGB', image.size, tint), .18)
    elif s['effect'] == 'invert':
        image = ImageOps.invert(image)
    elif s['effect'] == 'pixel':
        image = image.resize((32,32), Image.Resampling.BOX).resize((128,128), Image.Resampling.NEAREST)
    if s['layout'] != 'image':
        overlay = Image.new('RGBA', image.size)
        d = ImageDraw.Draw(overlay)
        if s['layout'] == 'card':
            d.rounded_rectangle((6, 73, 122, 122), radius=7, fill=(5, 12, 16, 230))
            d.rectangle((13, 84, 15, 109), fill=s['color'])
            title, title_font = text_fit(d,s['title'],15,93)
            subtitle, subtitle_font = text_fit(d,s['subtitle'],8,93)
            d.text((22, 88), title, font=title_font, fill='#ffffff')
            d.text((22, 106), subtitle, font=subtitle_font, fill=s['color'])
        else:
            d.rectangle((0, 0, 127, 127), fill=(0,0,0,130))
            d.line((48, 32, 80, 32), fill=s['color'], width=3)
            title, title_font = text_fit(d,s['title'],22,112)
            subtitle, subtitle_font = text_fit(d,s['subtitle'],9,112)
            d.text((64, 62), title, font=title_font, fill='#ffffff', anchor='mm')
            d.text((64, 85), subtitle, font=subtitle_font, fill=s['color'], anchor='mm')
        image = Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')
    return quantize565(image)


def render(data, settings):
    s = normalize_settings(settings)
    if data is None:
        return [render_frame(default_image(), s)], [50], []
    inspect_image(data)
    frames, durations, warnings = [], [], []
    with Image.open(io.BytesIO(data)) as im:
        for index in range(getattr(im, 'n_frames', 1)):
            im.seek(index)
            delay = int(im.info.get('duration', 50) or 50)
            actual = max(2, min(510, delay//2*2))
            if actual != delay and not warnings:
                warnings.append('Kare süreleri ekran biçimine uyarlandı (2–510 ms).')
            frames.append(render_frame(im.copy(), s))
            durations.append(actual)
    return frames, durations, warnings


def render_key(asset_id, settings):
    return hashlib.sha256(json.dumps([asset_id, normalize_settings(settings)], sort_keys=True).encode()).hexdigest()[:24]
