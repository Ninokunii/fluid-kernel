# Fluid Kernel

Fluid Kernel is an experimental handwritten OS kernel for Agent-native computing. The mainline is now a C/ASM kernel tree: a NASM boot sector loads a freestanding i386 C kernel, enters protected mode, parses a constrained Agent HTML payload, builds kernel-resident UI state, and renders directly to the VGA framebuffer in QEMU.

The original Python image generator still exists, but it has been demoted to `legacy/python-image-builder/`. It is no longer the first-class kernel source tree.

## Mainline Status

The current mainline boots this path:

```text
QEMU BIOS
  -> boot/stage1.asm
  -> protected-mode jump
  -> kernel/main.c
  -> builtin HTML payload from kernel/assets/order-agent.html
  -> kernel/html.c tokenizer
  -> kernel framebuffer renderer
  -> VGA mode 13h framebuffer
```

Runtime rendering is not browser/WebView/Chromium. Browser tooling is only allowed for reference comparison in the legacy verifier path.

## Repository Layout

```text
boot/                 NASM boot sector and protected-mode entry
include/fluid/        Freestanding kernel headers
kernel/               Mainline C kernel runtime
kernel/assets/        Builtin Agent HTML payloads
linker.ld             i386 ELF linker script
Makefile              Mainline build/run/verify entrypoint
tools/                Mainline QEMU runners/verifiers
legacy/               Previous Python-generated kernel prototype
```

## Requirements

On macOS with Homebrew:

```bash
brew install nasm llvm lld qemu
```

The Makefile defaults to Homebrew LLVM paths. On Linux, override `LLVM_PREFIX`, `LD`, `OBJCOPY`, and `QEMU` if needed.

## Build

```bash
make clean
make
```

Output:

```text
build/fluid-kernel.img
```

## Run

```bash
make run
```

## Verify

```bash
make verify
```

Expected result:

```json
{
  "status": "pass"
}
```

The verifier boots the C/ASM kernel in QEMU, captures serial output and framebuffer state, and requires these runtime markers:

```text
fluid.stage1 asm boot ok
fluid.kernel.c entry protected-mode=1 runtime=c/asm
initramfs.builtin file=/agent-order-task.html source=objcopy-blob status=mounted
html.parser.c start source=initramfs engine=c-tokenizer
html.parser.c complete buttons=15 status=ok
html.render.c framebuffer=mode13 dom=kernel-memory status=complete
kernel.halt reason=demo-complete
```

## Legacy Prototype

The previous Python-generated handwritten machine-code kernel is preserved here:

```text
legacy/python-image-builder/
```

Run its old verification path with:

```bash
make legacy-verify
```

That path still matters as a richer architecture/evidence prototype, but the repository front door is now the C/ASM kernel.

## Roadmap

Next mainline milestones:

1. Replace builtin HTML blob with a real packed initramfs table read by C VFS code.
2. Add C dentry/inode/file objects and component-by-component `namei` lookup.
3. Move framebuffer rendering from direct rectangles into a compositor/display-list API.
4. Port the stronger legacy evidence into real C subsystems: scheduler, syscall, fd table, page cache, driver model, input queue, and Agent provider IPC.
5. Improve HTML/CSS/layout fidelity while keeping runtime rendering inside the kernel.

## License

Apache-2.0. See `LICENSE`.
