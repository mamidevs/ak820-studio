"""One bounded main-thread HID cycle, isolated from HTTP/native run loops."""
import json,sys
from .qmk_transport import QmkTransport, BridgeUnsupported

def main():
    try:
        data=json.loads(sys.stdin.read(16384))
        out=QmkTransport().cycle(data['session'],data['sequence'],data['new_session'],data.get('sources',{}),data.get('settings'),data.get('media_show'),data.get('rgb_settings'))
    except BridgeUnsupported as exc:out={'connected':False,'unsupported':True,'message':str(exc)}
    except Exception as exc:out={'connected':False,'message':str(exc)}
    print(json.dumps(out,ensure_ascii=False),flush=True)
if __name__=='__main__':main()
