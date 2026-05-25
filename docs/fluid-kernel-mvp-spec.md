# Fluid Kernel MVP Spec And Development Flow

Version: 0.2 draft
Date: 2026-05-22
Status: execution spec for a new Agent-native kernel

## 1. One-Sentence Positioning

Fluid Kernel is a new kernel for an Agent-native operating system where the
primary OS object is not an app or window, but a user intent task connected to
capability handles, generated surfaces, trusted gates, and an auditable task
graph.

The first public target is not to beat Linux on device support. The first target
is to boot a non-Linux kernel and show that tasks, capabilities, generated UI,
and trusted actions are kernel-level primitives.

## 2. Product Claims We Can Defend

Strong claims:

- New kernel boot path: no Linux kernel, no Android framework, no browser shell.
- Task-first OS: kernel-visible task objects represent user intent.
- Capability-first execution: providers are called through kernel-issued handles.
- Generated surfaces: UI is a projection of task state, not an app-owned window.
- Trusted surface primitive: critical actions are rendered and routed separately.
- Audit graph: task/capability/provider/surface/trusted transitions are first-class
  kernel events.

Claims to avoid before hardware work exists:

- Complete mobile OS.
- Android replacement on arbitrary phones.
- Full driver ecosystem.
- Production security.
- Better performance than mature kernels.

## 3. Ruthless MVP Scope

### Keep

These are required for a convincing Agent-native demo:

1. Boot and early architecture setup.
2. Physical memory allocator and minimal virtual memory.
3. Timer interrupt and preemptive scheduling.
4. Process/thread model for Fluid Init, runtime, providers, and trusted service.
5. Syscall ABI.
6. Kernel IPC/message queues.
7. Capability handle table.
8. Task registry.
9. Authority session table.
10. Graph event ring and serial/debug graph output.
11. Display path: framebuffer first, software rendering.
12. Input path: keyboard, pointer, scroll/touch later.
13. Network path: VM virtio-net first; Wi-Fi later on one reference device.
14. Initramfs or read-only boot package.
15. Crash/panic serial log.
16. Trusted surface input capture and audit.

### Cut For MVP

Cut aggressively until the demo is undeniable:

- Android app compatibility.
- POSIX/Linux binary compatibility.
- Browser/WebView engine.
- Bluetooth.
- Audio.
- Camera.
- Cellular modem.
- GPU acceleration.
- Multi-monitor.
- Suspend/resume.
- Power optimization.
- USB hotplug beyond boot keyboard/pointer if avoidable.
- Full filesystem.
- Package manager UI.
- Multi-user accounts.
- Printing/scanning.
- Accessibility stack.
- General desktop window manager.

## 4. Reference Targets

### Target 0: QEMU x86_64 Or i386 BIOS Demo

Purpose: fastest proof of a new bootable kernel.

Required virtual devices:

- Serial console for verifier logs.
- VGA/linear framebuffer or simple packed framebuffer.
- PS/2 keyboard and pointer initially.
- Virtio-net later.
- Initramfs embedded in the image.

Why this target:

- Easy local automation.
- Easy screenshots and serial verification.
- Good for investor demos and CI.

### Target 1: UTM On Apple Silicon

Purpose: your Mac-friendly demo package.

Recommended path:

- Keep the kernel architecture portable.
- Use QEMU/UTM for display, serial, and network.
- Prefer virtio devices where possible.

### Target 2: One Reference Hardware Device

Purpose: later credibility outside VM.

Pick one only:

- x86_64 mini PC with Ethernet first; or
- ARM board with documented boot flow and Ethernet/Wi-Fi.

Do not target Android phones first. Phone boot chains, GPU, touch, modem, Wi-Fi,
power, secure boot, and vendor firmware will swallow the project before the
Agent-native architecture is proven.

## 5. Architecture

```text
Hardware / VM
  bootloader
  Fluid Kernel
    arch
    mem
    sched
    syscall
    ipc
    task
    cap
    authority
    graph
    surface
    input
    net
    initrd
    log
  Fluid Init
    starts runtime services
    starts provider services
    starts surface runtime
  Fluid Runtime
    agent planner
    task planner
    capability registry client
    interface projection generator
  Provider Services
    food provider
    payment/mock trusted provider
    network-backed providers later
  Surface Runtime
    generated task surfaces
    trusted surfaces
    graph/debug overlay
```

The kernel should stay small. It owns isolation, scheduling, memory, handles,
IPC, event ordering, input routing, and trusted-surface enforcement. It should
not contain a browser engine or an LLM.

## 6. Kernel Object Model

### Task

Represents one user intent.

Fields:

- `task_id`
- `owner_authority`
- `state`
- `priority_hint`
- `deadline_hint`
- `current_surface`
- `graph_cursor`

Kernel guarantees:

- every provider call is bound to a task;
- every generated surface is bound to a task;
- task cancel/complete emits graph events;
- trusted gates must reference a task.

### Capability

Represents an operation the Agent/runtime may call.

Fields:

- `capability_id`
- `provider_id`
- `risk_level`
- `authority_policy`
- `network_policy`
- `requires_trusted_surface`

Kernel guarantees:

- callers receive opaque handles, not ambient authority;
- calls without handles fail;
- risky capabilities require trusted flow;
- open/call/reply are audited.

### Provider

Represents an isolated service implementing capabilities.

Fields:

- `provider_id`
- `process_id`
- `authority_profile`
- `allowed_capabilities`
- `network_scope`
- `health_state`

Kernel guarantees:

- provider IPC endpoint is explicit;
- provider resource budget is enforceable later;
- provider crash emits graph event;
- provider cannot impersonate trusted UI.

### Surface

Represents a task-bound generated UI projection.

Fields:

- `surface_id`
- `task_id`
- `surface_type`: `generated`, `trusted`, `system`, `debug`
- `trust_level`
- `input_policy`
- `buffer_handle`

Kernel guarantees:

- generated UI cannot confirm trusted actions;
- trusted surface is above generated surface;
- trusted surface captures direct input;
- input events are tagged with authority.

### Graph Event

Represents ordered truth about the system.

Fields:

- `cursor`
- `timestamp`
- `event_type`
- `subject_id`
- `task_id`
- `authority_id`
- `payload_ref`

Kernel guarantees:

- append-only event order;
- serial/debug export;
- runtime can subscribe from cursor;
- audit-critical events cannot be hidden by generated UI.

## 7. Syscall ABI MVP

Use a narrow Fluid-specific ABI first. Do not chase POSIX.

```c
// task
sys_task_create(intent_ptr, intent_len, flags) -> task_handle
sys_task_current() -> task_handle
sys_task_cancel(task, reason_ptr, reason_len) -> int
sys_task_complete(task, result_ptr, result_len) -> int

// capability
sys_cap_open(task, cap_id_ptr, cap_id_len, flags) -> cap_handle
sys_cap_call(cap, req_ptr, req_len, resp_ptr, resp_cap, flags) -> int
sys_cap_close(cap) -> int

// provider
sys_provider_register(manifest_ptr, manifest_len) -> provider_handle
sys_provider_accept(provider, call_buf, call_buf_len) -> call_handle
sys_provider_reply(call, resp_ptr, resp_len, status) -> int

// authority
sys_authority_current() -> authority_handle
sys_authority_enter(token_ptr, token_len, flags) -> authority_handle
sys_authority_drop(authority) -> int

// surface
sys_surface_create(task, desc_ptr, desc_len, flags) -> surface_handle
sys_surface_present(surface, buffer, dirty_rect_ptr, dirty_rect_count) -> int
sys_surface_input_next(surface, event_ptr, flags) -> int
sys_trusted_surface_create(task, cap, desc_ptr, desc_len) -> trusted_handle
sys_trusted_surface_confirm(trusted, payload_ptr, payload_len) -> int

// graph/log
sys_graph_subscribe(after_cursor, flags) -> graph_handle
sys_graph_read(graph, buf, buf_len) -> int
sys_log(level, ptr, len) -> int

// network MVP
sys_net_open(policy_ptr, policy_len) -> net_handle
sys_net_send(net, buf, len) -> int
sys_net_recv(net, buf, len, flags) -> int
```

## 8. Network Strategy

### VM Network MVP

Required sequence:

1. Virtio-net device discovery.
2. RX/TX virtqueue setup.
3. Ethernet frame send/receive.
4. ARP.
5. IPv4.
6. UDP.
7. DHCP client.
8. DNS client in userspace.
9. TCP in userspace or minimal kernel/user split.
10. TLS in userspace provider library.

Kernel should not know HTTP or restaurant APIs. Kernel only provides packet path,
network handles, and policy/audit hooks.

### Wi-Fi Later

Wi-Fi is not a first-kernel problem. For a first real device, prefer Ethernet.
If Wi-Fi is mandatory later, pick one chipset and one driver strategy only.

## 9. Display And UI Strategy

### Rendering Rule

HTML can remain an interface description inspiration, but the first kernel demo
should render native task surfaces directly through the Fluid surface ABI.

Pipeline:

```text
intent -> task graph -> interface projection JSON/IR -> software renderer -> framebuffer
```

MVP generated interface IR:

```json
{
  "surface": "generated",
  "task": "order_food",
  "nodes": [
    {"type":"text", "id":"title", "text":"Dinner options"},
    {"type":"card", "id":"spice_lab", "action":"cap.food.createOrder"},
    {"type":"button", "id":"confirm", "action":"trusted.payment.confirmAndPay"}
  ]
}
```

The important architectural claim is not that it uses HTML. The important claim
is that the UI is transparent, generated, inspectable, task-bound, and executable
by the Agent/runtime.

## 10. Development Flow

### Stage A: Spec + Simulator

Goal: lock the ABI and task/capability/surface model before kernel complexity.

Deliverables:

- Fluid syscall ABI draft.
- Userspace simulator for task/capability/provider/trusted flow.
- Food-order demo emits the exact graph events expected from the kernel.

Exit criteria:

- `order food -> provider call -> generated surface -> trusted payment -> receipt`
  works in simulator and produces a stable event transcript.

### Stage B: Bootable Toy Kernel

Goal: prove new kernel boot and serial/screen output.

Deliverables:

- custom boot image;
- serial log;
- framebuffer clear/draw;
- keyboard input;
- graph ring;
- hardcoded food-flow state machine.

Exit criteria:

- QEMU boots non-Linux image;
- screen shows Fluid intent surface;
- serial log proves graph events.

### Stage C: Protected Mode / Early Isolation

Goal: leave real mode, introduce real kernel foundations.

Deliverables:

- GDT/IDT/TSS;
- syscalls;
- CPL3 Fluid Init proof;
- bump allocator;
- task/capability/provider/trusted records;
- keyboard/pointer input;
- framebuffer renderer.

Exit criteria:

- user payload enters CPL3 and returns through syscall;
- provider/trusted dispatch is visible as task-bound IPC evidence;
- verifier checks serial events and framebuffer pixels.

### Stage D: Real Userspace Services

Goal: stop faking provider/trusted services in kernel.

Deliverables:

- process loader from initramfs;
- basic ELF or flat binary loader;
- scheduler;
- provider process;
- trusted-surface process;
- IPC queues;
- capability handles.

Exit criteria:

- Fluid Init, provider, trusted service run as separate userspace tasks;
- provider replies through IPC;
- trusted confirmation is not kernel-hardcoded.

### Stage E: Memory And Filesystem Foundation

Goal: make the kernel maintainable.

Deliverables:

- physical page allocator;
- virtual address spaces;
- per-process mappings;
- kernel heap;
- initramfs file lookup;
- crash dump/log buffer.

Exit criteria:

- userspace tasks have separate address spaces;
- services are loaded from initramfs;
- kernel can recover useful panic logs.

### Stage F: Network Provider

Goal: make the demo truly connected.

Deliverables:

- virtio-net;
- DHCP;
- UDP/DNS;
- TCP path;
- simple HTTPS-capable provider in userspace, or mocked TLS boundary for demo;
- network policy graph events.

Exit criteria:

- provider can call an external or local HTTP endpoint through Fluid network handle;
- graph shows `net.open`, `net.send`, `net.recv`, and provider capability result.

### Stage G: Investor Demo Image

Goal: package the story.

Deliverables:

- bootable QEMU/UTM image;
- native intent screen;
- keyboard/pointer interaction;
- generated food-order interface;
- trusted payment gate;
- receipt;
- graph inspector/serial transcript;
- one-command host launcher;
- screenshots and screencast.

Exit criteria:

- a clean VM boots into FluidOS without Linux/Android/browser;
- user can complete the food demo;
- debug graph proves task/capability/provider/surface/trusted events;
- demo can be repeated from a fresh clone.

## 11. Engineering Rules

- Every new feature must add verifier evidence.
- Serial graph is a product feature, not just debugging.
- Prefer boring hardware targets and radical OS objects.
- Do not put Agent/LLM code in kernel.
- Do not put browser/HTML engine in kernel.
- Keep provider APIs replaceable.
- Make the first demo deterministic before making it smart.
- Use generated UI IR first; HTML compatibility can be a userspace translator later.

## 12. Recommended Near-Term Implementation Order

1. Move provider and trusted handlers to CPL3 userspace payloads.
2. Add syscall continuation so kernel can resume flow after userspace calls.
3. Add a real task scheduler with at least three runnable tasks.
4. Add IPC queues instead of fixed mailboxes.
5. Add initramfs and flat binary loader.
6. Move food provider into a userspace provider binary.
7. Move trusted gate into a userspace trusted service.
8. Replace rectangle-only renderer with text/cards/buttons in software.
9. Add virtio-net and a local-network provider call.
10. Package QEMU/UTM demo and verifier.

## 13. Demo Narrative

Use this wording:

> FluidOS is not app-first. It is task-first. The kernel knows tasks,
> capabilities, generated surfaces, trusted gates, and the audit graph. Apps are
> no longer the primitive; capabilities are. Interfaces are generated projections
> over live task state.

Then show:

1. Boot non-Linux Fluid Kernel.
2. Type or select food intent.
3. Kernel creates a task and graph event.
4. Runtime opens food capability.
5. Provider returns options/order.
6. Generated native surface appears.
7. Trusted payment gate captures input.
8. Receipt appears.
9. Graph inspector shows every transition.
