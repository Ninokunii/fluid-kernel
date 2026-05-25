# Fluid Kernel Stage Plan Toward Stage G

Objective: build a bootable Fluid Kernel demo image that can run the Agent-native
food flow without Linux userspace, browser, WebView, or Android.

## Completion Definition For Stage G

Stage G is complete only when current evidence proves all of these:

- QEMU/UTM boots a Fluid Kernel image.
- The boot path is not Linux.
- A native intent surface appears.
- Keyboard/pointer input works.
- The system has a Fluid task registry.
- The system has capability handles or their kernel-backed equivalent.
- A mock/real food provider can be called through Fluid capability IPC.
- The Agent food task generates a native interface projection.
- Selecting food transitions to a trusted surface.
- Trusted confirmation emits an audit/graph event.
- Receipt appears.
- A debug graph or serial log shows task/capability/provider/interface/trusted events.

## Current Status

Done:

- Stage C protected-mode proof image: `build/fluid-kernel-stagec-pm.img`.
- Stage C verifier: `tools/verify-fluid-kernel-stagec-pm.py`; injects `mouse_move`, `1`, `y`, and `esc` through QEMU monitor and requires protected-mode allocator/page-allocator/address-space/object/ring evidence, capability handle table/open/call/denial evidence plus generated-surface trusted-denial and syscall copyin/copyout pointer-denial evidence, PCI-read plus legacy-I/O virtio-net/net-handle evidence, capability IPC ring-queue evidence, init-package flat-binary loader evidence, flat payload map evidence, initramfs mapping/manifest/lookup evidence, scheduler runqueue/context/pick evidence, PIT IRQ0 timer tick evidence, cooperative yield and provider/trusted context-switch evidence, CPL3 fluid-init/provider/trusted work, userspace-written IPC replies, and int80 syscall evidence, provider/trusted task dispatch evidence, PS/2 pointer evidence, walker-emitted choose, provider-call, trusted-confirm, receipt, completion, halt graph lines, task-bound interface projection, PCI-read plus legacy-I/O virtio-net/provider handle proof, visible debug graph overlay, surface phase evidence, and screendump pixel checks.
- Fluid Kernel spec: `docs/fluid-kernel-spec.md`.
- Stage B single-sector boot evidence: `build/fluid-kernel-stageb.img`.
- Stage B2 multistage boot evidence: `build/fluid-kernel-stageb2.img`.
- Stage 1 loads a 40-sector Stage C body from floppy sectors and jumps to it; Stage B2 keeps its 16-sector body.
- QEMU serial smoke runner: `tools/run-fluid-kernel-stageb.py`.
- QEMU monitor verifiers: `tools/verify-fluid-kernel-stageb.py`, `tools/verify-fluid-kernel-stageb2.py`.
- Visible boot surface screenshots: `build/fluid-kernel-stageb.ppm`, `build/fluid-kernel-stageb2.ppm`.
- Visible Stage C protected-mode surface screenshot: `build/fluid-kernel-stagec-pm.ppm`; verifier checks a receipt-surface packed framebuffer green pixel from the final rendered phase.
- Keyboard graph event evidence: `graph input.key=a` in `build/fluid-kernel-stageb.serial.log`.
- Food-flow graph skeleton evidence in `build/fluid-kernel-stageb2.serial.log`: task created, capability table online, interface projected, create-order capability called, trusted surface created, trusted confirmed, receipt created, task completed.
- Stage B sources are modularized under `kernel/stage_b/`: `asm16.py`, `stage1.py`, `stage2.py`, `build_multistage.py`.
- Stage B2 now contains structured mutable object records plus graph event ring records with cursor/type/subject/state fields; verifier requires `kernel.object_records` and `kernel.object_transition` evidence before graph events.
- Stage B2 verifier requires `kernel.graph_ring` slot evidence with cursor/type/subject/state fields for boot, choose, trusted-confirm, receipt, and completion events.
- Stage B2 verifier requires `kernel.graph_flush source=ring walker=type-dispatch` evidence, proving graph text is emitted through a ring walker that dispatches on event type.
- Stage B2 verifier requires subject-specific graph output from ring records, including `source=ring.subject` for food/payment capability registration, input `1/y`, trusted payment confirmation, receipt, and task completion.
- Stage C now writes protected-mode object records at `0x00100000`, dynamically allocates order/receipt records from the protected-mode bump heap, writes opaque capability handles plus negative capability/trusted-surface enforcement records plus provider/trusted capability IPC ring queues at `0x00100380` and `0x001003C0`, copies flat32 fluid-init/provider/trusted binaries from the boot init package into manifest-selected entries, records a three-file initramfs map plus a manifest and per-service lookup results, records a real paging, page-fault handler, page allocator, per-task address spaces/CR3s, a three-task round-robin runqueue and context table, enables a PIT IRQ0 timer path, handles a CPL3 fluid-init cooperative yield syscall, switches into provider/trusted CPL3 contexts with `iretd` for capability and trusted-gate calls, and enters fluid-init/provider/trusted payloads through iret-style CPL3 transitions, receives int80 syscalls back through TSS/IDT, uses a syscall continuation slot to resume the provider and trusted food-flow handlers after CPL3 payloads write their queue replies, registers provider/trusted task descriptors, writes a ten-slot protected-mode graph ring at `0x00100080`, enables PS/2 pointer polling, handles keyboard scancodes in protected mode, mutates input/order/trusted/receipt/task records for the food choose/confirm flow, and renders home/trusted/receipt surfaces directly to packed framebuffer memory from protected mode.
- Stage C now reads QEMU virtio-net PCI config space through I/O ports `0xCF8/0xCFC`, records the matched `1AF4:1000` Ethernet device, programs legacy virtio status bits, RX/TX queue PFNs, qemu-sized RX/TX descriptors, valid ARP request plus IPv4/UDP DNS frames, RX/TX queue notify, PCI bus-master enable, TX used-ring sample, RX ARP reply and DNS response buffer evidence, and ISR sample records, emits `graph net.device.discovered`, `graph net.opened`, `graph net.queue.ready`, `graph net.send`, `graph net.udp.send`, `graph net.recv.poll`, `graph net.arp.reply`, `graph net.dns.reply`, `graph provider.dns.parsed`, `graph provider.result`, `graph net.tx.notify`, `graph net.isr.sampled`, and records CPL3 provider DNS parser/result-object tx/rx graph evidence.
- Stage G demo package now exists at `tools/run-fluid-kernel-stageg.py`; it boots the non-Linux image, drives pointer/food/trusted/receipt input, captures `build/stageg/fluidos-stageg-home.ppm`, `build/stageg/fluidos-stageg-trusted.ppm`, `build/stageg/fluidos-stageg-receipt.ppm`, writes `build/stageg/fluidos-stageg-serial.log`/manifest/transcript, and verifies the Stage G evidence checklist.
- Stage G native renderer now presents an agent-card home surface, trusted modal surface, success receipt card, and debug graph strip rather than plain color blocks; serial evidence marks `visual=agent-cards`, `visual=trusted-modal`, and `visual=success-receipt`.
- Stage G share package now exists at `tools/package-fluidos-stageg.py`; it reruns the demo, converts home/trusted/receipt framebuffer captures to PNG, exports `build/stageg/package/fluidos-stageg-demo.mp4`, writes `build/stageg/package/index.html`, and emits `build/stageg/package/fluidos-stageg-release.json`.
- Stage G UTM-friendly package now exists at `tools/package-fluidos-stageg-utm.py`; it creates `build/stageg/utm/FluidOS-StageG.utm`, copies the boot image and share package, writes UTM/manual import instructions plus QEMU launch commands, and archives `build/stageg/utm/FluidOS-StageG-UTM-Package.zip`.

Not done:

- long mode;
- real memory manager beyond the current real-paging/page-fault guard proof plus copyin/copyout denial proof, such as complete per-process page directories, full copyin/copyout validation across all syscalls, and richer fault recovery;
- richer graphics primitives beyond the current protected-mode packed framebuffer rectangles;
- hardware input driver beyond the current PS/2 keyboard and minimal PS/2 pointer proof;
- real userspace beyond the current CPL3 init-package-loaded fluid-init/provider/trusted flat-binary proofs, initramfs map/manifest/lookup records, runqueue/context records, PIT IRQ0 tick proof, cooperative yield, provider/trusted business context-switch proof, CPL3-written ring-queue replies, and int80 syscall continuation;
- provider IPC beyond the current small ring-queue proof, such as blocking waits, backpressure, and multi-message scheduling;
- real virtio-net packet completion interrupts, DHCP/TCP stack beyond the current PCI config-read plus legacy I/O queue-programming/notify/ARP request-reply and UDP DNS request-reply proof;
- trusted surface enforcement beyond the current generated-surface denial proof, including richer policy and negative UI tests;
- richer Stage G demo polish beyond the current one-command QEMU package and upgraded native card/modal/receipt renderer, such as deeper UTM-native config polish beyond the current UTM-friendly bundle/zip.

## Immediate Next Work

1. Continue virtio-net from current legacy queue programming/notify plus qemu-sized vring descriptor, ARP request/reply plus UDP PCAP and used-ring sample proof to real Ethernet frame TX/RX completion and interrupt evidence.
2. Done: ARP request/reply and UDP DNS request/reply are emitted, received, verified in PCAP, parsed by CPL3 provider evidence, and reflected into a provider result object; next is DHCP/TCP or HTTP/provider gateway.
3. Add DHCP or a deterministic static-IP mode for VM demos.
4. Extend the current CPL3 provider DNS parser/result object toward DHCP/TCP or an HTTP/provider gateway.
5. Complete per-process page directories plus full copyin/copyout validation across every syscall and broader negative verifier tests.
6. Split provider/trusted handlers into richer userspace binaries rather than kernel-resident business flow.
7. Upgrade projection IR renderer with text/card/list/button/receipt primitives.
8. After Stage G network evidence is real, start a UEFI/GOP x86_64 mini-PC target with wired Ethernet.

Recently completed:

- fixed provider/trusted mailboxes are replaced by small kernel IPC ring queues;
- runtime memory enables paging, emits page allocator/per-task address-space proof, and handles a guard page fault;
- provider/trusted/fluid-init flat32 payloads are copied from the init package and entered by manifest address;
- the Stage G launcher/share package/UTM-friendly package produce repeatable VM demo artifacts.

Current graph output is emitted through `kernel.graph_flush source=ring walker=type-dispatch` evidence before graph lines are emitted.

Current graph flush is subject-aware: graph lines include `source=ring.subject` for capability/input/trusted/receipt/task events.

Protected-mode proof:

- `build/fluid-kernel-stagec-pm.img` boots Stage 2 into 32-bit protected mode.
- It writes a tiny protected-mode object table at `0x00100000`, a runqueue/initramfs metadata area, and protected-mode graph ring records at `0x00100080`.
- It writes provider and trusted capability IPC ring queues at `0x00100380` and `0x001003C0`; it records an initramfs map for fluid-init/provider/trusted payloads and a round-robin runqueue. Choosing food enqueues `req=9001` to the provider queue, context-switches into a CPL3 provider payload, dequeues the provider reply in kernel context and returns through `int 0x80`. Confirming payment enqueues `req=9002` to the trusted queue, context-switches into a CPL3 trusted payload, dequeues the trusted reply in kernel context and returns through `int 0x80`.
- It enables a minimal PS/2 pointer polling path and records a pointer packet from QEMU `mouse_move`.
- It flushes boot, choose, and receipt records through a protected-mode type/subject dispatch walker.
- It renders native home, trusted, and receipt surfaces from task-bound projection IR to packed framebuffer memory from protected-mode code.
- `tools/verify-fluid-kernel-stagec-pm.py` requires protected-mode runtime allocation evidence for order/receipt plus allocator/object/ring evidence, payload-map, initramfs map/manifest/lookup, scheduler runqueue/context/pick evidence, PIT IRQ0 timer tick evidence, cooperative yield and provider/trusted context-switch evidence, CPL3 fluid-init/provider/trusted work, userspace-written IPC replies, and int80 syscall evidence, capability-handle call/denial plus IPC queue enqueue/dequeue/reply, generated-surface trusted denial, and syscall copyin/copyout bad-pointer denial, task-dispatch evidence, pointer evidence, walker-emitted task/capability/input/provider/trusted/receipt/completion graph lines, task-bound interface projection, PCI-read plus legacy-I/O virtio-net/provider handle proof, visible debug graph overlay, surface phase evidence, and green receipt/debug-overlay framebuffer pixels in the QEMU screendump.
