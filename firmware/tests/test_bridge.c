#include "app_bridge.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <limits.h>
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)){fprintf(stderr,"FAIL line %d: %s\n",__LINE__,#x);exit(1);} } while(0)
static void put32(uint8_t *p,uint32_t x){for(int i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
static void packet(uint8_t *p,uint8_t cmd,uint16_t seq,uint32_t session){
    memset(p,0,32);p[0]=7;p[1]=0x13;p[2]=cmd;p[3]=1;p[4]=(uint8_t)seq;p[5]=(uint8_t)(seq>>8);put32(p+8,session);
}
static void hello(app_bridge_t *b,uint16_t seq,uint32_t session,uint32_t now){
    uint8_t p[32];packet(p,0x80,seq,session);p[7]=1;
    CHECK(app_bridge_handle(b,p,32,now));CHECK(p[6]==1);CHECK(!memcmp(p+24,"AST2",4));
}
static void rejected(app_bridge_t *b,uint8_t *p,uint8_t len,uint8_t status){
    app_bridge_t previous=*b;app_menu_t menu=*b->menu;
    CHECK(app_bridge_handle(b,p,len,1000));CHECK(p[6]==status);
    CHECK(!memcmp(&previous,b,sizeof(*b)));CHECK(!memcmp(&menu,b->menu,sizeof(menu)));
}
static void snapshot(uint8_t *p,uint8_t cmd,uint16_t seq,uint32_t session){
    packet(p,cmd,seq,session);p[7]=1;p[12]=94;p[13]=255;put32(p+14,1792313625u);put32(p+22,2);
}
static void test_validation_sequence(void){
    app_menu_t m;app_bridge_t b;uint8_t p[32];app_menu_init(&m,NULL,NULL);app_bridge_init(&b,&m);
    packet(p,0x80,1,7);rejected(&b,p,32,APP_BRIDGE_BAD_SESSION);
    hello(&b,65534,7,100);
    CHECK(m.host_link==APP_LINK_LIVE);CHECK(m.device.battery==255);CHECK(!m.codex.weekly_available);
    snapshot(p,0x81,65535,7);CHECK(app_bridge_handle(&b,p,32,200));CHECK(p[6]==1);
    CHECK(m.codex.weekly_available&&m.codex.weekly_used_percent==94&&!m.codex.short_available);
    CHECK(m.codex.weekly_resets_at==1792313625u&&m.codex.age_seconds==2);
    snapshot(p,0x82,0,7);p[7]=3;p[12]=100;p[13]=0;CHECK(app_bridge_handle(&b,p,32,300));CHECK(p[6]==1);
    CHECK(m.claude.weekly_used_percent==100&&m.claude.short_used_percent==0);
    snapshot(p,0x81,0,7);rejected(&b,p,32,APP_BRIDGE_OLD_SEQUENCE);
    snapshot(p,0x81,65535,7);rejected(&b,p,32,APP_BRIDGE_OLD_SEQUENCE);
    snapshot(p,0x81,1,8);rejected(&b,p,32,APP_BRIDGE_BAD_SESSION);
    snapshot(p,0x81,1,7);p[12]=101;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    snapshot(p,0x81,1,7);p[13]=0;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    snapshot(p,0x81,1,7);p[18]=1;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    snapshot(p,0x81,1,7);p[31]=1;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    snapshot(p,0x81,1,7);p[7]=4;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    snapshot(p,0x81,1,7);p[3]=2;rejected(&b,p,32,APP_BRIDGE_BAD_VERSION);
    snapshot(p,0x81,1,7);rejected(&b,p,31,APP_BRIDGE_BAD_LENGTH);
    packet(p,0x85,1,7);rejected(&b,p,32,APP_BRIDGE_BAD_COMMAND);
    packet(p,0x84,1,7);rejected(&b,p,32,APP_BRIDGE_BAD_VALUE); /* epoch 0 */
    packet(p,0x84,1,7);put32(p+12,1791736920u);p[16]=(uint8_t)(-841&255);p[17]=(uint8_t)((-841>>8)&255);rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    packet(p,0x84,1,7);put32(p+12,1791736920u);p[16]=180;CHECK(app_bridge_handle(&b,p,32,400));CHECK(p[6]==1);
    CHECK(m.wall_clock_epoch==1791736920u&&m.utc_offset_minutes==180&&app_menu_now_epoch(&m)==1791736920u);
    packet(p,0x80,2,7);p[12]=1;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    packet(p,0x80,2,7);p[6]=1;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    packet(p,0x80,2,0);p[7]=1;rejected(&b,p,32,APP_BRIDGE_BAD_SESSION);
    hello(&b,1,8,500);CHECK(!m.codex.weekly_available&&!m.claude.short_available);
    CHECK(m.codex.age_seconds==UINT32_MAX);
    packet(p,0x80,2,8);p[1]=0x12;CHECK(!app_bridge_handle(&b,p,32,500));
    CHECK(!app_bridge_handle(&b,NULL,32,500));
    packet(p,0x80,2,8);CHECK(app_bridge_handle(&b,p,2,500));CHECK(b.sequence==1);
}
static void test_ages_settings_telemetry(void){
    app_menu_t m;app_bridge_t b;uint8_t p[32];app_menu_init(&m,NULL,NULL);app_bridge_init(&b,&m);
    m.device=(app_device_snapshot_t){85,true,true,1,2,3,true,3,false,0,false,false};m.uptime_ms=12000;
    packet(p,0x80,1,99);p[7]=1;CHECK(app_bridge_handle(&b,p,32,UINT32_MAX-1000u));
    CHECK(p[12]==85&&p[13]==3&&p[14]==1&&p[15]==2&&p[16]==3&&p[17]==1&&p[18]==3&&p[20]==12);
    snapshot(p,0x81,2,99);put32(p+22,299);CHECK(app_bridge_handle(&b,p,32,UINT32_MAX-500u));
    app_bridge_tick(&b,499);CHECK(m.codex.age_seconds==300);CHECK(m.host_link==APP_LINK_LIVE);
    app_bridge_tick(&b,15000);CHECK(m.host_link==APP_LINK_STALE);
    app_bridge_tick(&b,60000);CHECK(m.host_link==APP_LINK_OFFLINE);
    packet(p,0x80,3,99);CHECK(app_bridge_handle(&b,p,32,60001));CHECK(m.host_link==APP_LINK_LIVE);
    packet(p,0x83,4,99);p[12]=0;p[13]=15;CHECK(app_bridge_handle(&b,p,32,60002));
    CHECK(p[6]==1&&p[17]==0&&p[18]==15&&!memcmp(p+24,"AST2",4));
    CHECK(!m.device.screen_on&&m.device.sleep_minutes==15);
    packet(p,0x83,5,99);p[12]=255;p[13]=255;CHECK(app_bridge_handle(&b,p,32,60003));
    CHECK(p[6]==1&&!m.device.screen_on&&m.device.sleep_minutes==15);
    packet(p,0x83,6,99);p[12]=1;p[13]=2;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    packet(p,0x83,6,99);p[12]=2;p[13]=5;rejected(&b,p,32,APP_BRIDGE_BAD_VALUE);
    packet(p,0x83,6,99);p[12]=1;p[13]=0;CHECK(app_bridge_handle(&b,p,32,60004));
    CHECK(m.device.screen_on&&m.device.sleep_minutes==0);
    packet(p,0x82,7,99);p[12]=p[13]=255;put32(p+22,UINT32_MAX);CHECK(app_bridge_handle(&b,p,32,60005));
    app_bridge_tick(&b,90005);CHECK(!m.claude.weekly_available&&!m.claude.short_available&&m.claude.age_seconds==UINT32_MAX);
    /* Packet state updates do not change menu routing or emit media keys. */
    m.page=APP_PAGE_DISPLAY;m.menu_active=true;m.focus=1;m.editing=true;
    app_event_result_t r=app_menu_handle(&m,(app_event_t){.type=APP_EVENT_ROTATE,.data.rotation=1});
    CHECK(m.device.sleep_minutes==1&&r.action==APP_ACTION_NONE);
    m.menu_active=false;m.editing=false;m.page=APP_PAGE_HOME;
    r=app_menu_handle(&m,(app_event_t){.type=APP_EVENT_ROTATE,.data.rotation=1});CHECK(r.action==APP_ACTION_VOLUME_UP);
}
int main(void){test_validation_sequence();test_ages_settings_telemetry();printf("PASS: Studio bridge %u checks; no device access.\n",checks);return 0;}
