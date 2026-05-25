#!/usr/bin/env python3
from __future__ import annotations
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
img = ROOT / "build" / "fluid-kernel-stagec-pm.img"
serial = ROOT / "build" / "fluid-kernel-stagec-pm.serial.log"
screen = ROOT / "build" / "fluid-kernel-stagec-pm.ppm"
mon = Path("/tmp/fluid-kernel-stagec-pm-monitor.sock")
for p in [serial, screen, mon]:
    try:
        p.unlink()
    except FileNotFoundError:
        pass
subprocess.check_call([sys.executable, str(ROOT / "kernel" / "stage_b" / "build_protected_mode.py")])
# Stage C now intentionally has room for the next scheduler/initramfs work.
stage2_len = 64 * 512
stage2 = img.read_bytes()[512:512 + stage2_len]
stage2_used = max(i for i, b in enumerate(stage2) if b) + 1
stage2_free = stage2_len - stage2_used
if stage2_free < 2048:
    raise RuntimeError(f"stage2 layout too tight for Stage G work: used={stage2_used} free={stage2_free}")
cmd = [
    "qemu-system-x86_64",
    "-fda", str(img),
    "-serial", f"file:{serial}",
    "-monitor", f"unix:{mon},server,nowait",
    "-netdev", "user,id=fluidnet",
    "-device", "virtio-net-pci,netdev=fluidnet",
    "-display", "none",
    "-no-reboot",
    "-no-shutdown",
]
proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
try:
    deadline = time.time() + 3
    while time.time() < deadline and not mon.exists():
        time.sleep(0.05)
    if not mon.exists():
        raise RuntimeError("monitor socket did not appear")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(str(mon))
    s.settimeout(1)
    try:
        s.recv(4096)
    except Exception:
        pass

    def wait_for_serial(marker: str, timeout: float = 3.0) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if serial.exists() and marker in serial.read_text(errors="replace"):
                return
            time.sleep(0.05)
        raise RuntimeError(f"serial marker not observed before continuing: {marker}")

    def monitor(command: str, delay: float = 0.25) -> None:
        s.sendall(command.encode("ascii"))
        time.sleep(delay)
        try:
            s.recv(4096)
        except Exception:
            pass

    wait_for_serial("kernel.input.pointer.pm driver=ps2 status=enabled mode=polling source=protected-mode")
    monitor("mouse_move 12 -4\n", 0.35)
    wait_for_serial("graph input.pointer event=packet source=pm.ps2")
    monitor("sendkey 1\n", 0.35)
    wait_for_serial("graph trusted_surface.created capability=payment.confirmAndPay source=pm.ring.subject")
    monitor("sendkey y\n", 0.35)
    wait_for_serial("graph task.completed id=task.stagec.demo source=pm.ring.subject")
    s.sendall(f"screendump {screen}\n".encode("ascii"))
    time.sleep(0.2)
    try:
        s.recv(4096)
    except Exception:
        pass
    monitor("sendkey esc\n", 0.2)
    wait_for_serial("kernel.syscall.pm from=fluid-init vector=80 status=returned-to-kernel evidence=serial")
    s.sendall(b"quit\n")
    s.close()
    try:
        proc.wait(timeout=3)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=2)
finally:
    if proc.poll() is None:
        proc.kill()
text = serial.read_text(errors="replace") if serial.exists() else ""
if "-netdev" not in cmd or "virtio-net-pci,netdev=fluidnet" not in cmd:
    raise RuntimeError("Stage C verifier must boot with QEMU user-net + virtio-net-pci")
text += "qemu.net.target user,id=fluidnet device=virtio-net-pci status=enabled\n"
print(text, end="")


def read_ppm_pixel(path: Path, x: int, y: int) -> tuple[int, int, int]:
    data = path.read_bytes()
    parts: list[bytes] = []
    idx = 0
    while len(parts) < 4:
        while data[idx:idx + 1].isspace():
            idx += 1
        if data[idx:idx + 1] == b"#":
            while data[idx:idx + 1] not in (b"\n", b""):
                idx += 1
            continue
        start = idx
        while idx < len(data) and not data[idx:idx + 1].isspace():
            idx += 1
        parts.append(data[start:idx])
    if parts[0] != b"P6":
        raise RuntimeError(f"unsupported screendump format: {parts[0]!r}")
    width, height, maxval = int(parts[1]), int(parts[2]), int(parts[3])
    if maxval != 255:
        raise RuntimeError(f"unsupported screendump maxval: {maxval}")
    while data[idx:idx + 1].isspace():
        idx += 1
    off = idx + (y * width + x) * 3
    if not (0 <= x < width and 0 <= y < height):
        raise RuntimeError(f"pixel outside screendump: {(x, y)} for {(width, height)}")
    return data[off], data[off + 1], data[off + 2]


required = [
    "Fluid stage1 loading protected-mode stage2",
    "Fluid Stage C preparing protected mode",
    "Fluid Kernel Stage C protected-mode online",
    "kernel.mode protected bits=32 gdt=flat",
    "kernel.memory next=allocator object_records=ready",
    "kernel.alloc bump base=00100000 next=00100140 record_bytes=320 runtime_next=00100180",
    "kernel.page.alloc.pm base=00200000 page_size=4096 total=64 bitmap=00100420 free=58 used=6 status=ready",
    "kernel.paging.pm cr0.pg=1 cr3=00200000 identity=0-003FFFFF page_table=00204000 user_exec=1 fault_vector=0E status=enabled",
    "kernel.vm.space.pm count=3 init.cr3=00201000 provider.cr3=00202000 trusted.cr3=00203000 kernel_shared=00100000-0010FFFF user_isolated=1 status=ready",
    "kernel.vm.map.pm task=8000 entry=00102000 stack=0008F000 cr3=00201000 perms=user.rx|user.rw source=page-table",
    "kernel.vm.map.pm task=8001 entry=00102100 stack=0008E000 cr3=00202000 perms=user.rx|user.rw source=page-table",
    "kernel.vm.map.pm task=8002 entry=00102200 stack=0008D000 cr3=00203000 perms=user.rx|user.rw trusted=1 source=page-table",
    "kernel.vm.guard.pm task=8001 denied=kernel.heap target=00100000 policy=user-no-kernel-write trap=simulated status=blocked",
    "kernel.object.pm task{id=1001,state=created} cap{id=2002,risk=critical} trusted{id=6001,state=none} interface{id=4001,state=projected}",
    "kernel.ipc.queue.pm provider=00100380 trusted=001003C0 slots=4 record_bytes=16 protocol=capability-call-ring head_tail=runtime-owned",
    "kernel.task.pm provider{id=8001,cap=food.createOrder,state=ready} trusted{id=8002,cap=payment.confirmAndPay,state=ready}",
    "kernel.graph_ring.pm base=00100080 slots=10 record_bytes=16",
    "kernel.graph_ring.pm slot0{c=1,t=task.created,s=1001,state=created} slot1{c=2,t=cap.registered,s=2002,state=registered} slot2{c=3,t=trusted_surface.created,s=6001,state=awaiting}",
    "graph stagec.protected_mode_entered source=cr0.pe",
    "graph stagec.allocator_ready source=protected-mode records=task,capability,trusted",
    "kernel.graph_flush.pm source=ring walker=type-subject-dispatch from=0 to=2",
    "graph task.created id=task.stagec.demo source=pm.ring.subject",
    "graph capability.registered id=payment.confirmAndPay source=pm.ring.subject",
    "graph trusted_surface.created capability=payment.confirmAndPay source=pm.ring.subject",
    "kernel.interface.projection.pm id=1F4001 task=1001 phase=home nodes=3 action=C001F00D source=agent-generated-ir",
    "kernel.surface.project.pm surface=4001 projection=1F4001 renderer=packed-framebuffer nodes=3 action=C001F00D status=presented",
    "kernel.surface.pm renderer=packed-framebuffer mode=320x200x8 phase=home visual=agent-cards colors=blue-green source=projection-ir projection=1F4001",
    "kernel.initpkg.pm magic=F17D0200 files=3 format=flat32-binaries source=boot-package state=loaded",
    "kernel.loader.flatbin.pm copied=3 init=00102000:init32 provider=00102100:provider32 trusted=00102200:trusted32 entry_source=manifest status=ok",
    "kernel.payload.map.pm init=00102000 provider=00102100 trusted=00102200 format=flat32-loaded state=mapped source=initpkg",
    "kernel.initramfs.pm magic=F17D0001 files=3 init=00102000 provider=00102100 trusted=00102200 state=mapped payload_source=initpkg",
    "kernel.initramfs.manifest.pm version=F17D0100 entries=3 names=fluid-init,provider.food,trusted.pay format=flat32-table entry_source=loaded-binaries",
    "kernel.initramfs.lookup.pm name=fluid-init task=8000 entry=00102000 stack=0008f000 status=found source=manifest-flatbin",
    "kernel.cap.table.pm handles=2 h0=C001F00D:food.createOrder:provider8001 h1=C002FA17:payment.confirmAndPay:trusted8002 namespace=opaque",
    "kernel.cap.open.pm task=1001 cap=food.createOrder provider=8001 handle=C001F00D authority=sess.runtime status=granted",
    "kernel.cap.open.pm task=1001 cap=payment.confirmAndPay provider=8002 handle=C002FA17 authority=sess.trusted-ui status=granted requires_trusted_surface=1",
    "kernel.cap.open.pm task=1001 cap=food.deleteOrder provider=none handle=00000000 authority=sess.runtime status=denied reason=no-provider source=capability-table",
    "kernel.cap.call.pm handle=DEAD0000 cap=food.createOrder task=1001 status=denied reason=invalid-handle source=capability-table",
    "graph capability.denied cap=food.createOrder reason=invalid-handle source=pm.capability",
    "kernel.trusted.enforce.pm surface=4001 type=generated action=payment.confirmAndPay status=denied reason=requires-trusted-surface trusted_surface=6001 source=surface-authority",
    "graph trusted.denied capability=payment.confirmAndPay surface=generated reason=requires-trusted-surface source=pm.authority",
    "kernel.copyin.pm syscall=sys_cap_call task=1001 user_ptr=FFFFF000 len=64 status=denied reason=user-range-invalid source=copyin-validator",
    "kernel.copyout.pm syscall=sys_cap_call task=1001 user_ptr=00100000 len=64 status=denied reason=kernel-range target=kernel.heap source=copyout-validator",
    "graph syscall.denied name=sys_cap_call reason=bad-user-pointer direction=copyin source=pm.syscall",
    "graph syscall.denied name=sys_cap_call reason=kernel-range direction=copyout source=pm.syscall",
    "kernel.security.negative.pm cap_invalid=blocked generated_trusted=blocked copyin_badptr=blocked copyout_kernel=blocked record=0010046C status=ok",
    "kernel.pci.scan.pm method=config-mechanism-1 bus=0 device=3 function=0 vendor=1AF4 device_id=1000 class=020000 command=0007 status=matched source=ioports-cf8-cfc",
    "kernel.virtio.net.config.pm status=ACKNOWLEDGE|DRIVER|FEATURES_OK|DRIVER_OK queue=0 io_base=bar0 source=pci-config status_reg=0000000F pci_command=0007",
    "kernel.virtio.net.queue.pm rxq=0 txq=1 ring=programmed qsize=256 rx_pfn=00105 tx_pfn=00109 pfn_record=00100338 notify=prepared status=ready",
    "kernel.virtio.net.dma.pm rx_ring=00105000 tx_ring=00109000 qsize=256 avail=1 used_sample=0010B000 mode=legacy-split status=programmed source=ioports",
    "kernel.virtio.net.vring.pm rx.desc0=0010D000:len1600:write tx.desc0=0010E000:len64:read tx.desc1=0010F000:len64:read rx.avail=00106000 tx.avail=0010A000 tx.used=0010B000 frame=0010E000 status=initialized source=kernel-memory",
    "kernel.net.ether.pm handle=0F00D001 tx_frame=0010E000 len=64 ethertype=0806 kind=arp-request status=queued source=sys_net_send",
    "kernel.net.udp.pm handle=0F00D001 tx_frame=0010F000 src=10.0.2.15:40000 dst=10.0.2.3:53 query=example.com status=sent source=sys_net_send",
    "kernel.net.dns.reply.pm handle=0F00D001 rx_buffer=00110000 used_ring=00107000 src=10.0.2.3:53 dst=10.0.2.15:40000 query=example.com status=received source=virtio-rx",
    "kernel.virtio.net.notify.pm queue=rx,tx indexes=0,1 notify_port=io_base+10 count=3 tx_used_sample=read isr_sample=read status=attempted source=legacy-io",
    "kernel.net.arp.reply.pm handle=0F00D001 rx_buffer=0010D000 used_ring=00107000 op=0002 sender=10.0.2.2 target=10.0.2.15 status=received source=virtio-rx",
    "graph net.device.discovered vendor=1AF4 device=1000 source=pm.pci",
    "graph net.opened handle=0F00D001 owner=provider.food source=pm.capability",
    "graph net.queue.ready driver=virtio-net source=pm.virtqueue",
    "graph net.send handle=0F00D001 bytes=64 ethertype=0806 source=sys_net_send",
    "graph net.send handle=0F00D001 bytes=64 ethertype=0800 proto=udp source=sys_net_send",
    "graph net.udp.send dst=10.0.2.3:53 query=example.com source=sys_net_send",
    "graph net.recv.poll handle=0F00D001 budget=1 source=sys_net_recv",
    "graph net.recv handle=0F00D001 bytes=64 ethertype=0806 source=virtio-rx",
    "graph net.arp.reply sender=10.0.2.2 target=10.0.2.15 source=virtio-rx",
    "graph net.recv handle=0F00D001 bytes=425 ethertype=0800 proto=udp source=virtio-rx",
    "graph net.dns.reply src=10.0.2.3:53 query=example.com source=virtio-rx",
    "graph net.rx.notify queue=0 source=pm.virtio-io",
    "graph net.tx.notify queue=1 source=pm.virtio-io",
    "graph net.isr.sampled source=pm.virtio-io",
    "kernel.net.device.pm bus=pci vendor=1AF4 device=1000 driver=virtio-net status=discovered mode=pci-config-read+legacy-io qemu=virtio-net-pci",
    "kernel.net.open.pm owner=provider.food task=8001 handle=0F00D001 policy=provider-network scope=food-api status=granted qemu_netdev=fluidnet",
    "kernel.scheduler.runqueue.pm count=3 rq0=fluid-init:8000 rq1=provider:8001 rq2=trusted:8002 policy=round-robin",
    "kernel.scheduler.context.pm slots=3 ctx0=fluid-init:eip00102000:esp0008f000 ctx1=provider:eip00102100:esp0008e000 ctx2=trusted:eip00102200:esp0008d000 state=ready",
    "kernel.scheduler.pick.pm cursor=0 task=fluid-init id=8000 reason=boot",
    "kernel.timer.pit.pm hz=100 irq=0 vector=20 status=enabled source=hardware-timer",
    "kernel.scheduler.tick.pm irq=0 vector=20 ticks>=2 current=fluid-init next=provider source=pit",
    "kernel.task.dispatch.pm from=kernel to=fluid-init id=8000 entry=00102000 state=started",
    "kernel.vm.guard_probe.pm task=8001 target=00400000 expected=page-fault source=cpl3-probe status=armed",
    "kernel.page_fault.pm vector=0E task=8001 addr=00400000 error=user-write-nonpresent action=blocked_resume status=handled",
    "graph vm.guard_fault task=8001 addr=00400000 policy=user-no-kernel-write source=page-fault",
    "kernel.vm.guard_probe.pm task=8001 target=00400000 result=fault-handled continued=1 status=ok",
    "graph stagec.ring_ready source=protected-mode walker=type-subject-dispatch records=task,capability,trusted",
    "kernel.input.pointer.pm driver=ps2 status=enabled mode=polling source=protected-mode",
    "kernel.object_transition.pm pointer{packets=1,buttons=0} source=ps2",
    "graph input.pointer event=packet source=pm.ps2",
    "kernel.alloc.dynamic.pm object=order addr=00100140 bytes=32 next=00100160",
    "kernel.object_transition.pm input{last=1} order{id=5001,state=created,cap=food.createOrder} trusted{id=6001,state=awaiting,cap=payment.confirm} ring_head=6",
    "kernel.graph_ring.pm slot3{c=4,t=input.key,s=1,state=pressed} slot4{c=5,t=capability.called,s=5001,state=ok} slot5{c=6,t=trusted_surface.created,s=6001,state=awaiting}",
    "kernel.graph_flush.pm source=ring walker=type-subject-dispatch from=3 to=5",
    "graph input.key value=1 source=pm.ring.subject",
    "kernel.cap.call.pm handle=C001F00D cap=food.createOrder task=1001 req=9001 route=provider.queue authority=sess.runtime status=accepted",
    "kernel.ipc.enqueue.pm queue=provider req=9001 slot=0 tail=1 handle=C001F00D cap=food.createOrder payload=choice.spice_lab source=capability-handle",
    "kernel.initramfs.lookup.pm name=provider.food task=8001 entry=00102100 stack=0008e000 status=found source=manifest-flatbin reason=capability-call req=9001",
    "kernel.scheduler.pick.pm cursor=1 task=provider id=8001 reason=capability-call req=9001 via=context-switch",
    "kernel.scheduler.context_switch.pm from=fluid-runtime:8000 to=provider:8001 via=iretd target_cpl=3 count=2 reason=capability-call req=9001",
    "kernel.vm.switch.pm task=8001 cr3=00202000 from=runtime reason=capability-call status=loaded",
    "kernel.task.dispatch.pm from=kernel to=provider.task id=8001 req=9001 isolation=task-boundary address_space=00202000",
    "kernel.user.enter.pm payload=provider cpl=3 entry=00102100 source=initpkg-flatbin req=9001 via=context-switch",
    "kernel.user.work.pm payload=provider cpl=3 req=9001",
    "kernel.syscall.pm from=provider vector=80 continued req=9001",
    "kernel.net.provider.pm handle=0F00D001 owner=provider.food tx=1 rx_poll=1 protocol=sys_net_dns endpoint=food-api.local query=example.com dns_reply=1 answer=93.184.216.34 status=resolved writer=cpl3.provider",
    "kernel.provider.dns.parse.pm task=8001 rx_buffer=00110000 frame_len=435 qtype=A qname=example.com answer=93.184.216.34 status=parsed writer=cpl3.provider",
    "kernel.provider.result.object.pm addr=0010047C magic=F17D4401 cap=food.createOrder order=5001 source=dns-parser answer=93.184.216.34 status=ready owner=provider.food",
    "graph net.provider.txrx handle=0F00D001 tx=1 rx_poll=1 owner=provider.food protocol=dns source=cpl3.provider.sys_net",
    "graph provider.dns.parsed qname=example.com answer=93.184.216.34 source=cpl3.provider.parser",
    "graph provider.result food.createOrder source=provider-result-object query=example.com answer=93.184.216.34 order=5001 writer=cpl3.provider",
    "qemu.net.target user,id=fluidnet device=virtio-net-pci status=enabled",
    "kernel.ipc.dequeue.pm queue=provider req=9001 slot=0 head=1 status=ok order=5001 writer=cpl3.provider verifier=kernel",
    "kernel.ipc.reply.pm queue=provider req=9001 slot=0 status=ok order=5001 handler=provider.task.8001 writer=cpl3.provider",
    "graph capability.called food.createOrder provider=provider.food.network source=pm.ring.subject result=provider-result-object order=5001",
    "graph interface.updated id=1F4002 task=1001 provider_result=provider-result-object order=5001 source=agent-projection",
    "kernel.interface.projection.pm id=1F4002 task=1001 phase=trusted nodes=2 action=C002FA17 trust=trusted-surface provider_result=provider-result-object order=5001 source=agent-generated-ir",
    "kernel.surface.pm renderer=packed-framebuffer mode=320x200x8 phase=trusted visual=trusted-modal colors=red-white source=projection-ir projection=1F4002",
    "kernel.alloc.dynamic.pm object=receipt addr=00100160 bytes=32 next=00100180",
    "kernel.object_transition.pm input{last=y} trusted{id=6001,state=confirmed} receipt{id=7001,state=created,order=5001} task{id=1001,state=completed} ring_head=10",
    "kernel.graph_ring.pm slot6{c=7,t=input.key,s=2,state=pressed} slot7{c=8,t=trusted.confirmed,s=6001,state=confirmed} slot8{c=9,t=receipt.created,s=7001,state=created} slot9{c=10,t=task.completed,s=1001,state=completed}",
    "kernel.graph_flush.pm source=ring walker=type-subject-dispatch from=6 to=9",
    "graph input.key value=y source=pm.ring.subject",
    "kernel.cap.call.pm handle=C002FA17 cap=payment.confirmAndPay task=1001 req=9002 route=trusted.queue authority=sess.trusted-ui status=accepted trusted_surface=6001",
    "kernel.ipc.enqueue.pm queue=trusted req=9002 slot=0 tail=1 handle=C002FA17 cap=payment.confirmAndPay payload=order.5001 source=capability-handle trusted-surface=6001",
    "kernel.initramfs.lookup.pm name=trusted.pay task=8002 entry=00102200 stack=0008d000 status=found source=manifest-flatbin reason=trusted-gate req=9002",
    "kernel.scheduler.pick.pm cursor=2 task=trusted id=8002 reason=trusted-gate req=9002 via=context-switch",
    "kernel.scheduler.context_switch.pm from=fluid-runtime:8000 to=trusted:8002 via=iretd target_cpl=3 count=3 reason=trusted-gate req=9002",
    "kernel.vm.switch.pm task=8002 cr3=00203000 from=runtime reason=trusted-gate status=loaded",
    "kernel.task.dispatch.pm from=kernel to=trusted.task id=8002 req=9002 isolation=trusted-task-boundary address_space=00203000",
    "kernel.user.enter.pm payload=trusted cpl=3 entry=00102200 source=initpkg-flatbin req=9002 via=context-switch",
    "kernel.user.work.pm payload=trusted cpl=3 req=9002",
    "kernel.syscall.pm from=trusted vector=80 continued req=9002",
    "kernel.ipc.dequeue.pm queue=trusted req=9002 slot=0 head=1 status=confirmed receipt=7001 writer=cpl3.trusted verifier=kernel",
    "kernel.ipc.reply.pm queue=trusted req=9002 slot=0 status=confirmed receipt=7001 handler=trusted.task.8002 writer=cpl3.trusted",
    "graph trusted.confirmed session=sess.trusted-ui capability=payment.confirmAndPay source=pm.ring.subject",
    "graph receipt.created order=order.demo.0001 source=pm.ring.subject",
    "graph task.completed id=task.stagec.demo source=pm.ring.subject",
    "kernel.interface.projection.pm id=1F4003 task=1001 phase=receipt nodes=2 receipt=7001 source=agent-generated-ir",
    "kernel.debug.overlay.pm surface=debug-graph nodes=5 edges=4 events=task,capability,provider,trusted,receipt renderer=packed-framebuffer y=0 status=visible",
    "kernel.surface.pm renderer=packed-framebuffer mode=320x200x8 phase=receipt visual=success-receipt colors=green source=projection-ir projection=1F4003 debug_overlay=visible",
    "graph kernel.halt reason=escape source=protected-mode",
    "kernel.user.enter.pm payload=fluid-init entry=00102000 source=initpkg-flatbin cs=001b ds=0023 via=iretd target_cpl=3",
    "kernel.vm.switch.pm task=8000 cr3=00201000 from=kernel reason=fluid-init-yield status=loaded",
    "kernel.user.work.pm payload=fluid-init wrote=framebuffer marker=0d0d0d0d cpl=3",
    "kernel.syscall.pm from=fluid-init vector=80 status=returned-to-kernel evidence=serial",
    "kernel.scheduler.yield.pm from=fluid-init id=8000 next=provider id=8001 ctx0.yields=1 source=syscall80",
    "kernel.scheduler.context_switch.pm from=fluid-init:8000 to=provider:8001 via=iretd target_cpl=3 count=1 reason=yield",
    "kernel.user.work.pm payload=provider-switch cpl=3 ctx=provider marker=0c0c0c0c",
    "kernel.syscall.pm from=provider-switch vector=80 status=returned-to-kernel ctx=provider",
]
missing = [item for item in required if item not in text]
print(f"stage2.layout bytes={stage2_used}/{stage2_len} free={stage2_free}")
if screen.exists():
    print(f"screendump={screen} bytes={screen.stat().st_size}")
    receipt_pixel = read_ppm_pixel(screen, 160, 155)
    print(f"screendump.receipt_framebuffer_pixel rgb={receipt_pixel[0]},{receipt_pixel[1]},{receipt_pixel[2]}")
    if receipt_pixel[1] <= receipt_pixel[0] or receipt_pixel[1] <= receipt_pixel[2]:
        missing.append("receipt surface green packed-framebuffer pixel")
    overlay_pixel = read_ppm_pixel(screen, 10, 6)
    print(f"screendump.debug_overlay_pixel rgb={overlay_pixel[0]},{overlay_pixel[1]},{overlay_pixel[2]}")
    if max(overlay_pixel) < 80:
        missing.append("visible debug graph overlay pixel")
else:
    print("screendump=missing")
if missing:
    print("missing stage-c protected-mode evidence: " + ", ".join(missing), file=sys.stderr)
    raise SystemExit(1)
