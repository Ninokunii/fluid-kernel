# Fluid Kernel

This directory is the path from the current Linux-hosted FluidOS prototype to a
bootable Agent-native kernel demo image.

## Current Evidence

Single-sector proof:

- `build/fluid-kernel-stageb.img` boots directly in QEMU without Linux.
- It paints a visible VGA text intent surface.
- It accepts keyboard input and emits `graph input.key=*` events.

Multistage proof:

- `build/fluid-kernel-stageb2.img` is a bootable floppy image.
- Stage 1 loads Stage 2 from disk sectors and jumps to it.
- Stage B2 Stage 2 is large enough to carry a tiny Agent-native food flow skeleton; Stage C now loads a 48-sector body to leave room for scheduler/initramfs work.
- Stage 1/2 are now modularized under `kernel/stage_b/` instead of living in one monolithic generator.
- Stage 2 has structured mutable object records for task/capability/authority/interface/input/order/trusted/receipt plus graph ring head transitions.
- The serial graph proves task creation, capability table, interface projection,
  food create-order capability call, trusted surface creation, trusted
  confirmation, receipt creation, and task completion.

Protected-mode proof:

- `build/fluid-kernel-stagec-pm.img` boots Stage 2 into 32-bit protected mode.
- It sets up a flat GDT, enters protected mode through `CR0.PE`, writes `FK`
  directly to VGA memory, and emits serial graph evidence from 32-bit code.
- It writes a tiny protected-mode object table at `0x00100000` with task,
  capability, interface, input, order, trusted-session, receipt, and allocator
  records.
- It writes provider and trusted capability handle records plus IPC ring queues at `0x00100380`
  and `0x001003C0`, plus init-package loaded flat32 binaries and initramfs/runqueue metadata for fluid-init/provider/trusted services; the food choose path enqueues `req=9001` to the provider
  queue, enters a CPL3 provider payload, returns through `int 0x80`, and then
  dequeues the provider reply. The payment confirm path enqueues `req=9002` to the
  trusted queue, enters a CPL3 trusted payload, returns through `int 0x80`,
  and then dequeues the trusted reply.
- It writes ten protected-mode graph ring records at `0x00100080` across boot,
  choose, trusted-confirm, receipt, and task-completion phases.
- It handles `1`, `y`, and `esc` keyboard scancodes in protected mode and walks
  the protected-mode ring records with type/subject dispatch before emitting
  graph lines.
- It enables minimal PS/2 pointer polling and records a pointer packet from
  QEMU `mouse_move`.
- It renders home, trusted-payment, and receipt surfaces directly to packed framebuffer
  memory from protected-mode code; the verifier checks the final receipt
  surface in the QEMU screendump.

Run:

```bash
python3 kernel/stage_b/build_boot_sector.py
python3 tools/verify-fluid-kernel-stageb.py
python3 kernel/stage_b/build_multistage.py
python3 tools/verify-fluid-kernel-stageb2.py
python3 tools/verify-fluid-kernel-stagec-pm.py
```

Expected Stage B2 serial evidence:

```text
Fluid stage1 loading stage2
Fluid Kernel Stage B2 loaded
kernel.object_records task=created cap=registered authority=online interface=projected cursor=4
graph task.created id=task.food.demo
graph capability.table online food.search food.createOrder payment.confirm
graph interface.projected id=iface.food.native
kernel.object_transition input=1 order=created trusted=awaiting cursor=7
graph input.key=1
graph capability.called food.createOrder provider=kernel.mock.food
graph trusted_surface.created capability=payment.confirmAndPay
kernel.object_transition input=y trusted=confirmed receipt=created task=completed cursor=11
graph input.key=y
graph trusted.confirmed session=sess.trusted-ui
graph receipt.created order=order.demo.0001
graph task.completed id=task.food.demo
graph kernel.halt reason=escape
```

Verifier artifacts:

- `build/fluid-kernel-stageb.serial.log`
- `build/fluid-kernel-stageb.ppm`
- `build/fluid-kernel-stageb2.serial.log`
- `build/fluid-kernel-stageb2.ppm`
- `build/fluid-kernel-stagec-pm.serial.log`
- `build/fluid-kernel-stagec-pm.ppm`

This is not Stage G yet. It is still Stage B/C evidence: a real non-Linux boot
path plus a tiny kernel-resident Agent-native food flow skeleton. Stage G still
requires a real preemptive scheduler and richer init-package-loaded userspace service binaries, a richer native surface, network, and a
packaged QEMU/UTM demo image.

## Next Milestones

1. Grow the runtime allocator into a real free-list/page allocator.
2. Replace scheduler/runqueue/context/timer/yield evidence records with real multi-task context switching on timer ticks.
3. Expand init-package loaded provider/trusted binaries into richer userspace services.
4. Add richer packed-framebuffer primitives for generated surfaces.
5. Add network/provider plumbing.
6. Done: `tools/run-fluid-kernel-stageg.py` packages a QEMU Stage G demo image and captures serial/screenshots; next is deeper UTM-native config polish or real network I/O.

Current graph output is emitted through `kernel.graph_flush source=ring walker=type-dispatch` evidence before graph lines are emitted.

Current graph flush is subject-aware: graph lines include `source=ring.subject` for capability/input/trusted/receipt/task events.

Protected-mode proof:

- `build/fluid-kernel-stagec-pm.img` boots Stage 2 into 32-bit protected mode.
- It writes task/capability/interface/input/order/trusted/receipt allocator proof records at `0x00100000` and dynamically allocates order/receipt records from the protected-mode bump heap and graph ring records at `0x00100080`.
- It writes provider/trusted capability handle records and IPC ring queues at `0x00100380` and `0x001003C0`.
- It enables minimal PS/2 pointer polling and records a pointer packet.
- It renders home/trusted/receipt surfaces directly to packed framebuffer memory in protected mode.
- `tools/verify-fluid-kernel-stagec-pm.py` requires `kernel.mode protected bits=32 gdt=flat`, `kernel.alloc bump base=00100000 next=00100140 record_bytes=320 runtime_next=00100180`, dynamic order/receipt allocation evidence, protected-mode real-paging/page-fault/address-space/object/ring evidence, payload-map, initpkg-loader/initramfs-manifest/lookup, runqueue/context/timer/yield/provider/trusted-switch/userspace-reply/network evidence, CPL3 fluid-init/provider/trusted work, userspace-written IPC replies, and int80 syscall, capability handle open/call plus IPC send/reply and task-dispatch evidence, keyboard-driven choose/confirm transitions, pointer packet evidence, walker-emitted graph lines, task-bound interface projection, PCI-read plus legacy-I/O virtio-net/provider handle, vring descriptor, and ARP-frame queue proof, visible debug graph overlay, and surface phase evidence, and final receipt-surface/debug-overlay pixel checks.
