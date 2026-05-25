#!/usr/bin/env python3
from __future__ import annotations
import argparse, socket, subprocess, sys, time, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
IMG=ROOT/'build/fluid-kernel-dom-dashboard.img'
OUT=ROOT/'build/fluidos-dom-dashboard'
SERIAL=OUT/'serial.log'
SCREEN=OUT/'qemu-dom-dashboard.ppm'
PNG=OUT/'qemu-dom-dashboard.png'
MON=Path('/tmp/fluid-dom-dashboard-monitor.sock')

def wait_marker(marker, timeout=5):
    end=time.time()+timeout
    while time.time()<end:
        if SERIAL.exists() and marker in SERIAL.read_text(errors='replace'):
            return
        time.sleep(.05)
    raise RuntimeError(f'marker not found: {marker}')

def recv(sock):
    try: sock.recv(4096)
    except Exception: pass

def mon(sock, cmd, delay=.2):
    sock.sendall(cmd.encode()); time.sleep(delay); recv(sock)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--visible',action='store_true')
    args=ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    for p in [SERIAL,SCREEN,PNG,MON]:
        try:p.unlink()
        except FileNotFoundError: pass
    subprocess.check_call([sys.executable, str(ROOT/'kernel/stage_b/build_dom_dashboard_kernel.py')])
    display=['-display','default'] if args.visible else ['-display','none']
    cmd=['qemu-system-x86_64','-fda',str(IMG),'-serial',f'file:{SERIAL}','-monitor',f'unix:{MON},server,nowait',*display,'-no-reboot','-no-shutdown']
    proc=subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end=time.time()+4
        while time.time()<end and not MON.exists(): time.sleep(.05)
        if not MON.exists(): raise RuntimeError('monitor socket not found')
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); sock.connect(str(MON)); sock.settimeout(1); recv(sock)
        wait_marker('domdash.surface framebuffer=320x200 source=projection-ir page=smart-car-dashboard')
        mon(sock, f'screendump {SCREEN}\n', .4)
        wait_marker('domdash.projection nodes=109 interactive=16 text=45 leaf_text=19 image=17')
        mon(sock, 'quit\n', .1)
        try: proc.wait(timeout=2)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait(timeout=2)
    serial=SERIAL.read_text(errors='replace')
    required=['domdash.boot protected-mode online','domdash.surface framebuffer=320x200 source=projection-ir page=smart-car-dashboard','domdash.projection nodes=109 interactive=16 text=45 leaf_text=19 image=17','domdash.text visible','domdash.image visible','domdash.click target=auto-park state=available']
    missing=[m for m in required if m not in serial]
    if not SCREEN.exists() or SCREEN.stat().st_size<1000: missing.append('screendump')
    # simple pixel evidence: cyan top active button / dark bg not all black
    data=SCREEN.read_bytes()
    if data.startswith(b'P6'):
        parts=[];i=0
        while len(parts)<4:
            while data[i:i+1].isspace(): i+=1
            st=i
            while i<len(data) and not data[i:i+1].isspace(): i+=1
            parts.append(data[st:i])
        while data[i:i+1].isspace(): i+=1
        w,h=int(parts[1]),int(parts[2])
        def pix(x,y):
            off=i+(y*w+x)*3; return tuple(data[off:off+3])
        if max(pix(220,161)) < 80: missing.append('text pixel')
        if max(pix(60,60)) < 20: missing.append('dashboard pixel')
    report={'status':'pass' if not missing else 'fail','image':str(IMG.relative_to(ROOT)),'serial':str(SERIAL.relative_to(ROOT)),'screenshot':str(SCREEN.relative_to(ROOT)),'missing':missing}
    (OUT/'dom-dashboard-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f"FluidOS DOM Dashboard QEMU: {report['status'].upper()}")
    print(f"serial={SERIAL}")
    print(f"screenshot={SCREEN}")
    if missing: raise SystemExit(1)
if __name__=='__main__': main()
