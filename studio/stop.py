"""Stop this app's detached local process group, refusing stale/unrelated PIDs."""
from pathlib import Path
import os
import signal
import subprocess
ROOT=Path(__file__).resolve().parent
file=ROOT/'work'/'state'/'server.pid'
if not file.exists():
    print('Çalışan servis kaydı bulunamadı.')
else:
    pid=int(file.read_text())
    info=subprocess.run(['ps','-p',str(pid),'-o','command='],capture_output=True,text=True).stdout
    if '-m ak820.server' in info and str(ROOT/'work'/'state') in info and os.getpgid(pid)==pid:
        os.killpg(pid,signal.SIGTERM)
        file.unlink(missing_ok=True)
        print('AK820 Studio durduruldu.')
    else:
        print('Servis kapalı veya kayıt başka bir işleme ait; işlem yapılmadı.')
