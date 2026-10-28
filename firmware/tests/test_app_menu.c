#include "app_menu.h"
#include "app_font.h"
#include "app_icons.h"

#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned assertions;
#define CHECK(condition) do { \
    ++assertions; \
    if (!(condition)) { \
        fprintf(stderr, "FAIL %s:%d: %s\n", __FILE__, __LINE__, #condition); \
        exit(EXIT_FAILURE); \
    } \
} while (0)

#define NOW 1791736920u /* 2026-10-11 19:42 +03:00, a Sunday */

typedef struct {
    unsigned clears, shapes, strings, icons;
    char seen[2048]; /* every string drawn this frame, '|' separated */
} recorder_t;

static recorder_t *current;

static bool seen(const recorder_t *r, const char *s) {
    char needle[96];
    (void)snprintf(needle, sizeof(needle), "|%s|", s);
    return strstr(r->seen, needle) != NULL;
}

static void on_screen(int x, int y, unsigned w, unsigned h) {
    /* Shapes may run off an edge (menu carousel), never be entirely outside. */
    CHECK(w > 0 && h > 0);
    CHECK(x < (int)APP_SCREEN_WIDTH && y < (int)APP_SCREEN_HEIGHT);
    CHECK(x + (int)w > 0 && y + (int)h > 0);
}

static void record_clear(void *user, uint16_t color) {
    recorder_t *r = user;
    (void)color;
    r->clears++;
    r->seen[0] = '|';
    r->seen[1] = '\0';
}
static void record_rect(void *user, int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t c) {
    (void)c; on_screen(x, y, w, h); ((recorder_t *)user)->shapes++;
}
static void record_rrect(void *user, int16_t x, int16_t y, uint16_t w, uint16_t h, uint8_t radius, uint16_t c) {
    (void)c; (void)radius; on_screen(x, y, w, h); ((recorder_t *)user)->shapes++;
}
static void record_ring(void *user, int16_t x, int16_t y, uint8_t d, uint8_t t, uint16_t permille, uint16_t c) {
    (void)c;
    CHECK(t * 2u <= d && permille > 0u && permille <= 1000u);
    CHECK(x >= 0 && y >= 0 && x + d <= (int)APP_SCREEN_WIDTH && y + d <= (int)APP_SCREEN_HEIGHT);
    ((recorder_t *)user)->shapes++;
}
static void record_icon(void *user, int16_t x, int16_t y, uint8_t id, uint8_t size, uint16_t c) {
    (void)c;
    CHECK(id < APP_ICON_COUNT);
    CHECK(app_icon_find(id, size) != NULL); /* every drawn icon/size pair exists */
    on_screen(x, y, size, size);
    ((recorder_t *)user)->icons++;
}
static void record_text(void *user, int16_t x, int16_t y, const char *value, uint16_t c, uint8_t font) {
    recorder_t *r = user;
    (void)c;
    CHECK(value != NULL && font < APP_FONT_COUNT);
    /* Text is never clipped: a cut-off word is a layout bug. */
    if (x < 0 || y < 0 || (unsigned)x + app_font_width(value, font) > APP_SCREEN_WIDTH || (unsigned)y + app_font_height(font) > APP_SCREEN_HEIGHT)
        fprintf(stderr, "offending text \"%s\" font %u at %d,%d width %u\n", value, font, x, y, app_font_width(value, font));
    CHECK(x >= 0 && y >= 0);
    CHECK((unsigned)x + app_font_width(value, font) <= APP_SCREEN_WIDTH);
    CHECK((unsigned)y + app_font_height(font) <= APP_SCREEN_HEIGHT);
    if (strlen(r->seen) + strlen(value) + 2 < sizeof(r->seen)) {
        strcat(r->seen, value);
        strcat(r->seen, "|");
    }
    r->strings++;
}

static const app_renderer_t renderer = {record_clear, record_rect, record_text, record_rrect, record_ring, record_icon};

static app_event_result_t send(app_menu_t *app, app_event_type_t type, int32_t value) {
    app_event_t event;
    memset(&event, 0, sizeof(event));
    event.type = type;
    if (type == APP_EVENT_TICK) event.data.elapsed_ms = (uint32_t)value;
    if (type == APP_EVENT_ROTATE) event.data.rotation = (int16_t)value;
    if (type == APP_EVENT_FN_CHANGED) event.data.fn_held = value != 0;
    return app_menu_handle(app, event);
}
static app_event_result_t tick(app_menu_t *app, uint32_t ms) { return send(app, APP_EVENT_TICK, (int32_t)ms); }
static app_event_result_t rotate(app_menu_t *app, int16_t r) { return send(app, APP_EVENT_ROTATE, r); }
static app_event_result_t press(app_menu_t *app) { return send(app, APP_EVENT_KNOB_PRESS, 0); }
static app_event_result_t back(app_menu_t *app) { return send(app, APP_EVENT_BACK, 0); }
static void fn_press(app_menu_t *app) {
    CHECK(send(app, APP_EVENT_FN_CHANGED, 1).action == APP_ACTION_NONE);
    CHECK(press(app).action == APP_ACTION_NONE);
    CHECK(send(app, APP_EVENT_FN_CHANGED, 0).action == APP_ACTION_NONE);
}
static void render(app_menu_t *app, recorder_t *r) {
    current = r;
    app_menu_render(app);
    CHECK(!app->dirty);
}

static void init_home(app_menu_t *app, recorder_t *r) {
    memset(r, 0, sizeof(*r));
    app_menu_init(app, &renderer, r);
    (void)tick(app, APP_BOOT_DURATION_MS);
    CHECK(app->page == APP_PAGE_HOME && !app->menu_active);
    render(app, r);
}

static void live_fixture(app_menu_t *app) {
    app_usage_snapshot_t s = {0};
    app_rgb_snapshot_t rgb = {true, true, APP_FX_CYCLE_ALL, 150, 255, 180, 128};
    s.short_available = true; s.short_used_percent = 18; s.short_resets_at = NOW + 3u * 3600u + 15u * 60u;
    s.weekly_available = true; s.weekly_used_percent = 76; s.weekly_resets_at = NOW + 2u * 86400u + 6u * 3600u;
    s.age_seconds = 4;
    CHECK(app_menu_set_codex_snapshot(app, &s));
    CHECK(app_menu_set_claude_snapshot(app, &s));
    CHECK(app_menu_set_clock(app, NOW, 180));
    app_menu_set_rgb_snapshot(app, &rgb);
    app->host_link = APP_LINK_LIVE;
}

static void test_boot_and_clock(void) {
    app_menu_t app;
    recorder_t r = {0};
    app_menu_init(&app, &renderer, &r);
    CHECK(app.page == APP_PAGE_BOOT && app.dirty && !app.menu_active);
    render(&app, &r);
    CHECK(seen(&r, "AK820"));
    CHECK(press(&app).action == APP_ACTION_NONE && app.page == APP_PAGE_BOOT); /* input waits for boot */
    CHECK(tick(&app, 899u).redraw && app.page == APP_PAGE_BOOT);
    render(&app, &r);
    CHECK(tick(&app, 1u).redraw && app.page == APP_PAGE_HOME);
    render(&app, &r);
    (void)tick(&app, 0u);
    CHECK(!app.dirty);
    (void)tick(&app, UINT32_MAX);
    CHECK(app.uptime_ms == UINT32_MAX);
    (void)tick(&app, 10u);
    CHECK(app.uptime_ms == UINT32_MAX);

    app_menu_init(&app, &renderer, &r);
    (void)tick(&app, APP_BOOT_DURATION_MS);
    CHECK(app_menu_now_epoch(&app) == 0);
    CHECK(!app_menu_set_clock(&app, NOW, 841) && !app_menu_set_clock(&app, NOW, -841));
    CHECK(app_menu_set_clock(&app, NOW, 180));
    render(&app, &r);
    CHECK(seen(&r, "19:42"));
    for (unsigned ms = 0; ms < 59999u; ms++) (void)tick(&app, 1u);
    CHECK(!app.dirty); /* a whole minute of main-loop ticks: nothing to redraw */
    CHECK(app_menu_set_clock(&app, NOW + 59u, 180)); /* Studio's periodic resync */
    CHECK(!app.dirty); /* same minute: no repaint */
    unsigned waited = 0;
    while (!app.dirty && waited < 5000u) { (void)tick(&app, 1u); waited++; }
    /* 19:42:59 -> 19:43:00 after one second; drawn within one poll interval. */
    CHECK(app.dirty && waited >= 1000u && waited <= 1000u + APP_CLOCK_POLL_MS);
    CHECK(app_menu_now_epoch(&app) == NOW + 60u);
    render(&app, &r);
    CHECK(seen(&r, "19:43"));
    app.face = APP_FACE_CLOCK;
    render(&app, &r);
    CHECK(seen(&r, "19:43") && seen(&r, "Pazar, 11 Ekim"));
    CHECK(app_menu_set_clock(&app, 1704067140u, 0)); /* 2023-12-31 23:59 UTC, Sunday */
    render(&app, &r);
    CHECK(seen(&r, "23:59") && seen(&r, "Pazar, 31 Aralık"));
    CHECK(app_menu_set_clock(&app, 951782400u, 0)); /* 2000-02-29, Tuesday (leap day) */
    render(&app, &r);
    CHECK(seen(&r, "Salı, 29 Şubat"));
    CHECK(app_menu_set_clock(&app, 100u, -180)); /* would be before 1970: no clock */
    render(&app, &r);
    CHECK(seen(&r, "--:--"));
    CHECK(app_menu_set_clock(&app, UINT32_MAX - 1u, 0));
    (void)tick(&app, 3000u);
    CHECK(app_menu_now_epoch(&app) == UINT32_MAX);
}

static void test_knob_modes(void) {
    static const struct { uint8_t mode; app_action_t up, down, push; } expect[] = {
        {APP_KNOB_VOLUME, APP_ACTION_VOLUME_UP, APP_ACTION_VOLUME_DOWN, APP_ACTION_MUTE_TOGGLE},
        {APP_KNOB_MEDIA, APP_ACTION_MEDIA_NEXT, APP_ACTION_MEDIA_PREV, APP_ACTION_MEDIA_PLAY},
        {APP_KNOB_BRIGHTNESS, APP_ACTION_BRIGHT_UP, APP_ACTION_BRIGHT_DOWN, APP_ACTION_NONE},
        {APP_KNOB_LIGHT, APP_ACTION_RGB_VAL_UP, APP_ACTION_RGB_VAL_DOWN, APP_ACTION_RGB_TOGGLE},
        {APP_KNOB_ZOOM, APP_ACTION_ZOOM_IN, APP_ACTION_ZOOM_OUT, APP_ACTION_ZOOM_RESET},
    };
    app_menu_t app;
    recorder_t r;
    app_event_result_t result;
    init_home(&app, &r);
    live_fixture(&app);
    result = rotate(&app, 3);
    CHECK(result.action == APP_ACTION_VOLUME_UP && result.amount == 3u && result.redraw);
    CHECK(app.toast && app.page == APP_PAGE_HOME);
    render(&app, &r);
    CHECK(seen(&r, "Ses +"));
    result = rotate(&app, INT16_MIN);
    CHECK(result.action == APP_ACTION_VOLUME_DOWN && result.amount == 32768u);
    CHECK(rotate(&app, 0).action == APP_ACTION_NONE);
    (void)tick(&app, APP_TOAST_MS);
    CHECK(app.toast == 0 && app.dirty);
    render(&app, &r);
    CHECK(!seen(&r, "Ses −"));

    for (uint8_t i = 0; i < APP_KNOB_COUNT; i++) {
        /* Choose the mode on the Düğme page, exactly as a user would. */
        fn_press(&app);
        CHECK(app.page == APP_PAGE_MENU);
        while (app_menu_item_page(app.selected) != APP_PAGE_KNOB) (void)rotate(&app, 1);
        (void)press(&app);
        CHECK(app.page == APP_PAGE_KNOB && app.focus == 1u);
        for (uint8_t step = 0; step < expect[i].mode; step++) (void)rotate(&app, 1);
        CHECK(press(&app).action == APP_ACTION_NONE && app.knob_mode == expect[i].mode);
        render(&app, &r);
        fn_press(&app);
        CHECK(app.page == APP_PAGE_HOME && !app.menu_active);
        result = rotate(&app, 2);
        CHECK(result.action == expect[i].up && result.amount == 2u);
        result = rotate(&app, -1);
        CHECK(result.action == expect[i].down && result.amount == 1u);
        result = press(&app);
        CHECK(result.action == expect[i].push);
        CHECK(app.toast != 0); /* every press answers on screen, even a no-op */
        render(&app, &r);
    }

    /* Fn + rotate flips the home face and never emits a key. */
    app.face = APP_FACE_RINGS;
    CHECK(send(&app, APP_EVENT_FN_CHANGED, 1).action == APP_ACTION_NONE);
    CHECK(rotate(&app, 1).action == APP_ACTION_NONE && app.face == APP_FACE_CLOCK);
    CHECK(rotate(&app, 1).action == APP_ACTION_NONE && app.face == APP_FACE_RINGS);
    CHECK(rotate(&app, -1).action == APP_ACTION_NONE && app.face == APP_FACE_CLOCK);
    (void)send(&app, APP_EVENT_FN_CHANGED, 0);
}

static void test_menu_navigation(void) {
    app_menu_t app;
    recorder_t r;
    init_home(&app, &r);
    fn_press(&app);
    CHECK(app.menu_active && app.page == APP_PAGE_MENU && app.selected == 0u);
    CHECK(rotate(&app, -1).action == APP_ACTION_NONE && app.selected == APP_MENU_ITEM_COUNT - 1u);
    (void)rotate(&app, (int16_t)(APP_MENU_ITEM_COUNT + 1));
    CHECK(app.selected == 0u);
    (void)rotate(&app, INT16_MIN);
    CHECK(app.selected < APP_MENU_ITEM_COUNT);
    while (app.selected != 0u) (void)rotate(&app, 1);

    for (uint8_t i = 0; i < APP_MENU_ITEM_COUNT; i++) {
        const app_page_t page = app_menu_item_page(i);
        CHECK(app.selected == i);
        render(&app, &r);
        CHECK(seen(&r, app_menu_item_name(i)));
        CHECK(press(&app).action == APP_ACTION_NONE);
        if (page == APP_PAGE_HOME) {
            CHECK(!app.menu_active && app.page == APP_PAGE_HOME);
            fn_press(&app);
            CHECK(app.page == APP_PAGE_MENU && app.selected == 0u);
            (void)rotate(&app, 1);
            continue;
        }
        CHECK(app.menu_active && app.page == page);
        render(&app, &r);
        const uint8_t rows = app_menu_row_count(page);
        if (rows > 1) {
            CHECK(app.focus == 1u && !app.editing);
            for (uint8_t k = 0; k < rows + 2u; k++) (void)rotate(&app, 1);
            CHECK(app.focus == rows - 1u); /* clamped, no wrap */
            for (uint8_t k = 0; k < rows + 2u; k++) (void)rotate(&app, -1);
            CHECK(app.focus == 0u);
            render(&app, &r);
            CHECK(press(&app).action == APP_ACTION_NONE && app.page == APP_PAGE_MENU); /* header = back */
        } else if (i % 2u) {
            CHECK(back(&app).action == APP_ACTION_NONE && app.page == APP_PAGE_MENU);
        } else {
            CHECK(press(&app).action == APP_ACTION_NONE && app.page == APP_PAGE_MENU);
        }
        CHECK(app.selected == i);
        (void)rotate(&app, 1);
    }
    CHECK(app.selected == 0u);

    /* The two quota pages flip with the knob and keep the menu in sync. */
    (void)rotate(&app, 1);
    (void)press(&app);
    CHECK(app.page == APP_PAGE_CODEX);
    CHECK(rotate(&app, 1).action == APP_ACTION_NONE && app.page == APP_PAGE_CLAUDE);
    CHECK(rotate(&app, -1).action == APP_ACTION_NONE && app.page == APP_PAGE_CODEX && app.selected == 1u);

    fn_press(&app);
    CHECK(!app.menu_active && app.page == APP_PAGE_HOME);
    CHECK(rotate(&app, 1).action == APP_ACTION_VOLUME_UP);
    CHECK(back(&app).action == APP_ACTION_NONE && app.page == APP_PAGE_HOME);
    fn_press(&app);
    CHECK(back(&app).action == APP_ACTION_NONE && !app.menu_active && app.page == APP_PAGE_HOME);

    /* An idle menu hands the knob back to volume. */
    fn_press(&app);
    (void)rotate(&app, 3);
    (void)press(&app);
    CHECK(app.page == APP_PAGE_LIGHT);
    (void)tick(&app, APP_MENU_TIMEOUT_MS - 1u);
    CHECK(app.menu_active);
    (void)rotate(&app, 1); /* activity resets the timer */
    (void)tick(&app, APP_MENU_TIMEOUT_MS - 1u);
    CHECK(app.menu_active);
    (void)tick(&app, 1u);
    CHECK(!app.menu_active && app.page == APP_PAGE_HOME && !app.editing);
    CHECK(rotate(&app, 1).action == APP_ACTION_VOLUME_UP);
}

static void open_page(app_menu_t *app, app_page_t page) {
    fn_press(app);
    while (app_menu_item_page(app->selected) != page) (void)rotate(app, 1);
    (void)press(app);
    CHECK(app->page == page);
}

static void test_light_controls(void) {
    app_menu_t app;
    recorder_t r;
    app_event_result_t result;
    init_home(&app, &r);
    open_page(&app, APP_PAGE_LIGHT);
    render(&app, &r);
    CHECK(seen(&r, "RGB bilgisi yok"));
    CHECK(press(&app).action == APP_ACTION_NONE && !app.editing); /* nothing to edit */
    live_fixture(&app);
    render(&app, &r);
    CHECK(seen(&r, "Döngü") && seen(&r, "Açık"));
    CHECK(press(&app).action == APP_ACTION_RGB_TOGGLE && !app.editing);
    static const struct { uint8_t row; app_action_t up, down; } rows[] = {
        {2, APP_ACTION_RGB_NEXT, APP_ACTION_RGB_PREV},
        {3, APP_ACTION_RGB_VAL_UP, APP_ACTION_RGB_VAL_DOWN},
        {4, APP_ACTION_RGB_HUE_UP, APP_ACTION_RGB_HUE_DOWN},
        {5, APP_ACTION_RGB_SAT_UP, APP_ACTION_RGB_SAT_DOWN},
        {6, APP_ACTION_RGB_SPEED_UP, APP_ACTION_RGB_SPEED_DOWN},
    };
    for (unsigned i = 0; i < sizeof(rows) / sizeof(rows[0]); i++) {
        (void)rotate(&app, 1);
        CHECK(app.focus == rows[i].row);
        CHECK(press(&app).action == APP_ACTION_NONE && app.editing);
        render(&app, &r);
        result = rotate(&app, 4);
        CHECK(result.action == rows[i].up && result.amount == 4u && app.focus == rows[i].row);
        result = rotate(&app, -1);
        CHECK(result.action == rows[i].down && result.amount == 1u);
        CHECK(press(&app).action == APP_ACTION_NONE && !app.editing);
    }
    CHECK(back(&app).action == APP_ACTION_NONE && app.page == APP_PAGE_MENU);

    /* The snapshot is the only source of truth for what the page shows. */
    app_rgb_snapshot_t rgb = app.rgb;
    rgb.effect = 200; /* unknown effect ids fall back, never index out of range */
    app_menu_set_rgb_snapshot(&app, &rgb);
    CHECK(app.rgb.effect == APP_FX_OTHER);
    (void)press(&app);
    render(&app, &r);
    CHECK(seen(&r, "Özel"));
}

static void test_display_settings(void) {
    static const uint8_t cycle[] = {5, 15, 30, 0, 1, 5};
    app_menu_t app;
    recorder_t r;
    init_home(&app, &r);
    CHECK(app.device.sleep_minutes == 3u);
    open_page(&app, APP_PAGE_DISPLAY);
    CHECK(press(&app).action == APP_ACTION_NONE && app.editing && app.focus == 1u);
    for (unsigned i = 0; i < sizeof(cycle); i++) {
        CHECK(rotate(&app, 1).action == APP_ACTION_NONE);
        CHECK(app.device.sleep_minutes == cycle[i]);
    }
    (void)rotate(&app, -1);
    CHECK(app.device.sleep_minutes == 1u);
    render(&app, &r);
    CHECK(seen(&r, "1 dk"));
    (void)press(&app);
    (void)rotate(&app, 1);
    (void)press(&app);
    CHECK(app.editing && app.focus == 2u);
    (void)rotate(&app, 1);
    CHECK(app.face == APP_FACE_CLOCK);
    (void)press(&app);
    (void)rotate(&app, 1);
    render(&app, &r);
    CHECK(seen(&r, "Yüklü değil"));
    CHECK(press(&app).action == APP_ACTION_NONE && !app.editing); /* no GIF uploaded */
    app.device.media_available = true;
    CHECK(press(&app).action == APP_ACTION_MEDIA_SHOW_TOGGLE);
    (void)rotate(&app, 1);
    CHECK(press(&app).action == APP_ACTION_SCREEN_OFF);
    CHECK(!app.menu_active && app.page == APP_PAGE_HOME);
}

static void test_link_controls(void) {
    app_menu_t app;
    recorder_t r;
    app_event_result_t result;
    init_home(&app, &r);
    app.device.route = 0; app.device.slot = 0; app.device.os = APP_OS_MAC;
    open_page(&app, APP_PAGE_LINK);
    CHECK(app.focus == 1u);
    render(&app, &r);
    CHECK(seen(&r, "USB kablo") && seen(&r, "Bluetooth 2") && !seen(&r, "Eşleştir")); /* 6 rows visible */
    CHECK(press(&app).action == APP_ACTION_NONE); /* already on USB */
    (void)rotate(&app, 1);
    result = press(&app);
    CHECK(result.action == APP_ACTION_ROUTE_BT && result.amount == 1u);
    app.device.route = 1; app.device.slot = 1; app.device.radio_state = 3;
    CHECK(press(&app).action == APP_ACTION_NONE); /* already on BT 1 */
    render(&app, &r);
    CHECK(seen(&r, "Bağlı") && seen(&r, "BT 1"));
    (void)rotate(&app, 2);
    result = press(&app);
    CHECK(result.action == APP_ACTION_ROUTE_BT && result.amount == 3u);
    (void)rotate(&app, 1);
    CHECK(press(&app).action == APP_ACTION_ROUTE_24G);
    (void)rotate(&app, 1);
    CHECK(app.focus == 6u && press(&app).action == APP_ACTION_OS_WINDOWS);
    app.device.os = APP_OS_WINDOWS;
    CHECK(press(&app).action == APP_ACTION_OS_MAC);
    (void)rotate(&app, 1);
    CHECK(app.focus == 7u);
    render(&app, &r);
    CHECK(seen(&r, "Eşleştir") && seen(&r, "Yeni cihaz") && !seen(&r, "USB kablo")); /* scrolled */
    CHECK(press(&app).action == APP_ACTION_PAIR);
    app.device.route = 0;
    CHECK(press(&app).action == APP_ACTION_NONE); /* pairing needs Bluetooth */
    render(&app, &r);
    CHECK(seen(&r, "Önce BT"));
    for (int k = 0; k < 10; k++) (void)rotate(&app, -1);
    CHECK(app.focus == 0u && press(&app).action == APP_ACTION_NONE && app.page == APP_PAGE_MENU);

    /* Cable out on Bluetooth: last numbers stay, with their age and the cause. */
    app_usage_snapshot_t s = {0};
    s.short_available = true; s.short_used_percent = 5; s.short_resets_at = NOW + 9000u; s.age_seconds = 724;
    CHECK(app_menu_set_claude_snapshot(&app, &s));
    CHECK(app_menu_set_clock(&app, NOW, 180));
    app.host_link = APP_LINK_OFFLINE; app.device.usb_active = false; app.device.route = 1;
    fn_press(&app); /* back home */
    CHECK(app.page == APP_PAGE_HOME);
    render(&app, &r);
    CHECK(seen(&r, "12 dk önce") && seen(&r, "95") && seen(&r, "19:42"));
    open_page(&app, APP_PAGE_DEVICE);
    render(&app, &r);
    CHECK(seen(&r, "Kablo yok"));
    app.device.usb_active = true;
    render(&app, &r);
    CHECK(seen(&r, "Bağlı değil"));
}

static void test_usage_honesty(void) {
    app_menu_t app;
    recorder_t r;
    app_usage_snapshot_t s = {0};
    init_home(&app, &r);
    CHECK(seen(&r, "Veri yok") && seen(&r, "Studio yok"));
    CHECK(!seen(&r, "0%") && !seen(&r, "100%"));
    s.weekly_available = true;
    s.weekly_used_percent = 94u;
    s.weekly_resets_at = NOW + 3600u;
    s.short_available = false;
    s.short_used_percent = 0u; /* unavailable must ignore this, never show 100% left */
    (void)snprintf(s.observed_label, sizeof(s.observed_label), "11 OCT");
    CHECK(app_menu_set_codex_snapshot(&app, &s));
    app.host_link = APP_LINK_LIVE;
    s.age_seconds = 2;
    CHECK(app_menu_set_codex_snapshot(&app, &s));
    render(&app, &r);
    /* Only the weekly window exists: the ring takes it (labelled), the
     * missing 5-hour window is a dash, never "100%". */
    CHECK(seen(&r, "6") && seen(&r, "7 gün") && seen(&r, "5 sa") && seen(&r, "—") && !seen(&r, "100%"));
    app.face = APP_FACE_CLOCK;
    render(&app, &r);
    CHECK(seen(&r, "6%") && seen(&r, "7 gün"));
    app.face = APP_FACE_RINGS;
    open_page(&app, APP_PAGE_CODEX);
    render(&app, &r);
    CHECK(seen(&r, "6%") && seen(&r, "Canlı") && seen(&r, "—"));
    app.host_link = APP_LINK_STALE;
    render(&app, &r);
    CHECK(seen(&r, "Bağsız") && !seen(&r, "Canlı"));
    app.host_link = APP_LINK_LIVE;
    app.codex.age_seconds = 300u;
    render(&app, &r);
    CHECK(seen(&r, "Eski"));
    s.weekly_used_percent = 101u;
    CHECK(!app_menu_set_codex_snapshot(&app, &s));
    CHECK(app.codex.weekly_used_percent == 94u);
    s.weekly_used_percent = 0u;
    s.short_available = true;
    memset(s.observed_label, 'X', sizeof(s.observed_label));
    CHECK(app_menu_set_codex_snapshot(&app, &s));
    CHECK(app.codex.observed_label[15] == '\0');
    render(&app, &r);
    CHECK(seen(&r, "100%"));
    CHECK(app_menu_set_codex_snapshot(&app, NULL));
    CHECK(!app.codex.weekly_available && !app.codex.short_available && app.codex.age_seconds == UINT32_MAX);
    render(&app, &r);
    CHECK(seen(&r, "Veri yok"));
}

static void test_no_driver_required(void) {
    app_menu_t app;
    app_event_t invalid;
    memset(&invalid, 0, sizeof(invalid));
    invalid.type = (app_event_type_t)99;
    app_menu_init(&app, NULL, NULL);
    app_menu_render(&app);
    CHECK(app_menu_handle(&app, invalid).action == APP_ACTION_NONE);
    app_menu_init(NULL, NULL, NULL);
    app_menu_render(NULL);
    CHECK(!app_menu_set_codex_snapshot(NULL, NULL));
    app_menu_set_rgb_snapshot(NULL, NULL);
    app_menu_set_device_snapshot(NULL, NULL);
    CHECK(app_menu_handle(NULL, invalid).action == APP_ACTION_NONE);
    CHECK(app_rgb565(255, 0, 0) == 0xF800u && app_rgb565(0, 255, 0) == 0x07E0u && app_rgb565(0, 0, 255) == 0x001Fu);
    CHECK(app_font_width("Wi", APP_FONT_BODY) != app_font_width("ii", APP_FONT_BODY));
    CHECK(app_font_width("Çevrimdışı", APP_FONT_SMALL) > 0);
    CHECK(app_font_glyph(0x4E2D, APP_FONT_BODY) == app_font_glyph(' ', APP_FONT_BODY)); /* unknown → space */
    CHECK(app_font_glyph('A', APP_FONT_CLOCK) == app_font_glyph(' ', APP_FONT_CLOCK));    /* digits-only font */
    CHECK(app_icon_find(APP_ICON_HOME, 13) == NULL);
}

/* Every page in every data state draws with all text fully on screen. */
static void test_all_visual_states(void) {
    app_menu_t app;
    recorder_t r;
    static const uint8_t used[] = {0, 1, 75, 90, 94, 100};
    static const uint8_t batteries[] = {0, 1, 8, 15, 16, 99, 100, 255};
    init_home(&app, &r);
    for (unsigned u = 0; u < sizeof(used); u++) {
        app_usage_snapshot_t s = {0};
        s.weekly_available = u % 2u == 0u;
        s.short_available = u != 3u;
        s.weekly_used_percent = used[u];
        s.short_used_percent = used[u];
        s.weekly_resets_at = u == 5u ? UINT32_MAX : NOW + u * 40000u;
        s.short_resets_at = u == 4u ? NOW - 5u : NOW + u * 700u;
        s.age_seconds = u == 2u ? UINT32_MAX : u * 120u;
        CHECK(app_menu_set_codex_snapshot(&app, &s));
        CHECK(app_menu_set_claude_snapshot(&app, u == 1u ? NULL : &s));
        CHECK(app_menu_set_clock(&app, u ? NOW : 0u, (int16_t)(u * 60)));
        for (unsigned b = 0; b < sizeof(batteries); b++) {
            app.device.battery = batteries[b];
            app.device.charging = b % 2u;
            app.device.usb_active = b % 3u == 0u;
            app.device.route = (uint8_t)(b % 4u);
            app.device.slot = (uint8_t)(b % 5u);
            app.device.caps_lock = b % 2u == 0u;
            app.device.os = (uint8_t)(b % 3u);
            app.device.media_available = b % 2u;
            app.device.sleep_minutes = b % 2u ? 30u : 0u;
            app.host_link = (app_link_t)(b % 4u);
            app.knob_mode = (uint8_t)(b % APP_KNOB_COUNT);
            app.rgb.available = b != 3u;
            app.rgb.enabled = b % 2u;
            app.rgb.effect = (uint8_t)(b % APP_FX_COUNT);
            app.rgb.hue = (uint8_t)(b * 37u);
            app.rgb.val = (uint8_t)(b * 36u);
            app.uptime_ms = b * 3600000u + 59000u;
            for (unsigned page = APP_PAGE_BOOT; page < APP_PAGE_COUNT; page++) {
                app.page = (app_page_t)page;
                app.menu_active = page >= APP_PAGE_MENU;
                for (unsigned face = 0; face < APP_FACE_COUNT; face++) {
                    app.face = (uint8_t)face;
                    app.selected = (uint8_t)((page + b) % APP_MENU_ITEM_COUNT);
                    app.focus = (uint8_t)((b + face) % app_menu_row_count(app.page));
                    app.editing = app.focus && face;
                    app.toast = app.menu_active ? 0u : (uint8_t)(1u + (b + u + face) % 15u);
                    app.boot_elapsed_ms = b * 120u;
                    render(&app, &r);
                    CHECK(r.strings > 0 && r.shapes > 0);
                }
            }
        }
    }
}

int main(void) {
    test_boot_and_clock();
    test_knob_modes();
    test_menu_navigation();
    test_light_controls();
    test_display_settings();
    test_link_controls();
    test_usage_honesty();
    test_no_driver_required();
    test_all_visual_states();
    printf("PASS: 9 suites, %u assertions. Menu routing, controls, honesty and layout bounds verified.\n", assertions);
    puts("No firmware, USB device, media keys or external integration was accessed.");
    return EXIT_SUCCESS;
}
