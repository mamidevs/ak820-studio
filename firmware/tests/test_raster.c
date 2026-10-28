/* Raster renderer: byte order, band clipping with canaries, anti-aliasing,
 * ring geometry and deterministic repeat rendering of every page. */
#include "app_menu.h"
#include "app_raster.h"
#include "app_font.h"
#include "app_icons.h"
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #x); exit(1); } } while (0)

typedef struct { uint64_t before; app_raster_t tile; uint64_t after; } guarded_t;
static void guards(const guarded_t *g) {
    CHECK(g->before == UINT64_C(0x123456789abcdef0));
    CHECK(g->after == UINT64_C(0xabcdef0123456789));
}
static uint16_t px(const app_raster_t *t, int x, int y) {
    const unsigned o = ((unsigned)(y - t->top) * 128u + (unsigned)x) * 2u;
    return (uint16_t)((t->bytes[o] << 8) | t->bytes[o + 1]);
}

int main(void) {
    guarded_t g = {UINT64_C(0x123456789abcdef0), {{0}, 0}, UINT64_C(0xabcdef0123456789)};
    const app_renderer_t *r = &app_raster_renderer;
    CHECK(sizeof(g.tile.bytes) == 2048);
    r->clear(&g.tile, 0);
    r->rect(&g.tile, 0, 0, 1, 1, 0xf800);
    CHECK(g.tile.bytes[0] == 0xf8 && g.tile.bytes[1] == 0);
    r->rect(&g.tile, 1, 0, 1, 1, 0x07e0);
    CHECK(g.tile.bytes[2] == 7 && g.tile.bytes[3] == 0xe0);

    /* Hostile coordinates clip without touching memory outside the band. */
    for (g.tile.top = 0; g.tile.top < 128; g.tile.top += APP_TILE_ROWS) {
        r->rect(&g.tile, -100, -100, 65535, 65535, 0xffff);
        r->rrect(&g.tile, -50, -50, 400, 400, 255, 0x1234);
        r->rrect(&g.tile, 120, 120, 30, 30, 15, 0x1234);
        r->ring(&g.tile, -20, -20, 255, 127, 999, 0xffff);
        r->ring(&g.tile, 100, 100, 60, 30, 1000, 0xffff);
        r->icon(&g.tile, -6, 122, APP_ICON_HOME, 16, 0xffff);
        r->icon(&g.tile, 120, -6, APP_ICON_HOME, 28, 0xffff);
        r->icon(&g.tile, 0, 0, APP_ICON_HOME, 13, 0xffff); /* missing size: no-op */
        r->text(&g.tile, -4, -4, "Ğışü öÇ test — 100%", 0xf800, APP_FONT_BIG);
        r->text(&g.tile, 121, 125, "100%", 0xffff, APP_FONT_CLOCK);
        r->text(&g.tile, 0, 0, NULL, 0xffff, APP_FONT_BODY);
        guards(&g);
    }

    /* Real coverage-based anti-aliasing on text and ring edges. */
    g.tile.top = 0;
    r->clear(&g.tile, 0);
    r->text(&g.tile, 0, 0, "Codex", 0xffff, APP_FONT_BODY);
    unsigned edges = 0, solid = 0;
    for (unsigned i = 0; i < sizeof(g.tile.bytes); i += 2) {
        const uint16_t p = (uint16_t)((g.tile.bytes[i] << 8) | g.tile.bytes[i + 1]);
        if (p == 0xffff) solid++;
        else if (p) edges++;
    }
    CHECK(solid > 0 && edges > 0);

    /* Ring: a 50% arc covers the right half, not the left. Band 40..47 is the
     * vertical middle of a 64px ring at y=12. */
    g.tile.top = 40;
    r->clear(&g.tile, 0);
    r->ring(&g.tile, 32, 12, 64, 8, 500, 0xffff);
    CHECK(px(&g.tile, 92, 44) == 0xffff);  /* right side, inside the stroke */
    CHECK(px(&g.tile, 35, 44) == 0);       /* left side stays empty */
    CHECK(px(&g.tile, 64, 44) == 0);       /* hole */
    r->clear(&g.tile, 0);
    r->ring(&g.tile, 32, 12, 64, 8, 1000, 0xffff);
    CHECK(px(&g.tile, 35, 44) == 0xffff && px(&g.tile, 92, 44) == 0xffff && px(&g.tile, 64, 44) == 0);
    r->clear(&g.tile, 0);
    r->ring(&g.tile, 32, 12, 64, 8, 0, 0xffff); /* 0% draws nothing */
    for (unsigned i = 0; i < sizeof(g.tile.bytes); i++) CHECK(g.tile.bytes[i] == 0);

    /* Rounded rectangle corners are softened, centres solid. */
    g.tile.top = 0;
    r->clear(&g.tile, 0);
    r->rrect(&g.tile, 10, 0, 20, 8, 4, 0xffff);
    CHECK(px(&g.tile, 20, 4) == 0xffff && px(&g.tile, 10, 0) != 0xffff);

    /* Every page renders identically twice, band by band (no hidden state). */
    app_menu_t app;
    app_menu_init(&app, r, &g.tile);
    app_menu_set_clock(&app, 1791736920u, 180);
    app_usage_snapshot_t s = {true, 40, 1791800000u, true, 10, 1791750000u, 3, ""};
    app_menu_set_codex_snapshot(&app, &s);
    app_menu_set_claude_snapshot(&app, &s);
    app.host_link = APP_LINK_LIVE;
    app.rgb.available = true;
    app.toast = 9;
    for (unsigned page = 0; page < APP_PAGE_COUNT; page++) {
        app.page = (app_page_t)page;
        app.menu_active = page >= APP_PAGE_MENU;
        for (g.tile.top = 0; g.tile.top < 128; g.tile.top += APP_TILE_ROWS) {
            static uint8_t first[2048];
            app_menu_render(&app);
            guards(&g);
            memcpy(first, g.tile.bytes, sizeof(first));
            app_menu_render(&app);
            CHECK(!memcmp(first, g.tile.bytes, sizeof(first)));
        }
    }
    printf("PASS: raster %u checks — RGB565 byte order, band clipping/canaries, AA text/rings/corners, repeatable pages (ASan/UBSan).\n", checks);
    return 0;
}
