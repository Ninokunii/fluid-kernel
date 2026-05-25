# Fluid Kernel Spec

Version: 0.1 draft
Date: 2026-05-22
Status: architecture proposal

## 1. Product Positioning

Fluid Kernel is a new kernel designed for an Agent-native operating system. Its
purpose is not to be a general-purpose Unix clone at first. Its purpose is to
make the OS primitive match the product primitive:

- user intent becomes a task;
- task execution is planned by an Agent;
- capabilities replace apps as the executable unit;
- interfaces are generated projections over task state;
- trusted gates isolate critical actions;
- system state is observable as a graph.

Fluid Kernel should be presented as a new kernel architecture, while early
implementations may run on a narrow hardware/VM target and intentionally omit
many conventional OS features.

## 2. Non-Goals For The First Kernel

The first Fluid Kernel is not trying to support every device or desktop feature.
These are explicitly out of scope for the MVP:

- Android compatibility.
- POSIX compatibility beyond a small compatibility shim.
- Linux binary compatibility.
- Multi-user desktop sessions.
- Bluetooth.
- Camera.
- Cellular modem.
- GPU acceleration.
- Audio stack.
- Printer/scanner support.
- Complex filesystem features.
- App package compatibility.
- Browser engine in kernel or system UI.
- Full power management.
- Suspend/resume.
- Secure boot production chain.
- Full hardware driver ecosystem.

The MVP can run in a VM first. Hardware support can come later.

## 3. MVP Must-Haves

The MVP must support one convincing Agent-native demo end to end:

1. Boot into Fluid Kernel.
2. Start Fluid Runtime as the first userspace process.
3. Show a native intent surface.
4. Accept keyboard/mouse input.
5. Connect to network.
6. Let Agent/runtime call capability providers.
7. Generate a task interface.
8. Render the generated interface.
9. Execute a trusted gate flow.
10. Emit system graph events.

Therefore the MVP kernel must provide:

- process/thread scheduling;
- virtual memory;
- basic IPC;
- capability-handle namespace;
- task object namespace;
- graph event queue;
- network device path;
- display framebuffer path;
- keyboard/pointer input path;
- provider isolation primitive;
- trusted surface primitive;
- minimal filesystem/initrd;
- crash logging;
- timer/clock;
- entropy/random;
- a small syscall ABI.

## 4. Hardware Target Strategy

### 4.1 Phase 0 Target: VM Only

First target should be a VM, not random consumer hardware.

Recommended target:

- aarch64 VM on Apple Silicon via UTM/QEMU, or
- x86_64 QEMU on developer machines.

Minimum virtual devices:

- virtio-net for network;
- virtio-input or PS/2 keyboard/mouse;
- virtio-gpu framebuffer or simple framebuffer;
- virtio-block or initramfs-only root;
- serial console for logs.

### 4.2 Phase 1 Target: One Reference Device

After VM success, choose exactly one hardware target:

- a dev board with known documentation;
- or one mini PC with simple x86_64 hardware;
- or one ARM board with supported Wi-Fi/Ethernet.

Do not target phones first. Phones require modem, touch, GPU, power, secure boot,
and vendor firmware complexity.

## 5. Kernel Architecture

Fluid Kernel should be a hybrid microkernel-style architecture:

- The kernel owns scheduling, memory, IPC, event queues, capability handles,
  task identities, and trusted surface primitives.
- Drivers should be userspace services when possible.
- Providers are userspace services with kernel-enforced authority profiles.
- The Agent/runtime is userspace, but uses first-class kernel objects.

High-level stack:

```text
Fluid Kernel
  - scheduler
  - memory manager
  - IPC
  - capability handle table
  - task registry
  - graph event queue
  - provider isolation
  - trusted surface primitive
  - framebuffer/input/net/block drivers

Fluid Init
  - starts runtime services
  - mounts minimal fs
  - starts graph daemon if not kernel-resident

Fluid Runtime
  - Agent planner
  - task runtime
  - capability registry
  - provider manager
  - interface generator
  - policy engine

Fluid Surface Runtime
  - native renderer
  - generated interface projection
  - trusted gate renderer
```

## 6. Core Kernel Objects

Fluid Kernel should expose these objects as first-class concepts.

### 6.1 Task

A task is the kernel-visible execution context for a user intent.

Fields:

- `task_id`
- `owner_session`
- `state`
- `priority`
- `created_at`
- `deadline_hint`
- `authority_context`
- `graph_cursor`

Kernel responsibilities:

- assign task id;
- bind processes/provider calls to task;
- expose task lifecycle events;
- support task cancellation;
- support task priority hints.

### 6.2 Capability

A capability is an operation the Agent may call.

Fields:

- `capability_id`
- `provider_id`
- `risk_level`
- `permission_scope`
- `requires_trusted_surface`
- `io_policy`
- `network_policy`

Kernel responsibilities:

- issue opaque capability handles;
- check caller authority;
- emit audit event on open/call;
- route to provider IPC endpoint;
- deny calls that violate policy.

### 6.3 Provider

A provider is a userspace service that implements capabilities.

Fields:

- `provider_id`
- `process_id`
- `authority_profile`
- `allowed_capabilities`
- `resource_budget`
- `network_scope`
- `health_state`

Kernel responsibilities:

- isolate provider process;
- attach cgroup-like budget;
- restrict IPC and network;
- restart is userspace supervisor responsibility;
- emit crash/exit events.

### 6.4 Authority Session

An authority session represents who is acting.

Examples:

- `sess.runtime`
- `sess.agent`
- `sess.generated-ui`
- `sess.trusted-ui`
- `sess.provider.food`

Kernel responsibilities:

- bind syscalls to authority session;
- enforce critical capability restrictions;
- prevent generated UI from confirming trusted actions.

### 6.5 Interface Projection

An interface projection is not a process-owned app window. It is a task-bound
surface.

Fields:

- `interface_id`
- `task_id`
- `surface_id`
- `renderer_session`
- `trust_level`
- `layout_hash`

Kernel responsibilities:

- create surface handle;
- bind surface to task;
- isolate generated surfaces from trusted surfaces;
- route input according to surface trust.

### 6.6 Trusted Surface

A trusted surface is a secure UI path for critical capabilities.

MVP guarantees:

- generated UI cannot create trusted surface;
- generated UI cannot inject input into trusted surface;
- trusted surface receives direct input routing;
- trusted confirmations include authority session id;
- all trusted confirmations are audited.

### 6.7 Graph Event

Every important kernel/system transition emits graph events.

Examples:

- `task.created`
- `task.cancelled`
- `capability.opened`
- `capability.called`
- `provider.started`
- `provider.exited`
- `interface.created`
- `trusted_surface.created`
- `trusted_surface.confirmed`

Kernel responsibilities:

- maintain ordered event cursor;
- allow subscription;
- allow snapshot cursor;
- expose event queue to Agent/runtime.

## 7. Syscall / ABI Draft

The MVP syscall ABI can be narrow and Fluid-specific. Names are conceptual.

### Task syscalls

```c
fluid_task_create(intent_ptr, intent_len, flags) -> task_handle
fluid_task_current() -> task_handle
fluid_task_set_priority(task_handle, priority_hint) -> int
fluid_task_cancel(task_handle, reason_ptr, reason_len) -> int
fluid_task_commit(task_handle, commit_ptr, commit_len) -> int
```

### Capability syscalls

```c
fluid_cap_open(capability_id_ptr, len, task_handle, flags) -> cap_handle
fluid_cap_call(cap_handle, request_ptr, request_len, response_ptr, response_len) -> int
fluid_cap_close(cap_handle) -> int
```

### Provider syscalls

```c
fluid_provider_register(manifest_ptr, manifest_len) -> provider_handle
fluid_provider_accept(provider_handle) -> call_handle
fluid_provider_reply(call_handle, response_ptr, response_len) -> int
fluid_provider_health(provider_handle, status) -> int
```

### Authority syscalls

```c
fluid_authority_enter(session_id_ptr, len, token_ptr, token_len) -> authority_handle
fluid_authority_current() -> authority_handle
fluid_authority_drop(authority_handle) -> int
```

### Graph syscalls

```c
fluid_graph_subscribe(after_cursor, flags) -> graph_stream_handle
fluid_graph_read(graph_stream_handle, buffer_ptr, buffer_len) -> int
fluid_graph_snapshot(buffer_ptr, buffer_len) -> int
```

### Surface syscalls

```c
fluid_surface_create(task_handle, descriptor_ptr, descriptor_len) -> surface_handle
fluid_surface_present(surface_handle, buffer_handle) -> int
fluid_surface_input_subscribe(surface_handle) -> input_stream_handle
fluid_trusted_surface_create(task_handle, cap_handle, descriptor_ptr, len) -> trusted_surface_handle
fluid_trusted_surface_confirm(trusted_surface_handle, payload_ptr, len) -> int
```

### IO syscalls

```c
fluid_net_open(policy_ptr, policy_len) -> net_handle
fluid_net_send(net_handle, buffer_ptr, len) -> int
fluid_net_recv(net_handle, buffer_ptr, len) -> int
fluid_time_now() -> timestamp
fluid_log(level, message_ptr, len) -> int
```

## 8. Display Model

MVP display can be simple:

- one primary framebuffer;
- one compositor process in userspace;
- SHM buffers first;
- no GPU acceleration required;
- fixed resolution initially;
- double buffering;
- dirty rectangle optional.

The compositor is not an app window manager. It manages task surfaces:

- generated task surface;
- trusted surface;
- system status surface;
- debug/serial overlay if enabled.

Trusted surface must always appear above generated surfaces.

## 9. Input Model

MVP input:

- keyboard;
- pointer;
- scroll wheel / axis;
- optional touch later.

Input routing rules:

- active generated surface receives normal input;
- trusted surface captures input while active;
- generated UI cannot synthesize trusted input;
- all input delivered to trusted surface is tagged with authority context.

## 10. Network Model

MVP network must exist because Agent/capability providers need external calls.

Phase 0:

- virtio-net Ethernet in VM;
- IPv4 DHCP;
- DNS resolver in userspace;
- TCP client support;
- TLS in userspace library, not kernel.

Phase 1:

- Wi-Fi via one supported chipset or external userspace driver path;
- network permission per provider;
- per-capability network audit.

Kernel should not implement high-level HTTP. Providers do HTTP/TLS in userspace.

## 11. Filesystem Model

MVP can avoid a complex filesystem.

Phase 0:

- initramfs contains Fluid runtime and providers;
- read-only image;
- small append-only log store;
- optional virtio-block for state.

Phase 1:

- simple filesystem or port an existing small FS;
- persistent task log;
- provider package store;
- crash dump store.

## 12. Security Model

Fluid Kernel security centers on authority sessions and capabilities, not app
packages.

Rules:

- no process can call a capability without a handle;
- no handle is issued without authority check;
- generated UI has no critical authority;
- trusted UI authority cannot be impersonated by generated UI;
- providers are isolated by authority profile;
- network is denied by default unless profile allows it;
- graph events are append-only;
- audit events include task id, authority session, capability id, provider id.

## 13. Scheduling Model

MVP scheduler can be simple round-robin or priority-based.

Fluid-specific additions:

- task priority hints;
- trusted surface priority boost;
- input-to-render priority path;
- provider call deadline hints;
- Agent planning can be background priority unless user-visible.

Do not over-engineer scheduler first. The first goal is deterministic demo flow.

## 14. Development Strategy

### Stage A: Spec and Simulator

Goal: prove the ABI before kernel implementation.

Deliverables:

- `fluid-kernel-spec.md`;
- userspace simulator for syscalls;
- current Linux FluidOS runtime maps to future ABI;
- demo still works.

### Stage B: Toy Kernel Boot

Goal: boot a screen and log events.

Deliverables:

- custom bootable kernel for QEMU;
- serial console;
- memory allocator;
- basic scheduler;
- framebuffer clear/draw;
- keyboard input;
- graph event ring buffer.

### Stage C: Fluid Init and Surface

Goal: boot into a native Fluid surface.

Deliverables:

- init process;
- surface primitive;
- basic input routing;
- native renderer ported or rewritten for kernel surface ABI;
- static intent screen.

### Stage D: Provider IPC and Capability Handles

Goal: call capabilities without POSIX/Linux assumptions.

Deliverables:

- provider registration;
- capability open/call/reply;
- authority sessions;
- graph events for calls;
- mock food provider.

### Stage E: Network MVP

Goal: external HTTP-capable providers.

Deliverables:

- virtio-net driver;
- userspace network stack or small kernel/user split;
- DHCP;
- DNS;
- TCP;
- TLS in provider runtime;
- network policy hooks.

### Stage F: Trusted Surface

Goal: payment demo with trusted gate.

Deliverables:

- trusted surface primitive;
- input capture;
- generated UI denial path;
- trusted confirmation audit;
- receipt interface.

### Stage G: Bootable Demo Image

Goal: investor/demo image.

Deliverables:

- QEMU/UTM boot image;
- no Linux userspace;
- no browser;
- Agent-native food demo;
- graph inspector/debug console;
- crash logs.

## 15. Implementation Language Options

Recommended split:

- Kernel: Rust or C.
- Boot/early arch: small amount of assembly.
- Userspace runtime: Rust first, Python only for simulator/prototyping.
- Renderer: C/Rust with software rasterizer first.

Rust advantages:

- memory safety;
- strong type model for handles;
- better long-term security story.

C advantages:

- simpler bootstrapping examples;
- easier low-level control;
- more OSDev references.

Recommendation: Rust kernel for product narrative, with a tiny assembly boot path.

## 16. Minimal Module List

MVP kernel modules:

1. `arch`: boot, interrupts, CPU setup.
2. `mem`: physical/virtual memory allocator.
3. `sched`: threads/processes.
4. `ipc`: message queues.
5. `task`: Fluid task registry.
6. `cap`: capability handle table.
7. `authority`: authority session table.
8. `graph`: event queue and snapshot cursor.
9. `surface`: framebuffer/surface handles.
10. `input`: keyboard/pointer events.
11. `net`: virtio-net path.
12. `provider`: provider registry/call routing.
13. `trusted`: trusted surface enforcement.
14. `log`: serial/crash logs.
15. `initrd`: load initial userspace.

## 17. What To Cut Aggressively

Cut these until the demo is strong:

- multiple monitors;
- GPU acceleration;
- Bluetooth;
- sound;
- camera;
- USB hotplug beyond keyboard/mouse if possible;
- phone hardware;
- battery optimization;
- app compatibility;
- full shell;
- full POSIX;
- multi-user;
- printing;
- accessibility stack;
- file manager;
- package manager UI.

## 18. Naming

Recommended external wording:

- Fluid Kernel: an Agent-native kernel.
- FluidOS: the operating system built around Fluid Kernel.
- Capability-first OS, not app-first OS.
- Task graph and capability handles are kernel primitives.
- Interfaces are generated task projections.

Avoid claiming mature hardware support early. Claim architecture and bootable
prototype.

## 19. Success Criteria For First Public Demo

A successful first public demo should show:

1. A VM boots Fluid Kernel, not Linux.
2. The first screen is an intent surface.
3. User asks for food.
4. Agent calls food provider.
5. Generated native UI appears.
6. User selects an option.
7. Trusted gate appears.
8. Payment confirmation emits audit/graph event.
9. Receipt appears.
10. Debug graph shows task/capability/provider/interface/trusted events.

If this works, the product story is credible even with many drivers omitted.

