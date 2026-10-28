#pragma once
#include "app_menu.h"
#define APP_TILE_ROWS 8
typedef struct {
    /* Word-aligned so the band can be hashed 32 bits at a time on the M0. */
    uint8_t bytes[APP_SCREEN_WIDTH * APP_TILE_ROWS * 2] __attribute__((aligned(4)));
    uint16_t top;
} app_raster_t;

/* FNV-1a over the band, used to skip sending bands the panel already shows. */
static inline uint32_t app_raster_hash(const app_raster_t *r) {
    const uint32_t *word = (const uint32_t *)(const void *)r->bytes;
    uint32_t hash = 2166136261u;
    for (unsigned i = 0; i < sizeof(r->bytes) / 4u; i++) hash = (hash ^ word[i]) * 16777619u;
    return hash;
}
extern const app_renderer_t app_raster_renderer;
