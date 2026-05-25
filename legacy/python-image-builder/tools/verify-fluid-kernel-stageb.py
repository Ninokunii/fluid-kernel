#!/usr/bin/env python3
from __future__ import annotations
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
img = ROOT / "build" / "fluid-kernel-stageb.img"
serial = ROOT / "build" / "fluid-kernel-stageb.serial.log"
screen = ROOT / "build" / "fluid-kernel-stageb.ppm"
mon = Path("/tmp/fluid-kernel-stageb-monitor.sock")
for p in [serial, screen, mon]:
    try:
        p.unlink()
    except FileNotFoundError:
        pass
if not img.exists():
    subprocess.check_call([sys.executable, str(ROOT / "kernel" / "stage_b" / "build_boot_sector.py")])
cmd = [
    "qemu-system-x86_64",
    "-drive", f"format=raw,file={img}",
    "-serial", f"file:{serial}",
    "-monitor", f"unix:{mon},server,nowait",
    "-display", "none",
    "-no-reboot",
    "-no-shutdown",
]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    deadline = time.time() + 3
    while time.time() < deadline and not mon.exists():
        time.sleep(0.05)
    if not mon.exists():
        raise RuntimeError("monitor socket did not appear")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(str(mon))
    s.settimeout(1)
    try:
        s.recv(4096)
    except Exception:
        pass
    for command in ["sendkey a\n", f"screendump {screen}\n", "sendkey esc\n", "quit\n"]:
        s.sendall(command.encode("ascii"))
        time.sleep(0.25)
        try:
            s.recv(4096)
        except Exception:
            pass
    s.close()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
finally:
    if proc.poll() is None:
        proc.kill()

text = serial.read_text(errors="replace") if serial.exists() else ""
print(text, end="")
required = [
    "Fluid Kernel B boot",
    "graph kernel.boot c=1",
    "task on cap on auth on",
    "surface visible input keyboard",
    "graph input.key=a",
    "graph halt esc",
]
missing = [item for item in required if item not in text]
if screen.exists():
    print(f"screendump={screen} bytes={screen.stat().st_size}")
else:
    print("screendump=missing")
if missing:
    print("missing stage-b evidence: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
