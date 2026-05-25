# Contributing

Fluid Kernel is a research kernel, not an app wrapper. Contributions should preserve these constraints:

- Mainline kernel code belongs in `boot/`, `kernel/`, `include/`, and `linker.ld`.
- Runtime UI rendering must remain in the QEMU-booted handwritten kernel path.
- Browser/Chrome/WebView may be used only as tooling or golden-reference comparison, never as the runtime renderer.
- Python belongs in tooling or `legacy/`, not as the main kernel runtime.
- Every kernel milestone should include QEMU serial/framebuffer evidence and a verifier update.
- Do not commit generated `build/` artifacts, screenshots, logs, disk images, packet captures, private keys, keystores, or environment files.

Before sending a change, run:

```bash
make clean
make verify
```
