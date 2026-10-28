"""Private subprocess boundary. Invoked by server only after a deliberate send."""
import json
from pathlib import Path
import sys
from .transport import NativeTransport


def emit(value):
    print(json.dumps(value,ensure_ascii=False),flush=True)


def main():
    try:
        if sys.argv[1:] == ['--detect']:
            value=NativeTransport().detect()
            if value.get('connected'):
                value['firmware']='stock'
                value['stock_controls_available']=True
            else:
                from .qmk_transport import detect
                qmk=detect()
                if qmk.get('connected'): value=qmk
            emit(value)
            return 0
        if len(sys.argv)==3 and sys.argv[1]=='--rgb':
            settings=json.loads(Path(sys.argv[2]).read_text())
            result=NativeTransport(timeout_seconds=15).send_rgb(settings,progress=emit)
        else:
            payload=Path(sys.argv[1]).read_bytes()
            result=NativeTransport().send(payload,progress=emit)
        emit({'event':'complete','result':result})
    except Exception as e:
        emit({'event':'error','message':str(e)})
        return 1
    return 0

if __name__=='__main__': sys.exit(main())
