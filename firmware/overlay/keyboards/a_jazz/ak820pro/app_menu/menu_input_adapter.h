#pragma once
/* QMK side of the portable menu core: knob keycodes in, action intents out. */
#include "quantum.h"
#include "ak820pro.h"
#include "app_menu.h"

enum app_keycodes {
    APP_KNOB = AK820PRO_SAFE_RANGE,
    APP_KNOB_CCW,
    APP_KNOB_CW
};

void app_qmk_bind(app_menu_t *app);
bool app_qmk_process(uint16_t keycode, keyrecord_t *record, bool fn_active);
void app_qmk_tick(uint32_t now_ms);
/* Copies the live RGB matrix state into the menu; cheap, call every loop. */
void app_qmk_sync_rgb(void);
