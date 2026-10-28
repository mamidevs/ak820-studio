#include "menu_input_adapter.h"
#include "display_app.h"
#include "graphics/display.h"

static app_menu_t *menu;
static uint32_t previous_tick;
static bool have_tick;

void app_qmk_bind(app_menu_t *app) { menu = app; have_tick = false; }

#ifdef RGB_MATRIX_ENABLE
static uint8_t effect_of(uint8_t mode) {
    switch (mode) {
#    ifdef ENABLE_RGB_MATRIX_SOLID_COLOR
        case RGB_MATRIX_SOLID_COLOR: return APP_FX_SOLID;
#    endif
#    ifdef ENABLE_RGB_MATRIX_BREATHING
        case RGB_MATRIX_BREATHING: return APP_FX_BREATHING;
#    endif
#    ifdef ENABLE_RGB_MATRIX_BAND_SAT
        case RGB_MATRIX_BAND_SAT: return APP_FX_BAND_SAT;
#    endif
#    ifdef ENABLE_RGB_MATRIX_CYCLE_ALL
        case RGB_MATRIX_CYCLE_ALL: return APP_FX_CYCLE_ALL;
#    endif
#    ifdef ENABLE_RGB_MATRIX_CYCLE_LEFT_RIGHT
        case RGB_MATRIX_CYCLE_LEFT_RIGHT: return APP_FX_CYCLE_LEFT_RIGHT;
#    endif
#    ifdef ENABLE_RGB_MATRIX_CYCLE_UP_DOWN
        case RGB_MATRIX_CYCLE_UP_DOWN: return APP_FX_CYCLE_UP_DOWN;
#    endif
#    ifdef ENABLE_RGB_MATRIX_RAINBOW_MOVING_CHEVRON
        case RGB_MATRIX_RAINBOW_MOVING_CHEVRON: return APP_FX_CHEVRON;
#    endif
#    ifdef ENABLE_RGB_MATRIX_CYCLE_PINWHEEL
        case RGB_MATRIX_CYCLE_PINWHEEL: return APP_FX_PINWHEEL;
#    endif
#    ifdef ENABLE_RGB_MATRIX_JELLYBEAN_RAINDROPS
        case RGB_MATRIX_JELLYBEAN_RAINDROPS: return APP_FX_RAINDROPS;
#    endif
#    ifdef ENABLE_RGB_MATRIX_TYPING_HEATMAP
        case RGB_MATRIX_TYPING_HEATMAP: return APP_FX_HEATMAP;
#    endif
        default: return APP_FX_OTHER;
    }
}
#endif

void app_qmk_sync_rgb(void) {
    if (!menu) return;
    app_rgb_snapshot_t rgb = {0};
#ifdef RGB_MATRIX_ENABLE
    rgb.available = true;
    rgb.enabled = rgb_matrix_is_enabled();
    rgb.effect = effect_of(rgb_matrix_get_mode());
    rgb.hue = rgb_matrix_get_hue();
    rgb.sat = rgb_matrix_get_sat();
    rgb.val = rgb_matrix_get_val();
    rgb.speed = rgb_matrix_get_speed();
#endif
    app_menu_set_rgb_snapshot(menu, &rgb);
}

/* RGB changes go through the keyboard's own RM_* handling: *_noeeprom while
 * turning plus its debounced EEPROM flush, never one flash write per detent. */
static void keyboard_key(uint16_t keycode) {
    keyrecord_t record = {0};
    record.event.type = KEY_EVENT;
    record.event.pressed = true;
    record.event.time = timer_read() | 1;
    process_record_kb(keycode, &record);
}

static uint16_t with_command(uint16_t key) {
    /* Studio keymap: layers 2/3 are the Mac base/Fn layers. */
    return get_highest_layer(default_layer_state) >= 2 ? LGUI(key) : LCTL(key);
}

static void deliver(app_event_t event) {
    const app_event_result_t result = app_menu_handle(menu, event);
    uint16_t key = KC_NO, board = KC_NO;
    switch (result.action) {
        case APP_ACTION_VOLUME_UP: key = KC_VOLU; break;
        case APP_ACTION_VOLUME_DOWN: key = KC_VOLD; break;
        case APP_ACTION_MUTE_TOGGLE: key = KC_MUTE; break;
        case APP_ACTION_MEDIA_NEXT: key = KC_MNXT; break;
        case APP_ACTION_MEDIA_PREV: key = KC_MPRV; break;
        case APP_ACTION_MEDIA_PLAY: key = KC_MPLY; break;
        case APP_ACTION_BRIGHT_UP: key = KC_BRIU; break;
        case APP_ACTION_BRIGHT_DOWN: key = KC_BRID; break;
        case APP_ACTION_ZOOM_IN: key = with_command(KC_EQL); break;
        case APP_ACTION_ZOOM_OUT: key = with_command(KC_MINS); break;
        case APP_ACTION_ZOOM_RESET: key = with_command(KC_0); break;
        case APP_ACTION_RGB_TOGGLE: board = RM_TOGG; break;
        case APP_ACTION_RGB_NEXT: board = RM_NEXT; break;
        case APP_ACTION_RGB_PREV: board = RM_PREV; break;
        case APP_ACTION_RGB_VAL_UP: board = RM_VALU; break;
        case APP_ACTION_RGB_VAL_DOWN: board = RM_VALD; break;
        case APP_ACTION_RGB_HUE_UP: board = RM_HUEU; break;
        case APP_ACTION_RGB_HUE_DOWN: board = RM_HUED; break;
        case APP_ACTION_RGB_SAT_UP: board = RM_SATU; break;
        case APP_ACTION_RGB_SAT_DOWN: board = RM_SATD; break;
        case APP_ACTION_RGB_SPEED_UP: board = RM_SPDU; break;
        case APP_ACTION_RGB_SPEED_DOWN: board = RM_SPDD; break;
        case APP_ACTION_MEDIA_SHOW_TOGGLE: app_display_media_toggle(); break;
        case APP_ACTION_SCREEN_OFF: display_set_power(false); break;
        case APP_ACTION_ROUTE_USB: ak820_select_route(0, 0); break;
        case APP_ACTION_ROUTE_BT: ak820_select_route(1, (uint8_t)result.amount); break; /* amount = slot */
        case APP_ACTION_ROUTE_24G: ak820_select_route(2, 0); break;
        case APP_ACTION_PAIR: ak820_pair_route(); break;
        /* Studio keymap: layer 0 Windows base, layer 2 Mac base. RAM only, like
         * the keymap's switch handler minus the EEPROM write; the Mac/Win
         * switch re-applies its position when moved and at every boot. */
        case APP_ACTION_OS_MAC: default_layer_set((layer_state_t)1 << 2); keymap_config.no_gui = false; break;
        case APP_ACTION_OS_WINDOWS: default_layer_set((layer_state_t)1 << 0); break;
        default: break;
    }
    /* Bounded: a fast spin never queues more than a few taps per scan. */
    const uint16_t amount = result.amount > 8u ? 8u : result.amount;
    if (key != KC_NO) for (uint16_t i = 0; i < amount; i++) tap_code16(key);
    if (board != KC_NO) {
        for (uint16_t i = 0; i < amount; i++) keyboard_key(board);
        app_qmk_sync_rgb();
    }
}

bool app_qmk_process(uint16_t keycode, keyrecord_t *record, bool fn_active) {
    if (keycode != APP_KNOB && keycode != APP_KNOB_CCW && keycode != APP_KNOB_CW) return true;
    if (!menu || !record->event.pressed) return false; /* consume releases too */
    app_menu_handle(menu, (app_event_t){.type = APP_EVENT_FN_CHANGED, .data.fn_held = fn_active});
    if (keycode == APP_KNOB) deliver((app_event_t){.type = APP_EVENT_KNOB_PRESS});
    else deliver((app_event_t){.type = APP_EVENT_ROTATE, .data.rotation = keycode == APP_KNOB_CW ? 1 : -1});
    return false;
}

void app_qmk_tick(uint32_t now_ms) {
    if (!menu) return;
    if (!have_tick) { previous_tick = now_ms; have_tick = true; return; }
    const uint32_t elapsed = now_ms - previous_tick;
    previous_tick = now_ms;
    app_menu_handle(menu, (app_event_t){.type = APP_EVENT_TICK, .data.elapsed_ms = elapsed});
}
