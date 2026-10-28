#include "app_media.h"
#include "graphics/flash_io.h"
#include <string.h>
static uint16_t get16(const uint8_t *p){return (uint16_t)p[0]|((uint16_t)p[1]<<8);}
static uint32_t get32(const uint8_t *p){return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);}
static void put16(uint8_t *p,uint16_t x){p[0]=(uint8_t)x;p[1]=(uint8_t)(x>>8);}
static void put32(uint8_t *p,uint32_t x){for(uint8_t i=0;i<4;i++)p[i]=(uint8_t)(x>>(8*i));}
static bool zeros(const uint8_t *p,uint8_t n){for(uint8_t i=0;i<n;i++)if(p[i])return false;return true;}
bool app_media_parse(app_media_t *m,const uint8_t *h,uint32_t length){
    if(!m||!h||length<256||memcmp(h,"AKM2",4)||h[4]!=2||h[5]!=0)return false;
    uint16_t count=get16(h+6);
    if(count<1||count>APP_MEDIA_MAX_FRAMES||get32(h+8)!=(uint32_t)count*APP_MEDIA_FRAME_BYTES)return false;
    for(uint16_t i=0;i<count;i++)if(get16(h+16+i*2)<APP_MEDIA_MIN_DELAY||get16(h+16+i*2)>10000)return false;
    m->count=count;m->crc=get32(h+12);m->index=0;m->frame_started=0;m->available=true;
    for(uint16_t i=0;i<count;i++)m->delays[i]=get16(h+16+i*2);
    return true;
}
static bool reload(app_media_t *m){
    uint8_t h[256];
    if(flash_busy())return false;
    flash_read_bytes(APP_MEDIA_BASE,h,sizeof h);
    return app_media_parse(m,h,sizeof h);
}
void app_media_init(app_media_t *m){memset(m,0,sizeof *m);reload(m);}
uint32_t app_media_frame_address(const app_media_t *m){return APP_MEDIA_BASE+APP_MEDIA_HEADER_BYTES+(uint32_t)m->index*APP_MEDIA_FRAME_BYTES;}
void app_media_advance(app_media_t *m,uint32_t now){
    if(!m->available||!m->show||m->uploading)return;
    if(!m->frame_started){m->frame_started=now;return;}
    if((uint32_t)(now-m->frame_started)>=m->delays[m->index]){m->index=(uint16_t)((m->index+1)%m->count);m->frame_started=now;}
}
bool app_media_command(app_media_t *m,uint8_t *p,uint8_t length){
    if(!m||!p||length<2||p[0]!=7||p[1]!=0x14)return false;
    if(length<7)return true;
    if(length!=32||p[3]!=1||p[6]||p[7]||!get32(p+8)){p[6]=2;return true;}
    const uint8_t cmd=p[2];
    if(cmd<0x90||cmd>0x94){p[6]=7;return true;}
    if(!zeros(p+(cmd==0x93?13:12),(uint8_t)(cmd==0x93?19:20))||(cmd==0x93&&p[12]>1)){p[6]=4;return true;}
    if(cmd==0x91){m->show=false;m->uploading=true;m->available=false;}
    else if(cmd==0x92){if(!reload(m)){p[6]=4;return true;}m->uploading=false;m->show=true;}
    else if(cmd==0x93){if(p[12]&&(!m->available||m->uploading)){p[6]=4;return true;}m->show=p[12]!=0;m->frame_started=0;}
    else if(cmd==0x94){m->uploading=false;m->show=false;}
    p[6]=1;memset(p+12,0,20);p[12]=m->available;p[13]=m->show;p[14]=m->uploading;p[15]=APP_MEDIA_MAX_FRAMES;
    put16(p+16,m->available?m->count:0);put32(p+18,m->available?(uint32_t)m->count*APP_MEDIA_FRAME_BYTES:0);put32(p+22,m->crc);put16(p+26,APP_MEDIA_MIN_DELAY);
    memcpy(p+28,"MED2",4);return true;
}
