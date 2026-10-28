#pragma once
#include <stdint.h>
#include <stdbool.h>
/* Called by studio keymap housekeeping. One 128x8 tile per eligible scan. */
void app_display_task(void);
bool app_display_hid_command(uint8_t *data,uint8_t length);
uint32_t app_display_sleep_timeout_ms(void);
void app_display_media_toggle(void);
/* Implemented in ak820pro.c: route 0 USB, 1 Bluetooth (slot 1..3), 2 2.4 GHz. */
void ak820_select_route(uint8_t route, uint8_t bt_slot);
void ak820_pair_route(void);
