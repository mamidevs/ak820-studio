/* Idle cost with Studio connected: one simulated minute of the firmware main
 * loop (1 ms ticks, bridge tick every loop, Studio cycle every 5 s with an
 * ageing source). Counts full-frame repaints, which block key scanning. */
#include "app_bridge.h"
#include "app_raster.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define NOW 1791736920u
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

static void put32(uint8_t *p, uint32_t v) { for (int i = 0; i < 4; i++) p[i] = (uint8_t)(v >> (8 * i)); }
static uint16_t seq;
static void packet(uint8_t *p, uint8_t cmd, uint32_t session) {
    memset(p, 0, 32); p[0] = 7; p[1] = 0x13; p[2] = cmd; p[3] = 1; seq++;
    p[4] = (uint8_t)seq; p[5] = (uint8_t)(seq >> 8); put32(p + 8, session);
}

static unsigned frames, sent;
static uint32_t shown[16];
static bool known;
/* Mirrors display_app.c: render every band, send only bands that changed. */
static void paint_if_dirty(app_menu_t *m, app_raster_t *t) {
    if (!m->dirty) return;
    frames++;
    for (t->top = 0; t->top < 128; t->top += APP_TILE_ROWS) {
        app_menu_render(m);
        const uint32_t h = app_raster_hash(t);
        if (!known || shown[t->top / APP_TILE_ROWS] != h) sent++;
        shown[t->top / APP_TILE_ROWS] = h;
    }
    known = true;
}

int main(void) {
    app_menu_t m; app_bridge_t b; app_raster_t tile; uint8_t p[32];
    app_menu_init(&m, &app_raster_renderer, &tile);
    app_bridge_init(&b, &m);
    for (uint32_t now = 1; now <= 60000u * 2u; now++) {
        if (now % 5000u == 1u) { /* Studio cycle: HELLO, CLOCK, CODEX, CLAUDE */
            const uint32_t epoch = NOW + now / 1000u, age = 10u + (now / 1000u) % 5u;
            packet(p, 0x80, 7); p[7] = now == 1u; CHECK(app_bridge_handle(&b, p, 32, now) && p[6] == 1);
            packet(p, 0x84, 7); put32(p + 12, epoch); p[16] = 180; CHECK(app_bridge_handle(&b, p, 32, now) && p[6] == 1);
            packet(p, 0x81, 7); p[7] = 1; p[12] = 47; p[13] = 255; put32(p + 14, NOW + 600000u); put32(p + 22, age);
            CHECK(app_bridge_handle(&b, p, 32, now) && p[6] == 1);
            packet(p, 0x82, 7); p[7] = 2; p[12] = 255; p[13] = 5; put32(p + 18, NOW + 14000u); put32(p + 22, age);
            CHECK(app_bridge_handle(&b, p, 32, now) && p[6] == 1);
        }
        app_menu_handle(&m, (app_event_t){.type = APP_EVENT_TICK, .data.elapsed_ms = 1});
        app_bridge_tick(&b, now);
        paint_if_dirty(&m, &tile);
        if (now == 60000u) { printf("first minute (boot + first data): %u frames\n", frames); frames = 0; sent = 0; }
    }
    printf("steady minute with Studio connected: %u full-screen repaints, %u of %u bands sent over SPI\n", frames, sent, frames * 16u);
    CHECK(frames <= 2u); /* the clock minute, at most one more */
    CHECK(sent <= frames * 4u); /* a minute change touches the status bar and countdown rows only */
    CHECK(m.host_link == APP_LINK_LIVE && m.codex.weekly_available && m.claude.short_available);

    /* Cable out (Bluetooth): no more packets for three minutes. Expect the
     * stale and offline transitions plus one repaint per minute of age/clock. */
    frames = 0;
    for (uint32_t now = 120001u; now <= 300000u; now++) {
        app_menu_handle(&m, (app_event_t){.type = APP_EVENT_TICK, .data.elapsed_ms = 1});
        app_bridge_tick(&b, now);
        paint_if_dirty(&m, &tile);
    }
    printf("three minutes with the cable out: %u full-screen repaints\n", frames);
    CHECK(m.host_link == APP_LINK_OFFLINE && m.claude.age_seconds >= 180u);
    CHECK(frames >= 3u && frames <= 10u);
    printf("PASS: idle %u checks\n", checks);
    return 0;
}
