#ifndef AK820_APP_MENU_H
#define AK820_APP_MENU_H

/* Portable application core for the AK820 128x128 screen. No USB, display
 * driver or firmware hooks: the adapter feeds events and device/host snapshots,
 * executes the returned action intents and supplies a renderer.
 * Call from one event-loop context. Renderer callbacks are synchronous.
 */
#include <stdbool.h>
#include <stdint.h>

#define APP_SCREEN_WIDTH 128u
#define APP_SCREEN_HEIGHT 128u
#define APP_BOOT_DURATION_MS 900u
#define APP_MENU_TIMEOUT_MS 30000u /* an idle menu hands the knob back */
#define APP_TOAST_MS 1400u
#define APP_CLOCK_POLL_MS 250u        /* minute roll-over is drawn within this */
#define APP_USAGE_FRESH_SECONDS 300u  /* older usage data is drawn as stale */

typedef enum {
    APP_PAGE_BOOT = 0,
    APP_PAGE_HOME,
    APP_PAGE_MENU,
    APP_PAGE_CODEX,
    APP_PAGE_CLAUDE,
    APP_PAGE_LIGHT,
    APP_PAGE_KNOB,
    APP_PAGE_DISPLAY,
    APP_PAGE_DEVICE,
    APP_PAGE_SHORTCUTS,
    APP_PAGE_LINK,
    APP_PAGE_COUNT
} app_page_t;

#define APP_MENU_ITEM_COUNT 9u /* every page except BOOT and MENU */

typedef enum {
    APP_EVENT_TICK = 0,
    APP_EVENT_FN_CHANGED,
    APP_EVENT_KNOB_PRESS,
    APP_EVENT_ROTATE,
    APP_EVENT_BACK
} app_event_type_t;

typedef struct {
    app_event_type_t type;
    union {
        uint32_t elapsed_ms; /* TICK: elapsed interval, not an absolute clock. */
        int16_t rotation;    /* ROTATE: positive clockwise. */
        bool fn_held;        /* FN_CHANGED: caller's actual Fn key state. */
    } data;
} app_event_t;

/* Intents only: the adapter decides whether and how to execute them. */
typedef enum {
    APP_ACTION_NONE = 0,
    APP_ACTION_VOLUME_UP,
    APP_ACTION_VOLUME_DOWN,
    APP_ACTION_MUTE_TOGGLE,
    APP_ACTION_MEDIA_NEXT,
    APP_ACTION_MEDIA_PREV,
    APP_ACTION_MEDIA_PLAY,
    APP_ACTION_BRIGHT_UP,
    APP_ACTION_BRIGHT_DOWN,
    APP_ACTION_ZOOM_IN,
    APP_ACTION_ZOOM_OUT,
    APP_ACTION_ZOOM_RESET,
    APP_ACTION_RGB_TOGGLE,
    APP_ACTION_RGB_NEXT,
    APP_ACTION_RGB_PREV,
    APP_ACTION_RGB_VAL_UP,
    APP_ACTION_RGB_VAL_DOWN,
    APP_ACTION_RGB_HUE_UP,
    APP_ACTION_RGB_HUE_DOWN,
    APP_ACTION_RGB_SAT_UP,
    APP_ACTION_RGB_SAT_DOWN,
    APP_ACTION_RGB_SPEED_UP,
    APP_ACTION_RGB_SPEED_DOWN,
    APP_ACTION_MEDIA_SHOW_TOGGLE, /* uploaded GIF on the home screen */
    APP_ACTION_SCREEN_OFF,
    APP_ACTION_ROUTE_USB,
    APP_ACTION_ROUTE_BT,          /* amount = Bluetooth slot 1..3 */
    APP_ACTION_ROUTE_24G,
    APP_ACTION_PAIR,              /* pair the active Bluetooth slot */
    APP_ACTION_OS_MAC,            /* Mac key layout (default layer) */
    APP_ACTION_OS_WINDOWS
} app_action_t;

typedef struct {
    app_action_t action;
    uint16_t amount; /* Detents, or 1; the slot for APP_ACTION_ROUTE_BT. */
    bool redraw;
} app_event_result_t;

typedef enum {
    APP_KNOB_VOLUME = 0,
    APP_KNOB_MEDIA,
    APP_KNOB_BRIGHTNESS,
    APP_KNOB_LIGHT,
    APP_KNOB_ZOOM,
    APP_KNOB_COUNT
} app_knob_mode_t;

typedef enum { APP_FACE_RINGS = 0, APP_FACE_CLOCK, APP_FACE_COUNT } app_face_t;

typedef enum {
    APP_FX_OTHER = 0,
    APP_FX_SOLID,
    APP_FX_BREATHING,
    APP_FX_BAND_SAT,
    APP_FX_CYCLE_ALL,
    APP_FX_CYCLE_LEFT_RIGHT,
    APP_FX_CYCLE_UP_DOWN,
    APP_FX_CHEVRON,
    APP_FX_PINWHEEL,
    APP_FX_RAINDROPS,
    APP_FX_HEATMAP,
    APP_FX_COUNT
} app_effect_t;

/* Coordinates are physical pixels inside the 128 x 128 canvas. */
typedef struct {
    void (*clear)(void *user, uint16_t rgb565);
    void (*rect)(void *user, int16_t x, int16_t y, uint16_t width, uint16_t height, uint16_t rgb565);
    void (*text)(void *user, int16_t x, int16_t y, const char *utf8, uint16_t rgb565, uint8_t font);
    /* Anti-aliased rounded rectangle; radius >= min(w,h)/2 draws a pill/disc. */
    void (*rrect)(void *user, int16_t x, int16_t y, uint16_t width, uint16_t height, uint8_t radius, uint16_t rgb565);
    /* Anti-aliased ring in the diameter box at x,y. permille >= 1000 is a full
     * ring; otherwise an arc clockwise from 12 o'clock with round caps. */
    void (*ring)(void *user, int16_t x, int16_t y, uint8_t diameter, uint8_t thickness, uint16_t permille, uint16_t rgb565);
    void (*icon)(void *user, int16_t x, int16_t y, uint8_t id, uint8_t size, uint16_t rgb565);
} app_renderer_t;

typedef struct {
    bool weekly_available;
    uint8_t weekly_used_percent;
    uint32_t weekly_resets_at; /* Unix seconds, informational; no wall-clock IO. */
    bool short_available;      /* false means unavailable, never zero usage. */
    uint8_t short_used_percent;
    uint32_t short_resets_at;
    uint32_t age_seconds;      /* UINT32_MAX = observation time unavailable. */
    char observed_label[16];   /* E.g. "11 OCT". Copied, always terminated. */
} app_usage_snapshot_t;

typedef enum { APP_LINK_UNKNOWN, APP_LINK_LIVE, APP_LINK_STALE, APP_LINK_OFFLINE } app_link_t;
typedef enum { APP_OS_UNKNOWN = 0, APP_OS_MAC, APP_OS_WINDOWS } app_os_t;

typedef struct {
    uint8_t battery;          /* 0..100 from CH582, 255 = unknown. */
    bool charging;
    bool usb_active;
    uint8_t route;            /* 0 USB, 1 Bluetooth, 2 dongle, 3 unknown. */
    uint8_t slot;
    uint8_t radio_state;      /* 0 idle, 1 linking, 2 pairing, 3 connected, 4 rejected. */
    bool screen_on;
    uint8_t sleep_minutes;    /* Real runtime setting; 0 disables idle sleep. */
    bool caps_lock;
    uint8_t os;               /* app_os_t, from the Mac/Windows switch. */
    bool media_available;     /* An uploaded GIF exists. */
    bool media_show;
} app_device_snapshot_t;

typedef struct {
    bool available;           /* false: no RGB matrix, the page says so. */
    bool enabled;
    uint8_t effect;           /* app_effect_t */
    uint8_t hue, sat, val, speed;
} app_rgb_snapshot_t;

typedef struct {
    app_page_t page;
    bool menu_active;    /* true on the menu and on pages opened from it. */
    bool fn_held;
    bool dirty;
    bool editing;        /* list page: rotation changes the focused value. */
    uint8_t selected;    /* menu item */
    uint8_t focus;       /* list page row; 0 is the back header */
    uint8_t knob_mode;   /* app_knob_mode_t */
    uint8_t face;        /* app_face_t */
    uint8_t toast;       /* toast kind, 0 = none */
    uint16_t toast_ms;
    uint32_t menu_idle_ms;
    uint32_t boot_elapsed_ms;
    uint32_t uptime_ms;
    uint32_t wall_clock_epoch;
    uint32_t clock_uptime_ms;
    int16_t utc_offset_minutes;
    uint16_t clock_minute; /* last drawn local minute, for minute redraws */
    uint16_t uptime_minute;
    uint32_t check_ms;     /* uptime of the last clock poll */
    app_renderer_t renderer;
    void *renderer_user;
    app_usage_snapshot_t codex;
    app_usage_snapshot_t claude;
    app_device_snapshot_t device;
    app_rgb_snapshot_t rgb;
    app_link_t host_link;
} app_menu_t;

void app_menu_init(app_menu_t *app, const app_renderer_t *renderer, void *user);
app_event_result_t app_menu_handle(app_menu_t *app, app_event_t event);
void app_menu_render(app_menu_t *app);
bool app_menu_set_codex_snapshot(app_menu_t *app, const app_usage_snapshot_t *snapshot);
bool app_menu_set_claude_snapshot(app_menu_t *app, const app_usage_snapshot_t *snapshot);
void app_menu_set_device_snapshot(app_menu_t *app, const app_device_snapshot_t *snapshot);
void app_menu_set_rgb_snapshot(app_menu_t *app, const app_rgb_snapshot_t *snapshot);
bool app_menu_set_clock(app_menu_t *app, uint32_t epoch, int16_t offset_minutes);
uint32_t app_menu_now_epoch(const app_menu_t *app);
const char *app_menu_page_name(app_page_t page);
const char *app_menu_item_name(uint8_t index);
app_page_t app_menu_item_page(uint8_t index);
uint8_t app_menu_row_count(app_page_t page); /* focusable rows incl. header */
uint16_t app_rgb565(uint8_t red, uint8_t green, uint8_t blue);

#endif
