# Fluid Kernel

Fluid Kernel is an experimental handwritten OS kernel for Agent-native computing. It boots in QEMU without Linux, Android, Chromium, WebView, or a browser shell, mounts a tiny initramfs-like package, parses a constrained HTML/CSS subset, builds kernel-resident DOM/render/compositor state, and paints the Agent-generated interface directly to the framebuffer.

This repository is intentionally early and research-oriented. The goal is not to ship a normal app launcher; the goal is to grow a clean non-Linux kernel architecture where tasks, interfaces, capabilities, files, devices, input, and generated UI are first-class kernel/runtime concepts.

## What Works Today

- BIOS floppy boot path: stage1 -> stage1.5 loader -> protected-mode handwritten kernel.
- QEMU-bootable HTML kernel image generated from `kernel/stage_b/build_html_kernel.py`.
- FHTML1 initramfs-style payload containing `kernel/stage_b/html/order-agent.html`.
- Kernel-side parser for a constrained HTML/CSS subset.
- Kernel memory DOM, render tree, CSS/style state, compositor damage/display-list path, and framebuffer paint.
- Prototype Linux-class primitives: VFS/initramfs/devfs records, dentry/inode/file/page-cache evidence, task/process/mm records, ring3/int80 syscall evidence, driver/devfs/input/socket-style evidence, and visual regression artifacts.
- Browser/Chrome is used only as an optional golden-reference screenshot generator for visual comparison; it is not used at runtime by the kernel.

## What This Is Not

- Not a WebView wrapper.
- Not an Android launcher.
- Not a Chromium shell.
- Not Linux.
- Not production-ready.
- Not yet a Linux-class complete kernel; it is a bootable research prototype moving in that direction.

## Requirements

On macOS or Linux:

- Python 3.11+
- QEMU with `qemu-system-x86_64`
- Pillow for PNG/report generation: `python3 -m pip install pillow`
- Google Chrome or Chromium only if running the browser golden visual comparison

## Quick Start

Build and run the handwritten HTML kernel headlessly in QEMU:

```bash
python3 tools/run-fluid-kernel-html.py
```

Expected result:

- `build/fluid-kernel-html.img`
- `build/fluidos-html-kernel/serial.log`
- `build/fluidos-html-kernel/html-kernel-final.png`
- `build/fluidos-html-kernel/html-kernel-report.json`

Run the visual comparison against a browser-rendered reference:

```bash
python3 tools/compare-fluid-html-visual.py
```

Expected result:

- `build/fluidos-html-kernel/reference-html.png`
- `build/fluidos-html-kernel/visual-side-by-side.png`
- `build/fluidos-html-kernel/visual-report.json`

Open an interactive QEMU window:

```bash
python3 tools/run-fluid-kernel-html.py --visible
```

## Current Architecture

```text
BIOS/QEMU
  -> stage1 boot sector
  -> stage1.5 disk loader
  -> protected-mode handwritten kernel
  -> FHTML1 initramfs mount
  -> VFS/dentry/inode/file/page-cache path
  -> HTML stream parser
  -> kernel DOM + attributes + style records
  -> render tree + compositor damage/display-list
  -> framebuffer paint
  -> PS/2 keyboard/mouse input
  -> Agent task/provider/payment capability flow evidence
```

The browser golden path is separate:

```text
HTML file -> Chrome screenshot -> visual reference only
```

Runtime rendering stays inside the QEMU-booted kernel.

## Repository Layout

```text
docs/                    Architecture/spec/roadmap notes
kernel/stage_b/          Bootloader and handwritten kernel generators
kernel/stage_b/html/     Agent-generated HTML payload sample
tools/                   QEMU runners, verifiers, visual comparison tools
```

## Verification Commands

```bash
python3 -m py_compile kernel/stage_b/build_html_kernel.py tools/run-fluid-kernel-html.py tools/compare-fluid-html-visual.py
python3 - <<'PY'
import kernel.stage_b.build_html_kernel as k
k.assert_memory_map_nonoverlap()
k.assert_state_words_unique()
print('maps ok')
PY
python3 tools/run-fluid-kernel-html.py
python3 tools/compare-fluid-html-visual.py
```

## Roadmap

The next serious architecture milestones are:

1. Replace remaining fixed-path probes with reusable component-by-component `namei` lookup.
2. Move fixed kernel tables toward allocator-backed objects and lifetime/refcount rules.
3. Strengthen scheduler, process, fd, VFS, device, socket, and page-cache semantics beyond evidence markers.
4. Add a real network path suitable for provider calls.
5. Expand HTML/CSS/layout/rendering fidelity while keeping runtime rendering inside the kernel.
6. Build a contribution-friendly verifier suite so regressions are caught by QEMU evidence, not screenshots alone.

## License

Apache-2.0. See `LICENSE`.
