"""RGB on Studio QMK firmware (AST2).

The keyboard owns its RGB matrix: effect, brightness, colour, saturation and
speed are changed from the on-screen Işık page with the knob, through the
firmware's own debounced RM_* handling. This Mac-side bridge has no RGB
command yet, so it reports that honestly instead of pretending to apply.
"""
from .qmk_transport import BridgeUnsupported

REASON = 'Işık, klavye ekranındaki Işık sayfasından düğmeyle yönetilir.'


def capabilities():
    return {'available': False, 'hardware_send_available': False, 'reason': REASON}


def rgb_exchange(transport, settings=None):
    """Called once per bridge cycle; never sends an RGB packet."""
    if settings is not None:
        raise BridgeUnsupported(REASON)
    return {}
