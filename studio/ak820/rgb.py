"""Source-backed stock USB RGB settings, without any device I/O.

Evidence: work/rgb-provenance.txt and work/rgb-control-validation.txt.
The record defaults are software defaults, never a readback of device state.
"""
import re

MODE_MASKS = (0x00, 0x31, 0x33, 0x33, 0x33, 0x33, 0x03, 0x33, 0x03, 0x33,
              0x3B, 0x37, 0x37, 0x33, 0x33, 0x33, 0x37, 0x33, 0x37, 0x33)
SOURCE_RECORD_DEFAULTS = {
    'mode': 11, 'color': '#ff0000', 'brightness': 5, 'speed': 3,
    'multicolor': True, 'direction': 0,
}
DEFAULT_RGB_SETTINGS = {
    'mode': 1, 'color': '#ffffff', 'brightness': 5, 'speed': 3,
    'multicolor': False, 'direction': 0,
}
RGB_ACKS = (True, True, False, True, False)
RGB_STAGES = ('rgb_start', 'rgb_config', 'rgb_settings', 'rgb_finish', 'rgb_finalize')
RGB_DELAY_SECONDS = .035


def _integer(value, low, high, label):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(f'{label} {low}–{high} arasında bir tam sayı olmalı.')
    return value


def normalize_rgb(raw: dict) -> dict:
    if not isinstance(raw, dict):
        raise ValueError('Aydınlatma ayarları geçersiz.')
    if set(raw) - set(DEFAULT_RGB_SETTINGS):
        raise ValueError('Bilinmeyen aydınlatma ayarı.')
    mode = _integer(raw.get('mode', DEFAULT_RGB_SETTINGS['mode']), 0, 19, 'Efekt')
    if mode == 0:
        return {'mode': 0, 'color': '#000000', 'brightness': 0, 'speed': 0,
                'multicolor': False, 'direction': 0}
    mask = MODE_MASKS[mode]
    settings = dict(SOURCE_RECORD_DEFAULTS, mode=mode)
    settings['brightness'] = _integer(raw.get('brightness', 5), 1, 5, 'Parlaklık')
    if mask & 0x02:
        settings['speed'] = _integer(raw.get('speed', 3), 1, 5, 'Hız')
    if mask & 0x10:
        color = raw.get('color', DEFAULT_RGB_SETTINGS['color'])
        if not isinstance(color, str) or not re.fullmatch(r'#[0-9a-fA-F]{6}', color):
            raise ValueError('Renk #RRGGBB biçiminde olmalı.')
        settings['color'] = color.lower()
    if mask & 0x20:
        multicolor = raw.get('multicolor', DEFAULT_RGB_SETTINGS['multicolor'])
        if type(multicolor) is not bool:
            raise ValueError('Çok renkli seçimi açık veya kapalı olmalı.')
        settings['multicolor'] = multicolor
    if mask & 0x04:
        settings['direction'] = _integer(raw.get('direction', 0), 0, 1, 'Yön')
    elif mask & 0x08:
        settings['direction'] = _integer(raw.get('direction', 2), 2, 3, 'Yön')
    # The official sender copies every field for nonzero modes, even when a
    # control is disabled. Keep its documented backing-record defaults for
    # ignored fields; never pass arbitrary browser values into those bytes.
    return settings


def rgb_packets(raw: dict) -> tuple[bytes, ...]:
    settings = normalize_rgb(raw)
    start = bytes([4, 0x18]) + bytes(62)
    config = bytearray(64)
    config[:2] = bytes([4, 0x13])
    config[8] = 1
    values = bytearray(64)
    values[0] = settings['mode']
    if settings['mode']:
        values[1:4] = bytes.fromhex(settings['color'][1:])
        values[8:12] = bytes([int(settings['multicolor']), settings['brightness'],
                             settings['speed'], settings['direction']])
    values[14:16] = bytes([0xAA, 0x55])
    finish = bytes([4, 0x02]) + bytes(62)
    finalize = bytes([4, 0xF0]) + bytes(62)
    return start, bytes(config), bytes(values), finish, finalize
