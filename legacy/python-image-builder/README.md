# Legacy Python Image Builder

This directory contains the earlier Python-generated handwritten-kernel prototype. It generated x86 boot images directly from Python assembler/codegen scripts and has richer experimental evidence than the new C mainline.

It is kept for reference and migration only. New kernel work should happen in the root `boot/`, `kernel/`, `include/`, `linker.ld`, and `Makefile` path.

Run legacy verification from the repository root:

```bash
make legacy-verify
```
