#pragma once
#include <stdbool.h>
#include <stdint.h>
#define APP_MEDIA_BASE 0xCE0000u
#define APP_MEDIA_HEADER_BYTES 4096u
#define APP_MEDIA_FRAME_BYTES 32768u
#define APP_MEDIA_MAX_FRAMES 96u
#define APP_MEDIA_MIN_DELAY 100u
typedef struct {
    bool available, show, uploading;
    uint16_t count, index;
    uint16_t delays[APP_MEDIA_MAX_FRAMES];
    uint32_t crc, frame_started;
} app_media_t;
void app_media_init(app_media_t *media);
bool app_media_parse(app_media_t *media,const uint8_t *header,uint32_t length);
bool app_media_command(app_media_t *media,uint8_t *packet,uint8_t length);
uint32_t app_media_frame_address(const app_media_t *media);
void app_media_advance(app_media_t *media,uint32_t now);
