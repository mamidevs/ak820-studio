// SPDX-License-Identifier: GPL-2.0-or-later
// Streaming 128x8 RGB565 renderer. Every primitive clips to the current band,
// so one frame is 16 passes of the same draw list. Coverage-based anti-aliasing
// in Q4 fixed point (1/16 px); no floats and only edge pixels divide.
#include "app_raster.h"
#include "app_font.h"
#include "app_icons.h"
#include <stddef.h>

static const uint16_t sin_q14[91] = {
    0,286,572,857,1143,1428,1713,1997,2280,2563,2845,3126,3406,3686,3964,4240,4516,4790,5063,
    5334,5604,5872,6138,6402,6664,6924,7182,7438,7692,7943,8192,8438,8682,8923,9162,9397,9630,
    9860,10087,10311,10531,10749,10963,11174,11381,11585,11786,11982,12176,12365,12551,12733,
    12911,13085,13255,13421,13583,13741,13894,14044,14189,14330,14466,14598,14726,14849,14968,
    15082,15191,15296,15396,15491,15582,15668,15749,15826,15897,15964,16026,16083,16135,16182,
    16225,16262,16294,16322,16344,16362,16374,16382,16384};

static int32_t sin_deg(int32_t deg) {
    deg %= 360;
    if (deg < 0) deg += 360;
    if (deg <= 90) return sin_q14[deg];
    if (deg <= 180) return sin_q14[180 - deg];
    if (deg <= 270) return -(int32_t)sin_q14[deg - 180];
    return -(int32_t)sin_q14[360 - deg];
}

static bool row_visible(const app_raster_t *r, int32_t y) {
    return y >= r->top && y < r->top + APP_TILE_ROWS && y < 128;
}

/* Rows [y0,y1) of an object intersected with this band. */
static bool band(const app_raster_t *r, int32_t y, int32_t h, int32_t *y0, int32_t *y1) {
    *y0 = y < r->top ? r->top : y;
    *y1 = y + h;
    if (*y1 > r->top + APP_TILE_ROWS) *y1 = r->top + APP_TILE_ROWS;
    if (*y1 > 128) *y1 = 128;
    return *y0 < *y1;
}

static uint8_t *at(app_raster_t *r, int32_t x, int32_t y) {
    return &r->bytes[((size_t)(y - r->top) * 128u + (size_t)x) * 2u];
}

static void put(app_raster_t *r, int32_t x, int32_t y, uint16_t c) {
    if (x < 0 || x >= 128 || !row_visible(r, y)) return;
    uint8_t *p = at(r, x, y);
    p[0] = (uint8_t)(c >> 8);
    p[1] = (uint8_t)c;
}

/* alpha: 0..256 */
static void blend(app_raster_t *r, int32_t x, int32_t y, uint16_t fg, uint32_t alpha) {
    if (alpha == 0 || x < 0 || x >= 128 || !row_visible(r, y)) return;
    if (alpha >= 256) { put(r, x, y, fg); return; }
    uint8_t *p = at(r, x, y);
    const uint16_t bg = (uint16_t)((p[0] << 8) | p[1]);
    const uint32_t inv = 256u - alpha;
    const uint32_t red = ((((uint32_t)fg >> 11) & 31u) * alpha + (((uint32_t)bg >> 11) & 31u) * inv) >> 8;
    const uint32_t green = ((((uint32_t)fg >> 5) & 63u) * alpha + (((uint32_t)bg >> 5) & 63u) * inv) >> 8;
    const uint32_t blue = (((uint32_t)fg & 31u) * alpha + ((uint32_t)bg & 31u) * inv) >> 8;
    const uint16_t c = (uint16_t)((red << 11) | (green << 5) | blue);
    p[0] = (uint8_t)(c >> 8);
    p[1] = (uint8_t)c;
}

static uint32_t a4(uint8_t alpha) { return alpha ? (uint32_t)alpha * 17u + 1u : 0u; }

static void clear(void *user, uint16_t c) {
    app_raster_t *r = user;
    for (size_t i = 0; i < sizeof(r->bytes); i += 2) {
        r->bytes[i] = (uint8_t)(c >> 8);
        r->bytes[i + 1] = (uint8_t)c;
    }
}

static void rect(void *user, int16_t x, int16_t y, uint16_t w, uint16_t h, uint16_t c) {
    app_raster_t *r = user;
    int32_t y0, y1, x0 = x < 0 ? 0 : x, x1 = (int32_t)x + w;
    if (x1 > 128) x1 = 128;
    if (x0 >= x1 || !band(r, y, h, &y0, &y1)) return;
    for (int32_t row = y0; row < y1; row++)
        for (int32_t col = x0; col < x1; col++) put(r, col, row, c);
}

static void text(void *user, int16_t x, int16_t y, const char *s, uint16_t c, uint8_t font) {
    app_raster_t *r = user;
    int32_t y0, y1;
    if (!s || !band(r, y, app_font_height(font), &y0, &y1)) return;
    const uint8_t *pixels = app_font_pixels(font);
    int32_t gx = x;
    for (unsigned n = 0; *s && n < 64u && gx < 128; n++) {
        const app_font_glyph_t *g = app_font_glyph(app_font_next(&s), font);
        for (uint8_t row = 0; row < g->height; row++) {
            const int32_t py = y + g->y + row;
            if (py < y0 || py >= y1) continue;
            for (uint8_t col = 0; col < g->width; col++)
                blend(r, gx + g->x + col, py, c, a4(app_font_alpha(pixels, g, row, col)));
        }
        gx += g->advance;
    }
}

/* Coverage 0..256 of a pixel centre at squared Q4 distance d2 from a disc of
 * Q4 radius rq: a one-pixel ramp across the edge, linear in d2. */
static uint32_t disc_cover(int32_t d2, int32_t rq) {
    if (rq <= 0) return 0;
    const int32_t inner = rq > 8 ? (rq - 8) * (rq - 8) : 0, outer = (rq + 8) * (rq + 8);
    if (d2 <= inner) return 256;
    if (d2 >= outer) return 0;
    return (uint32_t)(((outer - d2) * 256) / (outer - inner)); /* fits int32: radii <= 128 px */
}

static void rrect(void *user, int16_t x, int16_t y, uint16_t w, uint16_t h, uint8_t radius, uint16_t c) {
    app_raster_t *r = user;
    int32_t y0, y1;
    if (!w || !h || !band(r, y, h, &y0, &y1)) return;
    uint32_t rad = radius;
    if (rad * 2u > w) rad = w / 2u;
    if (rad * 2u > h) rad = h / 2u;
    /* Corner centres in Q4; odd sizes put the centre on a half pixel. */
    const int32_t rq = (int32_t)rad * 16;
    const int32_t left = x * 16 + rq, right = (x + (int32_t)w) * 16 - rq;
    const int32_t top = y * 16 + rq, bottom = (y + (int32_t)h) * 16 - rq;
    for (int32_t row = y0; row < y1; row++) {
        const int32_t py = row * 16 + 8;
        const int32_t dy = py < top ? top - py : py > bottom ? py - bottom : 0;
        for (int32_t col = x < 0 ? 0 : x; col < x + (int32_t)w && col < 128; col++) {
            const int32_t px = col * 16 + 8;
            const int32_t dx = px < left ? left - px : px > right ? px - right : 0;
            if (!dx && !dy) put(r, col, row, c);
            else blend(r, col, row, c, disc_cover(dx * dx + dy * dy, rq));
        }
    }
}

static uint32_t isqrt(uint32_t v) {
    uint32_t root = 0, bit = 1u << 30;
    while (bit > v) bit >>= 2;
    while (bit) {
        if (v >= root + bit) { v -= root + bit; root = (root >> 1) + bit; }
        else root >>= 1;
        bit >>= 2;
    }
    return root;
}

static uint32_t half_plane(int32_t distance_q4) {
    const int32_t v = (distance_q4 + 8) * 16;
    return v <= 0 ? 0u : v >= 256 ? 256u : (uint32_t)v;
}

static void ring(void *user, int16_t x, int16_t y, uint8_t d, uint8_t t, uint16_t permille, uint16_t c) {
    app_raster_t *r = user;
    int32_t y0, y1;
    if (!d || !t || !permille || !band(r, y, d, &y0, &y1)) return;
    const int32_t cx = x * 16 + d * 8, cy = y * 16 + d * 8;
    const int32_t outer = d * 8, inner = outer - t * 16 > 0 ? outer - t * 16 : 0;
    const bool full = permille >= 1000u;
    const int32_t degrees = full ? 360 : (int32_t)((permille * 360u + 500u) / 1000u);
    const int32_t s = sin_deg(degrees), co = sin_deg(degrees + 90);
    const int32_t mid = (outer + inner) / 2, cap = t * 8;
    const int32_t cap0x = cx, cap0y = cy - mid;
    const int32_t capsx = cx + ((s * mid) >> 14), capsy = cy - ((co * mid) >> 14);
    /* hole keeps one extra pixel so rounded cap centres never lose their fringe */
    const int32_t reach = outer + 8, hole = inner > 16 ? inner - 16 : 0, cap_reach = cap + 16;
    for (int32_t row = y0; row < y1; row++) {
        const int32_t dy = row * 16 + 8 - cy, dy2 = dy * dy;
        if (dy2 >= reach * reach) continue;
        /* Visit only this row's annulus: two integer square roots per row
         * instead of a distance test for every pixel of the bounding box. */
        const int32_t span = (int32_t)isqrt((uint32_t)(reach * reach - dy2));
        const int32_t gap = dy2 < hole * hole ? (int32_t)isqrt((uint32_t)(hole * hole - dy2)) : -1;
        int32_t c0 = (cx - span - 8) >> 4, c1 = (cx + span - 8 + 15) >> 4;
        if (c0 < 0) c0 = 0;
        if (c1 > 127) c1 = 127;
        for (int32_t col = c0; col <= c1; col++) {
            const int32_t dx = col * 16 + 8 - cx;
            if (gap >= 0 && dx > -gap && dx < gap) { col = (cx + gap - 8) >> 4; continue; }
            const int32_t d2 = dx * dx + dy2;
            uint32_t a = (disc_cover(d2, outer) * (256u - disc_cover(d2, inner))) >> 8;
            if (!full) {
                if (a) {
                    const uint32_t start = half_plane(dx);
                    const uint32_t end = half_plane(-((s * dy + co * dx) >> 14));
                    const uint32_t angular = degrees <= 180 ? (start < end ? start : end) : (start > end ? start : end);
                    a = (a * angular) >> 8;
                }
                const int32_t ax = dx + cx, ay = dy + cy;
                if (ax - cap0x < cap_reach && cap0x - ax < cap_reach && ay - cap0y < cap_reach && cap0y - ay < cap_reach) {
                    const uint32_t c = disc_cover((ax - cap0x) * (ax - cap0x) + (ay - cap0y) * (ay - cap0y), cap);
                    if (c > a) a = c;
                }
                if (ax - capsx < cap_reach && capsx - ax < cap_reach && ay - capsy < cap_reach && capsy - ay < cap_reach) {
                    const uint32_t c = disc_cover((ax - capsx) * (ax - capsx) + (ay - capsy) * (ay - capsy), cap);
                    if (c > a) a = c;
                }
            }
            blend(r, col, row, c, a);
        }
    }
}

static void icon(void *user, int16_t x, int16_t y, uint8_t id, uint8_t size, uint16_t c) {
    app_raster_t *r = user;
    int32_t y0, y1;
    const app_icon_t *glyph = app_icon_find(id, size);
    if (!glyph || !band(r, y, size, &y0, &y1)) return;
    for (int32_t row = y0; row < y1; row++)
        for (uint8_t col = 0; col < size; col++)
            blend(r, x + col, row, c, a4(app_icon_alpha(glyph, (uint8_t)(row - y), col)));
}

const app_renderer_t app_raster_renderer = {clear, rect, text, rrect, ring, icon};
