#!/usr/bin/env python3
from __future__ import annotations
import json, re, socket, subprocess, time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'build/c-kernel'
IMG = ROOT / 'build/fluid-kernel.img'
SERIAL = OUT / 'serial.log'
SCREEN = OUT / 'framebuffer.ppm'
REPORT = OUT / 'report.json'
MON = Path('/tmp/fluid-c-kernel-monitor.sock')


def recv(sock: socket.socket) -> None:
    try:
        sock.recv(4096)
    except Exception:
        pass


def send(sock: socket.socket, cmd: str, delay: float = 0.2) -> None:
    sock.sendall(cmd.encode())
    time.sleep(delay)
    recv(sock)


def ppm_metrics(path: Path) -> dict[str, int]:
    data = path.read_bytes()
    m = re.match(rb'P6\s+(\d+)\s+(\d+)\s+(\d+)\s', data)
    if not m:
        raise RuntimeError(f'not a P6 PPM: {path}')
    w, h = int(m.group(1)), int(m.group(2))
    pix = data[m.end():]
    nonzero = sum(1 for i in range(0, len(pix), 3) if pix[i:i+3] != b'\0\0\0')
    colors = len({pix[i:i+3] for i in range(0, len(pix), 3)})
    return {'width': w, 'height': h, 'nonzero_pixels': nonzero, 'palette_colors': colors}


def wait_serial(marker: str, timeout: float = 5.0) -> str:
    end = time.time() + timeout
    while time.time() < end:
        if SERIAL.exists():
            text = SERIAL.read_text(errors='replace')
            if marker in text:
                return text
        time.sleep(0.05)
    raise RuntimeError(f'missing serial marker: {marker}')


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for p in (SERIAL, SCREEN, REPORT, MON):
        try:
            p.unlink()
        except FileNotFoundError:
            pass
    subprocess.check_call(['make', 'build/fluid-kernel.img'], cwd=ROOT)
    proc = subprocess.Popen([
        'qemu-system-i386', '-fda', str(IMG), '-serial', f'file:{SERIAL}',
        '-monitor', f'unix:{MON},server,nowait', '-display', 'none', '-no-reboot', '-no-shutdown'
    ], cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        end = time.time() + 4
        while time.time() < end and not MON.exists():
            time.sleep(0.05)
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(str(MON)); sock.settimeout(1); recv(sock)
        serial = wait_serial('kernel.halt reason=demo-complete', timeout=5)
        send(sock, f'screendump {SCREEN}\n', 0.4)
        send(sock, 'quit\n', 0.1)
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill(); proc.wait(timeout=2)
    finally:
        if proc.poll() is None:
            proc.kill(); proc.wait(timeout=2)
    required = [
        'fluid.stage1 asm boot ok',
        'fluid.kernel.c entry protected-mode=1 runtime=c/asm',
        'initramfs.builtin file=/agent-order-task.html source=objcopy-blob status=mounted',
        'html.parser.c start source=initramfs engine=c-tokenizer',
        'html.parser.c complete buttons=15 status=ok',
        'html.render.c framebuffer=mode13 dom=kernel-memory status=complete',
        'kernel.halt reason=demo-complete',
    ]
    missing = [m for m in required if m not in serial]
    metrics = ppm_metrics(SCREEN)
    status = 'pass' if not missing and metrics['nonzero_pixels'] > 30000 and metrics['palette_colors'] >= 4 else 'fail'
    report = {'status': status, 'missing': missing, 'framebuffer_metrics': metrics, 'serial': str(SERIAL.relative_to(ROOT)), 'screenshot': str(SCREEN.relative_to(ROOT))}
    REPORT.write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))
    if status != 'pass':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
