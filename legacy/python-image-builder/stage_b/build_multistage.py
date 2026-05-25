#!/usr/bin/env python3
"""Build a multistage Fluid Kernel demo image."""
from __future__ import annotations
from pathlib import Path
import sys

THIS = Path(__file__).resolve().parent
if str(THIS) not in sys.path:
    sys.path.insert(0, str(THIS))
from stage1 import build_stage1
from stage2 import build_stage2

ROOT = THIS.parents[1]
OUT = ROOT / "build" / "fluid-kernel-stageb2.img"


def main() -> int:
    stage1 = build_stage1()
    stage2 = build_stage2()
    image = bytearray(stage1 + stage2)
    floppy_size = 1440 * 1024
    image.extend(b"\0" * (floppy_size - len(image)))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(image)
    print(f"built {OUT} ({len(image)} bytes, stage2={len(stage2)} bytes)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
