#!/usr/bin/env python3
"""Start the local service independently of the terminal; no login item."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT=Path(__file__).resolve().parent

def python_runtime():
    """Use this checkout's environment when present, otherwise the caller's."""
    local=ROOT/'.venv'/'bin'/'python'
    return str(local) if local.is_file() else sys.executable

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--no-open',action='store_true')
    parser.add_argument('--port',type=int,default=8765)
    parser.add_argument('--simulate',choices=['connected','error','disconnected'])
    args=parser.parse_args()
    url=f'http://127.0.0.1:{args.port}'
    def ready():
        try:
            with urllib.request.urlopen(url+'/api/state',timeout=1) as response:
                state=json.load(response)
                return 'capabilities' in state and bool(state['device'].get('simulated'))==bool(args.simulate)
        except Exception:
            return False
    if not ready():
        python=python_runtime()
        env=os.environ.copy()
        env['PYTHONPATH']=str(ROOT)
        dependencies=subprocess.run([python,'-c','import PIL, hid'],
                                    stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        if dependencies.returncode:
            print('Bağımlılıklar eksik. studio klasöründe kurulum adımlarını README.md dosyasından izleyin.')
            return 1
        folder=ROOT/'work'/('test-'+args.simulate if args.simulate else 'state')
        folder.mkdir(parents=True,exist_ok=True)
        command=[python,'-m','ak820.server','--port',str(args.port),'--state-dir',str(folder)]
        if args.simulate: command+=['--simulate',args.simulate]
        with (folder/'server.log').open('a') as log:
            process=subprocess.Popen(command,cwd=ROOT,env=env,stdin=subprocess.DEVNULL,stdout=log,stderr=log,
                                     start_new_session=True)
        (folder/'server.pid').write_text(str(process.pid))
        for _ in range(50):
            if ready(): break
            if process.poll() is not None:
                print('Başlatılamadı. Ayrıntılar: '+str(folder/'server.log')); return 1
            time.sleep(.1)
        else:
            print('Yerel servis yanıt vermedi. Ayrıntılar: '+str(folder/'server.log')); return 1
    print('AK820 Studio hazır: '+url)
    if not args.no_open: webbrowser.open(url)
    return 0

if __name__=='__main__': sys.exit(main())
