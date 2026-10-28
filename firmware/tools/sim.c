/* Host-side simulator around the real firmware core and raster renderer.
 * Built as a shared library for previews (make_previews.py) and the
 * interactive simulator (simulator.py). Fixture data lives only here. */
#include "app_menu.h"
#include "app_raster.h"
#include <stdio.h>
#include <string.h>

static app_menu_t app;
static app_raster_t tile;
static int last_action;
static char state_json[512];

#define NOW 1767268800u /* Fictional 2026-01-01 fixture, not account history. */

static void fixture_live(void) {
    app_device_snapshot_t d = app.device;
    d.battery = 76; d.charging = true; d.usb_active = true; d.route = 0; d.slot = 1;
    d.screen_on = true; d.sleep_minutes = 5; d.os = APP_OS_MAC; d.caps_lock = false;
    app_menu_set_device_snapshot(&app, &d);
    app.host_link = APP_LINK_LIVE;
    app_menu_set_clock(&app, NOW, 180);
    app_usage_snapshot_t s = {0};
    s.short_available = true; s.short_used_percent = 18; s.short_resets_at = NOW + 3u * 3600u + 15u * 60u;
    s.weekly_available = true; s.weekly_used_percent = 76; s.weekly_resets_at = NOW + 2u * 86400u + 6u * 3600u;
    s.age_seconds = 4;
    app_menu_set_codex_snapshot(&app, &s);
    s.short_used_percent = 4; s.short_resets_at = NOW + 4u * 3600u + 2u * 60u;
    s.weekly_used_percent = 38; s.weekly_resets_at = NOW + 5u * 86400u + 3u * 3600u;
    app_menu_set_claude_snapshot(&app, &s);
    app_rgb_snapshot_t rgb = {true, true, APP_FX_CYCLE_ALL, 150, 255, 180, 128};
    app_menu_set_rgb_snapshot(&app, &rgb);
}

/* preset 0: nothing known (fresh boot without Studio)
 * preset 1: live Studio data
 * preset 2: Studio gone stale, Bluetooth, low battery
 * preset 3: live, quotas nearly exhausted
 * preset 4: live, an illustrative one-window-per-provider scenario: Codex weekly only,
 *           Claude 5 hours only
 * preset 5: preset 4 after unplugging the cable on Bluetooth */
void sim_init(int preset) {
    app_menu_init(&app, &app_raster_renderer, &tile);
    last_action = 0;
    if (preset >= 1) fixture_live();
    if (preset == 2) {
        app.host_link = APP_LINK_STALE;
        app.device.route = 1; app.device.slot = 2; app.device.battery = 8;
        app.device.charging = false; app.device.usb_active = false; app.device.os = APP_OS_WINDOWS;
        app.codex.age_seconds = 900; app.claude.short_available = false;
    }
    if (preset == 3) {
        app.codex.short_used_percent = 93; app.codex.weekly_used_percent = 97;
        app.claude.short_used_percent = 78; app.claude.weekly_used_percent = 55;
        app.device.caps_lock = true; app.knob_mode = APP_KNOB_MEDIA;
    }
    if (preset == 4 || preset == 5) {
        app.codex.short_available = false; app.codex.weekly_used_percent = 30;
        app.claude.weekly_available = false; app.claude.short_used_percent = 20;
        app.device.charging = false; app.device.battery = 100;
    }
    if (preset == 5) { /* Bluetooth, cable out: Studio data 12 minutes old */
        app.host_link = APP_LINK_OFFLINE; app.device.route = 1; app.device.slot = 1; app.device.radio_state = 3;
        app.device.usb_active = false; app.codex.age_seconds = 724; app.claude.age_seconds = 724;
    }
}

void sim_event(int type, int value) {
    app_event_t e;
    memset(&e, 0, sizeof(e));
    e.type = (app_event_type_t)type;
    if (type == APP_EVENT_TICK) e.data.elapsed_ms = (uint32_t)value;
    else if (type == APP_EVENT_ROTATE) e.data.rotation = (int16_t)value;
    else if (type == APP_EVENT_FN_CHANGED) e.data.fn_held = value != 0;
    const app_event_result_t r = app_menu_handle(&app, e);
    if (r.action) last_action = r.action;
    /* Pretend to be the adapter for RGB so the simulator responds. */
    app_rgb_snapshot_t rgb = app.rgb;
    for (unsigned i = 0; i < r.amount; i++) switch (r.action) {
        case APP_ACTION_RGB_TOGGLE: rgb.enabled = !rgb.enabled; break;
        case APP_ACTION_RGB_NEXT: rgb.effect = (uint8_t)(rgb.effect % (APP_FX_COUNT - 1) + 1); break;
        case APP_ACTION_RGB_PREV: rgb.effect = (uint8_t)(rgb.effect <= 1 ? APP_FX_COUNT - 1 : rgb.effect - 1); break;
        case APP_ACTION_RGB_VAL_UP: rgb.val = (uint8_t)(rgb.val > 239 ? 255 : rgb.val + 16); break;
        case APP_ACTION_RGB_VAL_DOWN: rgb.val = (uint8_t)(rgb.val < 16 ? 0 : rgb.val - 16); break;
        case APP_ACTION_RGB_HUE_UP: rgb.hue = (uint8_t)(rgb.hue + 8); break;
        case APP_ACTION_RGB_HUE_DOWN: rgb.hue = (uint8_t)(rgb.hue - 8); break;
        case APP_ACTION_RGB_SAT_UP: rgb.sat = (uint8_t)(rgb.sat > 239 ? 255 : rgb.sat + 16); break;
        case APP_ACTION_RGB_SAT_DOWN: rgb.sat = (uint8_t)(rgb.sat < 16 ? 0 : rgb.sat - 16); break;
        case APP_ACTION_RGB_SPEED_UP: rgb.speed = (uint8_t)(rgb.speed > 239 ? 255 : rgb.speed + 16); break;
        case APP_ACTION_RGB_SPEED_DOWN: rgb.speed = (uint8_t)(rgb.speed < 16 ? 0 : rgb.speed - 16); break;
        case APP_ACTION_MEDIA_SHOW_TOGGLE: app.device.media_show = !app.device.media_show; app.dirty = true; break;
        default: break;
    }
    /* Route intents: the adapter switches the CH582 and the next snapshot
     * reports it; pretend the link comes up at once. */
    app_device_snapshot_t d = app.device;
    switch (r.action) {
        case APP_ACTION_ROUTE_USB: d.route = 0; d.slot = 0; d.radio_state = 0; d.usb_active = true; break;
        case APP_ACTION_ROUTE_BT: d.route = 1; d.slot = (uint8_t)r.amount; d.radio_state = 3; break;
        case APP_ACTION_ROUTE_24G: d.route = 2; d.slot = 1; d.radio_state = 1; break;
        case APP_ACTION_PAIR: d.radio_state = 2; break;
        case APP_ACTION_OS_MAC: d.os = APP_OS_MAC; break;
        case APP_ACTION_OS_WINDOWS: d.os = APP_OS_WINDOWS; break;
        default: break;
    }
    app_menu_set_device_snapshot(&app, &d);
    app_menu_set_rgb_snapshot(&app, &rgb);
}

/* Direct state pokes for preview scenes. */
void sim_set(const char *key, int value) {
    if (!strcmp(key, "page")) app.page = (app_page_t)value;
    else if (!strcmp(key, "menu")) app.menu_active = value != 0;
    else if (!strcmp(key, "selected")) app.selected = (uint8_t)value;
    else if (!strcmp(key, "focus")) app.focus = (uint8_t)value;
    else if (!strcmp(key, "editing")) app.editing = value != 0;
    else if (!strcmp(key, "face")) app.face = (uint8_t)value;
    else if (!strcmp(key, "knob")) app.knob_mode = (uint8_t)value;
    else if (!strcmp(key, "toast")) { app.toast = (uint8_t)value; app.toast_ms = APP_TOAST_MS; }
    else if (!strcmp(key, "boot")) app.boot_elapsed_ms = (uint32_t)value;
    else if (!strcmp(key, "caps")) app.device.caps_lock = value != 0;
    else if (!strcmp(key, "media")) app.device.media_available = value != 0;
    else if (!strcmp(key, "uptime")) app.uptime_ms = app.clock_uptime_ms = (uint32_t)value;
    app.dirty = true;
}

int sim_frame(uint8_t *out) {
    for (tile.top = 0; tile.top < 128; tile.top += APP_TILE_ROWS) {
        app_menu_render(&app);
        memcpy(out + (size_t)tile.top * 256u, tile.bytes, sizeof(tile.bytes));
    }
    return 128 * 128 * 2;
}

int sim_dirty(void) { return app.dirty; }

const char *sim_state(void) {
    (void)snprintf(state_json, sizeof(state_json),
                   "{\"page\":\"%s\",\"menu\":%s,\"fn\":%s,\"editing\":%s,\"knob\":%u,\"face\":%u,\"action\":%d}",
                   app_menu_page_name(app.page), app.menu_active ? "true" : "false", app.fn_held ? "true" : "false",
                   app.editing ? "true" : "false", app.knob_mode, app.face, last_action);
    last_action = 0;
    return state_json;
}
