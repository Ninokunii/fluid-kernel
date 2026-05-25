# Stage B Kernel Sources

This directory contains the current non-Linux Fluid Kernel boot path.

Files:

- `asm16.py`: tiny internal 16-bit assembler DSL used until a real assembler / Rust toolchain is installed.
- `stage1.py`: 512-byte BIOS boot sector. Initializes serial, loads Stage 2 from floppy sectors, jumps to `0x8000`.
- `stage2.py`: larger real-mode kernel body. Shows the Agent-native food task surface, mutates structured task/capability/authority/trusted object records, then emits task/capability/trusted/receipt graph events.
- `build_protected_mode.py`: Stage C protected-mode proof. Loads from the same boot path, enters 32-bit protected mode, renders projection-IR-backed packed framebuffer surfaces, writes task/capability/interface/input/order/trusted/receipt allocator proof records at `0x00100000`, dynamically allocates order/receipt records from the protected-mode bump heap, writes opaque capability handles plus provider/trusted capability IPC mailboxes at `0x00100040` and `0x00100060`, maps flat32 fluid-init/provider/trusted payload entries, records initramfs/runqueue/context metadata, enables PIT IRQ0 timer tick proof, handles cooperative yield, proves provider/trusted context switches, and enters fluid-init/provider/trusted payloads through iret-style CPL3 transitions, receives int80 syscalls back through TSS/IDT, uses a syscall continuation slot for provider/trusted, registers provider/trusted task descriptors, writes graph ring records at `0x00100080`, handles keyboard scancodes, enables minimal PS/2 pointer polling, and walks those records with type/subject dispatch.
- `build_boot_sector.py`: older single-sector proof.
- `build_multistage.py`: current multistage image builder.

Current command:

```bash
python3 tools/verify-fluid-kernel-stageb2.py
python3 tools/verify-fluid-kernel-stagec-pm.py
```

The Stage B2 food flow is still real-mode and intentionally primitive. Stage C
has entered protected mode and now proves the first protected-mode allocator,
object table, capability handle records and IPC mailbox records, flat32 payload entries, initramfs-manifest/lookup, runqueue/context/timer/yield/provider/trusted-switch/userspace-reply/network metadata, CPL3 fluid-init/provider/trusted work/syscall transition, provider/trusted task descriptors, graph ring records,
keyboard/pointer input, keyboard-driven food transitions, ring walker, and
native packed framebuffer surface renderer. The next architectural step is to
replace the current runqueue/initramfs evidence records with scheduled, initramfs-loaded userspace services and add richer framebuffer
primitives for generated surfaces.

Current ring evidence includes `kernel.graph_ring slot0..slot10` with cursor/type/subject/state fields.

Current graph output is emitted through `kernel.graph_flush source=ring walker=type-dispatch` evidence before graph lines are emitted.

Current graph flush is subject-aware: graph lines include `source=ring.subject` for capability/input/trusted/receipt/task events.

Protected-mode proof:

- `build/fluid-kernel-stagec-pm.img` boots Stage 2 into 32-bit protected mode.
- `tools/verify-fluid-kernel-stagec-pm.py` requires `kernel.mode protected bits=32 gdt=flat`, protected-mode bump allocator/object/ring evidence, dynamic order/receipt allocation evidence, payload-map, initramfs-manifest/lookup, runqueue/context/timer/yield/provider/trusted-switch/userspace-reply/network evidence, CPL3 fluid-init/provider/trusted work, userspace-written IPC replies, and int80 syscall, capability handle open/call plus IPC send/reply and task-dispatch evidence, keyboard-driven choose/confirm transitions, pointer packet evidence, protected-mode ring walker output, task-bound interface projection, VM network/provider handle proof, visible debug graph overlay, and surface phase evidence, and receipt-surface/debug-overlay pixel checks.
