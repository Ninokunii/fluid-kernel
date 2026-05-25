# Mainline Kernel

This directory is the first-class Fluid Kernel runtime. It is freestanding i386 C linked by `linker.ld` and loaded by `boot/stage1.asm`.

Current files:

- `main.c`: kernel entrypoint and HTML payload mount/render flow.
- `serial.c`: COM1 serial logging.
- `fb.c`: VGA mode 13h framebuffer primitives.
- `font.c`: tiny bitmap glyph renderer.
- `html.c`: constrained Agent HTML tokenizer and renderer.
- `assets/order-agent.html`: builtin Agent task UI payload.

The legacy Python generator is intentionally outside this directory under `legacy/python-image-builder/`.
