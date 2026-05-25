#!/usr/bin/env python3
from __future__ import annotations
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
img = ROOT / "build" / "fluid-kernel-stageb2.img"
serial = ROOT / "build" / "fluid-kernel-stageb2.serial.log"
screen = ROOT / "build" / "fluid-kernel-stageb2.ppm"
mon = Path("/tmp/fluid-kernel-stageb2-monitor.sock")
for p in [serial, screen, mon]:
    try:
        p.unlink()
    except FileNotFoundError:
        pass
subprocess.check_call([sys.executable, str(ROOT / "kernel" / "stage_b" / "build_multistage.py")])
cmd = [
    "qemu-system-x86_64",
    "-fda", str(img),
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
    def wait_for_serial(marker: str, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if serial.exists() and marker in serial.read_text(errors="replace"):
                return
            time.sleep(0.05)
        raise RuntimeError(f"serial marker not observed before input: {marker}")

    def monitor(command: str, delay: float = 0.25) -> None:
        s.sendall(command.encode("ascii"))
        time.sleep(delay)
        try:
            s.recv(4096)
        except Exception:
            pass

    wait_for_serial("graph interface.projected id=iface.food.native")
    monitor("sendkey 1\n", 0.35)
    wait_for_serial("graph trusted_surface.created capability=payment.confirmAndPay")
    monitor("sendkey y\n", 0.35)
    wait_for_serial("graph task.completed id=task.food.demo")
    monitor(f"screendump {screen}\n", 0.25)
    monitor("sendkey esc\n", 0.25)
    monitor("quit\n", 0.1)
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
    "Fluid stage1 loading stage2",
    "Fluid Kernel Stage B2 loaded",
    "kernel.object_records task{id=1001,state=created,auth=runtime} cap_food{id=2001,risk=medium} cap_pay{id=2002,risk=critical} authority{id=3001,runtime=1,trusted=1} interface{id=4001,state=projected} ring_head=4",
    "kernel.graph_ring slot0{c=1,t=task.created,s=1001,state=created} slot1{c=2,t=cap.registered,s=2001,state=registered} slot2{c=3,t=cap.registered,s=2002,state=registered} slot3{c=4,t=interface.projected,s=4001,state=projected}",
    "kernel.graph_flush source=ring walker=type-dispatch from=0 to=3",
    "graph task.created id=task.food.demo",
    "graph capability.registered id=food.createOrder source=ring.subject",
    "graph capability.registered id=payment.confirmAndPay source=ring.subject",
    "graph interface.projected id=iface.food.native",
    "kernel.object_transition input{last=1} order{id=5001,state=created,cap=food.createOrder} trusted{id=6001,state=awaiting,cap=payment.confirm} ring_head=7",
    "kernel.graph_ring slot4{c=5,t=input.key,s=1,state=pressed} slot5{c=6,t=capability.called,s=5001,state=ok} slot6{c=7,t=trusted_surface.created,s=6001,state=awaiting}",
    "kernel.graph_flush source=ring walker=type-dispatch from=4 to=6",
    "graph input.key value=1 source=ring.subject",
    "graph capability.called food.createOrder provider=kernel.mock.food source=ring.subject",
    "graph trusted_surface.created capability=payment.confirmAndPay source=ring.subject",
    "kernel.object_transition input{last=y} trusted{id=6001,state=confirmed} receipt{id=7001,state=created,order=5001} task{id=1001,state=completed} ring_head=11",
    "kernel.graph_ring slot7{c=8,t=input.key,s=2,state=pressed} slot8{c=9,t=trusted.confirmed,s=6001,state=confirmed} slot9{c=10,t=receipt.created,s=7001,state=created} slot10{c=11,t=task.completed,s=1001,state=completed}",
    "kernel.graph_flush source=ring walker=type-dispatch from=7 to=10",
    "graph input.key value=y source=ring.subject",
    "graph trusted.confirmed session=sess.trusted-ui capability=payment.confirmAndPay source=ring.subject",
    "graph receipt.created order=order.demo.0001 source=ring.subject",
    "graph task.completed id=task.food.demo source=ring.subject",
    "graph kernel.halt reason=escape",
]
missing = [item for item in required if item not in text]
if screen.exists():
    print(f"screendump={screen} bytes={screen.stat().st_size}")
else:
    print("screendump=missing")
if missing:
    print("missing stage-b2 evidence: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
