# Fluid Kernel Founder MVP Spec

Version: 0.1
Date: 2026-05-23
Status: founder-facing execution spec for a new Agent-native kernel

## 1. North Star

FluidOS is an app-less, Agent-native operating system built around tasks rather
than apps. The kernel is new because the native OS objects are task, capability,
generated surface, trusted gate, provider, and audit graph, not Android Activity,
Linux process, browser tab, or desktop window.

Founder claim:

```text
FluidOS boots its own kernel. The system has no apps as the primary model. An
Agent receives intent, binds capabilities, generates a task surface only when
needed, calls providers, routes risky actions through trusted gates, and leaves a
kernel-visible graph of what happened.
```

The reason to write a new kernel is not that Linux cannot technically run this.
The reason is product category ownership: the OS contract itself is Agent-native.

## 2. Brutal Scope Rule

The first kernel must not try to be a general Android, Linux, HarmonyOS, or phone
OS replacement. It must prove one new thing extremely clearly:

```text
A user task can boot, render, call a provider, use network, confirm through a
trusted surface, and complete with graph evidence without Linux, Android,
WebView, browser, or app windows underneath.
```

Everything else is cut until this proof is undeniable.

## 3. MVP Capability Matrix

### Must Keep For Founder Demo

| Area | MVP Requirement | Why It Stays |
| --- | --- | --- |
| Boot | BIOS first, UEFI later | proves this is a real OS image |
| CPU mode | 32-bit protected mode first, x86_64 long mode later | fastest path to real isolation story |
| Memory | physical allocator, paging, user/kernel boundary, guard faults | security credibility |
| Syscalls | Fluid syscall ABI, not POSIX-first | proves new OS contract |
| Scheduling | timer tick, runnable tasks, basic preemption | providers/runtime/trusted service need isolation |
| IPC | kernel message queues | capability calls must not be function calls hidden in kernel |
| Capabilities | opaque handles, policy, risk level | replaces app permissions |
| Task registry | create/cancel/complete task objects | replaces app/window as primary primitive |
| Providers | isolated userspace services | replaces apps with capability suppliers |
| Trusted service | separate confirmation path | payment/identity actions need believable trust |
| Surfaces | generated/trusted/debug surface objects | replaces app windows/screens |
| Renderer | software framebuffer renderer | enough to demo generated UI without GPU stack |
| Input | keyboard, pointer, scroll | minimum real interaction |
| Network | virtio-net, ARP, IPv4, UDP, DNS, narrow HTTP gateway | tasks need live data |
| Graph | append-only event ring, serial export, debug overlay | makes Agent actions auditable |
| Packaging | QEMU/UTM launcher, screenshots, video, manifest | repeatable demo and proof |

### Explicitly Cut From MVP

- Android compatibility.
- Linux userspace compatibility.
- Browser/WebView/DOM engine inside the kernel.
- Bluetooth.
- Audio.
- Camera.
- Cellular modem.
- Wi-Fi for the first hardware demo.
- GPU acceleration.
- Full filesystem.
- App store/package manager.
- General window manager.
- Multi-user desktop.
- Power management and suspend/resume.
- Arbitrary phone hardware.
- Production payment integration.
- Production LLM inference inside the kernel.

### Deferred But Important Later

- Wi-Fi on one locked reference device.
- Touchscreen driver.
- Audio output.
- Secure boot/signing.
- Filesystem persistence.
- Accessibility stack.
- GPU compositor.
- TCP/TLS stack or userspace network gateway.
- Real provider marketplace.

## 4. Hardware Strategy

### Target 0: QEMU/UTM VM

This is the main development and investor-demo target.

Required devices:

- serial console;
- VGA or linear framebuffer;
- PS/2 keyboard and pointer, or UTM/QEMU-compatible input;
- virtio-net;
- embedded init package or read-only boot disk.

Exit criteria:

- one command boots the image;
- verifier injects input and captures serial output;
- verifier captures home/trusted/receipt screenshots;
- pcap proves network packets when network is claimed;
- package can be opened by UTM on the Mac.

### Target 1: Locked x86_64 Mini PC With Ethernet

This is the first real-hardware credibility target.

Required devices:

- UEFI boot;
- GOP framebuffer;
- timer/interrupt controller;
- USB keyboard and pointer, or simple fallback input;
- exactly one selected Ethernet chipset.

Why Ethernet first:

- Wi-Fi drivers and firmware will waste months;
- Ethernet proves real network without RF association complexity;
- wired demo is credible enough for a founder/investor story.

### Target 2: One ARM Board

Only after Target 1 works. Choose a board with documented boot, interrupts,
timer, framebuffer/display, and Ethernet. Do not start with Android phones.

## 5. System Architecture

```text
Hardware / VM
  Bootloader
  Fluid Kernel
    arch        CPU mode, interrupts, syscalls
    memory      allocator, paging, copyin/copyout, faults
    sched       timer, task switch, budgets
    ipc         queues, calls, replies, backpressure
    cap         handle table, policy, risk gates
    task        intent tasks and lifecycle
    surface     generated/trusted/system/debug surface objects
    input       keyboard, pointer, scroll routing
    net         packet handles, policy, virtio/Ethernet drivers
    graph       append-only event log and debug export
    initpkg     read-only boot package loader
    panic/log   serial, crash buffer, verifier hooks
  Fluid Init
    starts runtime, providers, trusted service, surface runtime
  Fluid Runtime
    receives intent, plans task, emits Projection IR
  Provider Services
    food/search/payment/network-backed capability providers
  Trusted Service
    renders and confirms risky actions
  Surface Runtime
    Projection IR -> draw list -> framebuffer
```

Kernel owns identity, isolation, ordering, authority, routing, and hardware. It
must not own business logic, restaurant logic, LLM inference, HTML parsing,
payment semantics, or app compatibility.

## 6. Native Primitives

### Task

A live user intent. Example: `task.order_food.0001`.

Required fields:

- task id;
- owner authority;
- lifecycle state;
- priority/deadline hints;
- current surface;
- opened capabilities;
- network policy;
- graph cursor.

Required graph events:

- `task.created`;
- `task.surface.bound`;
- `task.cancelled`;
- `task.completed`.

### Capability

An operation the Agent/runtime may call. Example: `food.search`,
`food.createOrder`, `payment.confirmAndPay`.

Required fields:

- capability id;
- provider id;
- opaque handle;
- authority policy;
- network policy;
- risk level;
- trusted gate requirement.

Required graph events:

- `cap.opened`;
- `cap.called`;
- `cap.replied`;
- `cap.closed`;
- `cap.denied`.

### Provider

An isolated userspace service implementing capabilities.

Required fields:

- provider id;
- process id;
- manifest hash;
- capability list;
- network scope;
- resource budget;
- health state.

Required graph events:

- `provider.registered`;
- `provider.call.accepted`;
- `provider.reply.sent`;
- `provider.crashed`.

### Surface

A task-bound UI object. Surface types are `generated`, `trusted`, `system`, and
`debug`.

Required fields:

- surface id;
- task id;
- type;
- trust level;
- projection hash;
- input policy;
- buffer handle;
- focus state.

Required graph events:

- `surface.created`;
- `surface.presented`;
- `surface.input`;
- `trusted.created`;
- `trusted.confirmed`;
- `trusted.cancelled`.

### Graph Event

Ordered truth for the Agent-native OS.

Required fields:

- cursor;
- timestamp/tick;
- event type;
- task id;
- subject id;
- authority id;
- payload reference.

Guarantees:

- append-only ordering;
- serial export for verifier;
- debug overlay subscription;
- security-critical events cannot be hidden by generated UI.

## 7. UI Model

The kernel should not render HTML and should not embed a DOM engine. The native
ABI is Fluid Projection IR: a small, inspectable, Agent-friendly tree.

Minimum node types:

- text;
- image placeholder or decoded bitmap handle;
- card;
- button;
- list;
- input;
- modal;
- receipt;
- graph strip.

Minimum interactions:

- click/tap;
- key;
- text input;
- scroll;
- focus;
- trusted confirm/cancel.

Bridge model:

```text
Agent output / HTML-like DSL / JSX-like code
  -> userspace compiler
  -> Fluid Projection IR
  -> kernel surface object
  -> framebuffer draw list
```

This keeps the UI transparent to the Agent while avoiding a browser-shaped OS.

## 8. Networking MVP

Network is required, but the first version must be narrow.

Stages:

1. Discover virtio-net through PCI.
2. Negotiate device status/features.
3. Program RX/TX virtqueues.
4. Send/receive Ethernet frames.
5. ARP request/reply.
6. IPv4 packet parse/build.
7. Static IP for deterministic VM demo.
8. DHCP after static IP works.
9. UDP send/receive.
10. DNS query/response.
11. Userspace provider consumes DNS/network result.
12. Narrow HTTP gateway or local provider bridge.
13. TCP/TLS later.

Kernel responsibilities:

- packet handles;
- task/capability network policy;
- driver and queues;
- audit `net.open`, `net.send`, `net.recv`;
- narrow `sys_net_*` ABI.

Userspace responsibilities:

- DNS library after primitive packets work;
- HTTP semantics;
- TLS policy;
- provider API semantics;
- restaurant/payment business logic.

Wi-Fi is not in the first kernel MVP. For the first physical hardware demo, use
Ethernet. Wi-Fi becomes Target 1.5 only after the wired demo is stable.

## 9. Syscall ABI MVP

```c
// task
sys_task_create(intent_ptr, intent_len, flags) -> task_handle
sys_task_current() -> task_handle
sys_task_cancel(task, reason_ptr, reason_len) -> int
sys_task_complete(task, result_ptr, result_len) -> int

// capability
sys_cap_open(task, cap_id_ptr, cap_id_len, flags) -> cap_handle
sys_cap_call(cap, req_ptr, req_len, resp_ptr, resp_len, flags) -> int
sys_cap_close(cap) -> int

// provider
sys_provider_register(manifest_ptr, manifest_len) -> provider_handle
sys_provider_accept(provider, call_ptr, call_len, flags) -> call_handle
sys_provider_reply(call, resp_ptr, resp_len, status) -> int

// surface
sys_surface_create(task, desc_ptr, desc_len, flags) -> surface_handle
sys_surface_present(surface, buffer, dirty_rects, dirty_count) -> int
sys_surface_input_next(surface, event_ptr, flags) -> int
sys_trusted_surface_create(task, cap, desc_ptr, desc_len) -> trusted_handle
sys_trusted_surface_confirm(trusted, payload_ptr, payload_len) -> int

// graph/log
sys_graph_subscribe(after_cursor, flags) -> graph_handle
sys_graph_read(graph, buf, len) -> int
sys_log(level, ptr, len) -> int

// network
sys_net_open(task, policy_ptr, policy_len) -> net_handle
sys_net_send(net, buf, len) -> int
sys_net_recv(net, buf, len, flags) -> int
```

POSIX can be emulated later as a compatibility layer. It is not the native
contract.

## 10. Development Flow

### Stage A: ABI Simulator

Goal: lock the object model before kernel complexity.

Deliverables:

- task/cap/provider/surface/graph simulator;
- food-order transcript;
- Projection IR examples;
- graph event schema;
- syscall ABI draft.

Exit criteria:

- a full order-food task emits stable graph events in simulator;
- no Linux/Android/browser claim is made yet.

### Stage B: Bootable Toy Kernel

Goal: prove a new boot path.

Deliverables:

- custom boot image;
- serial output;
- framebuffer draw;
- keyboard input;
- graph ring;
- hardcoded food flow.

Exit criteria:

- QEMU/UTM boots non-Linux image;
- native intent surface appears;
- serial graph proves task/cap/surface/trusted skeleton.

### Stage C: Protected Mode And Early Isolation

Goal: stop being only a boot demo.

Deliverables:

- GDT/IDT/TSS;
- syscall interrupt;
- CPL3 entry;
- allocator;
- paging proof;
- page-fault guard;
- task/cap/provider/trusted records;
- keyboard/pointer/scroll;
- framebuffer renderer;
- timer tick evidence.

Exit criteria:

- userspace payload enters CPL3 and returns by syscall;
- provider/trusted dispatch is visible through IPC evidence;
- verifier checks serial events and pixels.

### Stage D: Real Userspace Services

Goal: remove business flow from kernel.

Deliverables:

- flat binary or ELF loader;
- Fluid Init process;
- Runtime process;
- Provider process;
- Trusted Service process;
- scheduler with runnable tasks;
- IPC queues;
- capability handles.

Exit criteria:

- food provider replies through userspace IPC;
- trusted confirmation is handled by trusted userspace;
- kernel only brokers handles, scheduling, memory, IPC, routing, and audit.

### Stage E: Credible Memory Isolation

Goal: make security claims believable.

Deliverables:

- real physical page allocator;
- virtual memory mappings;
- per-process page directories;
- user/kernel copy helpers;
- guard pages;
- provider/trusted separation;
- fault recovery;
- panic/crash log.

Exit criteria:

- provider cannot write kernel memory;
- provider cannot write trusted service memory;
- bad pointer in syscall is denied and audited;
- verifier includes negative tests.

### Stage F: Network-Backed Provider

Goal: make the task use real packet I/O.

Deliverables:

- virtio-net TX/RX DMA;
- RX completion and interrupt or reliable polling;
- ARP;
- IPv4;
- static IP then DHCP;
- UDP;
- DNS;
- provider network policy;
- provider result from network response.

Exit criteria:

- provider calls through `sys_net_*`;
- pcap proves packets;
- serial graph proves `net.open`, `net.send`, `net.recv`, `provider.result`;
- UI changes based on network/provider result.

### Stage G: Founder Demo Image

Goal: repeatable public demo.

Deliverables:

- bootable QEMU/UTM image;
- one-command launcher;
- beautiful native food-order demo;
- pointer/keyboard/scroll interaction;
- userspace provider;
- trusted payment gate;
- receipt;
- debug graph overlay;
- serial transcript;
- screenshots and video;
- manifest of proof points.

Exit criteria:

- VM boots FluidOS without Linux/Android/browser/WebView;
- user completes food flow;
- graph proves task/cap/provider/surface/trusted/network events;
- demo repeats from a fresh clone.

### Stage H: First Hardware Boot

Goal: leave VM-only territory.

Deliverables:

- UEFI x86_64 boot;
- GOP framebuffer;
- timer/interrupts;
- USB input;
- one Ethernet driver;
- same food demo using real Ethernet.

Exit criteria:

- locked mini PC boots FluidOS directly;
- no Linux underneath;
- food demo completes with graph evidence.

### Stage I: Reference Device Polish

Goal: turn demo into platform seed.

Deliverables:

- persistent storage;
- crash recovery;
- better projection renderer;
- provider SDK;
- capability manifest format;
- network gateway;
- signed init package;
- documentation for external provider authors.

Exit criteria:

- third-party provider can implement a capability without changing kernel code.

## 11. Current Repo Status On 2026-05-23

Already proven in this repository:

- non-Linux boot image;
- 32-bit protected mode;
- GDT/IDT/TSS;
- `int 0x80` syscall path;
- timer tick evidence;
- paging enabled and page-fault guard proof;
- init-package-loaded CPL3 payloads;
- task/capability/provider/trusted records;
- capability handles and IPC queues;
- native framebuffer home/trusted/receipt surfaces;
- keyboard, pointer, and scroll input evidence;
- debug graph overlay;
- virtio-net discovery and queue programming;
- ARP request/reply proof;
- UDP/DNS packet proof in QEMU pcap path;
- Stage G package/UTM-friendly demo artifacts.

Still not production-proven:

- x86_64 long mode;
- complete page-table isolation and copyin/copyout;
- real preemptive multitasking beyond current proof level;
- rich userspace service split;
- blocking/backpressure IPC;
- full DNS/provider integration;
- TCP/TLS/HTTP provider stack;
- real hardware UEFI/GOP/Ethernet boot;
- Wi-Fi;
- production-grade renderer;
- production security.

## 12. Next 30 Engineering Moves

1. Make Stage G manifest require DNS response evidence, not just UDP send.
2. Feed DNS/network receive result into provider response.
3. Display provider-derived result in the food UI.
4. Add negative verifier for missing capability handle.
5. Add negative verifier for generated UI attempting trusted confirm.
6. Add copyin/copyout helpers for all syscalls with user pointers.
7. Add bad-pointer syscall test and graph event.
8. Replace remaining kernel-resident food logic with userspace provider logic.
9. Add blocking provider accept/reply semantics.
10. Add IPC backpressure and queue-full verifier.
11. Add per-process page directories for runtime/provider/trusted.
12. Add provider crash containment proof.
13. Add projection IR parser in userspace.
14. Add renderer primitives: text, card, button, list, modal, receipt.
15. Add image placeholder/bitmap support for food cards.
16. Add deterministic frame pacing and input latency measurement.
17. Add DHCP after static IP path is stable.
18. Add minimal DNS parser in userspace.
19. Add narrow HTTP gateway or local network provider bridge.
20. Add network policy denial test.
21. Add UEFI boot path.
22. Add GOP framebuffer path.
23. Move to x86_64 long mode.
24. Pick exact mini PC hardware.
25. Pick exact Ethernet chipset.
26. Bring up USB keyboard/pointer or choose PS/2-compatible fallback hardware.
27. Boot same demo on hardware with wired Ethernet.
28. Write provider SDK manifest schema.
29. Add signed init package format.
30. Build the first external capability provider outside kernel tree.

## 13. Verifier Contract

No feature is accepted because it is described in a doc. Every feature needs:

- serial graph line;
- in-memory object record or state dump;
- verifier-required string or parsed artifact;
- screenshot/pixel check for UI;
- pcap check for network;
- negative test for security claims.

If a claim cannot be verified automatically, it is not part of the public demo
claim.

## 14. Public Narrative Boundaries

Say now:

- FluidOS is a new Agent-native OS kernel project.
- The demo boots without Linux, Android, WebView, or browser.
- Tasks, capabilities, generated surfaces, trusted gates, and graph events are
  kernel-visible primitives.
- The first target is VM, then one locked Ethernet mini PC.

Do not say yet:

- production Android replacement;
- works on arbitrary phones;
- mature driver ecosystem;
- production security;
- real Wi-Fi stack;
- GPU-accelerated UI;
- faster than Android/Linux;
- complete network stack.
