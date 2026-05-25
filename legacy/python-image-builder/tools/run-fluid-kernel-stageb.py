#!/usr/bin/env python3
from __future__ import annotations
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
img = ROOT / "build" / "fluid-kernel-stageb.img"
if not img.exists():
    subprocess.check_call([sys.executable, str(ROOT / "kernel" / "stage_b" / "build_boot_sector.py")])
cmd = [
    "qemu-system-x86_64",
    "-drive", f"format=raw,file={img}",
    "-serial", "stdio",
    "-display", "none",
    "-no-reboot",
    "-no-shutdown",
]
try:
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    assert proc.stdin is not None
    # Feed a key and ESC. In graphical QEMU this would come from keyboard input;
    # with -display none stdio also exercises the BIOS keyboard path enough for serial evidence.
    try:
        proc.stdin.write(b"a\x1b")
        proc.stdin.flush()
    except BrokenPipeError:
        pass
    out, _ = proc.communicate(timeout=3)
except subprocess.TimeoutExpired:
    proc.kill()
    out, _ = proc.communicate()
text = out.decode("utf-8", errors="replace")
print(text, end="")
required = [
    "Fluid Kernel B boot",
    "graph kernel.boot c=1",
    "task on cap on auth on",
    "surface visible input keyboard",
]
missing = [item for item in required if item not in text]
if missing:
    print("\nmissing boot evidence: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
