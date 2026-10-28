#!/usr/bin/env python3
"""Control the running Studio's local data forwarding; never sign accounts out."""
import argparse
import json
import sys
import urllib.error
import urllib.request

def main():
    parser=argparse.ArgumentParser(description='AK820 Studio AI bağlantıları')
    parser.add_argument('provider',choices=['codex','claude_code','all'])
    parser.add_argument('action',choices=['status','connect','disconnect','refresh','setup'],nargs='?',default='status')
    parser.add_argument('--port',type=int,default=8765)
    args=parser.parse_args()
    if not 1024<=args.port<=65535:parser.error('Geçersiz yerel port.')
    base=f'http://127.0.0.1:{args.port}'
    def request(path,body=None,token=None):
        headers={'Content-Type':'application/json','Origin':base}
        if token:headers['X-AK820-Token']=token
        req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
        with urllib.request.urlopen(req,timeout=20) as response:return json.load(response)
    try:
        if args.action=='status':result=request('/api/connections')
        else:
            token=request('/api/state')['token']
            providers=['codex','claude_code'] if args.provider=='all' else [args.provider]
            for provider in providers:result=request(f'/api/connections/{provider}/{args.action}',{},token)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except urllib.error.HTTPError as exc:
        try:message=json.load(exc).get('error','İşlem tamamlanamadı.')
        except Exception:message='İşlem tamamlanamadı.'
        print(message,file=sys.stderr);return 1
    except (OSError,ValueError,KeyError):
        print('Studio açık değil veya yanıt vermiyor. Önce AK820 Studio.command dosyasını açın.',file=sys.stderr)
        return 1

if __name__=='__main__':sys.exit(main())
