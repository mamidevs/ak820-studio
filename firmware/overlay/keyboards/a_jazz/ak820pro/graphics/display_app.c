// SPDX-License-Identifier: GPL-2.0-or-later
// GC9107 setup/sleep sequence derived from fpb's display_qp.c at 8777e05.
// Single owner of boot/home/menu pixels; no old splash/clock/media overlay.
#include "quantum.h"
#include "qp.h"
#include "qp_comms.h"
#include "gpio.h"
#include "graphics/display.h"
#include "graphics/lcd_bus.h"
#include "app_menu/app_menu.h"
#include "app_menu/app_bridge.h"
#include "app_menu/app_media.h"
#include "app_menu/app_raster.h"
#include "app_menu/menu_input_adapter.h"
#include "app_menu/display_app.h"
#include "bluetooth/ch582f_ajazz.h"
#include "usb_main.h"

#define PANEL_DC D14
#define PANEL_CS B8
#define PANEL_RST A17
#define PANEL_BKL A16

static painter_device_t panel;
static app_menu_t menu, frame;
static app_bridge_t bridge;
static app_media_t media;
static bool media_mode, painting_media;
static uint16_t media_frame=UINT16_MAX, frozen_media_frame;
static app_raster_t raster;
static bool ready, powered=true, paused, slept, resume_animation, painting;
static uint8_t next_top;
static uint32_t last_tile, last_snapshot;
/* What the panel holds per 8-row band; a band whose pixels did not change is
 * not sent again. Cleared whenever the panel content is unknown. */
static uint32_t band_hash[128/APP_TILE_ROWS];
static bool bands_known;

static void invalidate(void) { menu.dirty=true; painting=false; bands_known=false; }
bool display_get_power(void) { return powered; }
void display_set_power(bool on) {
    powered=on;
    menu.device.screen_on=on;
    gpio_write_pin(PANEL_BKL,on&&!slept);
    invalidate();
}
void display_toggle_power(void) { display_set_power(!powered); }
void display_set_paused(bool value) { paused=value; invalidate(); }

void display_enter_sleep(void) {
    if(slept||!ready)return;
    slept=true;
    resume_animation=anim_active();
    if(resume_animation)anim_toggle();
    display_set_paused(true);
    qp_power(panel,false);
    gpio_write_pin(PANEL_BKL,false);
}
void display_exit_sleep(void) {
    if(!slept||!ready)return;
    slept=false;
    qp_power(panel,true);
    gpio_write_pin(PANEL_BKL,powered);
    if(resume_animation)anim_toggle();
    else display_set_paused(false);
}

bool display_init_kb(void) {
    panel=qp_gc9107_make_spi_device(128,128,PANEL_CS,PANEL_DC,PANEL_RST,2,3);
    if(!panel)return false;
    qp_set_viewport_offsets(panel,1,2);
#if defined(LCD_PANEL_V2)
    if(!qp_init(panel,QP_ROTATION_90))return false;
    qp_comms_start(panel); qp_comms_command(panel,0x21); qp_comms_stop(panel);
#else
    if(!qp_init(panel,QP_ROTATION_270))return false;
#endif
    app_menu_init(&menu,&app_raster_renderer,&raster);
    app_bridge_init(&bridge,&menu);
    app_media_init(&media);
    app_qmk_bind(&menu);
    // No Codex/Claude snapshot is silently embedded in the device build.
    gpio_set_pin_output(PANEL_BKL);
    gpio_write_pin(PANEL_BKL,powered);
    ready=true;
    return true;
}

void display_housekeeping_task(void) {
    if(!ready)return;
    const uint32_t now=timer_read32();
    app_qmk_tick(now);
    app_bridge_tick(&bridge,now);
    /* Device and RGB state change on human time scales: sample every 20 ms
     * instead of on every pass of the scan loop. */
    if(now-last_snapshot<20u)return;
    last_snapshot=now;
    app_device_snapshot_t snapshot=menu.device;
    const uint8_t battery=ch582_get_battery();
    snapshot.battery=battery<=100?battery:255;
    snapshot.charging=!gpio_read_pin(CHARGE_CHRG_PIN)&&gpio_read_pin(CHARGE_STDBY_PIN);
    snapshot.usb_active=USB_DRIVER.state==USB_ACTIVE;
    snapshot.route=ch582_is_usb()?0:ch582_is_24g()?2:1;
    snapshot.slot=ch582_get_target_slot();
    snapshot.radio_state=(uint8_t)ch582_get_conn_state();
    snapshot.screen_on=powered;
    snapshot.caps_lock=host_keyboard_led_state().caps_lock;
    /* Studio keymap: default layer 2 is the Mac base (switch position). */
    snapshot.os=get_highest_layer(default_layer_state)>=2?APP_OS_MAC:APP_OS_WINDOWS;
    snapshot.media_available=media.available&&!media.uploading;
    snapshot.media_show=media.show;
    app_menu_set_device_snapshot(&menu,&snapshot);
    app_qmk_sync_rgb();
}

uint32_t app_display_sleep_timeout_ms(void) {
    return ready?(uint32_t)menu.device.sleep_minutes*60000u:DISPLAY_SLEEP_TIMEOUT_MS;
}

bool app_display_hid_command(uint8_t *data,uint8_t length) {
    if(!ready)return false;
    if(app_media_command(&media,data,length)) { invalidate();return true; }
    const bool handled=app_bridge_handle(&bridge,data,length,timer_read32());
    if(handled&&length==APP_BRIDGE_LENGTH&&data[2]==0x83&&data[6]==APP_BRIDGE_OK)
        display_set_power(menu.device.screen_on);
    return handled;
}

void app_display_media_toggle(void) {
    if(!ready||!media.available||media.uploading)return;
    media.show=!media.show;media.frame_started=0;invalidate();
}

void app_display_task(void) {
    // Check before every tile. Never share SPI0 with animation DMA or sleep.
    if(!ready||slept||!powered||paused||anim_active()||lcd_blit_busy())return;
    if(timer_elapsed32(last_tile)<4)return;
    /* Typing wins: a band costs up to ~1 ms of CPU and SPI, so hold the paint
     * inside a burst of key presses; the gaps between keystrokes are enough. */
    if(last_matrix_activity_elapsed()<50)return;
    last_tile=timer_read32();
    const bool want_media=media.available&&media.show&&!media.uploading&&menu.page==APP_PAGE_HOME&&!menu.menu_active;
    if(want_media!=media_mode){media_mode=want_media;media_frame=UINT16_MAX;invalidate();}
    if(!painting) {
        if(want_media){
            app_media_advance(&media,last_tile);
            if(media.index==media_frame)return;
            frozen_media_frame=media.index;painting_media=true;
        }else{
            if(!menu.dirty)return;
            frame=menu; /* freeze this frame; later input dirties the next frame */
            painting_media=false;
        }
        menu.dirty=false;
        next_top=0; painting=true;
    }
    raster.top=next_top;
    if(painting_media){
        if(flash_busy())return;
        const uint32_t address=APP_MEDIA_BASE+APP_MEDIA_HEADER_BYTES+(uint32_t)frozen_media_frame*APP_MEDIA_FRAME_BYTES+(uint32_t)next_top*256u;
        flash_read_bytes(address,raster.bytes,sizeof raster.bytes);
        bands_known=false;
    }else{
        app_menu_render(&frame); /* clipping writes only this 8-row RGB565 band */
        const uint32_t hash=app_raster_hash(&raster);
        const uint8_t band=next_top/APP_TILE_ROWS;
        if(bands_known&&band_hash[band]==hash){ /* panel already shows it */
            next_top+=APP_TILE_ROWS;
            if(next_top>=128)painting=false;
            return;
        }
        band_hash[band]=hash;
    }
    if(!qp_viewport(panel,0,next_top,127,next_top+APP_TILE_ROWS-1) ||
       !qp_pixdata(panel,raster.bytes,128u*APP_TILE_ROWS) || !qp_flush(panel)) {
        invalidate();
        return;
    }
    next_top+=APP_TILE_ROWS;
    if(next_top>=128){
        painting=false;
        if(painting_media)media_frame=frozen_media_frame;
        else bands_known=true; /* every band now matches band_hash */
    }
}

// Existing callers may change hardware status or end an animation. They only
// invalidate our current page; none draws a stock icon/clock over an open menu.
uint32_t display_redraw_dashboard(uint32_t when,void *context) {
    (void)when;(void)context;invalidate();return 0;
}
void display_draw_mac_logo(void) { invalidate(); }
void display_draw_windows_logo(void) { invalidate(); }
void display_draw_usb_logo(void) { invalidate(); }
void display_draw_bluetooth_logo(void) { invalidate(); }
void display_draw_2_4_g_logo(void) { invalidate(); }
void display_toggle_media(void) { invalidate(); }
bool display_blink(uint16_t period_ms) { return !period_ms||timer_read32()%period_ms<period_ms/2; }
