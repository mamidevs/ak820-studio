#include "app_menu.h"
#include "app_font.h"
#include "app_icons.h"

#include <stddef.h>
#include <stdio.h>
#include <string.h>

#define C565(r, g, b) ((uint16_t)((((r) >> 3) << 11) | (((g) >> 2) << 5) | ((b) >> 3)))

/* Dark slate surfaces, never pure black; text >= 4.5:1 on every surface. */
enum {
    BG = C565(0x0B, 0x11, 0x20),
    SURFACE = C565(0x15, 0x1D, 0x2E),
    SURFACE_HI = C565(0x21, 0x2C, 0x42),
    STROKE = C565(0x31, 0x40, 0x58),
    TRACK = C565(0x27, 0x34, 0x4A),
    TEXT = C565(0xF1, 0xF5, 0xF9),
    MUTED = C565(0x9A, 0xA8, 0xBC),
    DIM = C565(0x62, 0x72, 0x8A),
    LIME = C565(0xBD, 0xF1, 0x6E),
    CYAN = C565(0x5E, 0xE6, 0xD6),
    CORAL = C565(0xF4, 0x8E, 0x70),
    AMBER = C565(0xFB, 0xBF, 0x24),
    VIOLET = C565(0xA7, 0x8B, 0xFA),
    SKY = C565(0x60, 0xA5, 0xFA),
    PINK = C565(0xF4, 0x72, 0xB6),
    SLATE = C565(0xCB, 0xD5, 0xE1),
    ORANGE = C565(0xFB, 0x92, 0x3C),
    OK = C565(0x4A, 0xDE, 0x80),
    WARN = C565(0xFB, 0xBF, 0x24),
    DANGER = C565(0xF8, 0x71, 0x71),
};

enum { F_SMALL = APP_FONT_SMALL, F_BODY = APP_FONT_BODY, F_TITLE = APP_FONT_TITLE, F_BIG = APP_FONT_BIG, F_CLOCK = APP_FONT_CLOCK };

typedef struct {
    app_page_t page;
    const char *name, *title, *hint;
    uint8_t icon;
    uint16_t color;
} item_t;

static const item_t items[APP_MENU_ITEM_COUNT] = {
    {APP_PAGE_HOME, "Ana ekran", "Ana ekran", "Halkalar ve saat", APP_ICON_HOME, LIME},
    {APP_PAGE_CODEX, "Codex", "Codex", "5 saat · 7 gün kalan", APP_ICON_CODEX, CYAN},
    {APP_PAGE_CLAUDE, "Claude Code", "Claude", "5 saat · 7 gün kalan", APP_ICON_CLAUDE, CORAL},
    {APP_PAGE_LIGHT, "Işık", "Işık", "Efekt · renk · parlaklık", APP_ICON_LIGHT, AMBER},
    {APP_PAGE_KNOB, "Düğme modu", "Düğme", "Ses · medya · zoom", APP_ICON_KNOB, VIOLET},
    {APP_PAGE_DISPLAY, "Ekran", "Ekran", "Uyku · yüz · görsel", APP_ICON_DISPLAY, SKY},
    {APP_PAGE_LINK, "Bağlantı", "Bağlantı", "USB · Bluetooth · 2.4 GHz", APP_ICON_LINKS, ORANGE},
    {APP_PAGE_DEVICE, "Cihaz", "Cihaz", "Pil · bağlantı · Studio", APP_ICON_DEVICE, PINK},
    {APP_PAGE_SHORTCUTS, "Kısayollar", "Kısayollar", "Fn kombinasyonları", APP_ICON_HELP, SLATE},
};

typedef struct {
    const char *name, *hint;
    uint8_t icon;
} knob_t;

static const knob_t knobs[APP_KNOB_COUNT] = {
    {"Ses", "Çevir: ses · Bas: sessiz", APP_ICON_VOLUME},
    {"Medya", "Çevir: parça · Bas: oynat", APP_ICON_MEDIA},
    {"Parlaklık", "Bilgisayar ekranı", APP_ICON_BRIGHT},
    {"Işık", "RGB parlaklık · Bas: aç/kapat", APP_ICON_LIGHT},
    {"Yakınlaştır", "Çevir: zoom · Bas: sıfırla", APP_ICON_ZOOM},
};

static const char *const effects[APP_FX_COUNT] = {
    "Özel", "Sabit", "Nefes", "Doygunluk", "Döngü", "Yatay akış",
    "Dikey akış", "Ok dalgası", "Fırıldak", "Yağmur", "Isı haritası"};

static const uint8_t sleep_choices[] = {0, 1, 5, 15, 30};

enum { /* toast kinds */
    T_NONE = 0, T_VOL_UP, T_VOL_DOWN, T_MUTE, T_NEXT, T_PREV, T_PLAY,
    T_BRIGHT_UP, T_BRIGHT_DOWN, T_LIGHT_VAL, T_LIGHT_TOGGLE, T_ZOOM_IN,
    T_ZOOM_OUT, T_ZOOM_RESET, T_FACE, T_NO_ACTION
};

/* ------------------------------------------------------------------ state */

uint16_t app_rgb565(uint8_t red, uint8_t green, uint8_t blue) {
    return (uint16_t)(((uint16_t)(red >> 3) << 11) | ((uint16_t)(green >> 2) << 5) | (blue >> 3));
}

static uint16_t mix(uint16_t fg, uint16_t bg, uint8_t alpha) { /* alpha 0..255 */
    const uint32_t a = alpha, b = 255u - alpha;
    const uint32_t red = ((((uint32_t)fg >> 11) & 31u) * a + (((uint32_t)bg >> 11) & 31u) * b + 127u) / 255u;
    const uint32_t green = ((((uint32_t)fg >> 5) & 63u) * a + (((uint32_t)bg >> 5) & 63u) * b + 127u) / 255u;
    const uint32_t blue = (((uint32_t)fg & 31u) * a + ((uint32_t)bg & 31u) * b + 127u) / 255u;
    return (uint16_t)((red << 11) | (green << 5) | blue);
}

const char *app_menu_item_name(uint8_t index) {
    return index < APP_MENU_ITEM_COUNT ? items[index].name : "?";
}

app_page_t app_menu_item_page(uint8_t index) {
    return index < APP_MENU_ITEM_COUNT ? items[index].page : APP_PAGE_HOME;
}

const char *app_menu_page_name(app_page_t page) {
    if (page == APP_PAGE_BOOT) return "Açılış";
    if (page == APP_PAGE_MENU) return "Menü";
    for (uint8_t i = 0; i < APP_MENU_ITEM_COUNT; i++)
        if (items[i].page == page) return items[i].name;
    return "?";
}

uint8_t app_menu_row_count(app_page_t page) {
    switch (page) {
        case APP_PAGE_LIGHT: return 7;
        case APP_PAGE_KNOB: return 1 + APP_KNOB_COUNT;
        case APP_PAGE_DISPLAY: return 5;
        case APP_PAGE_LINK: return 8;
        default: return 1;
    }
}

static bool list_page(app_page_t page) { return app_menu_row_count(page) > 1; }

void app_menu_init(app_menu_t *app, const app_renderer_t *renderer, void *user) {
    if (app == NULL) return;
    memset(app, 0, sizeof(*app));
    app->page = APP_PAGE_BOOT;
    app->dirty = true;
    app->device.battery = 255;
    app->device.route = 3;
    app->device.screen_on = true;
    app->device.sleep_minutes = 3;
    app->codex.age_seconds = UINT32_MAX;
    app->claude.age_seconds = UINT32_MAX;
    app->clock_minute = UINT16_MAX;
    if (renderer != NULL) app->renderer = *renderer;
    app->renderer_user = user;
}

/* What the screen shows of a snapshot: values, resets and fresh/stale.
 * The age itself is not drawn, so a ticking age must not cost a repaint. */
static bool same_view(const app_usage_snapshot_t *a, const app_usage_snapshot_t *b) {
    return a->weekly_available == b->weekly_available && a->short_available == b->short_available &&
           (!a->weekly_available || (a->weekly_used_percent == b->weekly_used_percent && a->weekly_resets_at == b->weekly_resets_at)) &&
           (!a->short_available || (a->short_used_percent == b->short_used_percent && a->short_resets_at == b->short_resets_at)) &&
           (a->age_seconds < APP_USAGE_FRESH_SECONDS) == (b->age_seconds < APP_USAGE_FRESH_SECONDS);
}

static bool set_usage(app_menu_t *app, app_usage_snapshot_t *target, const app_usage_snapshot_t *snapshot) {
    app_usage_snapshot_t next;
    if (snapshot == NULL) {
        memset(&next, 0, sizeof(next));
        next.age_seconds = UINT32_MAX;
    } else {
        if ((snapshot->weekly_available && snapshot->weekly_used_percent > 100u) ||
            (snapshot->short_available && snapshot->short_used_percent > 100u)) return false;
        next = *snapshot;
        next.observed_label[sizeof(next.observed_label) - 1u] = '\0';
    }
    if (!same_view(target, &next)) app->dirty = true;
    *target = next;
    return true;
}

bool app_menu_set_codex_snapshot(app_menu_t *app, const app_usage_snapshot_t *snapshot) {
    return app != NULL && set_usage(app, &app->codex, snapshot);
}

bool app_menu_set_claude_snapshot(app_menu_t *app, const app_usage_snapshot_t *snapshot) {
    return app != NULL && set_usage(app, &app->claude, snapshot);
}

void app_menu_set_device_snapshot(app_menu_t *app, const app_device_snapshot_t *snapshot) {
    if (!app || !snapshot || !memcmp(&app->device, snapshot, sizeof(*snapshot))) return;
    app->device = *snapshot;
    app->dirty = true;
}

void app_menu_set_rgb_snapshot(app_menu_t *app, const app_rgb_snapshot_t *snapshot) {
    if (!app || !snapshot || !memcmp(&app->rgb, snapshot, sizeof(*snapshot))) return;
    app->rgb = *snapshot;
    if (app->rgb.effect >= APP_FX_COUNT) app->rgb.effect = APP_FX_OTHER;
    app->dirty = true;
}

static uint16_t clock_minute(const app_menu_t *app);

bool app_menu_set_clock(app_menu_t *app, uint32_t epoch, int16_t offset_minutes) {
    if (!app || offset_minutes < -840 || offset_minutes > 840) return false;
    const uint16_t before = app->clock_minute;
    app->wall_clock_epoch = epoch;
    app->clock_uptime_ms = app->uptime_ms;
    app->utc_offset_minutes = offset_minutes;
    app->clock_minute = clock_minute(app);
    /* Studio re-sends the time every cycle; only a new minute is news. */
    if (app->clock_minute != before) app->dirty = true;
    return true;
}

uint32_t app_menu_now_epoch(const app_menu_t *app) {
    if (!app || !app->wall_clock_epoch) return 0;
    const uint32_t seconds = (app->uptime_ms - app->clock_uptime_ms) / 1000u;
    return seconds > UINT32_MAX - app->wall_clock_epoch ? UINT32_MAX : app->wall_clock_epoch + seconds;
}

/* Local wall time; false when the host never sent a clock. */
typedef struct { uint8_t hour, minute, weekday, day, month; uint16_t year; uint32_t minute_index; } local_time_t;

static bool local_time(const app_menu_t *app, local_time_t *t) {
    const uint32_t now = app_menu_now_epoch(app);
    const int32_t offset = (int32_t)app->utc_offset_minutes * 60;
    if (!now || (offset < 0 && now < (uint32_t)-offset) || (offset > 0 && now > UINT32_MAX - (uint32_t)offset)) return false;
    const uint32_t seconds = offset < 0 ? now - (uint32_t)-offset : now + (uint32_t)offset;
    const uint32_t days = seconds / 86400u, rest = seconds % 86400u;
    t->hour = (uint8_t)(rest / 3600u);
    t->minute = (uint8_t)((rest / 60u) % 60u);
    t->weekday = (uint8_t)((days + 4u) % 7u); /* 0 = Sunday */
    t->minute_index = seconds / 60u;
    /* Howard Hinnant's civil_from_days, unsigned since days >= 0. */
    const uint32_t z = days + 719468u, era = z / 146097u, doe = z - era * 146097u;
    const uint32_t yoe = (doe - doe / 1460u + doe / 36524u - doe / 146096u) / 365u;
    const uint32_t doy = doe - (365u * yoe + yoe / 4u - yoe / 100u), mp = (5u * doy + 2u) / 153u;
    t->day = (uint8_t)(doy - (153u * mp + 2u) / 5u + 1u);
    t->month = (uint8_t)(mp < 10u ? mp + 3u : mp - 9u);
    t->year = (uint16_t)(yoe + era * 400u + (t->month <= 2u));
    return true;
}

/* Wraps every ~45 days; only compared for change, so that is harmless. */
static uint16_t clock_minute(const app_menu_t *app) {
    local_time_t t;
    return local_time(app, &t) ? (uint16_t)(t.minute_index & 0xFFFFu) : UINT16_MAX;
}

static uint32_t saturated_add(uint32_t first, uint32_t second) {
    return second > UINT32_MAX - first ? UINT32_MAX : first + second;
}

/* ------------------------------------------------------------- navigation */

static void go(app_menu_t *app, app_page_t page) {
    app->page = page;
    app->editing = false;
    app->focus = list_page(page) ? 1u : 0u;
    app->dirty = true;
}

static void enter_menu(app_menu_t *app) {
    for (uint8_t i = 0; i < APP_MENU_ITEM_COUNT; ++i)
        if (items[i].page == app->page) app->selected = i;
    app->menu_active = true;
    app->menu_idle_ms = 0;
    app->toast = T_NONE;
    go(app, APP_PAGE_MENU);
}

static void exit_menu(app_menu_t *app) {
    app->menu_active = false;
    go(app, APP_PAGE_HOME);
}

static void toast(app_menu_t *app, uint8_t kind) {
    app->toast = kind;
    app->toast_ms = APP_TOAST_MS;
    app->dirty = true;
}

static app_event_result_t act(app_action_t action, uint16_t amount) {
    app_event_result_t result = {action, amount, false};
    return result;
}

static app_event_result_t knob_press(app_menu_t *app) {
    switch (app->knob_mode) {
        case APP_KNOB_VOLUME: toast(app, T_MUTE); return act(APP_ACTION_MUTE_TOGGLE, 1);
        case APP_KNOB_MEDIA: toast(app, T_PLAY); return act(APP_ACTION_MEDIA_PLAY, 1);
        case APP_KNOB_LIGHT: toast(app, T_LIGHT_TOGGLE); return act(APP_ACTION_RGB_TOGGLE, 1);
        case APP_KNOB_ZOOM: toast(app, T_ZOOM_RESET); return act(APP_ACTION_ZOOM_RESET, 1);
        default: toast(app, T_NO_ACTION); return act(APP_ACTION_NONE, 0);
    }
}

static app_event_result_t knob_turn(app_menu_t *app, int32_t delta) {
    const bool up = delta > 0;
    const uint16_t amount = (uint16_t)(up ? delta : -delta);
    switch (app->knob_mode) {
        case APP_KNOB_MEDIA:
            toast(app, up ? T_NEXT : T_PREV);
            return act(up ? APP_ACTION_MEDIA_NEXT : APP_ACTION_MEDIA_PREV, amount);
        case APP_KNOB_BRIGHTNESS:
            toast(app, up ? T_BRIGHT_UP : T_BRIGHT_DOWN);
            return act(up ? APP_ACTION_BRIGHT_UP : APP_ACTION_BRIGHT_DOWN, amount);
        case APP_KNOB_LIGHT:
            toast(app, T_LIGHT_VAL);
            return act(up ? APP_ACTION_RGB_VAL_UP : APP_ACTION_RGB_VAL_DOWN, amount);
        case APP_KNOB_ZOOM:
            toast(app, up ? T_ZOOM_IN : T_ZOOM_OUT);
            return act(up ? APP_ACTION_ZOOM_IN : APP_ACTION_ZOOM_OUT, amount);
        default:
            toast(app, up ? T_VOL_UP : T_VOL_DOWN);
            return act(up ? APP_ACTION_VOLUME_UP : APP_ACTION_VOLUME_DOWN, amount);
    }
}

static uint8_t step_choice(uint8_t current, int32_t delta) {
    int index = 0;
    for (int i = 0; i < 5; i++) if (sleep_choices[i] <= current) index = i;
    index = (index + (delta > 0 ? 1 : 4)) % 5;
    return sleep_choices[index];
}

/* A value row changed by rotation while editing. */
static app_event_result_t edit_value(app_menu_t *app, int32_t delta) {
    const bool up = delta > 0;
    const uint16_t amount = (uint16_t)(up ? delta : -delta);
    app->dirty = true;
    if (app->page == APP_PAGE_LIGHT) {
        switch (app->focus) {
            case 2: return act(up ? APP_ACTION_RGB_NEXT : APP_ACTION_RGB_PREV, amount);
            case 3: return act(up ? APP_ACTION_RGB_VAL_UP : APP_ACTION_RGB_VAL_DOWN, amount);
            case 4: return act(up ? APP_ACTION_RGB_HUE_UP : APP_ACTION_RGB_HUE_DOWN, amount);
            case 5: return act(up ? APP_ACTION_RGB_SAT_UP : APP_ACTION_RGB_SAT_DOWN, amount);
            case 6: return act(up ? APP_ACTION_RGB_SPEED_UP : APP_ACTION_RGB_SPEED_DOWN, amount);
            default: break;
        }
    } else if (app->page == APP_PAGE_DISPLAY) {
        if (app->focus == 1) app->device.sleep_minutes = step_choice(app->device.sleep_minutes, delta);
        else if (app->focus == 2) app->face = (uint8_t)((app->face + 1u) % APP_FACE_COUNT);
    }
    return act(APP_ACTION_NONE, 0);
}

/* Press on a list row: toggles and actions fire, value rows enter/leave edit. */
static app_event_result_t activate_row(app_menu_t *app) {
    app->dirty = true;
    if (app->editing) { app->editing = false; return act(APP_ACTION_NONE, 0); }
    switch (app->page) {
        case APP_PAGE_LIGHT:
            if (!app->rgb.available) return act(APP_ACTION_NONE, 0);
            if (app->focus == 1) return act(APP_ACTION_RGB_TOGGLE, 1);
            app->editing = true;
            break;
        case APP_PAGE_KNOB:
            app->knob_mode = (uint8_t)(app->focus - 1u);
            break;
        case APP_PAGE_LINK: {
            /* Rows: 1 USB, 2..4 Bluetooth 1..3, 5 2.4 GHz, 6 Mac/Windows, 7 pair.
             * Choosing the route already in use does nothing; pairing needs BT. */
            const app_device_snapshot_t *d = &app->device;
            if (app->focus == 1 && d->route != 0) return act(APP_ACTION_ROUTE_USB, 1);
            if (app->focus >= 2 && app->focus <= 4 && (d->route != 1 || d->slot != app->focus - 1u))
                return act(APP_ACTION_ROUTE_BT, (uint16_t)(app->focus - 1u));
            if (app->focus == 5 && d->route != 2) return act(APP_ACTION_ROUTE_24G, 1);
            if (app->focus == 6) return act(d->os == APP_OS_MAC ? APP_ACTION_OS_WINDOWS : APP_ACTION_OS_MAC, 1);
            if (app->focus == 7 && d->route == 1) return act(APP_ACTION_PAIR, 1);
            break;
        }
        case APP_PAGE_DISPLAY:
            if (app->focus == 3) {
                if (app->device.media_available) return act(APP_ACTION_MEDIA_SHOW_TOGGLE, 1);
            } else if (app->focus == 4) {
                exit_menu(app);
                return act(APP_ACTION_SCREEN_OFF, 1);
            } else {
                app->editing = true;
            }
            break;
        default:
            break;
    }
    return act(APP_ACTION_NONE, 0);
}

app_event_result_t app_menu_handle(app_menu_t *app, app_event_t event) {
    app_event_result_t result = act(APP_ACTION_NONE, 0);
    if (app == NULL) return result;
    switch (event.type) {
        case APP_EVENT_FN_CHANGED:
            app->fn_held = event.data.fn_held;
            break;
        case APP_EVENT_TICK: {
            const uint32_t elapsed = event.data.elapsed_ms, previous = app->uptime_ms;
            app->uptime_ms = saturated_add(app->uptime_ms, elapsed);
            if (app->page == APP_PAGE_BOOT) {
                const uint32_t before = app->boot_elapsed_ms;
                app->boot_elapsed_ms = saturated_add(before, elapsed);
                if (app->boot_elapsed_ms >= APP_BOOT_DURATION_MS) {
                    app->boot_elapsed_ms = APP_BOOT_DURATION_MS;
                    app->page = APP_PAGE_HOME;
                }
                if (before != app->boot_elapsed_ms) app->dirty = true;
                break;
            }
            if (app->toast) {
                if (elapsed >= app->toast_ms) { app->toast = T_NONE; app->toast_ms = 0; app->dirty = true; }
                else app->toast_ms = (uint16_t)(app->toast_ms - elapsed);
            }
            if (app->menu_active) {
                app->menu_idle_ms = saturated_add(app->menu_idle_ms, elapsed);
                if (app->menu_idle_ms >= APP_MENU_TIMEOUT_MS) exit_menu(app);
            }
            /* Calendar maths costs software divisions on the M0: poll it four
             * times a second, not on every pass of the main loop. */
            (void)previous;
            if (app->uptime_ms - app->check_ms < APP_CLOCK_POLL_MS) break;
            app->check_ms = app->uptime_ms;
            const uint16_t minute = clock_minute(app);
            const uint16_t up_minute = (uint16_t)(app->uptime_ms / 60000u);
            if (minute != app->clock_minute) {
                app->clock_minute = minute;
                app->dirty = true;
            }
            if (up_minute != app->uptime_minute) {
                app->uptime_minute = up_minute;
                if (app->page == APP_PAGE_DEVICE) app->dirty = true;
            }
            break;
        }
        case APP_EVENT_KNOB_PRESS:
            if (app->page == APP_PAGE_BOOT) break;
            app->menu_idle_ms = 0;
            if (app->fn_held) {
                if (app->menu_active) exit_menu(app);
                else enter_menu(app);
            } else if (!app->menu_active) {
                result = knob_press(app);
            } else if (app->page == APP_PAGE_MENU) {
                if (items[app->selected].page == APP_PAGE_HOME) exit_menu(app);
                else go(app, items[app->selected].page);
            } else if (list_page(app->page) && app->focus > 0) {
                result = activate_row(app);
            } else {
                go(app, APP_PAGE_MENU);
            }
            break;
        case APP_EVENT_ROTATE: {
            const int32_t delta = event.data.rotation;
            if (delta == 0 || app->page == APP_PAGE_BOOT) break;
            app->menu_idle_ms = 0;
            if (!app->menu_active) {
                if (app->fn_held) {
                    app->face = (uint8_t)((app->face + (delta > 0 ? 1u : APP_FACE_COUNT - 1u)) % APP_FACE_COUNT);
                    toast(app, T_FACE);
                } else {
                    result = knob_turn(app, delta);
                }
            } else if (app->page == APP_PAGE_MENU) {
                int32_t selected = ((int32_t)app->selected + delta) % (int32_t)APP_MENU_ITEM_COUNT;
                if (selected < 0) selected += APP_MENU_ITEM_COUNT;
                if ((uint8_t)selected != app->selected) { app->selected = (uint8_t)selected; app->dirty = true; }
            } else if (list_page(app->page)) {
                if (app->editing) {
                    result = edit_value(app, delta);
                } else {
                    int32_t focus = (int32_t)app->focus + delta; /* fast spins skip rows, as in the menu */
                    const int32_t last = app_menu_row_count(app->page) - 1;
                    focus = focus < 0 ? 0 : focus > last ? last : focus;
                    if ((uint8_t)focus != app->focus) { app->focus = (uint8_t)focus; app->dirty = true; }
                }
            } else if (app->page == APP_PAGE_CODEX || app->page == APP_PAGE_CLAUDE) {
                /* The two quota pages flip like cards. */
                const app_page_t next = app->page == APP_PAGE_CODEX ? APP_PAGE_CLAUDE : APP_PAGE_CODEX;
                app->selected = next == APP_PAGE_CODEX ? 1u : 2u;
                go(app, next);
            }
            break;
        }
        case APP_EVENT_BACK:
            if (!app->menu_active) break;
            app->menu_idle_ms = 0;
            if (app->editing) { app->editing = false; app->dirty = true; }
            else if (app->page == APP_PAGE_MENU) exit_menu(app);
            else go(app, APP_PAGE_MENU);
            break;
        default:
            break;
    }
    result.redraw = app->dirty;
    return result;
}

/* --------------------------------------------------------------- drawing */

static void rect(app_menu_t *app, int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t c) {
    if (w && h && app->renderer.rect) app->renderer.rect(app->renderer_user, x, y, w, h, c);
}
static void rrect(app_menu_t *app, int16_t x, int16_t y, uint16_t w, uint16_t h, uint8_t r, uint16_t c) {
    if (!w || !h) return;
    if (app->renderer.rrect) app->renderer.rrect(app->renderer_user, x, y, w, h, r, c);
    else rect(app, x, y, w, h, c);
}
static void ring(app_menu_t *app, int16_t x, int16_t y, uint8_t d, uint8_t t, uint16_t permille, uint16_t c) {
    if (permille && app->renderer.ring) app->renderer.ring(app->renderer_user, x, y, d, t, permille, c);
}
static void icon(app_menu_t *app, uint8_t id, int16_t x, int16_t y, uint8_t size, uint16_t c) {
    if (app->renderer.icon) app->renderer.icon(app->renderer_user, x, y, id, size, c);
}
static void text(app_menu_t *app, int16_t x, int16_t y, const char *s, uint16_t c, uint8_t font) {
    if (app->renderer.text) app->renderer.text(app->renderer_user, x, y, s, c, font);
}
static int16_t width(const char *s, uint8_t font) { return (int16_t)app_font_width(s, font); }
static void right(app_menu_t *app, int16_t x, int16_t y, const char *s, uint16_t c, uint8_t font) {
    text(app, (int16_t)(x - width(s, font)), y, s, c, font);
}
static void center(app_menu_t *app, int16_t cx, int16_t y, const char *s, uint16_t c, uint8_t font) {
    text(app, (int16_t)(cx - width(s, font) / 2), y, s, c, font);
}
/* y of a text box whose capitals/digits are centred on cy. */
static int16_t cap_y(int16_t cy, uint8_t font) {
    return (int16_t)(cy - (app_font_cap_top(font) + app_font_cap_bottom(font) + 1) / 2);
}
static void outline(app_menu_t *app, int16_t x, int16_t y, uint16_t w, uint16_t h, uint8_t r, uint16_t stroke, uint16_t fill) {
    rrect(app, x, y, w, h, r, stroke);
    rrect(app, (int16_t)(x + 1), (int16_t)(y + 1), (uint16_t)(w - 2), (uint16_t)(h - 2), (uint8_t)(r ? r - 1 : 0), fill);
}
static void bar(app_menu_t *app, int16_t x, int16_t y, uint16_t w, uint8_t h, uint16_t permille, uint16_t c) {
    rrect(app, x, y, w, h, (uint8_t)(h / 2), TRACK);
    if (permille > 1000u) permille = 1000u;
    uint16_t fill = (uint16_t)((w * permille + 500u) / 1000u);
    if (permille && fill < h) fill = h;
    rrect(app, x, y, fill, h, (uint8_t)(h / 2), c);
}
static void toggle(app_menu_t *app, int16_t x, int16_t y, bool on, uint16_t accent) {
    rrect(app, x, y, 22, 12, 6, on ? accent : TRACK);
    rrect(app, (int16_t)(on ? x + 12 : x + 2), (int16_t)(y + 2), 8, 8, 4, on ? BG : MUTED);
}
static uint16_t hsv(uint8_t hue, uint8_t sat, uint8_t val) {
    const uint8_t region = hue / 43, rem = (uint8_t)((hue - region * 43) * 6);
    const uint8_t p = (uint8_t)((val * (255u - sat)) >> 8);
    const uint8_t q = (uint8_t)((val * (255u - ((sat * rem) >> 8))) >> 8);
    const uint8_t t = (uint8_t)((val * (255u - ((sat * (255u - rem)) >> 8))) >> 8);
    switch (region) {
        case 0: return app_rgb565(val, t, p);
        case 1: return app_rgb565(q, val, p);
        case 2: return app_rgb565(p, val, t);
        case 3: return app_rgb565(p, q, val);
        case 4: return app_rgb565(t, p, val);
        default: return app_rgb565(val, p, q);
    }
}

/* ------------------------------------------------------------ formatting */

static bool fresh(const app_menu_t *app, const app_usage_snapshot_t *s) {
    return app->host_link == APP_LINK_LIVE && s->age_seconds < APP_USAGE_FRESH_SECONDS;
}
static bool has_data(const app_usage_snapshot_t *s) { return s->weekly_available || s->short_available; }

/* compact: fits the 34 px under a home ring. */
static void countdown(const app_menu_t *app, uint32_t reset, char *b, size_t size, bool compact) {
    const uint32_t now = app_menu_now_epoch(app);
    if (!reset || !now) { (void)snprintf(b, size, compact ? "—" : "Yenilenme bilinmiyor"); return; }
    if (reset <= now) { (void)snprintf(b, size, compact ? "Şimdi" : "Yenileniyor"); return; }
    const uint32_t delta = reset - now, minutes = delta / 60u + (delta % 60u != 0u);
    if (minutes / 1440u > 99u) (void)snprintf(b, size, "99g+");
    else if (minutes >= 1440u) (void)snprintf(b, size, "%lug %lusa", (unsigned long)(minutes / 1440u), (unsigned long)((minutes % 1440u) / 60u));
    else if (minutes >= 60u) (void)snprintf(b, size, "%lusa %ludk", (unsigned long)(minutes / 60u), (unsigned long)(minutes % 60u));
    else (void)snprintf(b, size, "%ludk", (unsigned long)minutes);
}

static void age_label(uint32_t age, char *b, size_t size) {
    if (age == UINT32_MAX) (void)snprintf(b, size, "Eski veri");
    else if (age < 60u) (void)snprintf(b, size, "Az önce");
    else if (age < 3600u) (void)snprintf(b, size, "%lu dk önce", (unsigned long)(age / 60u));
    else if (age < 86400u) (void)snprintf(b, size, "%lu sa önce", (unsigned long)(age / 3600u));
    else (void)snprintf(b, size, "%lu gün önce", (unsigned long)(age / 86400u));
}

static uint16_t quota_color(uint8_t remaining, uint16_t accent) {
    return remaining <= 10u ? DANGER : remaining <= 25u ? WARN : accent;
}

static const char *route_name(const app_device_snapshot_t *d) {
    return d->route == 0 ? "USB" : d->route == 1 ? "Bluetooth" : d->route == 2 ? "2.4 GHz" : "Bilinmiyor";
}
static uint8_t route_icon(const app_device_snapshot_t *d) {
    return d->route == 1 ? APP_ICON_BT : d->route == 2 ? APP_ICON_RF : APP_ICON_USB;
}

/* ------------------------------------------------------------- components */

static void battery(app_menu_t *app, int16_t x, int16_t y, uint8_t w, uint8_t h, bool dim_fill) {
    const uint8_t value = app->device.battery;
    uint16_t fill = value > 100 ? DIM : value <= 15 ? DANGER : app->device.charging ? OK : TEXT;
    if (dim_fill) fill = mix(fill, BG, 120);
    outline(app, x, y, w, h, 3, MUTED, BG);
    rrect(app, (int16_t)(x + w), (int16_t)(y + h / 3), 2, (uint16_t)(h - 2 * (h / 3)), 1, MUTED);
    if (value <= 100) {
        const uint16_t inner = (uint16_t)(w - 4);
        uint16_t level = (uint16_t)((inner * value + 50u) / 100u);
        if (value && level < 2) level = 2;
        rrect(app, (int16_t)(x + 2), (int16_t)(y + 2), level, (uint16_t)(h - 4), 1, fill);
    }
}

/* Top 16 px: left = clock or Studio link, right = state icons and battery. */
static void status_bar(app_menu_t *app, bool show_clock) {
    char b[12];
    local_time_t t;
    if (show_clock && local_time(app, &t)) {
        (void)snprintf(b, sizeof(b), "%02u:%02u", t.hour, t.minute);
        text(app, 4, 0, b, TEXT, F_TITLE);
        /* Data stopped arriving (cable out, Studio closed): say so up top. */
        if (app->host_link == APP_LINK_STALE || app->host_link == APP_LINK_OFFLINE)
            icon(app, APP_ICON_LINK_OFF, (int16_t)(width(b, F_TITLE) + 7), 2, 12, WARN);
    } else {
        const bool live = app->host_link == APP_LINK_LIVE;
        icon(app, live ? APP_ICON_LINK : APP_ICON_LINK_OFF, 6, 2, 12, live ? OK : DIM);
        text(app, 21, 1, live ? "Studio" : "Studio yok", live ? MUTED : DIM, F_SMALL);
    }
    /* Battery with the percentage inside, like a phone status bar. */
    int16_t x = 99;
    battery(app, x, 2, 24, 12, true);
    if (app->device.battery <= 100) {
        (void)snprintf(b, sizeof(b), "%u", app->device.battery);
        center(app, (int16_t)(x + 12), 2, b, TEXT, F_SMALL);
    }
    if (app->device.charging) {
        x = (int16_t)(x - 10);
        icon(app, APP_ICON_BOLT, x, 3, 9, OK);
    }
    x = (int16_t)(x - 14);
    icon(app, route_icon(&app->device), x, 2, 12, app->device.route > 2 ? DIM : SLATE);
    if (app->device.caps_lock) {
        x = (int16_t)(x - 13);
        icon(app, APP_ICON_CAPS, x, 2, 12, LIME);
    }
    if (app->knob_mode != APP_KNOB_VOLUME) {
        x = (int16_t)(x - 13);
        icon(app, knobs[app->knob_mode].icon, x, 2, 12, VIOLET);
    }
}

/* Big remaining number with a small % sign, centred on cx/cy. */
static void percent_label(app_menu_t *app, int16_t cx, int16_t cy, uint8_t remaining, uint16_t c, uint8_t font) {
    char b[8];
    (void)snprintf(b, sizeof(b), "%u", remaining);
    const int16_t w = (int16_t)(width(b, font) + 1 + width("%", F_SMALL));
    const int16_t x = (int16_t)(cx - w / 2), y = cap_y(cy, font);
    text(app, x, y, b, c, font);
    const int16_t baseline = (int16_t)(y + app_font_baseline(font));
    text(app, (int16_t)(x + width(b, font) + 1), (int16_t)(baseline - app_font_baseline(F_SMALL)), "%", c, F_SMALL);
}

/* The window a ring shows: 5 hours when the source reports it, otherwise the
 * weekly one, so a provider that only reports one window never wastes the ring. */
typedef struct {
    bool available;
    uint8_t remaining;
    uint32_t reset;
    const char *label;
} window_t;

static void windows(const app_usage_snapshot_t *s, window_t *primary, window_t *other) {
    const window_t five = {s->short_available, (uint8_t)(100u - s->short_used_percent), s->short_resets_at, "5 sa"};
    const window_t week = {s->weekly_available, (uint8_t)(100u - s->weekly_used_percent), s->weekly_resets_at, "7 gün"};
    const bool five_first = s->short_available || !s->weekly_available;
    *primary = five_first ? five : week;
    *other = five_first ? week : five;
}

static void ring_tile(app_menu_t *app, int16_t x, const app_usage_snapshot_t *s, const char *name, uint8_t symbol, uint16_t accent) {
    char b[20];
    const int16_t y = 18, w = 60, h = 108;
    const bool live = fresh(app, s), data = has_data(s);
    window_t main, other;
    windows(s, &main, &other);
    rrect(app, x, y, (uint16_t)w, (uint16_t)h, 10, SURFACE);
    /* Stale data swaps the brand symbol for a warning, never silently. */
    if (data && !live) icon(app, APP_ICON_ALERT, (int16_t)(x + 7), (int16_t)(y + 7), 12, WARN);
    else icon(app, symbol, (int16_t)(x + 7), (int16_t)(y + 7), 12, accent);
    text(app, (int16_t)(x + 22), (int16_t)(y + 6), name, TEXT, F_SMALL);

    const int16_t rx = (int16_t)(x + 6), ry = (int16_t)(y + 23), cx = (int16_t)(x + w / 2), cy = (int16_t)(ry + 24);
    ring(app, rx, ry, 48, 5, 1000, TRACK);
    if (main.available) {
        const uint16_t color = live ? quota_color(main.remaining, accent) : mix(accent, SURFACE, 110);
        ring(app, rx, ry, 48, 5, (uint16_t)(main.remaining * 10u), color);
        center(app, cx, cap_y((int16_t)(cy - 10), F_SMALL), main.label, MUTED, F_SMALL);
        percent_label(app, cx, (int16_t)(cy + 4), main.remaining, live ? TEXT : MUTED, F_BIG);
    } else {
        center(app, cx, cap_y(cy, F_BIG), "—", DIM, F_BIG);
    }

    const int16_t row = (int16_t)(y + 76);
    if (!data) {
        center(app, cx, row, "Veri yok", DIM, F_SMALL);
        center(app, cx, (int16_t)(row + 13), "bekleniyor", DIM, F_SMALL);
        return;
    }
    text(app, (int16_t)(x + 7), row, other.label, MUTED, F_SMALL);
    if (other.available) (void)snprintf(b, sizeof(b), "%u%%", other.remaining);
    else (void)snprintf(b, sizeof(b), "—");
    right(app, (int16_t)(x + w - 7), row, b, other.available ? (live ? TEXT : MUTED) : DIM, F_SMALL);
    bar(app, (int16_t)(x + 7), (int16_t)(row + 14), (uint16_t)(w - 14), 4,
        other.available ? (uint16_t)(other.remaining * 10u) : 0u, live ? mix(accent, SURFACE, 200) : DIM);
    if (!live) {
        /* How old the numbers are; they update again over the USB cable. */
        age_label(s->age_seconds, b, sizeof(b));
        center(app, cx, (int16_t)(row + 21), b, WARN, F_SMALL);
        return;
    }
    countdown(app, main.reset, b, sizeof(b), true);
    icon(app, APP_ICON_RESET, (int16_t)(x + 7), (int16_t)(row + 22), 10, DIM);
    text(app, (int16_t)(x + 19), (int16_t)(row + 21), b, MUTED, F_SMALL);
}

static void compact_row(app_menu_t *app, int16_t y, const app_usage_snapshot_t *s, const char *name, uint8_t symbol, uint16_t accent) {
    char b[8];
    const bool live = fresh(app, s);
    window_t main, other;
    windows(s, &main, &other);
    rrect(app, 4, y, 120, 22, 8, SURFACE);
    icon(app, symbol, 10, (int16_t)(y + 5), 12, accent);
    text(app, 27, (int16_t)(y + 4), name, TEXT, F_SMALL);
    if (!main.available) {
        right(app, 117, (int16_t)(y + 4), "Veri yok", DIM, F_SMALL);
        return;
    }
    (void)snprintf(b, sizeof(b), "%u%%", main.remaining);
    const int16_t value_x = (int16_t)(117 - width(b, F_BODY));
    text(app, value_x, (int16_t)(y + 3), b, live ? TEXT : MUTED, F_BODY);
    right(app, (int16_t)(value_x - 4), (int16_t)(y + 4), main.label, DIM, F_SMALL);
    bar(app, 27, (int16_t)(y + 17), 90, 2, (uint16_t)(main.remaining * 10u), live ? quota_color(main.remaining, accent) : DIM);
}

static void draw_toast(app_menu_t *app) {
    char b[24];
    uint8_t symbol = APP_ICON_VOLUME;
    const char *label = b;
    int bar_value = -1;
    switch (app->toast) {
        case T_VOL_UP: label = "Ses +"; break;
        case T_VOL_DOWN: label = "Ses −"; break;
        case T_MUTE: symbol = APP_ICON_MUTE; label = "Sessiz / aç"; break;
        case T_NEXT: symbol = APP_ICON_NEXT; label = "Sonraki parça"; break;
        case T_PREV: symbol = APP_ICON_PREV; label = "Önceki parça"; break;
        case T_PLAY: symbol = APP_ICON_MEDIA; label = "Oynat / duraklat"; break;
        case T_BRIGHT_UP: symbol = APP_ICON_BRIGHT; label = "Parlaklık +"; break;
        case T_BRIGHT_DOWN: symbol = APP_ICON_BRIGHT; label = "Parlaklık −"; break;
        case T_LIGHT_VAL:
            symbol = APP_ICON_LIGHT;
            if (!app->rgb.available) { label = "Işık yok"; break; }
            (void)snprintf(b, sizeof(b), "%u%%", (app->rgb.val * 100u + 127u) / 255u);
            bar_value = app->rgb.val;
            break;
        case T_LIGHT_TOGGLE: symbol = APP_ICON_LIGHT; label = app->rgb.enabled ? "Işık açık" : "Işık kapalı"; break;
        case T_ZOOM_IN: symbol = APP_ICON_ZOOM; label = "Yakınlaştır"; break;
        case T_ZOOM_OUT: symbol = APP_ICON_ZOOM; label = "Uzaklaştır"; break;
        case T_ZOOM_RESET: symbol = APP_ICON_ZOOM; label = "Zoom sıfır"; break;
        case T_FACE: symbol = APP_ICON_FACE; label = app->face == APP_FACE_CLOCK ? "Saat yüzü" : "Halka yüzü"; break;
        default: symbol = knobs[app->knob_mode].icon; label = knobs[app->knob_mode].name; break;
    }
    outline(app, 8, 99, 112, 24, 12, STROKE, SURFACE_HI);
    icon(app, symbol, 17, 103, 16, VIOLET);
    if (bar_value >= 0) {
        bar(app, 40, 109, 50, 4, (uint16_t)((bar_value * 1000 + 127) / 255), AMBER);
        right(app, 113, 104, label, TEXT, F_BODY);
    } else {
        text(app, 39, 104, label, TEXT, F_BODY);
    }
}

/* --------------------------------------------------------------- pages */

static void page_boot(app_menu_t *app) {
    rrect(app, 38, 14, 52, 52, 26, LIME);
    icon(app, APP_ICON_DEVICE, 50, 26, 28, BG);
    center(app, 64, 76, "AK820", TEXT, F_TITLE);
    center(app, 64, 94, "Studio", MUTED, F_SMALL);
    bar(app, 34, 114, 60, 4, (uint16_t)(app->boot_elapsed_ms * 1000u / APP_BOOT_DURATION_MS), LIME);
}

static void page_home(app_menu_t *app) {
    if (app->face == APP_FACE_CLOCK) {
        char b[32];
        static const char *const days[] = {"Pazar", "Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi"};
        static const char *const months[] = {"Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
                                             "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"};
        local_time_t t;
        status_bar(app, false);
        if (local_time(app, &t)) {
            (void)snprintf(b, sizeof(b), "%02u:%02u", t.hour, t.minute);
            center(app, 64, cap_y(40, F_CLOCK), b, TEXT, F_CLOCK);
            (void)snprintf(b, sizeof(b), "%s, %u %s", days[t.weekday], t.day, months[t.month - 1u]);
            center(app, 64, 59, b, MUTED, F_BODY);
        } else {
            center(app, 64, cap_y(40, F_CLOCK), "--:--", DIM, F_CLOCK);
            center(app, 64, 59, "Saat Studio'dan gelir", DIM, F_SMALL);
        }
        compact_row(app, 78, &app->codex, "Codex", APP_ICON_CODEX, CYAN);
        compact_row(app, 103, &app->claude, "Claude", APP_ICON_CLAUDE, CORAL);
    } else {
        status_bar(app, true);
        ring_tile(app, 2, &app->codex, "Codex", APP_ICON_CODEX, CYAN);
        ring_tile(app, 66, &app->claude, "Claude", APP_ICON_CLAUDE, CORAL);
    }
}

static void page_menu(app_menu_t *app) {
    char b[8];
    const item_t *item = &items[app->selected];
    text(app, 7, 3, "Menü", MUTED, F_SMALL);
    (void)snprintf(b, sizeof(b), "%u/%u", app->selected + 1u, APP_MENU_ITEM_COUNT);
    right(app, 121, 3, b, DIM, F_SMALL);
    for (int8_t side = -1; side <= 1; side += 2) {
        const item_t *n = &items[(app->selected + APP_MENU_ITEM_COUNT + side) % APP_MENU_ITEM_COUNT];
        const int16_t cx = (int16_t)(64 + side * 50);
        rrect(app, (int16_t)(cx - 16), 29, 32, 32, 16, SURFACE_HI);
        icon(app, n->icon, (int16_t)(cx - 8), 37, 16, mix(n->color, SURFACE_HI, 150));
    }
    rrect(app, 37, 18, 54, 54, 27, item->color);
    icon(app, item->icon, 50, 31, 28, BG);
    center(app, 64, 78, item->name, TEXT, F_TITLE);
    center(app, 64, 96, item->hint, MUTED, F_SMALL);
    const int16_t total = (int16_t)((APP_MENU_ITEM_COUNT - 1) * 9 + 14), start = (int16_t)(64 - total / 2);
    int16_t x = start;
    for (uint8_t i = 0; i < APP_MENU_ITEM_COUNT; i++) {
        if (i == app->selected) { rrect(app, x, 117, 14, 5, 3, item->color); x = (int16_t)(x + 18); }
        else { rrect(app, x, 117, 5, 5, 3, STROKE); x = (int16_t)(x + 9); }
    }
}

/* Header row with back affordance; focused when app->focus == 0. */
static void header(app_menu_t *app, const item_t *item, bool focusable) {
    const bool focused = focusable && app->focus == 0 && list_page(app->page);
    if (focused) rrect(app, 2, 1, 124, 20, 8, SURFACE_HI);
    icon(app, APP_ICON_BACK, 4, 5, 12, focused ? TEXT : DIM);
    icon(app, item->icon, 17, 3, 16, item->color);
    text(app, 37, 2, item->title, TEXT, F_TITLE);
}

static const item_t *item_for(app_page_t page) {
    for (uint8_t i = 0; i < APP_MENU_ITEM_COUNT; i++) if (items[i].page == page) return &items[i];
    return &items[0];
}

static void chip(app_menu_t *app, int16_t right_x, int16_t y, const char *s, uint16_t c) {
    const int16_t w = (int16_t)(width(s, F_SMALL) + 10);
    rrect(app, (int16_t)(right_x - w), y, (uint16_t)w, 14, 7, mix(c, BG, 50));
    text(app, (int16_t)(right_x - w + 5), (int16_t)(y + 1), s, c, F_SMALL);
}

static void usage_section(app_menu_t *app, int16_t y, const char *label, bool available, uint8_t used, uint32_t reset, uint16_t accent, bool live) {
    char b[24];
    rrect(app, 4, y, 120, 47, 10, SURFACE);
    text(app, 12, (int16_t)(y + 5), label, MUTED, F_SMALL);
    if (available) {
        const uint8_t remaining = (uint8_t)(100u - used);
        const uint16_t color = live ? quota_color(remaining, accent) : MUTED;
        (void)snprintf(b, sizeof(b), "%u%%", remaining);
        right(app, 117, (int16_t)(y + 2), b, color, F_BIG);
        countdown(app, reset, b, sizeof(b), false);
        icon(app, APP_ICON_RESET, 12, (int16_t)(y + 20), 10, DIM);
        text(app, 24, (int16_t)(y + 19), b, TEXT, F_SMALL);
        bar(app, 12, (int16_t)(y + 35), 104, 5, (uint16_t)(remaining * 10u), live ? color : DIM);
    } else {
        right(app, 117, (int16_t)(y + 2), "—", DIM, F_BIG);
        text(app, 12, (int16_t)(y + 19), "Veri yok", DIM, F_SMALL);
        bar(app, 12, (int16_t)(y + 35), 104, 5, 0, DIM);
    }
}

static void page_usage(app_menu_t *app, const app_usage_snapshot_t *s, const item_t *item) {
    header(app, item, false);
    if (!has_data(s)) chip(app, 124, 4, "Veri yok", DIM);
    else if (app->host_link != APP_LINK_LIVE) chip(app, 124, 4, "Bağsız", WARN);
    else if (s->age_seconds >= APP_USAGE_FRESH_SECONDS) chip(app, 124, 4, "Eski", WARN);
    else chip(app, 124, 4, "Canlı", OK);
    const bool live = fresh(app, s);
    usage_section(app, 25, "5 saatlik", s->short_available, s->short_used_percent, s->short_resets_at, item->color, live);
    usage_section(app, 77, "Haftalık", s->weekly_available, s->weekly_used_percent, s->weekly_resets_at, item->color, live);
}

/* One list row; returns the x where a right-aligned value should end. */
/* Six rows fit under the header; longer lists scroll to keep focus visible. */
#define LIST_ROWS 6
static int list_scroll(const app_menu_t *app) { return app->focus > LIST_ROWS ? app->focus - LIST_ROWS : 0; }

/* Draws one list row; false (and nothing drawn) when scrolled out of view. */
static bool row_frame(app_menu_t *app, uint8_t index, uint8_t symbol, const char *label, uint16_t accent, int16_t *y_out) {
    const int slot = index - 1 - list_scroll(app);
    if (slot < 0 || slot >= LIST_ROWS) return false;
    const int16_t y = (int16_t)(23 + slot * 17);
    const bool focused = app->focus == index, editing = focused && app->editing;
    if (editing) outline(app, 2, y, 124, 16, 7, accent, mix(accent, BG, 40));
    else if (focused) rrect(app, 2, y, 124, 16, 7, SURFACE_HI);
    icon(app, symbol, 7, y, 16, focused ? accent : MUTED);
    text(app, 28, (int16_t)(y + 1), label, focused ? TEXT : SLATE, F_BODY);
    *y_out = y;
    return true;
}

static void scrollbar(app_menu_t *app) {
    const int rows = app_menu_row_count(app->page) - 1;
    if (rows <= LIST_ROWS) return;
    const int16_t track = LIST_ROWS * 17 - 1, thumb = (int16_t)(track * LIST_ROWS / rows);
    rrect(app, 125, 23, 2, (uint16_t)track, 1, TRACK);
    rrect(app, 125, (int16_t)(23 + (track - thumb) * list_scroll(app) / (rows - LIST_ROWS)), 2, (uint16_t)thumb, 1, MUTED);
}

static void value_bar(app_menu_t *app, uint8_t index, uint8_t value, uint16_t accent) {
    const int16_t y = (int16_t)(23 + (index - 1) * 17);
    const bool editing = app->focus == index && app->editing;
    bar(app, 90, (int16_t)(y + 6), 30, 4, (uint16_t)((value * 1000u + 127u) / 255u), editing ? accent : mix(accent, BG, 170));
}

static void page_light(app_menu_t *app) {
    const item_t *item = item_for(APP_PAGE_LIGHT);
    const app_rgb_snapshot_t *rgb = &app->rgb;
    int16_t y;
    header(app, item, true);
    if (!rgb->available) {
        center(app, 64, 56, "RGB bilgisi yok", DIM, F_BODY);
        return;
    }
    chip(app, 124, 4, rgb->enabled ? "Açık" : "Kapalı", rgb->enabled ? AMBER : DIM);
    row_frame(app, 1, APP_ICON_POWER, "Işık", AMBER, &y);
    toggle(app, 98, (int16_t)(y + 2), rgb->enabled, AMBER);
    row_frame(app, 2, APP_ICON_EFFECT, "Efekt", AMBER, &y);
    right(app, 120, (int16_t)(y + 2), effects[rgb->effect], app->focus == 2 && app->editing ? AMBER : MUTED, F_SMALL);
    row_frame(app, 3, APP_ICON_BRIGHT, "Parlaklık", AMBER, &y);
    value_bar(app, 3, rgb->val, AMBER);
    row_frame(app, 4, APP_ICON_PALETTE, "Renk", AMBER, &y);
    for (uint8_t i = 0; i < 30; i++) rect(app, (int16_t)(90 + i), (int16_t)(y + 6), 1, 4, hsv((uint8_t)(i * 255u / 29u), 255, 255));
    {
        const int16_t mx = (int16_t)(90 + rgb->hue * 29u / 255u);
        rrect(app, (int16_t)(mx - 2), (int16_t)(y + 3), 5, 10, 2, TEXT);
        rect(app, (int16_t)mx, (int16_t)(y + 5), 1, 6, hsv(rgb->hue, 255, 255));
    }
    row_frame(app, 5, APP_ICON_SAT, "Doygunluk", AMBER, &y);
    value_bar(app, 5, rgb->sat, AMBER);
    row_frame(app, 6, APP_ICON_SPEED, "Hız", AMBER, &y);
    value_bar(app, 6, rgb->speed, AMBER);
}

static void page_knob(app_menu_t *app) {
    const item_t *item = item_for(APP_PAGE_KNOB);
    int16_t y;
    header(app, item, true);
    for (uint8_t i = 0; i < APP_KNOB_COUNT; i++) {
        row_frame(app, (uint8_t)(i + 1), knobs[i].icon, knobs[i].name, VIOLET, &y);
        if (app->knob_mode == i) icon(app, APP_ICON_CHECK, 106, y, 16, VIOLET);
    }
    const uint8_t focus = app->focus ? (uint8_t)(app->focus - 1u) : app->knob_mode;
    center(app, 64, 113, knobs[focus].hint, MUTED, F_SMALL);
}

static void page_display(app_menu_t *app) {
    const item_t *item = item_for(APP_PAGE_DISPLAY);
    char b[16];
    int16_t y;
    const int16_t x = 120;
    header(app, item, true);
    row_frame(app, 1, APP_ICON_SLEEP, "Uyku", SKY, &y);
    if (app->device.sleep_minutes) (void)snprintf(b, sizeof(b), "%u dk", app->device.sleep_minutes);
    else (void)snprintf(b, sizeof(b), "Kapalı");
    right(app, x, (int16_t)(y + 1), b, app->focus == 1 && app->editing ? SKY : MUTED, F_BODY);
    row_frame(app, 2, APP_ICON_FACE, "Ana yüz", SKY, &y);
    right(app, x, (int16_t)(y + 1), app->face == APP_FACE_CLOCK ? "Saat" : "Halkalar", app->focus == 2 && app->editing ? SKY : MUTED, F_BODY);
    row_frame(app, 3, APP_ICON_IMAGE, "Görsel", SKY, &y);
    if (app->device.media_available) toggle(app, 98, (int16_t)(y + 2), app->device.media_show, SKY);
    else right(app, x, (int16_t)(y + 1), "Yüklü değil", DIM, F_SMALL);
    row_frame(app, 4, APP_ICON_POWER, "Ekranı kapat", SKY, &y);
    icon(app, APP_ICON_CHEVRON, 108, (int16_t)(y + 2), 12, DIM);
    center(app, 64, 100, app->focus == 4 ? "Fn + Home ile geri açılır" : "Ayarlar bu oturum için", DIM, F_SMALL);
}

static void page_link(app_menu_t *app) {
    static const char *const states[] = {"Bekliyor", "Bağlanıyor", "Eşleşmede", "Bağlı", "Reddedildi"};
    const item_t *item = item_for(APP_PAGE_LINK);
    const app_device_snapshot_t *d = &app->device;
    char b[16];
    int16_t y;
    header(app, item, true);
    if (d->route == 1) (void)snprintf(b, sizeof(b), "BT %u", d->slot);
    else (void)snprintf(b, sizeof(b), "%s", d->route == 0 ? "USB" : d->route == 2 ? "2.4G" : "?");
    chip(app, 124, 4, b, ORANGE);
    for (uint8_t row = 1; row <= 5; row++) {
        const bool bt = row >= 2 && row <= 4;
        const bool active = row == 1 ? d->route == 0 : bt ? d->route == 1 && d->slot == row - 1u : d->route == 2;
        if (bt) (void)snprintf(b, sizeof(b), "Bluetooth %u", row - 1u);
        if (!row_frame(app, row, row == 1 ? APP_ICON_USB : bt ? APP_ICON_BT : APP_ICON_RF,
                       row == 1 ? "USB kablo" : bt ? b : "2.4 GHz", ORANGE, &y) || !active) continue;
        if (row == 1) icon(app, APP_ICON_CHECK, 106, y, 16, ORANGE);
        else right(app, 121, (int16_t)(y + 2), d->radio_state <= 4 ? states[d->radio_state] : "?",
                   d->radio_state == 3 ? OK : d->radio_state == 4 ? DANGER : ORANGE, F_SMALL);
    }
    /* Key layout of the computer on this route; the Mac/Win switch still wins. */
    if (row_frame(app, 6, d->os == APP_OS_WINDOWS ? APP_ICON_WINDOWS : APP_ICON_APPLE, "Sistem", ORANGE, &y))
        right(app, 121, (int16_t)(y + 1), d->os == APP_OS_MAC ? "macOS" : d->os == APP_OS_WINDOWS ? "Windows" : "—", MUTED, F_BODY);
    if (row_frame(app, 7, APP_ICON_PAIR, "Eşleştir", ORANGE, &y))
        right(app, 121, (int16_t)(y + 2), d->route == 1 ? "Yeni cihaz" : "Önce BT", d->route == 1 ? MUTED : DIM, F_SMALL);
    scrollbar(app);
}

static void info_row(app_menu_t *app, int16_t y, uint8_t symbol, const char *label, const char *value, uint16_t value_color) {
    icon(app, symbol, 8, y, 16, MUTED);
    text(app, 29, (int16_t)(y + 1), label, SLATE, F_BODY);
    right(app, 121, (int16_t)(y + 1), value, value_color, F_BODY);
}

static void page_device(app_menu_t *app) {
    char b[24];
    const app_device_snapshot_t *d = &app->device;
    header(app, item_for(APP_PAGE_DEVICE), false);
    rrect(app, 4, 24, 120, 38, 10, SURFACE);
    battery(app, 12, 33, 34, 19, false);
    if (d->battery <= 100) {
        (void)snprintf(b, sizeof(b), "%u%%", d->battery);
        text(app, 56, 23, b, TEXT, F_BIG);
    } else {
        text(app, 56, 23, "—", DIM, F_BIG);
    }
    if (d->charging) icon(app, APP_ICON_BOLT, 56, 46, 12, OK);
    text(app, d->charging ? 69 : 56, 45, d->charging ? "Şarj oluyor" : d->usb_active ? "USB güçte" : "Pilde", MUTED, F_SMALL);
    if (d->route == 1) (void)snprintf(b, sizeof(b), "BT %u", d->slot <= 3 ? d->slot : 0);
    else (void)snprintf(b, sizeof(b), "%s", route_name(d));
    info_row(app, 66, route_icon(d), "Bağlantı", b, TEXT);
    info_row(app, 81, d->os == APP_OS_WINDOWS ? APP_ICON_WINDOWS : APP_ICON_APPLE, "Sistem",
             d->os == APP_OS_MAC ? "macOS" : d->os == APP_OS_WINDOWS ? "Windows" : "—", TEXT);
    /* Studio talks over the USB cable only; name the likely cause. */
    info_row(app, 96, app->host_link == APP_LINK_LIVE ? APP_ICON_LINK : APP_ICON_LINK_OFF, "Studio",
             app->host_link == APP_LINK_LIVE ? "Canlı" : !d->usb_active ? "Kablo yok" :
             app->host_link == APP_LINK_STALE ? "Gecikmeli" : "Bağlı değil",
             app->host_link == APP_LINK_LIVE ? OK : app->host_link == APP_LINK_STALE || !d->usb_active ? WARN : DIM);
    const uint32_t minutes = app->uptime_ms / 60000u;
    if (minutes >= 60u) (void)snprintf(b, sizeof(b), "%lu sa %lu dk", (unsigned long)(minutes / 60u), (unsigned long)(minutes % 60u));
    else (void)snprintf(b, sizeof(b), "%lu dk", (unsigned long)minutes);
    info_row(app, 111, APP_ICON_CLOCK, "Açık", b, TEXT);
}

static int16_t keycap(app_menu_t *app, int16_t x, int16_t y, const char *label, uint8_t symbol) {
    const int16_t w = (int16_t)(label ? width(label, F_SMALL) + 8 : 16);
    rrect(app, x, y, (uint16_t)w, 14, 4, STROKE);
    rrect(app, x, y, (uint16_t)w, 12, 4, SURFACE_HI);
    if (label) text(app, (int16_t)(x + 4), y, label, TEXT, F_SMALL);
    else icon(app, symbol, (int16_t)(x + 2), y, 12, TEXT);
    return (int16_t)(x + w);
}

static void shortcut(app_menu_t *app, int16_t y, const char *a, const char *b, uint8_t symbol, const char *what) {
    int16_t x = 6;
    if (a) {
        x = keycap(app, x, y, a, 0);
        text(app, (int16_t)(x + 2), y, "+", DIM, F_SMALL);
        x = (int16_t)(x + 9);
    }
    keycap(app, x, y, b, symbol);
    right(app, 122, (int16_t)(y + 1), what, SLATE, F_SMALL);
}

static void page_shortcuts(app_menu_t *app) {
    header(app, item_for(APP_PAGE_SHORTCUTS), false);
    shortcut(app, 25, "Fn", NULL, APP_ICON_KNOB, "Menü");
    shortcut(app, 42, NULL, NULL, APP_ICON_KNOB, "Düğme modu");
    shortcut(app, 59, "Fn", "çevir", 0, "Ana yüz");
    shortcut(app, 76, "Fn", "Home", 0, "Ekran");
    shortcut(app, 93, "Fn", "Del", 0, "Görsel");
    shortcut(app, 110, "Fn", "Q W E", 0, "Bluetooth");
}

void app_menu_render(app_menu_t *app) {
    if (!app) return;
    if (app->renderer.clear) app->renderer.clear(app->renderer_user, BG);
    switch (app->page) {
        case APP_PAGE_BOOT: page_boot(app); break;
        case APP_PAGE_HOME: page_home(app); break;
        case APP_PAGE_MENU: page_menu(app); break;
        case APP_PAGE_CODEX: page_usage(app, &app->codex, item_for(APP_PAGE_CODEX)); break;
        case APP_PAGE_CLAUDE: page_usage(app, &app->claude, item_for(APP_PAGE_CLAUDE)); break;
        case APP_PAGE_LIGHT: page_light(app); break;
        case APP_PAGE_KNOB: page_knob(app); break;
        case APP_PAGE_DISPLAY: page_display(app); break;
        case APP_PAGE_DEVICE: page_device(app); break;
        case APP_PAGE_SHORTCUTS: page_shortcuts(app); break;
        case APP_PAGE_LINK: page_link(app); break;
        default: break;
    }
    if (app->toast && !app->menu_active && app->page == APP_PAGE_HOME) draw_toast(app);
    app->dirty = false;
}
