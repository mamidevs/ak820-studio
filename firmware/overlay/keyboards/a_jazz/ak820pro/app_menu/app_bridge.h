#ifndef AK820_APP_BRIDGE_H
#define AK820_APP_BRIDGE_H
#include "app_menu.h"
#include <stddef.h>

#define APP_BRIDGE_CHANNEL 0x13u
#define APP_BRIDGE_LENGTH 32u
#define APP_BRIDGE_VERSION 1u
#define APP_BRIDGE_STALE_MS 15000u
#define APP_BRIDGE_OFFLINE_MS 60000u
#define APP_USAGE_STALE_SECONDS 300u

enum { APP_BRIDGE_OK=1, APP_BRIDGE_BAD_LENGTH, APP_BRIDGE_BAD_VERSION,
       APP_BRIDGE_BAD_VALUE, APP_BRIDGE_BAD_SESSION, APP_BRIDGE_OLD_SEQUENCE,
       APP_BRIDGE_BAD_COMMAND };
typedef struct {
    app_menu_t *menu;
    uint32_t session;
    uint16_t sequence;
    uint32_t last_contact;
    uint32_t source_age[2];
    uint32_t source_tick[2];
    uint32_t age_ms;          /* last age refresh; ages are polled, not per loop */
    bool source_seen[2];
} app_bridge_t;

void app_bridge_init(app_bridge_t *bridge, app_menu_t *menu);
/* True means Studio framing matched, including rejected malformed commands.
 * Only this mutable reply buffer is changed on rejection. No IO/flash/heap. */
bool app_bridge_handle(app_bridge_t *bridge, uint8_t *data, uint8_t length, uint32_t now_ms);
void app_bridge_tick(app_bridge_t *bridge, uint32_t now_ms);
#endif
