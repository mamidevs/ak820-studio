#include "app_bridge.h"
#include <string.h>

static uint16_t get16(const uint8_t *p) { return (uint16_t)((uint16_t)p[0]|((uint16_t)p[1]<<8)); }
static uint32_t get32(const uint8_t *p) { return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24); }
static void put32(uint8_t *p,uint32_t v) { for(uint8_t i=0;i<4;i++)p[i]=(uint8_t)(v>>(i*8)); }
static bool zeroes(const uint8_t *p,uint8_t n) { for(uint8_t i=0;i<n;i++)if(p[i])return false;return true; }
static bool valid_sleep(uint8_t v) { return v==0||v==1||v==5||v==15||v==30||v==255; }
static bool reject(uint8_t *data,uint8_t status) { data[6]=status;return true; }

void app_bridge_init(app_bridge_t *bridge,app_menu_t *menu) {
    if(!bridge)return;
    memset(bridge,0,sizeof(*bridge));bridge->menu=menu;
}

static void telemetry(const app_menu_t *menu,uint8_t *data) {
    memset(data+12,0,20);
    data[12]=menu->device.battery;
    data[13]=(uint8_t)((menu->device.charging?1:0)|(menu->device.usb_active?2:0));
    data[14]=menu->device.route;data[15]=menu->device.slot;data[16]=menu->device.radio_state;
    data[17]=menu->device.screen_on?1:0;data[18]=menu->device.sleep_minutes;
    put32(data+20,menu->uptime_ms/1000u);memcpy(data+24,"AST2",4);
}

bool app_bridge_handle(app_bridge_t *bridge,uint8_t *data,uint8_t length,uint32_t now_ms) {
    if(!bridge||!bridge->menu||!data||length<2||data[0]!=0x07||data[1]!=APP_BRIDGE_CHANNEL)return false;
    if(length<7)return true; /* A short reply cannot safely carry status. */
    if(length!=APP_BRIDGE_LENGTH)return reject(data,APP_BRIDGE_BAD_LENGTH);
    if(data[3]!=APP_BRIDGE_VERSION)return reject(data,APP_BRIDGE_BAD_VERSION);
    if(data[6]!=0)return reject(data,APP_BRIDGE_BAD_VALUE);
    const uint8_t cmd=data[2], flags=data[7];
    if(cmd<0x80||cmd>0x84)return reject(data,APP_BRIDGE_BAD_COMMAND);
    const uint32_t session=get32(data+8);
    if(!session)return reject(data,APP_BRIDGE_BAD_SESSION);
    if(cmd==0x80) {
        if(flags>1||!zeroes(data+12,20))return reject(data,APP_BRIDGE_BAD_VALUE);
    } else if(cmd==0x84) {
        const int16_t offset=(int16_t)get16(data+16);
        if(flags||!get32(data+12)||offset < -840||offset > 840||!zeroes(data+18,14))
            return reject(data,APP_BRIDGE_BAD_VALUE);
    } else if(cmd==0x83) {
        if(flags||!(data[12]==0||data[12]==1||data[12]==255)||!valid_sleep(data[13])||!zeroes(data+14,18))
            return reject(data,APP_BRIDGE_BAD_VALUE);
    } else {
        if(flags&~3u||!zeroes(data+26,6))return reject(data,APP_BRIDGE_BAD_VALUE);
        for(uint8_t i=0;i<2;i++) {
            const bool available=(flags&(1u<<i))!=0;
            if((available&&data[12+i]>100)||(!available&&(data[12+i]!=255||get32(data+14+i*4)!=0)))
                return reject(data,APP_BRIDGE_BAD_VALUE);
        }
    }
    const bool new_session=cmd==0x80&&flags==1&&session!=bridge->session;
    if(!new_session&&session!=bridge->session)return reject(data,APP_BRIDGE_BAD_SESSION);
    const uint16_t sequence=get16(data+4);
    const uint16_t delta=(uint16_t)(sequence-bridge->sequence);
    if(!new_session&&(delta==0||delta>=32768u))return reject(data,APP_BRIDGE_OLD_SEQUENCE);

    /* All checks precede state mutation; settings and snapshots are atomic. */
    app_menu_t *menu=bridge->menu;
    if(new_session) {
        bridge->session=session;
        memset(bridge->source_seen,0,sizeof(bridge->source_seen));
        app_menu_set_codex_snapshot(menu,NULL);app_menu_set_claude_snapshot(menu,NULL);
    }
    bridge->sequence=sequence;bridge->last_contact=now_ms;
    if(menu->host_link!=APP_LINK_LIVE) { menu->host_link=APP_LINK_LIVE;menu->dirty=true; }
    if(cmd==0x81||cmd==0x82) {
        const uint8_t provider=(uint8_t)(cmd-0x81);
        app_usage_snapshot_t usage={0};
        usage.weekly_available=(flags&1)!=0;usage.short_available=(flags&2)!=0;
        usage.weekly_used_percent=data[12];usage.short_used_percent=data[13];
        usage.weekly_resets_at=get32(data+14);usage.short_resets_at=get32(data+18);
        usage.age_seconds=get32(data+22);
        bridge->source_seen[provider]=true;bridge->source_tick[provider]=now_ms;bridge->source_age[provider]=usage.age_seconds;
        bridge->age_ms=now_ms;
        if(provider==0)app_menu_set_codex_snapshot(menu,&usage);else app_menu_set_claude_snapshot(menu,&usage);
    } else if(cmd==0x84) {
        app_menu_set_clock(menu,get32(data+12),(int16_t)get16(data+16));
    } else if(cmd==0x83) {
        if(data[12]!=255)menu->device.screen_on=data[12]!=0;
        if(data[13]!=255)menu->device.sleep_minutes=data[13];
        menu->dirty=true;
    }
    data[6]=APP_BRIDGE_OK;
    if(cmd==0x80||cmd==0x83)telemetry(menu,data);
    return true;
}

void app_bridge_tick(app_bridge_t *bridge,uint32_t now_ms) {
    if(!bridge||!bridge->menu)return;
    app_menu_t *menu=bridge->menu;
    const uint32_t elapsed=now_ms-bridge->last_contact;
    const app_link_t link=!bridge->session?APP_LINK_UNKNOWN:
        elapsed>=APP_BRIDGE_OFFLINE_MS?APP_LINK_OFFLINE:elapsed>=APP_BRIDGE_STALE_MS?APP_LINK_STALE:APP_LINK_LIVE;
    if(menu->host_link!=link) { menu->host_link=link;menu->dirty=true; }
    /* Ages advance every second but only crossing the stale limit is drawn:
     * refresh them a few times a second and repaint only on that change. */
    if(now_ms-bridge->age_ms<250u)return;
    bridge->age_ms=now_ms;
    for(uint8_t i=0;i<2;i++) {
        if(!bridge->source_seen[i])continue;
        app_usage_snapshot_t *usage=i?&menu->claude:&menu->codex;
        const uint32_t extra=(now_ms-bridge->source_tick[i])/1000u,base=bridge->source_age[i];
        const uint32_t age=extra>UINT32_MAX-base?UINT32_MAX:base+extra;
        const bool fresh_before=usage->age_seconds<APP_USAGE_FRESH_SECONDS,fresh_now=age<APP_USAGE_FRESH_SECONDS;
        /* Stale tiles print "N dk önce": then a new minute of age is news too. */
        if(fresh_before!=fresh_now||((link!=APP_LINK_LIVE||!fresh_now)&&usage->age_seconds/60u!=age/60u))menu->dirty=true;
        usage->age_seconds=age;
    }
}
