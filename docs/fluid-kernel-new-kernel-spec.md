# Fluid Kernel Founder Spec

Version: 0.4 founder draft
Date: 2026-05-22
Status: new-kernel product and engineering spec for an Agent-native OS

## 1. Positioning

FluidOS is not Android with a launcher, not Linux with a desktop, and not a
browser shell. It is a new kernel and system stack where the primary primitive is
not the app. The primary primitive is the task: a live user intent that can bind
capabilities, generate surfaces, call providers, enter trusted gates, use the
network, and emit an auditable graph.

The new-kernel reason is product and architecture, not novelty for its own sake.
Existing kernels optimize around processes, files, sockets, windows, and apps.
Fluid Kernel optimizes around task-bound authority, generated UI, provider
capabilities, trusted confirmations, and graph-visible agent execution.

Short claim:

```text
FluidOS is an app-less, Agent-native OS built on a new kernel where tasks,
capabilities, generated surfaces, trusted gates, and audit graphs are native
kernel objects.
```

## 2. Core Bet

Future interfaces are not preinstalled app screens. They are generated at task
time. Sometimes the Agent shows a generated surface; sometimes it performs the
whole task through provider capabilities and only shows a receipt.

The OS therefore needs native support for:

- task identity and lifetime;
- capability-scoped authority instead of app-scoped authority;
- generated surfaces that are inspectable and controllable by the Agent;
- trusted gates for risky actions;
- network policy tied to task and capability;
- an event graph that proves what happened.

HTML can remain an authoring or interchange format in userspace, but the kernel
should not contain a DOM or browser. The native UI ABI is Fluid Projection IR: a
small, transparent tree of text, cards, buttons, lists, forms, media, bindings,
and actions that compiles to framebuffer draw commands.

## 3. Non-Negotiable MVP

The MVP is deliberately narrow. It should be strong enough to prove the new OS
architecture and small enough that a tiny team can ship a deterministic demo.

Keep:

1. Bootable new kernel image.
2. Protected mode first; long mode later.
3. GDT, IDT, TSS, syscall path, interrupt path.
4. Physical page allocator and kernel heap.
5. Per-process address spaces and user/kernel copy validation.
6. Timer interrupt and runnable task scheduler.
7. Fluid-specific syscalls, not POSIX-first.
8. Init package loader for Fluid Init, Runtime, Provider, Trusted Service.
9. Capability handles and capability-bound IPC.
10. Task registry and task lifecycle.
11. Generated, trusted, system, and debug surface objects.
12. Software renderer to framebuffer.
13. Keyboard, pointer, and scroll input.
14. VM virtio-net first.
15. Ethernet on one real machine later.
16. Serial log, panic log, and graph export.
17. Automated verifier, screenshots, and demo package.

Cut from MVP:

- Android compatibility;
- Linux compatibility as a product goal;
- browser or WebView;
- DOM engine in kernel;
- GPU acceleration;
- Bluetooth;
- audio;
- camera;
- cellular modem;
- app store;
- full filesystem;
- multi-user desktop;
- power management;
- suspend/resume;
- arbitrary phone hardware;
- Wi-Fi on first hardware demo.

## 4. Hardware Strategy

### Target 0: QEMU and UTM

This is the truth machine for development and demos.

Required devices:

- BIOS or UEFI boot path;
- serial console;
- framebuffer/VGA/GOP;
- keyboard and pointer input;
- virtio-net;
- virtual disk or embedded init package.

Exit standard:

- one command boots the image;
- verifier injects input;
- verifier captures screenshots and serial graph;
- demo repeats deterministically.

### Target 1: x86_64 Mini PC With Ethernet

This gives real-hardware credibility without phone-driver chaos.

Required devices:

- UEFI boot;
- framebuffer through GOP;
- USB keyboard and pointer;
- one documented Ethernet chipset;
- no Wi-Fi required.

Recommended approach:

- choose one Intel NUC-like or mini-PC class target;
- lock the hardware model;
- write only the required drivers for that target;
- demo Ethernet through wired network.

### Target 2: One ARM Board

This is for portability story after Target 1 works.

Required devices:

- documented boot flow;
- documented interrupt controller;
- documented timer;
- framebuffer or simple display path;
- Ethernet.

Do not start with Android phones. Phone boot chains, GPUs, modems, Wi-Fi, power,
and secure-world details will bury the architecture before the product story is
proven.

## 5. Architecture

```text
Hardware / VM
  bootloader
  Fluid Kernel
    arch
    memory
    scheduler
    syscall
    ipc
    capability
    task
    authority
    surface
    input
    network
    graph
    initpkg
    log/panic
  Fluid Init
    starts runtime, providers, trusted service
  Fluid Runtime
    receives intent, plans task, emits projection IR
  Provider Services
    food/search/payment/network-backed services
  Trusted Service
    confirms risky actions on trusted surfaces
  Surface Runtime
    projection IR -> draw list -> framebuffer
```

Kernel owns identity, isolation, handles, IPC routing, input routing, trusted
surface enforcement, packet handles, resource budgets, and audit order.

Kernel must not contain:

- LLM inference;
- restaurant logic;
- payment business logic;
- HTML/DOM engine;
- HTTP API semantics;
- app framework compatibility.

## 6. Native Kernel Objects

### Task

A task is a live user intent.

Fields:

- task id;
- owner authority;
- lifecycle state;
- priority and deadline hints;
- current surface;
- opened capabilities;
- network policy;
- graph cursor.

Kernel guarantees:

- every provider call is task-bound;
- every surface is task-bound;
- cancel and complete are audited;
- trusted gates must reference a task.

### Capability

A capability is an operation the Agent/runtime may invoke.

Fields:

- capability id;
- provider id;
- opaque handle;
- risk level;
- authority policy;
- network policy;
- trusted-gate requirement.

Kernel guarantees:

- no ambient authority;
- no call without handle;
- risky calls require trusted flow;
- open, call, reply, close are graph events.

### Provider

A provider is an isolated userspace service implementing capabilities.

Fields:

- provider id;
- process id;
- manifest hash;
- capability list;
- network scope;
- resource budget;
- health state.

Kernel guarantees:

- explicit IPC endpoint;
- resource budget enforcement;
- crash graph event;
- cannot draw or impersonate trusted UI.

### Surface

A surface is a task-bound generated, trusted, system, or debug UI object.

Fields:

- surface id;
- task id;
- type;
- trust level;
- input policy;
- buffer handle;
- projection hash;
- focus state.

Kernel guarantees:

- generated UI cannot confirm trusted actions;
- trusted surface captures direct input;
- input is tagged with surface id and authority;
- debug graph can be displayed above normal surfaces.

### Graph Event

Graph events are ordered truth.

Fields:

- cursor;
- timestamp;
- event type;
- subject id;
- task id;
- authority id;
- payload reference.

Kernel guarantees:

- append-only order;
- serial/debug export;
- runtime subscription by cursor;
- audit-critical events cannot be hidden by generated UI.

## 7. Syscall ABI MVP

Fluid starts with a narrow ABI. POSIX can be emulated later if useful, but it is
not the core contract.

```c
// task
sys_task_create(intent, len, flags) -> task
sys_task_current() -> task
sys_task_cancel(task, reason, len) -> int
sys_task_complete(task, result, len) -> int

// capability
sys_cap_open(task, cap_id, len, flags) -> cap
sys_cap_call(cap, req, req_len, resp, resp_len, flags) -> int
sys_cap_close(cap) -> int

// provider
sys_provider_register(manifest, len) -> provider
sys_provider_accept(provider, call_buf, len, flags) -> call
sys_provider_reply(call, resp, len, status) -> int

// surface
sys_surface_create(task, desc, len, flags) -> surface
sys_surface_present(surface, buffer, dirty_rects, count) -> int
sys_surface_input_next(surface, event, flags) -> int
sys_trusted_surface_create(task, cap, desc, len) -> trusted
sys_trusted_surface_confirm(trusted, payload, len) -> int

// graph/log
sys_graph_subscribe(after_cursor, flags) -> graph
sys_graph_read(graph, buf, len) -> int
sys_log(level, ptr, len) -> int

// network
sys_net_open(task, policy, len) -> net
sys_net_send(net, buf, len) -> int
sys_net_recv(net, buf, len, flags) -> int
```

## 8. UI ABI

Native UI is Fluid Projection IR, not DOM.

Example:

```json
{
  "surface": "generated",
  "task": "order_food",
  "nodes": [
    {"type": "text", "id": "title", "text": "Dinner options"},
    {"type": "card", "id": "spice_lab", "action": "cap.food.createOrder"},
    {"type": "button", "id": "confirm", "action": "trusted.payment.confirmAndPay"}
  ]
}
```

Minimum node types:

- text;
- image placeholder;
- card;
- button;
- list;
- input;
- modal;
- receipt;
- graph strip.

Minimum interactions:

- click;
- key;
- text input;
- scroll;
- focus change;
- trusted confirm/cancel.

Long-term bridge:

```text
HTML / JSX / generated code -> userspace compiler -> Fluid Projection IR -> kernel surface -> framebuffer
```

The investor claim should not be that the kernel renders HTML. The stronger
claim is that the OS has a native, transparent generated-interface ABI designed
for Agents.

## 9. Networking MVP

Network is required because tasks need live providers, but first networking must
be narrow.

Stage sequence:

1. PCI scan discovers virtio-net.
2. Driver negotiates virtio status and features.
3. Driver allocates RX/TX virtqueues.
4. Driver sends and receives Ethernet frames.
5. ARP works.
6. IPv4 works.
7. DHCP gets an address.
8. UDP works.
9. DNS library runs in userspace.
10. TCP or narrow HTTP gateway works.
11. TLS remains userspace/provider-owned.

Kernel responsibilities:

- own packet handles;
- enforce task/capability network policy;
- audit net open/send/recv;
- expose narrow sys_net ABI.

Kernel non-responsibilities:

- HTTP semantics;
- restaurant API semantics;
- TLS certificate policy in MVP;
- Wi-Fi scanning/association in MVP.

## 10. Development Flow

Every stage has artifacts, verifier evidence, and a demo story.

### Stage A: Simulator and ABI Lock

Goal: lock object model before kernel complexity.

Deliverables:

- syscall ABI draft;
- task/cap/provider/surface simulator;
- food-order transcript;
- projection IR examples;
- graph event schema.

Exit criteria:

- order-food flow emits stable graph events in simulator.

### Stage B: Bootable Toy Kernel

Goal: prove new boot path.

Deliverables:

- custom boot image;
- serial output;
- framebuffer clear/draw;
- keyboard input;
- graph ring;
- hardcoded food flow.

Exit criteria:

- QEMU/UTM boots a non-Linux image;
- native intent surface appears;
- serial graph proves task/capability/surface/trusted events.

### Stage C: Protected Mode and Early Isolation

Goal: start acting like a real kernel.

Deliverables:

- GDT/IDT/TSS;
- syscall interrupt;
- CPL3 entry;
- allocator;
- task/cap/provider/trusted records;
- keyboard/pointer/scroll input;
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

- provider replies through userspace IPC;
- trusted confirmation is handled by trusted userspace;
- kernel only brokers handles, routing, scheduling, isolation, and audit.

### Stage E: Credible Memory Isolation

Goal: make the security story believable.

Deliverables:

- real physical page allocator;
- virtual memory mappings;
- per-process page directories;
- user/kernel copy helpers;
- guard pages;
- fault recovery;
- panic/crash log buffer.

Exit criteria:

- userspace cannot write kernel memory;
- provider and trusted service have separate address spaces;
- invalid access is trapped and audited.

### Stage F: Network Provider

Goal: connect provider to real network.

Deliverables:

- virtio-net TX/RX DMA;
- virtio interrupt handling;
- ARP;
- IPv4;
- DHCP;
- UDP;
- DNS in userspace;
- TCP or HTTP gateway;
- network policy handles.

Exit criteria:

- provider calls a local or external endpoint through sys_net;
- graph shows net.open, net.send, net.recv, provider result.

### Stage G: Investor Demo Image

Goal: repeatable story in a VM.

Deliverables:

- bootable QEMU/UTM image;
- one-command launcher;
- native generated food-order surface;
- pointer/keyboard/scroll interaction;
- userspace provider;
- trusted payment gate;
- receipt;
- debug graph overlay;
- serial transcript;
- screenshots;
- screencast;
- verifier from fresh clone.

Exit criteria:

- VM boots into FluidOS without Linux/Android/browser;
- user completes food demo;
- debug graph proves task/capability/provider/surface/trusted/network events;
- demo repeats deterministically.

### Stage H: First Hardware Demo

Goal: leave VM-only territory.

Deliverables:

- UEFI boot on locked x86_64 mini PC;
- GOP framebuffer;
- timer and interrupt controller;
- USB keyboard/pointer or simple PS/2 fallback;
- one Ethernet driver;
- same food demo through real Ethernet.

Exit criteria:

- real machine boots FluidOS directly;
- no Linux underneath;
- demo completes with graph evidence.

## 11. Current Implementation Status

Current image:

- `build/fluid-kernel-stagec-pm.img`

Already proven in this repo:

- non-Linux boot path;
- 32-bit protected mode;
- GDT, IDT, TSS;
- `int 0x80` syscall path;
- PIT tick evidence;
- init-package-loaded CPL3 flat binaries;
- task/capability/provider/trusted records;
- capability table/open/call evidence;
- provider/trusted IPC ring queues;
- init package loader plus manifest lookup;
- real paging enabled;
- page-fault guard probe;
- per-task CR3/address-space records;
- framebuffer-rendered home/trusted/receipt surfaces;
- keyboard, pointer, and scroll input evidence;
- debug graph overlay;
- PCI discovery of virtio-net;
- virtio status, legacy I/O queue-programming, vring descriptor, and Ethernet frame queue proof;
- mock network provider tx/rx graph proof;
- Stage G launcher, screenshots, video package, and UTM-friendly bundle.

Not proven yet:

- long mode;
- complete per-process page directories and copyin/copyout;
- real preemptive scheduling;
- richer userspace service binaries;
- blocking/backpressure IPC;
- real virtio-net packet completion interrupts and inbound Ethernet RX;
- ARP/IP/DHCP/UDP/DNS/TCP;
- polished projection renderer;
- real-hardware UEFI/GOP/Ethernet boot.

## 12. Immediate Build Order

The next work should avoid random features and move directly through credibility
gaps.

1. Real virtio-net packet completion evidence beyond current queue programming, ARP-frame queue, and notify.
2. ARP and IPv4 minimum stack.
3. DHCP or static IP plus UDP.
4. Local HTTP gateway or provider network call.
5. Per-process page directories and copyin/copyout verifier.
6. Provider/trusted service split into real userspace binaries.
7. Projection IR renderer with text/card/list/button/receipt primitives.
8. UEFI/GOP x86_64 boot path.
9. First Ethernet hardware target.

## 13. Verifier Rules

No claim is accepted without automated evidence.

For every feature, add:

- serial graph line;
- in-memory object record;
- verifier required string or pixel check;
- screenshot or transcript when visual;
- negative test when security-related.

Examples:

- network feature requires net.open, net.send, net.recv, provider result;
- trusted feature requires generated-surface denial plus trusted-surface confirm;
- memory feature requires a blocked invalid write or handled fault;
- renderer feature requires pixel or screenshot evidence;
- boot feature requires QEMU launch from a fresh image.

## 14. Public Narrative

Safe public claims now:

- We are building a new Agent-native OS kernel.
- The demo boots without Linux, Android, WebView, or a browser.
- Tasks, capabilities, generated surfaces, trusted gates, and graph events are
  kernel-visible primitives.
- The UI is generated from transparent projection IR and rendered natively.
- The current target is VM first, then one locked x86_64 Ethernet machine.

Avoid claiming yet:

- production phone OS;
- Android replacement;
- mature driver ecosystem;
- production security;
- real Wi-Fi stack;
- GPU acceleration;
- faster than Linux/Android;
- complete network stack until packet I/O is real.
