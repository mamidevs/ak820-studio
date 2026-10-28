"""One explicit asset transfer; the parent owns the live bridge operation lock."""
import json
from pathlib import Path
import sys
from .qmk_transport import QmkTransport
from .qmk_media import AssetSender
def emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)
def main():
    try:
        payload=Path(sys.argv[1]).read_bytes()
        context=json.loads(sys.stdin.read(16384))
        with QmkTransport().connected() as transport:
            result=AssetSender(transport,context,emit).send(payload)
        emit({'event':'complete','result':result});return 0
    except Exception as exc:
        emit({'event':'error','message':str(exc)});return 1
if __name__=='__main__':sys.exit(main())
