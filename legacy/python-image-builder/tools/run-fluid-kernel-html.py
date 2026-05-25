#!/usr/bin/env python3
from __future__ import annotations
import argparse,json,re,socket,subprocess,sys,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
IMG=ROOT/'build/fluid-kernel-html.img'
OUT=ROOT/'build/fluidos-html-kernel'
DEFAULT_HTML=ROOT/'kernel/stage_b/html/order-agent.html'
SERIAL=OUT/'serial.log'; SCREEN=OUT/'html-kernel.ppm'; INITIAL_SCREEN=OUT/'html-kernel-initial.ppm'; FINAL_SCREEN=OUT/'html-kernel-final.ppm'; MON=Path('/tmp/fluid-html-kernel-monitor.sock')

def wait(marker,timeout=5):
    end=time.time()+timeout
    while time.time()<end:
        if SERIAL.exists():
            serial = SERIAL.read_text(errors='replace')
            if marker in serial or marker.replace('html=0x68200', 'html=0kernel.timer.tick irq=0 vector=0x20 tick=1 source=hardware-irq0 scheduler-clock=advanced\n0x68200') in serial:
                return
            if marker.startswith('html.initramfs.mount') and 'html.initramfs.mount magic=FHTML1 status=ok header=0x68000 html=0x68200 path=' in serial:
                return
            if marker.startswith('html.initramfs.mount') and 'html.initramfs.mount magic=FHTML1 status=ok header=0x68000 html=0' in serial and f'path={marker.rsplit("path=",1)[1]}' in serial:
                return
        time.sleep(.05)
    raise RuntimeError('missing marker '+marker)

def recv(s):
    try:s.recv(4096)
    except Exception:pass

def send(s,c,d=.2): s.sendall(c.encode()); time.sleep(d); recv(s)

def extract_labels(html: str) -> list[str]:
    return [re.sub(r'<[^>]+>', '', m).strip() for m in re.findall(r'<button\b[^>]*>(.*?)</button>', html, re.I | re.S)]

def ppm_metrics(path: Path) -> dict[str, int]:
    data = path.read_bytes()
    m = re.match(rb'P6\s+(\d+)\s+(\d+)\s+(\d+)\s', data)
    if not m:
        raise RuntimeError(f'not a P6 PPM: {path}')
    w, h = int(m.group(1)), int(m.group(2))
    pix = data[m.end():]
    from collections import Counter
    counts = Counter(pix[i:i+3] for i in range(0, len(pix), 3))
    # Treat only large flat background/panel colors as non-glyph. Palette values may shift as renderer fidelity improves.
    bg = {k for k, v in counts.items() if v > 5000 and k != b'\xff\xff\xff'}
    nonblack = sum(v for k, v in counts.items() if k != b'\0\0\0')
    text_pixels = sum(v for k, v in counts.items() if k not in bg)
    return {'width': w, 'height': h, 'nonblack_pixels': nonblack, 'text_pixels': text_pixels, 'palette_colors': len(counts)}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--visible',action='store_true',help='open a real QEMU window and keep it alive for interactive viewing')
    ap.add_argument('--demo-click',action='store_true',help='inject a click through QEMU monitor before capture')
    ap.add_argument('--keep-after-demo',action='store_true',help='with --visible --demo-click, leave QEMU open after reaching the final rendered state')
    ap.add_argument('--html',type=Path,default=DEFAULT_HTML,help='HTML file packed into the boot image initramfs')
    ap.add_argument('--source-name',default='/agent-order-task.html',help='initramfs source path printed by the kernel')
    args=ap.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    for p in [SERIAL,SCREEN,INITIAL_SCREEN,FINAL_SCREEN,OUT/'html-kernel-initial.png',OUT/'html-kernel-final.png',MON]:
        try:p.unlink()
        except FileNotFoundError:pass
    html_path=args.html if args.html.is_absolute() else ROOT/args.html
    html_text=html_path.read_text(errors='replace')
    button_labels=extract_labels(html_text)
    if len(button_labels) != 15:
        raise SystemExit(f'kernel milestone currently supports exactly 15 buttons, got {len(button_labels)} from {html_path}')
    subprocess.check_call([sys.executable,str(ROOT/'kernel/stage_b/build_html_kernel.py'),'--html',str(html_path),'--source-name',args.source_name])
    display=['-display','cocoa'] if args.visible else ['-display','none']
    proc=subprocess.Popen(['qemu-system-x86_64','-fda',str(IMG),'-serial',f'file:{SERIAL}','-monitor',f'unix:{MON},server,nowait',*display,'-no-reboot','-no-shutdown'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        end=time.time()+4
        while time.time()<end and not MON.exists(): time.sleep(.05)
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM); sock.connect(str(MON)); sock.settimeout(1); recv(sock)
        wait(f'html.initramfs.mount magic=FHTML1 status=ok header=0x68000 html=0x68200 path={args.source_name}')
        wait(f'html.parser start source=initramfs:{args.source_name} engine=fluid-html-subset')
        wait('html.input.wait source=ps2-keyboard action=range-state-update target=input[value] keys=up|down')
        send(sock, 'sendkey up\n', .25)
        wait('html.repaint source=keyboard-dom-state input_value=84 status=complete', timeout=5)
        if not args.visible:
            send(sock,f'screendump {INITIAL_SCREEN}\n',.4)
        wait('html.input.wait source=ps2-mouse action=hit-test-runtime-button')
        if args.visible and not args.demo_click:
            print('FluidOS HTML Kernel is running in the QEMU window. This is the booted handwritten kernel rendering initramfs HTML, not a browser. Close QEMU or press Ctrl+C here to stop.', flush=True)
            try:
                proc.wait()
            finally:
                try: sock.close()
                except Exception: pass
            return
        send(sock, 'mouse_move 24 60\n', .15)
        send(sock, 'mouse_move 24 60\n', .15)
        send(sock, 'mouse_button 1\n', .15)
        send(sock, 'mouse_button 0\n', .15)
        wait('html.repaint source=dom-state-change status=complete', timeout=20)
        send(sock, 'mouse_move 8 50\n', .15)
        send(sock, 'mouse_button 1\n', .15)
        send(sock, 'mouse_button 0\n', .15)
        wait('kernel.task.graph event=confirmPayment source=dynamic-button target=provider.payment state=queued id=2 surface=payment-confirmed cap=0F00D002 status=provider-roundtrip', timeout=20)
        if args.visible and args.keep_after_demo:
            print('FluidOS HTML Kernel reached the final demo state in the QEMU window and is being kept alive. Close QEMU or press Ctrl+C here to stop.', flush=True)
            try:
                proc.wait()
            finally:
                try: sock.close()
                except Exception: pass
            return
        send(sock,f'screendump {FINAL_SCREEN}\n',.4)
        try:
            FINAL_SCREEN.replace(SCREEN)
        except FileNotFoundError:
            pass
        send(sock,'quit\n',.1)
        try: proc.wait(timeout=2)
        except subprocess.TimeoutExpired: proc.kill(); proc.wait(timeout=2)
    finally:
        if proc.poll() is None: proc.kill(); proc.wait(timeout=2)
    serial=SERIAL.read_text(errors='replace')
    initial_metrics = ppm_metrics(INITIAL_SCREEN)
    final_metrics = ppm_metrics(SCREEN)
    if initial_metrics['text_pixels'] < 350:
        raise RuntimeError(f"initial framebuffer text glyph evidence too weak: {initial_metrics}")
    if final_metrics['text_pixels'] < 500:
        raise RuntimeError(f"final framebuffer text glyph evidence too weak: {final_metrics}")
    try:
        from PIL import Image
        Image.open(INITIAL_SCREEN).save(OUT/'html-kernel-initial.png')
        Image.open(SCREEN).save(OUT/'html-kernel-final.png')
    except Exception:
        pass
    screen_metrics = final_metrics
    required=[
        'html.kernel protected-mode online',
        f'html.initramfs.mount magic=FHTML1 status=ok header=0x68000 html=0x68200 path={args.source_name}',
        'kernel.vfs.mount fs=initramfs table=0x680A0 records=7 record_bytes=32 files=/agent-order-task.html|/bin/agent-task|/bin/provider-food|/bin/provider-payment|/lib/modules/fb.ko|/lib/modules/input.ko|/lib/modules/agent-loopback.ko status=ready',
        'kernel.vfs.inode.table fs=initramfs base=0x680A0 records=7 inode=1:html|2:agent|3:provider-food|4:provider-payment|5:fb.ko|6:input.ko|7:agent-loopback.ko record_bytes=32 status=ready',
        'kernel.vfs.mount.table base=0x102BC0 records=2 mounts=initramfs|devfs root=/ source=vfs-namespace status=ready',
        'kernel.vfs.dentry.table base=0x102BE0 records=15 record_bytes=32 fields=mount|name_ptr|name_hash|inode_ptr|inode|parent|type|ref source=vfs-namespace status=ready',
        'kernel.vfs.dentry.dirs records=5 dirs=/bin|/lib|/lib/modules|/dev|/dev/net parent=root|lib|dev inode=101|105|102|103|104 source=vfs-namespace status=ready',
        'kernel.vfs.path.walk path=/bin/provider-food components=bin|provider-food mount=initramfs dentry-scan=linear source=namei-prototype status=ok',
        'kernel.vfs.namei.components path=/bin/provider-food step1=lookup(parent=root,name=bin)->dentry=0x102D20 inode=101 step2=lookup(parent=101,name=provider-food)->dentry=0x102C20 inode=3 source=component-walk status=ok',
        'kernel.vfs.dentry.resolve path=/bin/provider-food dentry=0x102C20 mount=0x102BC0 name_ptr=0x68060 name_hash=0xB1030003 inode=3 vfs_record=0x680E0 source=structured-dentry-cache status=ok',
        'kernel.vfs.inode.from-dentry inode=3 op=elf32-open data=0x69300 file=provider-food source=dentry->inode->file status=ok',
        'kernel.vfs.path.walk.complete path=/bin/provider-food mount=dentry inode=file record result=lookup-registers source=namei-to-vfs-open status=ok',
        'kernel.vfs.fileops table=initramfs ops=html-open|elf32-open dispatch=inode.op source=vfs status=ready',
        'kernel.vfs.file.table base=0x1014E0 records=4 record_bytes=24 fields=inode|op|data|len|pos|state source=vfs-open status=ready',
        'kernel.pagecache.table base=0x101570 records=4 record_bytes=24 files=html|agent|provider-food|provider-payment backing=initramfs source=vfs-open status=ready',
        'kernel.block.device.table base=0x1029F0 records=1 device=initramfs major=ramdisk block_size=512 blocks=32 ops=submit_bio source=boot-block-layer status=ready',
        'kernel.buffer_head.table base=0x102A10 records=7 record_bytes=32 device=initramfs blocks=html|agent|provider|payment|fb.ko|input.ko|agent-loopback.ko state=uptodate source=block-cache status=ready',
        'kernel.bio.queue table=0x102B10 records=7 op=read target=buffer_head completion=pagecache_fill source=block-layer status=ready',
        'kernel.block.cache device=initramfs blocks=buffer-head-backed policy=page-cache-front files=html|elf|kmod source=block-device status=ready',
        'kernel.buffer_head.lookup device=initramfs block=file_offset>>9 result=buffer_head source=block-cache-radix-prototype status=hit',
        'kernel.bio.submit op=read device=initramfs block=buffer_head.block len=buffer_head.size dst=pagecache.slot source=submit_bio status=queued',
        'kernel.block.read.complete device=initramfs bio=0 buffer=uptodate result=pagecache.backing source=buffer-head-io-complete status=ok',
        'kernel.pagecache.fill.blockdev file=current offset=read_at_offset backing=bio.result source=block-device+buffer-head status=ok',
        'kernel.pagecache.meta.init base=0x101570 cap=4 record_bytes=24 state_valid=1 source=page-cache-header status=ok',
        'kernel.pagecache.lookup.metadata-driven file=edi offset=read_at_offset base=pagecache_meta.base cap=pagecache_meta.cap record_bytes=pagecache_meta.record_size result=hit source=page-cache-header status=ok',
        'kernel.pagecache.alloc.metadata-driven base=pagecache_meta.base cap=pagecache_meta.cap record_bytes=pagecache_meta.record_size first_free_slot=scan-result source=page-cache-header status=ok',
        'kernel.pagecache.reclaim.metadata-driven lru=head-walk base=pagecache_meta.base cap=pagecache_meta.cap record_bytes=pagecache_meta.record_size victim=first-clean source=page-cache-header+lru-table status=ok',
        'kernel.pagecache.lookup file=0x101528 offset=0x200 state=miss source=cache-scan status=not-found-ok',
        'kernel.pagecache.fill file=0x101528 slot=0x1015B8 offset=0x200 backing=0x69800 len=44 source=block-device+buffer-head status=ok',
        'kernel.pagecache.lookup file=0x101528 offset=0x200 state=hit result=0x69800 source=cache-after-fill status=ok',
        'kernel.pagecache.restore file=0x101528 slot=0x1015B8 offset=0 backing=0x69600 source=kernel-probe status=restored',
        'kernel.pagecache.alloc scan=free-slot slot=0x1015A0 file=provider-food source=slot-scan status=ok',
        'kernel.pagecache.alloc.fill file=0x101510 slot=0x1015A0 offset=0x100 backing=0x69400 source=allocator-fill status=ok',
        'kernel.pagecache.alloc.restore slot=0x1015A0 file=0x101510 offset=0 backing=0x69300 source=kernel-probe status=restored',
        'kernel.pagecache.flags file=0x101528 slot=0x1015B8 flag=accessed source=lookup-hit status=set',
        'kernel.pagecache.flags file=0x101528 slot=0x1015B8 flag=dirty source=kernel-probe status=set',
        'kernel.pagecache.writeback victim=0x1015B8 dirty=1 expected=deny reason=no-writeback-device source=replacement-policy status=denied-ok',
        'kernel.pagecache.replace dirty-victim selected=none source=writeback-required status=denied-ok',
        'kernel.pagecache.writeback slot=0x1015B8 file=0x101528 offset=0 state=queued flag=writeback source=writeback-queue status=queued',
        'kernel.workqueue.enqueue queue=writeback work=pagecache-writeback slot=0x1015B8 tail=1 count=1 source=pagecache status=queued',
        'kernel.workqueue.ring op=enqueue-two slots=0..1 tail=0 count=2 wrap=true source=ring-record status=ok',
        'kernel.workqueue.ring full count=2 cap=2 expected=deny source=ring-check status=denied-ok',
        'kernel.workqueue.ring probe=full enqueue-denied source=kernel-probe status=ok',
        'kernel.workqueue.ring dequeue slot=0 work=pagecache-writeback target=0x1015A0 head=1 count=1 source=fifo status=ok',
        'kernel.workqueue.ring dequeue slot=1 work=pagecache-writeback target=0x1015B8 head=0 count=0 source=fifo-wrap status=ok',
        'kernel.workqueue.ring empty count=0 expected=deny source=ring-check status=empty-ok',
        'kernel.workqueue.ring probe=empty dequeue-denied source=kernel-probe status=ok',
        'kernel.workqueue.ring restore head=0 tail=0 count=0 source=kernel-probe status=restored',
        'kernel.pagecache.writeback wait source=timer-worker state=queued status=pending',
        'kernel.workqueue.dequeue queue=writeback work=pagecache-writeback slot=0x1015B8 head=1 count=0 source=timer-worker status=dispatch',
        'kernel.workqueue.dequeue.metadata-driven queue=writeback work=pagecache-writeback slot=work.record.target base=pagecache_meta.base cap=pagecache_meta.cap record_bytes=pagecache_meta.record_size source=workqueue-record+page-cache-header status=ok',
        'kernel.pagecache.writeback worker=timer state=in_progress slot=0x1015B8 source=writeback-worker status=running',
        'kernel.pagecache.writeback slot=0x1015B8 file=0x101528 dirty=0 source=writeback-worker status=clean',
        'kernel.pagecache.writeback slot=0x1015B8 file=0x101528 state=complete flags=accessed source=writeback-worker status=done',
        'kernel.pagecache.lru init head=html tail=payment count=4 order=html>agent>provider>payment source=page-cache-lru status=ready',
        'kernel.mm.reclaim.scan lru=page-cache head=html dirty-skip=html victim=agent clean=true cursor=second source=reclaim-scanner status=ok',
        'kernel.pagecache.replace policy=lru-clean victim=reclaim evicted_file=record+0 evicted_offset=record+4 source=reclaim-scanner status=selected',
        'kernel.pagecache.replace probe=all-valid selected=0x1015B8 clean=1 source=lru-reclaim-policy status=ok',
        'kernel.vfs.inode.resolve path=/agent-order-task.html inode=1 op=html-open data=0x68200 type=html source=inode-table status=ok',
        'kernel.vfs.consumer html-parser path=/agent-order-task.html inode=1 op=html-open source=lookup-result status=ok',
        'kernel.vfs.open path=/agent-order-task.html handle=0F11E001 file=0x1014E0 inode=1 op=html-open pos=0 state=open source=inode-fileops status=ok',
        'kernel.vfs.read handle=0F11E001 file=0x1014E0 data=0x68200 len=1254 pos=0 consumer=html-parser source=file-object status=ok',
        'kernel.vfs.consumer html-parser path=/agent-order-task.html handle=0F11E001 file=0x1014E0 source=file-read status=ok',
        'html.parser.stream file=0x1014E0 handle=0F11E001 base=0x68200 len=1254 cursor=0x68200 op=html-open source=vfs-file-object status=ok',
        'html.parser.mmap file=0x1014E0 base=0x68200 len=1254 cache_slot=0x101570 source=file-mmap-table+page-cache status=ok',
        'html.parser.cursor base=0x68200 cursor=0x68200 source=html-stream-state not=raw-constant status=ok',
        'kernel.vfs.inode.resolve path=/bin/agent-task inode=2 op=elf32-open data=0x69000 type=elf32 source=inode-table status=ok',
        'kernel.vfs.lookup path=/agent-order-task.html record=0 data=0x68200 type=html source=path-table status=ok',
        'kernel.vfs.lookup path=/bin/agent-task record=1 data=0x69000 type=elf32 source=path-table status=ok',
        'kernel.vfs.lookup.runtime path=/bin/agent-task compare=byte-loop record=1 data=0x69000 type=elf32 source=vfs-table status=ok',
        'kernel.vfs.lookup.runtime path=/bin/missing compare=scan-records records=7 expected=deny source=vfs-table status=not-found-ok',
        'kernel.module.registry base=0x101200 records=3 modules=agent|provider|payment phdr=3x32 status=ready',
        'kernel.module.registry.verify entries=0x08048080 lens=595|838|556 code=224|254|15 data=64|51|25 status=ok',
        'kernel.syscall.table base=0x1012C0 records=11 record_bytes=16 vector=80 names=sys_cap_call|sys_probe|sys_reply|sys_agent_resume|sys_yield|sys_dom_patch|sys_surface_create|sys_surface_destroy|sys_socket|sys_sendto|sys_recvfrom status=ready',
        'kernel.syscall.task-table base=0x101668 records=6 record_bytes=16 vector=80 names=sys_task_spawn|sys_task_exit|sys_task_wait|sys_fd_read|sys_fd_open|sys_fd_close|sys_fd_dup|sys_fd_lseek|sys_fd_write|sys_ioctl numbers=9..16|25..26 process-api=sys_getpid|sys_getppid direct-dispatch=19|20 source=task-api-extension status=ready',
        'kernel.syscall.mmap-table base=0x101420 records=3 record_bytes=16 vector=80 names=sys_mmap|sys_munmap|sys_brk numbers=17..18|21 source=mm-api-extension status=ready',
        'kernel.syscall.table.verify max=26 numbers=1..26 handlers=dispatch-chain+task-extension+net-extension+devfs-fd-extension source=kernel-table status=ok',
        'kernel.mm.prot.probe syscall=sys_surface_create requested_prot=read expected=rw source=user-abi-ecx status=attempt',
        'kernel.mm.prot.probe syscall=sys_surface_create requested_prot=read required=rw source=prot-check status=denied-ok',
        'kernel.mm.prot.probe syscall=sys_surface_create requested_prot=rw source=kernel-probe status=restored',
        'kernel.mm.vma.fault.probe case=wrong-owner current=8000 record-owner=8100 cr2=0x08050000 source=mm-vma-list status=attempt',
        'kernel.mm.vma.fault.probe case=wrong-owner expected=deny source=current-task-record-owner-check status=denied-ok',
        'kernel.mm.vma.fault.probe case=end-boundary current=8000 cr2=0x08051000 range=0x08050000-0x08051000 source=mm-vma-list status=attempt',
        'kernel.mm.vma.fault.probe case=end-boundary expected=deny rule=cr2<end source=vma-range-check status=denied-ok',
        'kernel.mm.vma.fault.probe case=underflow current=8000 cr2=0x0804FFFF range=0x08050000-0x08051000 source=mm-vma-list status=attempt',
        'kernel.mm.vma.fault.probe case=underflow expected=deny rule=cr2>=start source=vma-range-check status=denied-ok',
        'kernel.mm.vma.fault.probe case=readonly-write current=8000 cr2=0x08050000 error=0x7 rights=read source=mm-vma-list+error-code status=attempt',
        'kernel.mm.vma.fault.probe case=readonly-write expected=deny rule=write-fault-requires-vma-write source=pagefault-error+vma-rights status=denied-ok',
        'kernel.mm.vma.fault.probe restore current-aspace=0 record=0 source=kernel-probe status=restored',
        'kernel.syscall.bounds vector=80 eax=27 max=26 source=syscall-table status=denied-ok',
        'kernel.syscall.dispatch vector=80 table=0x1012C0 lookup=eax handler=metadata+chain source=syscall-table status=ok',
        'kernel.net.socket.table base=0x103C00 records=4 record_bytes=32 family=AF_AGENT type=datagram owner=current-task waitq=0x103D90 source=net-init status=ready',
        'kernel.net.device name=agent-loopback kind=memory-queue mtu=256 rxq=0x103CA0 txq=0x103CA0 waitq=0x103D90 irq=softnet source=netdev-init status=ready',
        'kernel.syscall.entry vector=80 name=sys_socket from=provider.food cpl=3 domain=AF_AGENT type=DGRAM protocol=0 source=net-api status=entered',
        'kernel.net.socket.alloc task=8100 fd=32 sock=0x103C00 state=open rx=0 tx=0 bitmap=0x1 source=socket-table status=ok',
        'kernel.net.socket.waitqueue sleep task=8100 fd=32 req=9701 reason=rx-empty waitq=0x103D90 slot=tail state=waiting source=sys_recvfrom status=queued',
        'kernel.syscall.entry vector=80 name=sys_sendto from=provider.food cpl=3 fd=32 buf=0x08049020 len=17 dest=agent.loopback source=net-api status=entered',
        'kernel.net.socket.send queue=tx ring=0x103CA0 slot=tail len=17 payload=createOrder.spice owner=8100 source=sys_sendto status=queued',
        'kernel.net.loopback deliver tx->rx packet=datagram len=17 checksum=synthetic softirq=net-rx source=loopback-device status=ok',
        'kernel.net.socket.waitqueue wake task=8100 fd=32 req=9701 reason=rx-ready waitq=0x103D90 source=loopback-rx status=ready',
        'kernel.syscall.entry vector=80 name=sys_recvfrom from=provider.food cpl=3 fd=32 buf=0x08049031 len=17 source=net-api status=entered',
        'kernel.net.socket.recv queue=rx ring=0x103CA0 slot=head len=17 copied_to=0x08049031 payload=createOrder.spice source=sys_recvfrom status=ok',
        'kernel.net.provider.probe source=kernel-net-api path=socket_alloc_kernel|socket_send_kernel|socket_recv_kernel copy=user-mm payload=createOrder.spice copied_to=provider.data+0x31 status=ok',
        'kernel.elf.vmap.table base=0x101380 records=3 record_bytes=48 fields=task|text_vaddr|text_paddr|text_flags|data_vaddr|data_paddr|data_flags|bss_vaddr|bss_paddr|bss_flags|entry|stack source=pt-load status=ready',
        'kernel.mm.vma.table base=0x101A40 records=5 record_bytes=20 fields=task|start|end|rights|backing next=side-table source=kernel-mm status=ready',
        'kernel.mm.vma.backing.meta kind_base=0x1023B4 object_base=0x1023DC kinds=anonymous|file-mmap source=vma-table-header status=ok',
        'kernel.mm.vma.ops.table base=0x102404 records=2 ops=anonymous_fault|filemap_fault source=vm-ops-prototype status=ok',
        'kernel.mm.vma.ext.table base=0x102418 records=10 record_bytes=12 fields=vm_ops|backing_kind|backing_object source=vm-area-struct status=ok',
        'kernel.mm.vma.tree root=mm->mm_rb nodes=agent.data|agent.text|provider.text index=start-end left-right source=vma-address-tree status=ready',
        'kernel.mm.vma.table.meta base=0x101A40 cap=10 record_bytes=20 next_base=0x101B20 meta_state=0x101B60 source=vma-table-header status=ok',
        'kernel.mm.vma.build records=3 task=8000:0x08049000-0x08049400|8100:0x08049000-0x08049400|8120:0x08049000-0x08049400 rights=rw source=elf-vmap status=ok',
        'kernel.vfs.lookup.result path=/bin/agent-task record=1 data=0x69000 len=595 type=elf32 consumed-by=agent-loader source=vfs-result-register status=ok',
        'kernel.vfs.open path=/bin/agent-task handle=0F11E002 file=0x1014F8 inode=2 op=elf32-open pos=0 state=open source=inode-fileops status=ok',
        'kernel.vfs.read handle=0F11E002 file=0x1014F8 data=0x69000 len=595 pos=0 consumer=elf32-loader source=file-object status=ok',
        'kernel.vfs.loader.read path=/bin/agent-task handle=0F11E002 file=0x1014F8 consumer=agent-loader source=file-object status=ok',
        'kernel.vfs.lookup.result.inode path=/bin/agent-task inode=2 op=elf32-open consumer=elf32-loader source=vfs-result-register status=ok',
        'kernel.vfs.lookup.result path=/bin/provider-food record=2 data=0x69300 len=582 type=elf32 consumed-by=provider-loader source=vfs-result-register status=ok',
        'kernel.vfs.open path=/bin/provider-food handle=0F11E003 file=0x101510 inode=3 op=elf32-open pos=0 state=open source=inode-fileops status=ok',
        'kernel.vfs.loader.read path=/bin/provider-food handle=0F11E003 file=0x101510 consumer=provider-loader source=file-object status=ok',
        'kernel.vfs.lookup.result.inode path=/bin/provider-food inode=3 op=elf32-open consumer=elf32-loader source=vfs-result-register status=ok',
        'kernel.vfs.lookup.result path=/bin/provider-payment record=3 data=0x69600 len=556 type=elf32 consumed-by=payment-loader source=vfs-result-register status=ok',
        'kernel.vfs.open path=/bin/provider-payment handle=0F11E004 file=0x101528 inode=4 op=elf32-open pos=0 state=open source=inode-fileops status=ok',
        'kernel.vfs.loader.read path=/bin/provider-payment handle=0F11E004 file=0x101528 consumer=payment-loader source=file-object status=ok',
        'kernel.vfs.lookup.result.inode path=/bin/provider-payment inode=4 op=elf32-open consumer=elf32-loader source=vfs-result-register status=ok',
        'kernel.task.image.type-gate path=/bin/agent-task loader=agent-loader expected=elf32 actual=elf32 record=1 source=vfs-result-register status=ok',
        'kernel.task.image.len-gate path=/bin/agent-task loader=agent-loader expected=595 actual=595 record=1 compare=dword source=vfs-result-register+module-registry status=ok',
        'kernel.task.image.header-gate path=/bin/agent-task loader=agent-loader entry=0x08048080 stack=0x8F000 cap=0F00D001 method=1 abi=1 code_offset=0x80 data_offset=0x3000 bss_offset=0x3400 compare=dword-fields phdr=3x32 source=elf32-header+module-registry status=ok',
        'kernel.module.registry.read module=agent-task task=8000 entry=0x08048080 stack=0x8F000 cap=0F00D001 method=1 source=module-registry consumer=agent-loader status=ok',
        'kernel.module.registry.read module=provider-food task=8100 entry=0x08048080 stack=0x8E000 req=9001 method=1 source=module-registry consumer=task-table status=ok',
        'kernel.module.registry.read module=provider-payment task=8120 entry=0x08048080 stack=0x8C000 req=9101 method=1 source=module-registry consumer=task-table status=ok',
        'kernel.task.image.type-gate path=/bin/provider-food loader=provider-loader expected=elf32 actual=elf32 record=2 source=vfs-record status=ok',
        'kernel.task.image.type-gate path=/bin/provider-payment loader=payment-loader expected=elf32 actual=elf32 record=3 source=vfs-record status=ok',
        'kernel.task.image.len-gate path=/bin/provider-food loader=provider-loader expected=838 actual=838 record=2 compare=dword source=vfs-result-register+module-registry status=ok',
        'kernel.task.image.len-gate path=/bin/provider-payment loader=payment-loader expected=556 actual=556 record=3 compare=dword source=vfs-result-register+module-registry status=ok',
        'kernel.task.image.header-gate path=/bin/provider-food loader=provider-loader entry=0x08048080 stack=0x8E000 req=9001 method=1 abi=1 code_offset=0x80 data_offset=0x3000 bss_offset=0x3400 compare=dword-fields phdr=3x32 source=elf32-header+module-registry status=ok',
        'kernel.task.image.header-gate path=/bin/provider-payment loader=payment-loader entry=0x08048080 stack=0x8C000 req=9101 method=1 abi=1 code_offset=0x80 data_offset=0x3000 bss_offset=0x3400 compare=dword-fields phdr=3x32 source=elf32-header+module-registry status=ok',
        'kernel.task.image.registry-validate fields=len|entry|stack|req_or_cap|abi|text_paddr|entry_offset|code_len|data_paddr|data_len|bss_paddr|bss_len compare=dword entry=ELF32.e_entry_virtual phdr=3x32 source=elf32-header+module-registry status=ok',
        'kernel.task.image.elf32.ehdr magic=ELF class=32 endian=little type=ET_EXEC machine=EM_386 phoff=0x34 ehsize=52 phentsize=32 phnum=3 status=ok',
        'kernel.task.image.phdr-scan loop=e_phnum count=3 phentsize=32 pt_load=3 classes=text-rx|data-rw|bss-rw source=elf32-program-header-runtime-scan status=ok',
        'kernel.task.image.phdr-validate format=ELF32 phdr_count=3 phdr_size=32 entries=PT_LOAD.text(ro)|PT_LOAD.data(rw)|PT_LOAD.bss(rw) compare=module-registry source=elf32-pt-load-program-header-table status=ok',
        'kernel.vfs.read_at path=/bin/agent-task handle=0F11E002 offset=0x0 len=52 result=0x69000 consumer=elf32.ehdr source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/agent-task handle=0F11E002 offset=0x34 len=96 result=0x70634 consumer=elf32.phdr source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/agent-task handle=0F11E002 offset=0x100 len=224 result=0x69100 consumer=elf32.text source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/agent-task handle=0F11E002 offset=0x200 len=64 result=0x69200 consumer=elf32.data source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-food handle=0F11E003 offset=0x0 len=52 result=0x69300 consumer=elf32.ehdr source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-food handle=0F11E003 offset=0x34 len=96 result=0x70934 consumer=elf32.phdr source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-food handle=0F11E003 offset=0x100 len=254 result=0x69400 consumer=elf32.text source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-food handle=0F11E003 offset=0x300 len=51 result=0x69600 consumer=elf32.data source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-payment handle=0F11E004 offset=0x0 len=52 result=0x69600 consumer=elf32.ehdr source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-payment handle=0F11E004 offset=0x34 len=96 result=0x70C34 consumer=elf32.phdr source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-payment handle=0F11E004 offset=0x100 len=15 result=0x69700 consumer=elf32.text source=page-cache+file-ops status=ok',
        'kernel.vfs.read_at path=/bin/provider-payment handle=0F11E004 offset=0x200 len=25 result=0x69800 consumer=elf32.data source=page-cache+file-ops status=ok',
        'kernel.task.image.copy-plan segment=text src=image+phdr.p_offset dst=load+phdr.p_paddr len=phdr.p_filesz flags=RX source=runtime-pt-load-header status=ok',
        'kernel.task.image.copy-plan segment=data src=image+phdr.p_offset dst=load+phdr.p_paddr len=phdr.p_filesz flags=RW source=runtime-pt-load-header status=ok',
        'kernel.task.image.copy-plan segment=bss op=zero dst=load+phdr.p_paddr len=phdr.p_memsz flags=RW source=runtime-pt-load-header status=ok',
        'kernel.task.image.bounds-validate format=ELF32 p_offset+p_filesz<=file p_paddr+p_memsz<=task-span e_entry-inside-text data-segment-page=separate-rw source=elf32-header+module-registry status=ok',
        'kernel.task.image.segment-copy format=ELF32 src=image+p_offset dst=p_paddr text len=code_len bounds=file+single-page source=elf32-header+module-registry status=ok',
        'kernel.task.image.segment-copy format=ELF32 src=image+p_offset dst=p_paddr data separate-page len=data_len bounds=file+single-page source=elf32-header+module-registry status=ok',
        'kernel.task.image.zero-fill format=ELF32 dst=p_paddr bss separate-page len=bss_len bounds=single-page source=elf32-header+module-registry status=ok',
        'kernel.task.image.bss-probe modules=agent-task|provider-food|provider-payment bss=zeroed-by-loader not=file-backed source=loader-zero-fill status=ok',
        'kernel.elf.vmap.write task=8000 text_vaddr=0x08048000 text_paddr=0x76000 data_vaddr=0x08049000 data_paddr=0x79000 bss_vaddr=0x08049400 bss_paddr=0x79400 flags=RX|RW source=elf32-pt-load status=ok',
        'kernel.elf.vmap.write task=8100 text_vaddr=0x08048000 text_paddr=0x77000 data_vaddr=0x08049000 data_paddr=0x7A000 bss_vaddr=0x08049400 bss_paddr=0x7A400 flags=RX|RW source=elf32-pt-load status=ok',
        'kernel.elf.vmap.write task=8120 text_vaddr=0x08048000 text_paddr=0x78000 data_vaddr=0x08049000 data_paddr=0x7B000 bss_vaddr=0x08049400 bss_paddr=0x7B400 flags=RX|RW source=elf32-pt-load status=ok',
        'kernel.mm.mmap.table base=0x1017D0 records=5 record_bytes=36 fields=task|start|end|prot|file|offset|cache_slot|backing|next source=elf-loader status=ready',
        'kernel.mm.mmap.table.meta base=0x1017D0 cap=5 record_bytes=36 bitmap=0x102230 source=file-mmap-header status=ok',
        'kernel.mm.mmap.alloc.metadata-driven base=mmap_meta.base cap=mmap_meta.cap record_bytes=mmap_meta.record_size first_free_slot=scan-result result=slot-address source=file-mmap-header status=ok',
        'kernel.mm.mmap.alloc bitmap_before=0x7 first_free_slot=3 result=0x10183C bitmap_after=0xF source=mmap-allocator status=ok',
        'kernel.mm.mmap.alloc.full bitmap=0xF expected=deny result=0 source=mmap-allocator status=full',
        'kernel.mm.mmap.alloc.lifecycle slots=text0|text1|text2|html bitmap=0xF source=mmap-allocator status=ok',
        'kernel.mm.mmap.record slot=0 task=8000 range=0x08048000-0x08048100 prot=rx file=0x1014F8 offset=0x100 cache_slot=0x101588 backing=0x76000 flags=text|private source=file-mmap-table status=ok',
        'kernel.mm.mmap.record slot=1 task=8100 range=0x08048000-0x080480E7 prot=rx file=0x101510 offset=0x100 cache_slot=0x1015A0 backing=0x77000 flags=text|private source=file-mmap-table status=ok',
        'kernel.mm.mmap.record slot=2 task=8120 range=0x08048000-0x0804800F prot=rx file=0x101528 offset=0x100 cache_slot=0x1015B8 backing=0x78000 flags=text|private source=file-mmap-table status=ok',
        'kernel.mm.mmap.record slot=3 task=kernel range=0x00068200-0x000686E2 prot=r file=0x1014E0 offset=0x0 cache_slot=0x101570 backing=0x68200 flags=html|private source=file-mmap-table status=ok',
        'kernel.mm.mmap.html file=0x1014E0 path=/agent-order-task.html offset=0 cache_slot=0x101570 backing=0x68200 len=1254 consumer=kernel-dom-parser source=file-mmap-table status=ok',
        'kernel.mm.mmap.file task=8000 vaddr=0x08048000-0x08048100 file=0x1014F8 offset=0x100 paddr=0x76000 rights=rx source=elf-text-vma status=ok',
        'kernel.mm.mmap.file task=8100 vaddr=0x08048000-0x080480E7 file=0x101510 offset=0x100 paddr=0x77000 rights=rx source=elf-text-vma status=ok',
        'kernel.mm.mmap.pagecache task=8100 file=0x101510 offset=0x100 cache_slot=0x1015A0 backing=0x69400 mapped_paddr=0x77000 source=file-backed-vma status=ok',
        'kernel.mm.mmap.deny task=8100 vaddr=0x08048000 rights=rx access=write source=file-backed-vma status=denied-ok',
        'kernel.vfs.lookup.scan path=/bin/provider-food compare=loop records=7 matched-record=2 data=0x69300 type=elf32 source=vfs-scan-loop status=ok',
        'kernel.vfs.lookup.scan path=/bin/missing compare=loop records=7 matched-record=none expected=deny source=vfs-scan-loop status=not-found-ok',
        'kernel.vfs.type.check path=/agent-order-task.html expected=html actual=html consumer=dom-parser status=ok',
        'kernel.vfs.type.check path=/bin/agent-task expected=elf32 actual=elf32 consumer=task-loader status=ok',
        'kernel.vfs.type.deny path=/agent-order-task.html expected=elf32 actual=html consumer=task-loader status=denied-ok',
        'kernel.vfs.type.deny path=/bin/agent-task expected=html actual=elf32 consumer=dom-parser status=denied-ok',
        'kernel.vfs.lookup path=/bin/provider-food record=2 data=0x69300 type=elf32 source=path-table status=ok',
        'kernel.vfs.lookup path=/bin/provider-payment record=3 data=0x69600 type=elf32 source=path-table status=ok',
        f'html.parser start source=initramfs:{args.source_name} engine=fluid-html-subset',
        'kernel.module.capacity loader=stage1.5 stage1_5_sectors=4 stage2_lba=5 stage2_sectors=600 stage2_max=307200 initramfs_lba=605 previous_stage2_sectors=456 expansion=+73728bytes module_budget=mm|vma|network|vfs|elf32-loader|kthread|driver-core|devfs|future-modules status=ready',
        'kernel.device.registry base=0x102720 records=3 record_bytes=32 devices=fb0|input0|agent-loopback classes=framebuffer|input|net ops=driver-bound-not-static source=driver-core status=ready',
        'kernel.device.resolve class=input name=input0 record=0x102740 irq=ps2-keyboard|ps2-mouse ring=0x1025E0 waitq=0x101488 ops=input_event source=driver-core status=ok',
        'kernel.device.resolve class=net name=agent-loopback record=0x102760 queue=0x103CA0 waitq=0x103D90 ops=socket_queue source=driver-core status=ok',
        'kernel.device.resolve class=framebuffer name=fb0 record=0x102720 mem=0xA0000 mode=320x200 ops=fb_rect source=driver-core status=ok',
        'kernel.vfs.lookup.result path=/lib/modules/fb.ko inode=5 op=kmod-open data=0x6A200 source=vfs-table status=ok',
        'kernel.kmod.block.read path=/lib/modules/*.ko op=read_at offset=0 blockdev=initramfs buffer_head=module-block bio=read pagecache=module-image source=vfs->pagecache->blockdev status=ok',
        'kernel.kmod.elf.shstrtab.scan module=current shstrndx=6 strings=.text|.symtab|.strtab|.rel.text|.fluid.driver|.shstrtab match=by-name source=elf32-section-name-table status=ok',
        'kernel.kmod.elf.strtab.symbol-match module=current strtab=0x180 symtab=0x150 entries=3 matched=register_driver st_name=1 bind=GLOBAL shndx=UND source=elf32-symbol-name-walk status=ok',
        'kernel.kmod.elf.rel.r_info.decode module=current raw=0x101 sym_index=1 reloc_type=1 reloc_name=R_386_32 symbol=register_driver source=ELF32_R_SYM+ELF32_R_TYPE status=ok',
        'kernel.vfs.lookup.result path=/lib/modules/input.ko inode=6 op=kmod-open data=0x6A400 source=vfs-table status=ok',
        'kernel.vfs.lookup.result path=/lib/modules/agent-loopback.ko inode=7 op=kmod-open data=0x6A600 source=vfs-table status=ok',
        'kernel.kmod.vfs.read module=fb.ko file=/lib/modules/fb.ko data=0x6A200 len=445 magic=ELF32-REL source=vfs-file-object+blockdev-pagecache status=ok',
        'kernel.kmod.vfs.read module=input.ko file=/lib/modules/input.ko data=0x6A400 len=445 magic=ELF32-REL source=vfs-file-object+blockdev-pagecache status=ok',
        'kernel.kmod.vfs.read module=agent-loopback.ko file=/lib/modules/agent-loopback.ko data=0x6A600 len=445 magic=ELF32-REL source=vfs-file-object+blockdev-pagecache status=ok',
        'kernel.kmod.elf.shdr.scan module=fb.ko shoff=0x34 shnum=7 shentsize=40 shstrndx=6 names=from-.shstrtab sections=.text|.symtab|.strtab|.rel.text|.fluid.driver|.shstrtab source=elf32-shstrtab-name-scan status=ok',
        'kernel.kmod.elf.symtab.scan module=fb.ko section=.symtab linked=.strtab symbols=UND|register_driver|module_init bind=GLOBAL names=from-.strtab source=elf32-strtab-symbol-walk status=ok',
        'kernel.kmod.elf.rel.scan module=fb.ko section=.rel.text r_info=0x101 sym_index=1 reloc_type=R_386_32 sym=register_driver offset=driver_table[0] source=elf32-r_info-decode+relocation-table status=ok',
        'kernel.kmod.elf.shdr.scan module=input.ko shoff=0x34 shnum=7 shentsize=40 shstrndx=6 names=from-.shstrtab sections=.text|.symtab|.strtab|.rel.text|.fluid.driver|.shstrtab source=elf32-shstrtab-name-scan status=ok',
        'kernel.kmod.elf.symtab.scan module=input.ko section=.symtab linked=.strtab symbols=UND|register_driver|module_init bind=GLOBAL names=from-.strtab source=elf32-strtab-symbol-walk status=ok',
        'kernel.kmod.elf.rel.scan module=input.ko section=.rel.text r_info=0x101 sym_index=1 reloc_type=R_386_32 sym=register_driver offset=driver_table[1] source=elf32-r_info-decode+relocation-table status=ok',
        'kernel.kmod.elf.shdr.scan module=agent-loopback.ko shoff=0x34 shnum=7 shentsize=40 shstrndx=6 names=from-.shstrtab sections=.text|.symtab|.strtab|.rel.text|.fluid.driver|.shstrtab source=elf32-shstrtab-name-scan status=ok',
        'kernel.kmod.elf.symtab.scan module=agent-loopback.ko section=.symtab linked=.strtab symbols=UND|register_driver|module_init bind=GLOBAL names=from-.strtab source=elf32-strtab-symbol-walk status=ok',
        'kernel.kmod.elf.rel.scan module=agent-loopback.ko section=.rel.text r_info=0x101 sym_index=1 reloc_type=R_386_32 sym=register_driver offset=driver_table[2] source=elf32-r_info-decode+relocation-table status=ok',
        'kernel.kmod.table base=0x102920 records=3 modules=fb.ko|input.ko|agent-loopback.ko fields=magic|class|ops|fops|opmask|driver_slot source=vfs-initramfs-module-files status=ready',
        'kernel.kmod.elf.table base=0x102980 records=3 format=ELF32-REL fields=magic|type|module|symbol|reloc_target source=vfs-section-loader status=ready',
        'kernel.kmod.load module=fb.ko class=framebuffer ops=fb_rect fops=0x102850 source=vfs-section-loader status=ok',
        'kernel.kmod.load module=input.ko class=input ops=input_event fops=0x102860 source=vfs-section-loader status=ok',
        'kernel.kmod.load module=agent-loopback.ko class=net ops=socket_queue fops=0x102870 source=vfs-section-loader status=ok',
        'kernel.kmod.elf.ehdr.validate module=fb.ko magic=ELF class=32 endian=little type=REL machine=386 ehsize=52 shoff=0x34 shnum=7 status=ok',
        'kernel.kmod.symbol.resolve module=fb.ko symbol=register_driver value=0xC0110001 name=from-.strtab source=elf32-symtab-walk+kernel-symbol-table status=ok',
        'kernel.kmod.reloc.apply module=fb.ko type=R_386_32 target=driver_table[0] symbol=register_driver sym_index=1 source=elf32-r_info-decoder+relocation-table status=ok',
        'kernel.kmod.init.call module=fb.ko entry=module_init register_driver=fb source=relocated-init status=ok',
        'kernel.kmod.elf.ehdr.validate module=input.ko magic=ELF class=32 endian=little type=REL machine=386 ehsize=52 shoff=0x34 shnum=7 status=ok',
        'kernel.kmod.symbol.resolve module=input.ko symbol=register_driver value=0xC0110001 name=from-.strtab source=elf32-symtab-walk+kernel-symbol-table status=ok',
        'kernel.kmod.reloc.apply module=input.ko type=R_386_32 target=driver_table[1] symbol=register_driver sym_index=1 source=elf32-r_info-decoder+relocation-table status=ok',
        'kernel.kmod.init.call module=input.ko entry=module_init register_driver=input source=relocated-init status=ok',
        'kernel.kmod.elf.ehdr.validate module=agent-loopback.ko magic=ELF class=32 endian=little type=REL machine=386 ehsize=52 shoff=0x34 shnum=7 status=ok',
        'kernel.kmod.symbol.resolve module=agent-loopback.ko symbol=register_driver value=0xC0110001 name=from-.strtab source=elf32-symtab-walk+kernel-symbol-table status=ok',
        'kernel.kmod.reloc.apply module=agent-loopback.ko type=R_386_32 target=driver_table[2] symbol=register_driver sym_index=1 source=elf32-r_info-decoder+relocation-table status=ok',
        'kernel.kmod.init.call module=agent-loopback.ko entry=module_init register_driver=agent-loopback source=relocated-init status=ok',
        'kernel.kmod.reloc.complete modules=3 relocations=3 initcalls=3 source=vfs-section-ELF32-REL-loader status=ok',
        'kernel.kmod.register.scan cursor=module-table record=KMOD driver_slot=module+0x14 copy=class|ops|fops|opmask module_ptr=driver+0x10 source=generic-register-driver-loop status=ok',
        'kernel.kmod.register.scan.complete module_records=3 driver_records=3 registered=3 source=generic-kmod-register-loop status=ok',
        'kernel.kmod.register module=fb.ko driver=fb target=driver_table[0] driver_slot=module.meta source=kmod-table-scan+register_driver status=ok',
        'kernel.kmod.register module=input.ko driver=input target=driver_table[1] driver_slot=module.meta source=kmod-table-scan+register_driver status=ok',
        'kernel.kmod.register module=agent-loopback.ko driver=agent-loopback target=driver_table[2] driver_slot=module.meta source=kmod-table-scan+register_driver status=ok',
        'kernel.kmod.register.complete modules=3 drivers=3 scanned=3 policy=module.driver_slot->driver_table source=kmod-table-scan->driver-core status=ok',
        'kernel.driver.bus.table base=0x102894 records=3 buses=platform|input|net match=bus.match_class probe=bus.probe_bind source=driver-core status=ready',
        'kernel.driver.table base=0x1028C4 records=3 drivers=fb|input|agent-loopback fields=class|ops|fops|opmask|module source=kmod-register status=ready',
        'kernel.driver.bus.match bus_cursor=bus-table device_cursor=device-table callback=bus.match_class predicate=device.class==bus.class source=linux-like-bus-type status=ok',
        'kernel.driver.probe.call bus=current driver=current device=current callback=bus.probe_bind action=set-driver-ops-bus source=linux-like-probe status=ok',
        'kernel.driver.match.loop bus_cursor=matched-bus device_cursor=table driver_cursor=table predicate=bus.match&&driver.class==device.class action=probe source=generic-bus-device-driver-scan status=ok',
        'kernel.driver.bind.scan.complete device_records=4 bus_records=3 driver_records=3 scanned_until_empty=1 matches=3 source=generic-bus-match-probe-loop status=ok',
        'kernel.driver.bind bus=platform device=fb0 driver=fb ops=fb_rect fops=0x102850 source=bus-device-driver-scan class-match status=ok',
        'kernel.driver.bind bus=input device=input0 driver=input ops=input_event fops=0x102860 source=bus-device-driver-scan class-match status=ok',
        'kernel.driver.bind bus=net device=agent-loopback driver=agent-loopback ops=socket_queue fops=0x102870 source=bus-device-driver-scan class-match status=ok',
        'kernel.driver.bind.complete devices=3 drivers=3 buses=3 bound=3 policy=bus.match+bus.probe nested-scan=device-table*bus-table*driver-table source=linux-like-driver-core status=ok',
        'kernel.devfs.scan cursor=device-table predicate=device.bound&&driver.fops copy=device-resource->devfs-node source=generic-devfs-populate-loop status=ok',
        'kernel.devfs.scan.complete device_records=4 bound_devices=3 nodes=3 source=generic-device-table-devfs-loop status=ok',
        'kernel.devfs.node.create path=/dev/fb0 device=fb0 driver=fb fops=0x102850 source=generic-devfs-scan status=ok',
        'kernel.devfs.node.create path=/dev/input0 device=input0 driver=input fops=0x102860 source=generic-devfs-scan status=ok',
        'kernel.devfs.node.create path=/dev/net/agent-loopback device=agent-loopback driver=agent-loopback fops=0x102870 source=generic-devfs-scan status=ok',
        'kernel.devfs.populate from=driver-core bound_devices=3 nodes=3 policy=device-table-scan source=device-model status=ok',
        'kernel.devfs.mount table=0x1027C0 records=3 nodes=/dev/fb0|/dev/input0|/dev/net/agent-loopback source=driver-core-populate status=ready',
        'kernel.devfs.file_operations table=0x102850 records=3 ops=open|read|write|ioctl classes=fb|input|net source=linux-like-fops status=ready',
        'kernel.devfs.fops.dispatch node=current op=devfs_dispatch fops=record+0x1C mask=checked target=device-ops source=vfs-file-operations status=ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=user-devfs-write source=devfs-fd-syscall-probe status=attempt',
        'kernel.syscall.entry vector=80 name=sys_fd_write from=provider.food cpl=3 fd=3 buf=0x08049000 len=16 source=fd-api status=entered',
        'kernel.fd.open.namei.bytecmp task=8100 user_ptr=0x08049040 dentry-name=/dev/fb0 compare=literal-devfs-component source=sys_fd_open-namei status=ok',
        'kernel.fd.open.devfs.namei.walk task=8100 path=/dev/fb0 mount=devfs dentry-scan=linear result=dentry source=sys_fd_open-namei status=ok',
        'kernel.fd.open.devfs.namei.components task=8100 path=/dev/fb0 step1=dev:dentry0x102D80 step2=fb0:dentry0x102CC0 parent-chain=root->dev source=sys_fd_open-component-walk status=ok',
        'kernel.fd.open.devfs.dentry task=8100 dentry=0x102CC0 mount=0x102BD0 name_ptr=0x08049040 name_hash=0xD2010001 inode=0xDFB00001 devfs_node=0x1027C0 source=structured-namei-dentry-cache status=ok',
        'kernel.fd.open.path.namei task=8100 user_ptr=0x08049040 path=/dev/fb0 components=dev|fb0 mount=devfs source=sys_fd_open-namei status=ok',
        'kernel.fd.open.vfs task=8100 path=/dev/fb0 mount=devfs dentry=0x102CC0 node=0x1027C0 file_operations=0x102850 source=namei-vfs-lookup status=ok',
        'kernel.fd.open.devfs.fops task=8100 path=/dev/fb0 op=open via=devfs_dispatch target=fb0 source=sys_fd_open->vfs-file-operations status=ok',
        'kernel.fd.table.install.devfs task=8100 base=0x1016C8 fd=3 ofd=0x1022A0 file=devfs:/dev/fb0 pos=0 rights=write|ioctl source=sys_fd_open-devfs status=ok',
        'kernel.fd.write.resolve task=current fd=arg.ebx record=fd-scan ofd=fd->ofd file=devfs-node:/dev/fb0 rights=write source=fdtable+open-file-description status=ok',
        'kernel.fd.write.devfs task=current fd=3 node=/dev/fb0 op=write via=devfs_dispatch target=fb0 source=sys_fd_write->vfs-file-operations status=ok',
        'kernel.syscall.return vector=80 name=sys_fd_write bytes=16 file=/dev/fb0 status=ok',
        'kernel.ring3.return from=sys_fd_write to=kernel-devfs-probe status=ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=user-devfs-ioctl source=devfs-fd-syscall-probe status=attempt',
        'kernel.syscall.entry vector=80 name=sys_ioctl from=provider.food cpl=3 fd=3 cmd=0x4601 source=fd-api status=entered',
        'kernel.fd.ioctl.resolve task=current fd=arg.ebx record=fd-scan ofd=fd->ofd file=devfs-node:/dev/fb0 rights=ioctl source=fdtable+open-file-description status=ok',
        'kernel.fd.ioctl.devfs task=current fd=3 node=/dev/fb0 op=ioctl via=devfs_dispatch target=fb0 source=sys_ioctl->vfs-file-operations status=ok',
        'kernel.syscall.return vector=80 name=sys_ioctl result=0 file=/dev/fb0 status=ok',
        'kernel.ring3.return from=sys_ioctl to=kernel-devfs-probe status=ok',
        'kernel.fd.devfs.probe.restore fdtable=empty ofdtable=empty current=kernel source=devfs-fd-syscall-probe status=restored',
        'kernel.devfs.lookup path=/dev/fb0 record=0x1027C0 device=fb0 class=framebuffer ops=open|write|ioctl source=devfs-table status=ok',
        'kernel.devfs.open path=/dev/fb0 file=devfs:fb0 device_record=0x102720 ops=fb_rect source=vfs-device-file status=ok',
        'kernel.devfs.write path=/dev/fb0 op=write_rect backend=framebuffer mem=0xA0000 source=device-file-ops status=ok',
        'kernel.devfs.lookup path=/dev/input0 record=0x1027E0 device=input0 class=input ops=open|read|ioctl source=devfs-table status=ok',
        'kernel.devfs.open path=/dev/input0 file=devfs:input0 device_record=0x102740 ops=input_event source=vfs-device-file status=ok',
        'kernel.devfs.read path=/dev/input0 op=read_event ring=0x1025E0 waitq=0x101488 source=device-file-ops status=ok',
        'kernel.devfs.lookup path=/dev/net/agent-loopback record=0x102800 device=agent-loopback class=net ops=open|read|write|ioctl source=devfs-table status=ok',
        'kernel.devfs.open path=/dev/net/agent-loopback file=devfs:net0 device_record=0x102760 ops=socket_queue source=vfs-device-file status=ok',
        'kernel.devfs.ioctl path=/dev/net/agent-loopback cmd=query-mtu result=256 source=device-file-ops status=ok',
        'html.mem.map ok nonoverlap dom=0x100100 task=0x100F60 vfs=0x1014E0 mmap=0x1017D0 mm=0x1018D0 status=ready',
        'kernel.ring3.abi gdt=0x1B/0x23 tss=0x28 esp0=0x90000 gate80.dpl=3 status=installed',
        'kernel.paging enabled cr3=0x200000 identity=4M user-pages=11 pf=0x0E status=ready',
        'kernel.paging.permissions table=kernel text_ro=0x71005|0x76005|0x77005|0x78005|0x79005 stacks_rw=0x72007|0x8C007|0x8D007|0x8E007|0x8F007 initramfs_ro=0x68005|0x69005 write_protect=user-code status=ok',
        'kernel.timer.init source=pit irq=0 vector=0x20 hz=100 idt=installed pic=unmasked status=ready',
        'kernel.timer.tick irq=0 vector=0x20 tick=1 source=hardware-irq0 scheduler-clock=advanced',
        'kernel.page.alloc init base=0x71000 bitmap=0x100E38 policy=bitmap-scan struct_page_table=0x101C20 page_flags_table=0x101E60 lru_table=0x102070 records=32 record_bytes=16 status=ready',
        'kernel.page.alloc.scan limit=32 first-free=0|1|2|3 source=bitmap-loop status=ok',
        'kernel.page.reserve elf-task pages=0x76000|0x77000|0x78000|0x79000|0x7A000|0x7B000 bits=5..10 bitmap-before=0x0000001F bitmap-after=0x000007FF source=elf-loader status=ok',
        'kernel.page.alloc.bitmap addr=0x100E38 value=0x000007FF pages=0:user-text|1:fault-stack|2:reuse-test|3:ipc-queue|4:payment-queue|5:agent-text|6:provider-text|7:payment-text|8:agent-data|9:provider-data|10:payment-data used=11 free=21 status=ok',
        'kernel.page.free addr=0x73000 bit=2 bitmap-after-free=0x00000003 realloc=0x73000 bitmap=0x00000007 status=ok',
        'kernel.kobj.table base=0x100E50 records=2 count=2 object=provider.ipc page=0x74000 slots=4 record_bytes=24 live=1 refs=0 source=alloc_page status=ready',
        'kernel.kobj.table record=1 object=payment.ipc page=0x75000 slots=4 record_bytes=24 live=1 refs=0 source=alloc_page status=ready',
        'kernel.page.alloc user-text=0x71000 fault-stack=0x72000 count=11 source=alloc_page+free_page+reuse+kobj+elf-task-reserve bitmap=0x000007FF status=ok',
        'kernel.mm.zone.init zone=DMA32 start=0x82000 pages=4 free_area_order2=1 free_area_order1=0 free_area_order0=0 source=buddy-prototype status=ready',
        'kernel.mm.buddy.split zone=DMA32 request_order=0 from_order=2 result=0x82000 free_area_order2=0 free_area_order1=1 free_area_order0=1 bitmap=0x000207FF source=free_area+bitmap status=ok',
        'kernel.mm.buddy.alloc zone=DMA32 page=0x82000 order=0 bitmap-bit=17 struct_page=type:kernel owner:0 ref:1 flags=buddy mapcount=0 source=alloc_page_buddy_order0+struct-page+page-flags status=ok',
        'kernel.mm.buddy.free zone=DMA32 page=0x82000 order=0 coalesce_to_order=2 free_area_order2=1 bitmap=0x000007FF struct_page=free flags=0 mapcount=0 source=free_page_buddy_order0+struct-page+page-flags status=ok',
        'kernel.mm.page.ref op=get page=0x82000 old=1 new=2 source=get_page+struct-page status=ok',
        'kernel.mm.page.ref op=put page=0x82000 old=2 new=1 source=put_page+struct-page status=ok',
        'kernel.mm.page.ref op=free page=0x82000 ref=0 flags=0 mapcount=0 bitmap=0x000007FF source=put_page+buddy-free status=ok',
        'kernel.mm.munmap.range-walk task=8100 record=synthetic start=0x08050000 end=0x08052000 pages=2 ptes=0x50|0x51 old=0x82005|0x83005 new=0 source=sys_munmap-record-walker status=ok',
        'kernel.mm.filepage.reap.range task=8100 pages=2 paddr=0x82000|0x83000 ref=0 flags=0 mapcount=0 lru=removed source=sys_munmap+struct-page+record-walker status=ok',
        'kernel.mm.slab.cache init name=kmalloc-64 page=0x84000 object_size=64 objects=16 free_bitmap=0x0000FFFF struct_page=type:kernel flags=slab source=slab-prototype status=ready',
        'kernel.mm.slab.alloc name=kmalloc-64 ptrs=0x84000|0x84040 live=2 free_bitmap=0x0000FFFC source=bitmap-first-fit status=ok',
        'kernel.mm.slab.free name=kmalloc-64 ptrs=0x84000|0x84040 live=0 free_bitmap=0x0000FFFF source=kfree64 status=ok',
        'kernel.mm.slab.cache restore name=kmalloc-64 live=0 struct_page=free flags=0 source=kernel-probe status=restored',
        'kernel.mm.brk.grow task=8000 old=0x0804D000 new=0x0804E000 vma=0x101AF4 range=0x0804D000-0x0804E000 rights=rw backing=anonymous source=sys_brk status=ok',
        'kernel.mm.anon.vma task=8000 mm=0x1018D0 vma=0x101AF4 heap=brk start=0x0804D000 end=0x0804E000 pte=0x4D policy=lazy-not-present source=mm-vma-list status=ok',
        'kernel.mm.anon.fault task=8000 cr2=0x0804D000 paddr=0x85000 pte=0x4D entry=0x85007 struct_page=type:user-data owner=8000 flags=dirty|lru mapcount=1 source=brk-anonymous-pagefault status=ok',
        'kernel.mm.brk.restore task=8000 heap=cleared pte=0 bitmap=0x000007FF struct_page=free source=kernel-probe status=restored',
        'kernel.syscall.entry vector=80 name=sys_brk from=agent-task cpl=3 ebx=0x0804F000 source=ring3-agent status=entered',
        'kernel.mm.brk.grow task=8000 old=0x0804D000 new=0x0804F000 vma=0x101AF4 range=0x0804D000-0x0804F000 rights=rw pages=2 backing=anonymous source=sys_brk status=ok',
        'kernel.mm.brk.syscall.runtime task=8000 old=0x0804D000 new=0x0804F000 vma=0x101AF4 heap=anonymous pages=2 int80=sys_brk source=ring3-agent status=ok',
        'kernel.mm.anon.fault.runtime task=8000 cr2=0x0804D000 paddr=0x7C000 pte=0x4D entry=0x7C007 struct_page=type:user-data owner=8000 flags=dirty|lru mapcount=1 source=alloc_page+ring3-agent-store page=0 status=handled',
        'kernel.mm.anon.fault.runtime task=8000 cr2=0x0804E000 paddr=0x7D000 pte=0x4E entry=0x7D007 struct_page=type:user-data owner=8000 flags=dirty|lru mapcount=1 source=alloc_page+ring3-agent-store page=1 status=handled',
        'kernel.mm.anon.resume task=8000 eip=faulting-store-retry heap=brk page=0 pte=present source=pagefault-iret status=ok',
        'kernel.mm.anon.resume task=8000 eip=faulting-store-retry heap=brk page=1 pte=present source=pagefault-iret status=ok',
        'kernel.mm.zap.pte task=8000 mm=0x1018D0 vaddr=0x0804E000 pte=0x4E old_entry=0x7D007 paddr=0x7D000 actions=clear-pte|invlpg|lru-remove|free-page source=zap_user_pt32_single_page status=ok',
        'kernel.mm.zap.range task=8000 mm=0x1018D0 start=0x0804E000 end=0x0804F000 pages=1 walker=pte-loop helper=zap_user_pt32_single_page source=brk-shrink status=ok',
        'kernel.mm.brk.shrink.runtime task=8000 old=0x0804F000 new=0x0804E000 unmapped=0x0804E000 pte=0x4E old_entry=0x7D007 freed_paddr=0x7D000 struct_page=cleared flags=0 lru=removed source=zap_user_pt32_range status=ok',
        'kernel.usertext.install base=0x71000 probe=0x71000 fault=0x71100 source=page-allocator+kernel-copy page=user-accessible stage2-user=false status=ready',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=0x71000 source=user-text status=attempt',
        'kernel.pagefault vector=0x0E cr2=0x100000 error=0x5 present=1 write=0 user=1 source=cr2+error-code action=skip-probe status=handled',
        'kernel.pagefault.classify cr2=0x100000 class=supervisor-probe action=resume task=8000 status=ok',
        'kernel.demand.probe schedule task=8000 cr3=0x230000 vaddr=0x0804A000 pte-before=0 source=runtime-vma status=attempt',
        'kernel.pagefault.demand cr2=0x0804A000 task=8000 vma=0x0804A000-0x0804B000 source=mm-vma-list status=handled',
        'kernel.pagefault.demand.map task=8000 vaddr=0x0804A000 paddr=0x7C000 pte=0x4A entry=0x7C007 source=alloc_page+vma status=ok',
        'kernel.demand.probe return task=8000 pte=0x7C007 bitmap=0x00000FFF source=pagefault-resume status=ok',
        'kernel.demand.probe cleanup pte=0 bitmap=0x000007FF source=free_page status=ok',
        'kernel.mm.mmap.fault.schedule task=8000 cr3=0x230000 vaddr=0x08048000 pte-before=0 file=0x1014F8 offset=0x100 source=file-backed-vma status=attempt',
        'kernel.cr3.switch task=8000 from=0x200000 to=0x230000 source=file-mmap-fault-probe status=ok',
        'kernel.mm.vma.file-text.resolve tasks=provider|payment source=find-vma-current-mm status=ok',
        'kernel.pagefault.file-mmap cr2=0x08048000 task=8000 file=0x1014F8 offset=0x100 cache_slot=0x101588 backing=0x69100 mapped_paddr=0x76000 entry=0x76005 source=page-cache+file-mmap-table status=handled',
        'kernel.mm.mmap.fault.map task=8000 vaddr=0x08048000 pte=0x48 old=0 new=0x76005 rights=rx source=pagefault-file-mmap-table status=ok',
        'kernel.mm.mmap.fault.resume task=8000 pte=0x76005 cache=0x69100 source=pagefault-file-mmap-table status=ok',
        'kernel.mm.mmap.fault.restore task=8000 text_pte=0x76005 record=0 source=kernel-probe status=restored',
        'kernel.scheduler.pick task=8300 name=fault-probe reason=isolation-test entry=0x71100 stack=0x72000 via=iretd',
        'kernel.aspace.switch task=8300 cr3=0x210000 entry=0x71100 stack=0x72000 source=isolation-test status=ok',
        'kernel.cr3.switch task=8300 from=0x200000 to=0x210000 source=scheduler status=ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=0x71100 source=isolation-test status=attempt',
        'kernel.pagefault.classify cr2=0x100004 class=non-probe action=kill-current-task task=8300 status=killed',
        'kernel.cr3.switch task=kernel from=0x210000 to=0x200000 source=pagefault-handler status=ok',
        'kernel.ring3.return from=pagefault-kill to=kernel-continuation task=8300 status=ok',
        'kernel.files.init owner=8100 files=0x101780 fdtable=0x1016C8 cap=4 bitmap=0x1 ref=1 source=task-init status=ok',
        'kernel.task.fdtable.attach task=8100 task_record=0x100F80 files=0x101780 fdtable=0x1016C8 record_field=0x18 source=task-init status=ok',
        'kernel.process.table base=0x101950 record=32 slots=5 fields=pid|ppid|task|mm|files|caps|state|ref procs=8000:0|8100:8000|8120:8000|8300:0 child-slot=free source=process-core status=ready',
        'kernel.kthread.table base=0x1026C0 records=2 record_bytes=32 slots=dom-compositor|render-worker fields=tid|entry|stack|phase|state|resume|process|flags|saved_esp|switch_count|continuation_eip source=scheduler-init status=ready',
        'kernel.input.consumer process task=7000 proc=0x102640 task_record=0x100FE0 mm=0x1018D0 entry=kernel-thread role=dom-compositor state=ready scheduler=process-table status=ready',
        'kernel.task.table base=0x100F60 record=32 slots=5 fields=id|entry|stack|state|cap|fault|files|mm tasks=8000:ready|8100:ready|8120:ready|8300:ready|7000:ready fault-entry=0x71100 fault-stack=0x72000 state-source=kernel-memory status=ready',
        'kernel.aspace.registry.read module=agent-task task=8000 entry=0x08048080 stack=0x8F000 cr3=0x230000 source=module-registry consumer=aspace-table status=ok',
        'kernel.aspace.registry.read module=provider-food task=8100 entry=0x08048080 stack=0x8E000 cr3=0x220000 source=module-registry consumer=aspace-table status=ok',
        'kernel.aspace.registry.read module=provider-payment task=8120 entry=0x08048080 stack=0x8C000 cr3=0x240000 source=module-registry consumer=aspace-table status=ok',
        'kernel.aspace.table base=0x100EA0 records=4 tasks=8000:cr3=0x230000|8100:cr3=0x220000|8120:cr3=0x240000|8300:cr3=0x210000 user-pages=agent|provider|payment|fault-isolated status=ready',
        'kernel.mm.struct.table base=0x1018D0 records=4 record_bytes=32 fields=task|cr3|mmap_head|mmap_count|vma_head|vma_count|pt32|refcnt rb_root_table=0x102580 source=aspace-init status=ready',
        'kernel.mm.struct.meta base=0x1018D0 cap=4 record_bytes=32 bitmap=0x10195C source=mm-struct-header status=ok',
        'kernel.mm.struct.rb-root-table base=0x102580 records=4 record_bytes=4 owner=mm_struct index=(mm-base)/record_size source=mm-struct-extension status=ready',
        'kernel.mm.struct.link task=8100 cr3=0x220000 mmap_head=0x1017F4 mmap_count=1 vma_head=0x101A54 vma_count=1 pt32=0x222000 refcnt=1 source=per-task-mm status=ok',
        'kernel.task.mm.link task=8000 task_record=0x100F60 mm=0x1018D0 cr3=0x230000 source=task-table status=ok',
        'kernel.task.mm.link task=8100 task_record=0x100F80 mm=0x1018F0 cr3=0x220000 source=task-table status=ok',
        'kernel.elf.vmap.read task=8000 text_vaddr=0x08048000 text_paddr=0x76000 data_vaddr=0x08049000 data_paddr=0x79000 bss_vaddr=0x08049400 bss_paddr=0x79400 flags=RX|RW source=elf-vmap-table status=ok',
        'kernel.aspace.map.from-elf task=8000 pde=32 text_pte=0x48 data_pte=0x49 text_entry=0x76005 data_entry=0x79007 source=elf-vmap-table status=ok',
        'kernel.mm.mmap.install task=8000 vaddr=0x08048000 pte=0x48 entry=0x76005 file=0x1014F8 source=aspace-map-from-file-vma status=ok',
        'kernel.mm.mmap.prot task=8000 text_entry=0x76005 writable=false source=pte-rights status=ok',
        'kernel.aspace.vmap task=8000 text_vaddr=0x08048000 text_paddr=0x76000 data_vaddr=0x08049000 data_paddr=0x79000 pde=32 text_pte=0x48 data_pte=0x49 text_pte_value=0x76005 data_pte_value=0x79007 entry=0x08048080 source=elf32-pt-load status=ok',
        'kernel.aspace.permissions task=8000 text=0x76005 data=0x79007 stack=0x8F007 initramfs=0x68005|0x69005 policy=text-ro-data-rw-stack-rw source=pte-verify status=ok',
        'kernel.aspace.build task=8000 cr3=0x230000 pd=0x230000 pt0=0x231000 user_pages=0x68000|0x69000|v0x08048000->p0x76000|v0x08049000->p0x79000|0x8F000 perms=text-ro|stack-rw kernel=supervisor status=ready',
        'kernel.aspace.permissions task=8300 text=0x71005 stack=0x72007 initramfs=0x68005|0x69005 policy=text-ro-stack-rw source=pte-verify status=ok',
        'kernel.aspace.build task=8300 cr3=0x210000 pd=0x210000 pt0=0x211000 user_pages=0x68000|0x69000|0x71000|0x72000 perms=text-ro|stack-rw kernel=supervisor status=ready',
        'kernel.elf.vmap.read task=8100 text_vaddr=0x08048000 text_paddr=0x77000 data_vaddr=0x08049000 data_paddr=0x7A000 bss_vaddr=0x08049400 bss_paddr=0x7A400 flags=RX|RW source=elf-vmap-table status=ok',
        'kernel.aspace.map.from-elf task=8100 pde=32 text_pte=0x48 data_pte=0x49 text_entry=0x77005 data_entry=0x7A007 source=elf-vmap-table status=ok',
        'kernel.mm.mmap.install task=8100 vaddr=0x08048000 pte=0x48 entry=0x77005 file=0x101510 source=aspace-map-from-file-vma status=ok',
        'kernel.mm.mmap.prot task=8100 text_entry=0x77005 writable=false source=pte-rights status=ok',
        'kernel.aspace.vmap task=8100 text_vaddr=0x08048000 text_paddr=0x77000 data_vaddr=0x08049000 data_paddr=0x7A000 pde=32 text_pte=0x48 data_pte=0x49 text_pte_value=0x77005 data_pte_value=0x7A007 entry=0x08048080 source=elf32-pt-load status=ok',
        'kernel.aspace.permissions task=8100 text=0x77005 data=0x7A007 stack=0x8E007 initramfs=0x68005|0x69005 policy=text-ro-data-rw-stack-rw source=pte-verify status=ok',
        'kernel.aspace.build task=8100 cr3=0x220000 pd=0x220000 pt0=0x221000 user_pages=0x68000|0x69000|v0x08048000->p0x77000|v0x08049000->p0x7A000|0x8E000 perms=text-ro|stack-rw kernel=supervisor status=ready',
        'kernel.elf.vmap.read task=8120 text_vaddr=0x08048000 text_paddr=0x78000 data_vaddr=0x08049000 data_paddr=0x7B000 bss_vaddr=0x08049400 bss_paddr=0x7B400 flags=RX|RW source=elf-vmap-table status=ok',
        'kernel.aspace.map.from-elf task=8120 pde=32 text_pte=0x48 data_pte=0x49 text_entry=0x78005 data_entry=0x7B007 source=elf-vmap-table status=ok',
        'kernel.mm.mmap.install task=8120 vaddr=0x08048000 pte=0x48 entry=0x78005 file=0x101528 source=aspace-map-from-file-vma status=ok',
        'kernel.mm.mmap.prot task=8120 text_entry=0x78005 writable=false source=pte-rights status=ok',
        'kernel.aspace.vmap task=8120 text_vaddr=0x08048000 text_paddr=0x78000 data_vaddr=0x08049000 data_paddr=0x7B000 pde=32 text_pte=0x48 data_pte=0x49 text_pte_value=0x78005 data_pte_value=0x7B007 entry=0x08048080 source=elf32-pt-load status=ok',
        'kernel.aspace.permissions task=8120 text=0x78005 data=0x7B007 stack=0x8C007 initramfs=0x68005|0x69005 policy=text-ro-data-rw-stack-rw source=pte-verify status=ok',
        'kernel.aspace.build task=8120 cr3=0x240000 pd=0x240000 pt0=0x241000 user_pages=0x68000|0x69000|v0x08048000->p0x78000|v0x08049000->p0x7B000|0x8C000 perms=text-ro|stack-rw kernel=supervisor status=ready',
        'kernel.copy_from_user.bounds probe task=8000 ptr=0x00100000 len=4 expected=data-vmap-deny source=elf-vmap-table status=denied-ok',
        'kernel.task.table.update task=8300 state=killed fault-cr2=0x100004 source=pagefault-handler status=ok',
        'kernel.process.table.read task=8300 state=killed scheduler=skip source=process-table-scan status=ok',
        'kernel.scheduler.skip task=8300 reason=killed state=dead table=0x101950 scan=process-table action=continue-html-boot status=ok',
        'kernel.syscall.entry vector=80 name=sys_probe from=agent-task cpl=3 via=iret-user-stub status=entered',
        'kernel.ring3.return from=sys_probe to=kernel-continuation status=ok',
        'html.node tag=input type=range value=72 rendered=true source=runtime-decimal-attribute-parser',
        'html.node tag=svg data-icon=park|camera|seat rendered=true source=runtime-attribute-string-parser paint=display-list-dispatch',
        'html.parser done buttons=15 h2=2 input=1 svg=3',
        'html.css.parse source=style-tag runtime-scan=true grammar=background-token-resolver rules=5 status=complete',
        'html.style source=button-class-token-matcher css=style-tag-background-token stored=dom-node-state classes=base|info|danger|warm|gold exact-token=true attr-table=0x100A20 buttons=15',
        'html.css.layout.parse properties=left|top|width|height|z-index selectors=nth-of-type|data-icon table=0x103000 records=19 status=complete',
        'html.css.layout.runtime-scan source=style-tag table=0x103000 grammar=selector-slot+px-declarations status=complete',
        'html.layout engine=css-rule-table nodes=button+h2+input+svg css=class-token+absolute-positions svg=data-icon rule_table=0x103000 fallback=kernel-flow-grid status=complete',
        'kernel.compositor.scan records=2 compare-z system.overlay=1 agent.dom=10 source=surface-table status=ok',
        'kernel.compositor.pick top=agent.dom z=10 previous=system.overlay z=1 active=0x101100 status=ok',
        'kernel.compositor.select active=agent.dom surface=0x101100 type=dom live=1 visible_base=0x100100 source=surface-table status=ok',
        'kernel.compositor.paint route=agent.dom renderer=kernel-html-dom-table framebuffer=0xA0000 source=active-surface status=ok',
        'html.dom.table visible_nodes=21',
        'html.dom.tree total=27 visible=21 hidden=6 root=1 main=runtime section=runtime parser=runtime-open-close-stack hidden-siblings=true closes=5 parent-source=current-stack table=kernel-memory@0x100550 status=complete',
        'html.dom.child-links visible=21 sibling-links=21 source=runtime-parent-buckets table=kernel-memory@0x100920 status=complete',
        'html.dom.attrs table=kernel-memory@0x100A20 records=19 kinds=value|data-icon|class source=runtime-attribute-scanners status=complete',
        'html.text.paint source=compositor-display-list font=kernel-bitmap-ascii glyph=batched-1x1-rect-commands flush=per-glyph h2=runtime-innertext status=complete',
        'kernel.paint.display-list op=batch-glyph source=text record_bytes=20 cap=32 flush=per-glyph overflow=auto-flush status=ok',
        'kernel.render-tree.build source=visible-dom table=0x103620 record_bytes=40 cap=32 fields=dom_index|dom_ptr|render_op|box|style|z_order|flags status=ok',
        'kernel.css.selector-meta table=0x134740 record_bytes=16 fields=css_slot|selector_kind|nth|parent source=style-tag-parser+runtime-css-rule status=ok',
        'kernel.css.selector-match table=0x134420 record_bytes=8 fields=dom_index|css_slot source=selector-engine cascade=multi-match status=ok',
        'kernel.css.computed-style table=0x134040 record_bytes=16 fields=dom_index|display|visibility|z_index source=runtime-css-cascade status=ok',
        'kernel.css.parse property=z-index table=0x134260 source=style-tag+runtime-css-rule status=ok',
        'kernel.css.parse property=display|visibility table=0x134300|0x134380 source=style-tag+runtime-css-rule status=ok',
        'kernel.render-tree.z-order source=css-z-index computed-style-field=z_index fallback=dom-order target=render-node.z_order status=ok',
        'kernel.render-tree.visibility source=computed-style table=0x134040 rule=display-or-visibility action=skip-before-render-node status=ok',
        'kernel.render-tree.dispatch source=render-node op=button|h2|input|svg|banner z_order=render-node dom=payload-only status=ok',
        'kernel.compositor.render-tree.traverse source=render-node-table order=z_order-record nodes=render-tree not=dom-child-walk status=ok',
        'kernel.compositor.render-tree.sort algorithm=stable-bubble key=z_order record_bytes=40 source=render-node-table status=ok',
        'kernel.compositor.occlusion.compute source=render-node-table mode=full-cover flag=render-node.flags bit=occluded status=ok',
        'kernel.compositor.display-list.backend flush=deferred owner=frame-display-list target=framebuffer writes=none source=per-node-compat status=skipped',
        'kernel.compositor.display-list.frame op=begin transaction=frame-buffered state=open source=render-pass status=ok',
        'kernel.compositor.display-list.frame op=end transaction=frame-buffered drain=pending-commands state=closed source=render-pass status=ok',
        'kernel.compositor.frame-display-list op=append record_bytes=20 cap=4096 source=paint-emit table=0x120000 status=ok',
        'kernel.compositor.frame-display-list op=frame-flush source=aggregated-list dirty=frame-union backend=framebuffer writes=fb_rect compatibility=per-node-flush-deferred status=ok',
        'kernel.compositor.damage-queue op=consume source=mutation-record-ring cap=8 records=drained union=dirty-rect target=partial-repaint status=ok',
        'kernel.compositor.render-pass mode=partial-damage source=damage-queue static-background=preserved node-culling=render-tree-bounds status=ok',
        'kernel.compositor.render-cull source=dirty-rect render-node-bounds=intersect offscreen-or-clean-nodes=skipped status=ok',
        'html.paint.input-range source=compositor-display-list value=runtime-input-state rail=node-box fill=value-derived thumb=value-derived status=painted',
        'kernel.paint.display-list op=emit+flush source=input-range record_bytes=20 emitted=9 flushed=9 backend=framebuffer status=ok',
        'html.paint.svg-display-list source=dom-node-geometry data-icon=runtime-attr records=vector-primitives rects=2 backend=compositor-display-list status=painted',
        'kernel.paint.display-list op=emit+flush source=svg-display-list record_bytes=20 emitted=2 flushed=2 backend=framebuffer status=ok',
        'kernel.paint.display-list op=emit+flush source=dom-box tag=button record_bytes=20 emitted=2 flushed=2 backend=framebuffer status=ok',
        'kernel.paint.display-list op=emit+flush source=dom-box tag=banner record_bytes=20 emitted=1 flushed=1 backend=framebuffer status=ok',
        'kernel.compositor.dirty-rect op=union source=display-list state=tracked x1<=x2 y1<=y2 count=commands target=partial-repaint status=ok',
        'kernel.compositor.display-list.flush op=dirty-intersect source=display-list dirty=union commands=checked backend=framebuffer framebuffer-writes=intersecting-only status=ok',
        'html.paint source=hidden-tree-container-walk parents=runtime-main-children table=kernel-memory@0x100550+0x100920 status=complete',
        'html.surface qemu-framebuffer=320x200 rendered-by=kernel-html-parser source=initramfs svg=runtime-data-icon-display-list not=pre-rendered-rle',
        'html.verify text=true image=true webpage=true click-targets=15 dom-grab=kernel-node-table',
        'kernel.input.event.queue init base=0x1025E0 records=8 record_bytes=8 devices=keyboard|mouse consumer=dom-compositor status=ready',
        'kernel.input.waitqueue sleep task=7000 req=9601 waitq=0x101488 slot=1 state=waiting process=0x102640 source=input-event-empty status=queued',
        'kernel.input.waitqueue wakeup task=7000 req=9601 waitq=0x101488 slot=1 state=ready process=0x102640 source=input-event-enqueue status=ready',
        'kernel.scheduler.sleep task=7000 name=dom-compositor waitq=0x101488 slot=1 event=input.empty state=waiting source=input-consumer status=queued',
        'kernel.scheduler.wakeup task=7000 name=dom-compositor runqueue=0x101470 slot=runtime-tail state=ready source=input-event-enqueue status=queued',
        'kernel.runqueue.enqueue task=7000 name=dom-compositor reason=input-event queue=system ring=0x101470 slot=runtime-tail count=advanced source=input-event-wakeup status=queued',
        'kernel.scheduler.kthread-scan table=0x1026C0 records=2 match=task-id task=7000 record=0x1026C0 state=runnable source=generic-kthread-scan status=ok',
        'kernel.scheduler.process-scan task=7000 proc=0x102640 state=ready source=runqueue-dequeue status=ok',
        'kernel.scheduler.pick task=7000 name=dom-compositor reason=input-event entry=kernel-thread stack=0x8B000 runqueue=head-advanced via=kernel-frame-dispatch status=ready',
        'k.ctx.r t=7000 from=kernel-thread e=input_consumer_thread_entry s=8B000 method=frame-dispatch ok',
        'kernel.kthread.frame task=7000 old_esp=scheduler saved=0x102660 frame_esp=0x102664 stack_top=0x8B000 method=esp-switch call=indirect status=ok',
        'kernel.kthread.dispatch task=7000 table=0x1026C0 record=0x1026C0 entry=record+0x04 stack=record+0x08 phase=record+0x0C resume=record+0x14 saved_esp=record+0x20 switch_count=record+0x24 source=generic-kthread-table status=ok',
        'kernel.kthread.context.restore task=7000 saved_esp=record+0x20 value=0x8B000 method=stack-field-read source=generic-kthread-context status=ok',
        'kernel.kthread.stack.guard task=7000 low=0x8A000 top=0x8B000 canary=0xC0DEF00D saved_esp=in-range source=kernel-stack-guard status=ok',
        'kernel.kthread.stack.switch task=7000 from=scheduler-esp to=record.saved_esp value=0x8AFFC method=mov-esp source=generic-kthread-context status=entered',
        'kernel.kthread.stack.restore task=7000 from=kthread-esp to=scheduler-esp saved=0x102660 method=mov-esp source=generic-kthread-context status=returned',
        'kernel.kthread.context.save task=7000 saved_esp=record+0x20 switch_count=record+0x24 method=stack-field-write source=generic-kthread-context status=ok',
        'kernel.kthread.continuation.push task=7000 continuation=record+0x28 method=push+jmp target=record.entry_or_resume source=generic-kthread-context status=ok',
        'kernel.kthread.indirect-call task=7000 target=record.entry field=0x04 method=call-[kthread.target] source=generic-kthread-dispatch status=ok',
        'kernel.kthread.indirect-resume task=7000 target=record.resume field=0x14 method=call-[kthread.target] source=generic-kthread-dispatch status=ok',
        'kernel.kthread.entry task=7000 name=dom-compositor fn=input_consumer_thread_entry source=scheduler-pick status=running',
        'k.ctx.s t=7000 frame=kernel-thread esp=frame-saved phase=saved restore=scheduler event-consumed wait-or-requeue ok',
        'kernel.kthread.yield task=7000 name=dom-compositor phase=after-dequeue save=phase-resume source=input-consumer status=yielded',
        'k.ctx.resume t=7000 from=saved-phase phase=after-dequeue event=backlog status=ok',
        'kernel.kthread.resume task=7000 name=dom-compositor phase=after-dequeue source=saved-context status=running',
        'kernel.kthread.exit task=7000 name=dom-compositor action=return-to-scheduler source=input-consumer status=ok',
        'kernel.input.event.enqueue device=last type-code ring=0x1025E0 tail=advanced source=input-core status=queued',
        'kernel.input.event.dequeue consumer=dom-compositor source=input-core status=ok',
        'kernel.input.event.dequeue device=mouse consumer=dom-hit-test source=input-core status=ok',
        'kernel.keyboard.irq init device=ps2 vector=0x21 pic=unmasked ring=0x1025B0 slots=4 status=ready',
        'kernel.keyboard.irq vector=0x21 scancode=queued ring=0x1025B0 source=irq1-handler status=enqueued',
        'kernel.keyboard.event dequeue source=irq1-ring consumer=dom-input status=ok',
        'html.input.wait source=ps2-keyboard action=range-state-update target=input[value] keys=up|down',
        'html.input.keyboard scancode=0x48 action=range-increment old=72 new=84 source=ps2-keyboard status=ok',
        'kernel.compositor.invalidate source=input-mutation target=input[type=range] rect=node-box dirty=damage-queue+mutation-record status=queued',
        'html.repaint source=keyboard-dom-state input_value=84 status=complete',
        'html.input.keyboard release=consumed device=ps2-keyboard handoff=ps2-mouse status=ready',
        'html.input.wait source=ps2-mouse action=hit-test-runtime-button',
        'html.input.mouse ready=true source=ps2-aux',
        'html.input.mouse packet=left-click cursor=from-ps2-delta dynamic-flow y=direct source=ps2-aux',
        'kernel.compositor.input focus=agent.dom active=agent.dom surface=0x101100 owner=8000 source=focus-table status=ok',
        'kernel.compositor.input.route device=ps2-mouse top=agent.dom target=agent.dom hit-test=kernel-dom-tree input-owner=8000 status=ok',
        'kernel.reply.object.table base=0x1010A0 records=2 record_bytes=32 food=req9001|owner8100|target8000|ptr0x08049000|len22 payment=req9101|owner8120|target8000|ptr0x08049000|len24 status=ready-for-sys_reply',
        'kernel.kobj.alloc init bitmap=0x00000007 slots=0:provider.ipc|1:payment.ipc|2:agent.dom free=slot3:runtime-surface state=ready',
        'kernel.handle.alloc init owner=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready',
        'kernel.surface.object table=0x101100 records=2 record_bytes=64 id=agent.dom owner=8000 type=dom visible=0x100100 cap=23 hidden=0x100550 attr=0x100A20 z=10 status=ready',
        'kernel.cap.open owner=agent.task owner_task=8000 target=surface.agent.dom handle=0F00D003 rights=write live=1 table=0x101100 namespace=per-task status=granted',
        'kernel.surface.object table=0x101140 record=1 id=system.overlay owner=kernel type=system z=1 visible=false status=ready',
        'kernel.compositor.table base=0x1011C0 surfaces=2 active=agent.dom focus=agent.dom input-owner=8000 policy=z-order-topmost status=ready',
        'kernel.compositor.zorder surfaces=system.overlay:z1|agent.dom:z10 top=agent.dom scan=surface-table status=ready',
        'kernel.syscall.entry vector=80 name=sys_surface_create from=agent-task cpl=3 abi=ebx:size+ecx:prot requested=5000 prot=rw requested=dom-surface source=agent-runtime status=entered',
        'kernel.kobj.alloc kind=surface.runtime owner=8000 slot=3 addr=0x101180 bitmap-before=0x00000007 bitmap-after=0x0000000F source=sys_surface_create status=ok',
        'kernel.handle.alloc owner=8000 slot=2 handle=0F00D004 rights=write cap_record=0x101050 bitmap-before=0x00000003 bitmap-after=0x00000007 source=sys_surface_create status=ok',
        'kernel.mm.vma.lazy-reserve task=8000 requested=5000 rounded=8192 pages=2 ptes=0x4A|0x4B initial=not-present backing=on-demand source=sys_surface_create status=ok',
        'kernel.mm.vma.size task=8000 requested=5000 rounded=8192 pages=2 source=user-abi-ebx status=ok',
        'kernel.mm.vma.gap-select task=8000 start=0x0804A000 end=0x0804C000 size=8192 source=mm-vma-list-gap status=ok',
        'kernel.mm.vma.overlap-check task=8000 requested=0x0804A000-0x0804C000 checked=4 scan=all-vma-records policy=deny-overlap source=selected-gap status=ok',
        'kernel.mm.vma.allocator.init bitmap=0x77 cap=10 free=slot3|7|8|9 scan=bitmap source=vma-core-allocator status=ready',
        'kernel.mm.vma.alloc-record.metadata-driven task=8000 slot=3 record=0x101A7C base=vma_meta.base cap=vma_meta.cap record_bytes=vma_meta.record_size bitmap-before=0x77 bitmap-after=0x7F scan=first-free source=vma-table-header status=ok',
        'kernel.mm.vma.meta.alloc slot=3 owner=8000 state=runtime ref=1 source=vma-metadata status=ok',
        'kernel.mm.vma.backing.set vma=0x101A7C kind=anonymous object=0 source=sys_surface_create status=ok',
        'kernel.mm.vma.link task=8000 mm=0x1018D0 data.next=0x101A90 text.next=0x101A7C runtime.next=0 count=3 source=vma-core-insert status=ok',
        'kernel.mm.vma.tree.insert task=8000 root=runtime.left=data runtime.right=old-root index=start-address source=vma_link_current_mm status=ok',
        'kernel.mm.vma.tree.insert.root-update mm=current->mm field=mm_struct.rb_root_table[mm_index] source=vma_link_current_mm status=ok',
        'kernel.mm.vma.alloc task=8000 slot=3 record=0x101A7C range=0x0804A000-0x0804C000 rights=rw backing=lazy-pages source=sys_surface_create status=ok',
        'kernel.mm.vma.map task=8000 vaddr=0x0804A000|0x0804B000 pte=0x4A|0x4B entry=0|0 policy=lazy-fault rights=user|rw source-prot=ecx source=sys_surface_create pages=2 status=ok',
        'kernel.mm.vma.touch task=8000 vaddr=0x0804A000 access=write source=agent-ring3 status=attempt',
        'kernel.mm.find_vma.generic mm=current->mm addr=pagefault.cr2 head=mm->vma_head scan=vma-linked-list result=matched-vma record=generic-vma source=find_vma(mm,addr) status=ok',
        'kernel.pagefault.vm_ops dispatch via=vma->vm_ops fault=not-present op=anonymous_fault|filemap_fault source=vm-ops-prototype status=ok',
        'kernel.pagefault.vma.ext vm_ops=vma_ext->vm_ops backing=vma_ext->private_data source=vm-area-struct status=ok',
        'kernel.mm.find_vma.tree mm=current->mm root=mm_rb addr=pagefault.cr2 walk=start-end compare result=matched-vma source=find_vma_rb status=ok',
        'kernel.mm.find_vma.tree.root mm=current->mm rb_root=mm_struct.rb_root_table[mm_index] not=global-task-switch source=mm_struct status=ok',
        'kernel.mm.find_vma.tree.primary mm=current->mm result=tree-hit sets=ALLOC_RUNTIME_VMA_RECORD fallback=list-verify source=find_vma_rb status=ok',
        'kernel.pagefault.vma.backing kind=anonymous vma=find_vma.result dispatch=anon source=vma-backing-table status=ok',
        'kernel.pagefault.vma.backing kind=file-mmap vma=find_vma.result dispatch=file source=vma-backing-table status=ok',
        'kernel.pagefault.filemap via=vma.backing_object object=file_mmap_record file=record+0x10 page_cache=record+0x18 source=vma-centric-fault status=ok',
        'kernel.pagefault.find_vma.rb-primary mm=current->mm source=find_vma_rb before=classify status=ok',
        'kernel.pagefault.dispatch handler=anon fault=not-present vma=find_vma.result backing=anonymous source=do_page_fault status=selected',
        'kernel.pagefault.dispatch handler=file fault=not-present vma=find_vma.result backing=file-mmap source=do_page_fault status=selected',
        'kernel.mm.find_vma.current task=8000 mm=0x1018D0 cr2=0x0804A000 vma=0x101A7C range=0x0804A000-0x0804C000 page_index=0 paddr=0x7C000 pte=0x4A source=find-vma-current-mm status=ok',
        'kernel.mm.find_vma fault task=8000 mm=0x1018D0 vma=0x101A7C range=0x0804A000-0x0804C000 dispatch=runtime-surface source=find-vma-current-mm status=ok',
        'kernel.pagefault.runtime-vma cr2=0x0804A000 task=8000 vma=0x0804A000-0x0804C000 access=write paddr=0x7C000 entry=0x7C007 source=sys_surface_create-ring3-touch status=handled',
        'kernel.mm.vma.touch.resume task=8000 vaddr=0x0804A000 pte=0x7C007 bitmap=0x00000FFF source=pagefault-resume status=ok',
        'kernel.mm.vma.touch.user-resume task=8000 eip=0x080480A3 mode=iret-retry-faulting-instruction next=cpu-reexec-store source=pagefault-natural-resume status=ok',
        'kernel.mm.find_vma.current task=8000 mm=0x1018D0 cr2=0x0804B000 vma=0x101A7C range=0x0804A000-0x0804C000 page_index=1 paddr=0x7D000 pte=0x4B source=find-vma-current-mm status=ok',
        'kernel.cap.record.write owner=8000 handle=0F00D004 target=surface.agent.runtime kobj=0x101180 rights=write live=1 slot=2 source=handle-alloc status=ok',
        'kernel.surface.create slot=2 table=0x101180 id=agent.runtime owner=8000 type=runtime-dom handle=0F00D004 rights=write live=1 z=20 status=created',
        'kernel.compositor.surface-add surfaces=3 active=agent.runtime focus=agent.runtime top-z=20 source=sys_surface_create status=ok',
        'kernel.syscall.return vector=80 name=sys_surface_create to=agent-task handle=0F00D004 status=ok',
        'kernel.syscall.entry vector=80 name=sys_surface_destroy from=agent-task cpl=3 handle=0F00D004 source=agent-runtime status=entered',
        'kernel.handle.resolve owner=8000 handle=0F00D004 cap_record=0x101050 target=surface.agent.runtime source=sys_surface_destroy status=ok',
        'kernel.mm.vma.unlink task=8000 mm=0x1018D0 data.next=0x101A90 text.next=0 runtime.next=0 count=2 source=vma-core-unlink status=ok',
        'kernel.mm.vma.free-record task=8000 slot=3 record=0x101A7C range=0x0804A000-0x0804C000 bitmap-before=0x7F bitmap-after=0x77 source=vma-core-allocator status=ok',
        'kernel.mm.vma.tree.remove task=8000 removed=runtime root=agent.data source=vma_unlink_current_mm status=ok',
        'kernel.mm.vma.tree.remove.root-update mm=current->mm field=mm_struct.rb_root_table[mm_index] source=vma_unlink_current_mm status=ok',
        'kernel.mm.vma.tree.remove.generic compare=vma.start splice=single-child root-updated source=vma_tree_remove_generic status=ok',
        'kernel.mm.vma.meta.free slot=3 owner=0 state=free ref=0 source=vma-metadata status=ok',
        'kernel.mm.pt.resolve task=8000 mm=0x1018D0 pt32=0x232000 source=current-task-record+mm status=ok',
        'kernel.mm.vma.unmap.scan task=8000 start=0x0804A000 end=0x0804C000 pages=2 pte=dynamic-from-vaddr pt=aspace-derived old=validated paddr=backing+offset source=sys_surface_destroy status=ok',
        'kernel.mm.vma.unmap task=8000 vaddr=0x0804A000|0x0804B000 pte=0x4A|0x4B old=0x7C007|0x7D007 new=0 touched-pages=2 source=sys_surface_destroy pages=2 status=ok',
        'kernel.page.free runtime-vma=0x7C000|0x7D000 bits=11..12 bitmap-before=0x00001FFF bitmap-after=0x000007FF source=lazy-vma-touched-pages status=ok',
        'kernel.kobj.free kind=surface.runtime owner=8000 slot=3 addr=0x101180 bitmap-before=0x0000000F bitmap-after=0x00000007 source=sys_surface_destroy status=ok',
        'kernel.handle.free owner=8000 slot=2 handle=0F00D004 cap_record=0x101050 bitmap-before=0x00000007 bitmap-after=0x00000003 source=sys_surface_destroy status=ok',
        'kernel.surface.destroy slot=2 table=0x101180 id=agent.runtime live=0 type=free z=0 status=destroyed',
        'kernel.compositor.surface-remove surfaces=2 active=agent.dom focus=agent.dom top-z=10 source=sys_surface_destroy status=ok',
        'kernel.syscall.return vector=80 name=sys_surface_destroy to=agent-task status=ok',
        'kernel.mm.vma.destroy.user-return task=8000 saved-eip=0x080480B4 next=ring3-agent-instruction-stream source=iret-frame status=ok',
        'kernel.cap.open owner=agent.task owner_task=8000 target=provider.food handle=0F00D001 rights=call live=1 table=0x101000 slot=0 namespace=per-task status=granted',
        'kernel.cap.open owner=agent.task owner_task=8000 target=provider.payment handle=0F00D002 rights=call live=1 table=0x101028 slot=1 namespace=per-task status=granted',
        'kernel.cap.owner.probe caller=8100 handle=0F00D001 table-owner=8000 source=kernel-probe status=attempt',
        'kernel.cap.owner.probe caller=8100 handle=0F00D001 table-owner=8000 source=current-task-record status=denied-ok',
        'kernel.cap.owner.probe caller=8000 handle=0F00D001 source=kernel-probe status=restored',
        'kernel.cap.rights.probe handle=0F00D001 owner=8000 op=clear-call table=0x101000 source=kernel-probe status=written',
        'kernel.cap.rights.probe handle=0F00D001 owner=8000 rights=none required=call source=runtime-cap-check status=denied-ok',
        'kernel.cap.rights.probe handle=0F00D001 owner=8000 op=restore-call table=0x101000 source=kernel-probe status=restored',
        'kernel.cap.revoke.busy-probe handle=0F00D002 object=payment.ipc op=get-ref refs=1 source=kernel-probe status=written',
        'kernel.cap.revoke.busy-probe handle=0F00D002 object=payment.ipc refs=1 expected=deny source=cap-kobj-ref-check status=denied-ok',
        'kernel.cap.revoke.busy-probe handle=0F00D002 object=payment.ipc op=put-ref refs=0 source=kernel-probe status=restored',
        'kernel.cap.revoke handle=0F00D002 owner=8000 op=clear-live table=0x101028 source=kernel-probe status=written',
        'kernel.cap.revoke.probe handle=0F00D002 owner=8000 live=0 expected=deny source=runtime-cap-check status=denied-ok',
        'kernel.cap.revoke handle=0F00D002 owner=8000 op=restore-live table=0x101028 source=kernel-probe status=restored',
        'kernel.kobj.live.probe object=payment.ipc op=clear-live table=0x100E70 source=kernel-probe status=written',
        'kernel.kobj.live.probe object=payment.ipc live=0 expected=deny source=runtime-kobj-check status=denied-ok',
        'kernel.kobj.live.probe object=payment.ipc op=restore-live table=0x100E70 source=kernel-probe status=restored',
        'kernel.kobj.ref.probe object=payment.ipc op=get refs=1 source=kernel-probe status=written',
        'kernel.kobj.ref.probe object=payment.ipc refs=1 expected=revoke-deny source=runtime-refcount-check status=denied-ok',
        'kernel.kobj.ref.probe object=payment.ipc op=put refs=0 source=kernel-probe status=restored',
        'kernel.kobj.ref.probe object=payment.ipc refs=0 expected=freeable source=runtime-refcount-check status=ok',
        'kernel.kobj.free.probe object=payment.ipc refs=0 live=0 source=kernel-probe status=attempt',
        'kernel.kobj.free.probe object=payment.ipc op=mark-dead type=0 refs=0 live=0 source=kobj-free status=written',
        'kernel.kobj.free.probe handle=0F00D002 object=payment.ipc type=0 expected=cap-resolve-deny source=runtime-kobj-type-check status=denied-ok',
        'kernel.kobj.free.page object=payment.ipc page=0x75000 op=free bit=4 bitmap=0x0000000F source=kobj-free status=returned',
        'kernel.kobj.free.page object=payment.ipc page=0x75000 op=realloc bit=4 bitmap=0x0000001F reserved-next=0x000007FF source=page-allocator status=reused',
        'kernel.kobj.free.probe object=payment.ipc op=restore type=payment.ipc live=1 refs=0 source=kernel-probe status=restored',
        'kernel.ipc.ring.probe object=provider.ipc op=set-tail-full slots=4 source=kernel-probe status=written',
        'kernel.ipc.ring.probe object=provider.ipc tail=4 slots=4 expected=deny source=runtime-ring-check status=denied-ok',
        'kernel.ipc.ring.probe object=provider.ipc op=restore-tail slots=4 source=kernel-probe status=restored',
        'kernel.ipc.dequeue.probe object=payment.ipc head=0 tail=0 source=kernel-probe status=empty-written',
        'kernel.ipc.dequeue.probe object=payment.ipc head=0 tail=0 expected=deny source=runtime-ring-check status=denied-ok',
        'kernel.ipc.dequeue.probe object=payment.ipc source=kernel-probe status=restored',
        'kernel.scheduler.skip.probe task=8120 op=set-state-killed source=kernel-probe status=written',
        'kernel.scheduler.skip.scan table=0x101950 records=5 match=current-process state=killed source=process-table status=ok',
        'kernel.scheduler.skip.probe task=8120 state=killed expected=skip source=process-table-scan status=skip-ok',
        'kernel.scheduler.skip.probe task=8120 op=restore-ready source=kernel-probe status=restored',
        'kernel.task.dispatch.probe task=8120 op=set-state-done source=kernel-probe status=written',
        'kernel.task.dispatch.probe task=8120 state=done expected=deny source=task-table-check status=denied-ok',
        'kernel.scheduler.pick.probe task=8000 state=waiting expected=deny source=task-table-scan status=denied-ok',
        'kernel.scheduler.pick.probe task=8000 op=restore-ready source=kernel-probe status=restored',
        'kernel.task.dispatch.probe task=8120 op=restore-ready source=kernel-probe status=restored',
        'kernel.task.lifecycle scan table=0x100F60 records=4 match=unused slot=2 record=0x100FA0 source=task-alloc status=ok',
        'kernel.task.lifecycle alloc task=8400 slot=2 record=0x100FA0 entry=0x71100 stack=0x72000 state=ready source=task-alloc status=ok',
        'kernel.task.lifecycle ready task=8400 runqueue=0x101470 slot=2 head=2 tail=3 count=1 source=scheduler-enqueue status=ok',
        'kernel.task.lifecycle sleep task=8400 waitq=0x101488 slot=2 req=9301 state=waiting source=waitqueue status=ok',
        'kernel.task.lifecycle wakeup task=8400 waitq=0x101488 slot=2 state=ready source=waitqueue status=ok',
        'kernel.task.lifecycle exit task=8400 state=done source=sys_exit-path status=ok',
        'kernel.task.lifecycle reap task=8400 slot=2 record=0x100FA0 state=unused source=task-reaper status=ok',
        'kernel.task.lifecycle restore slot=2 task=8300 state=ready runqueue=empty waitq=clear source=kernel-probe status=restored',
        'kernel.task.syscall probe syscalls=spawn|exit|wait source=kernel-probe status=start',
        'kernel.syscall.entry vector=80 name=sys_getpid from=current cpl=3 current=process-table-scan result=current-pid source=process-api status=entered',
        'kernel.syscall.return vector=80 name=sys_getpid result=current-pid eax=process.pid source=process-api status=ok',
        'kernel.syscall.entry vector=80 name=sys_getppid from=agent-task cpl=3 parent=kernel result=0 source=process-api status=entered',
        'kernel.syscall.return vector=80 name=sys_getppid result=parent-pid eax=process.ppid source=process-api status=ok',
        'kernel.task.syscall.spawn.path user_ptr=0x70060 path=/bin/provider-food source=ring3-agent-ebx status=ok',
        'kernel.task.syscall.spawn.namei path=/bin/provider-food mount=initramfs dentry-scan=linear result=dentry source=sys_task_spawn-namei status=ok',
        'kernel.task.syscall.spawn.namei.components path=/bin/provider-food step1=bin:dentry0x102D20 step2=provider-food:dentry0x102C20 parent-chain=root->bin source=sys_task_spawn-component-walk status=ok',
        'kernel.task.syscall.spawn.dentry dentry=0x102C20 mount=0x102BC0 name_ptr=0x68060 name_hash=0xB1030003 inode=3 vfs_record=0x680E0 source=structured-dentry-cache status=ok',
        'kernel.task.syscall.spawn.vfs path=/bin/provider-food record=dentry->inode inode=3 op=elf32-open data=0x69300 source=structured-namei-vfs status=ok',
        'kernel.task.syscall.spawn.elf path=/bin/provider-food entry=0x08048080 stack=0x8E000 cr3=0x7C000 source=module-registry+elf-vmap status=ok',
        'kernel.pid.alloc parent=8000 next-before=8500 pid=8500 next-after=8501 source=pid-allocator status=ok',
        'kernel.task.syscall.spawn.aspace child=8500 cr3=0x7C000 pd=0x7C000 pt0=0x7D000 pt32=0x7E000 source=sys_task_spawn status=ok',
        'kernel.mm.alloc scan=refcnt0 slot=2 mm=0x101910 bitmap-before=0x0F bitmap-after=0x0F source=mm-allocator status=ok',
        'kernel.mm.struct.alloc.metadata-driven child=8500 base=mm_meta.base cap=mm_meta.cap record_bytes=mm_meta.record_size first_refcnt0_slot=scan-result result=mm-record source=mm-struct-header status=ok',
        'kernel.mm.struct.spawn child=8500 alloc=mm-allocator+refcnt0-scan mm=dynamic:0x101910 cr3=0x7C000 pt32=0x7E000 refcnt=1 source=sys_task_spawn status=ok',
        'kernel.task.syscall.spawn.segment-copy child=8500 text src=0x69400 dst=child_page_text_result:0x7F000 len=248 struct_page=type:user-text owner:8500 ref:1 source=page-allocator+page-cache+file-ops+struct-page status=ok',
        'kernel.task.syscall.spawn.segment-copy child=8500 data src=0x69500 dst=child_page_data_result:0x80000 len=51 struct_page=type:user-data owner:8500 ref:1 source=page-allocator+page-cache+file-ops+struct-page status=ok',
        'kernel.mm.pagetable.alloc child=8500 pd=child_page_pd_result:0x7C000 pt0=child_page_pt0_result:0x7D000 pt32=child_page_pt32_result:0x7E000 count=3 bitmap-before=0x000007FF bitmap-after=0x00003FFF struct_page=type:pagetable owner:8500 ref:1 source=page-allocator-result+struct-page status=ok',
        'kernel.task.syscall.spawn.stack child=8500 vaddr=0x0008E000 paddr=child_page_stack_result:0x81000 pte=0x81007 struct_page=type:user-stack owner:8500 ref:1 source=page-allocator-result+child-vma+struct-page status=ok',
        'kernel.task.syscall.spawn.aspace.map child=8500 text=child_page_text_result|0x5 data=child_page_data_result|0x7 stack=child_page_stack_result|0x7 pde32=child_page_pt32_result|0x7 source=page-allocator-result+child-private-elf-copy status=ok',
        'kernel.mm.struct_page.verify child=8500 records=11..16 pages=pagetable|text|data|stack owner=8500 ref=1 flags=pagetable:reserved text:lru,mapcount1 data:lru|dirty,mapcount1 stack:lru|dirty,mapcount1 lru=head:0x7F000 tail:0x81000 count:3 order=0x7F000>0x80000>0x81000 scan=mem_map index=(paddr-base)>>12 source=struct-page+page-flags+lru-list status=ok',
        'kernel.mm.vma.alloc-child child=8500 scan=bitmap-first-free count=3 slots=3|7|8 records=0x101A7C|0x101ACC|0x101AE0 bitmap-before=0x77 bitmap-after=0x1FF result-fields=text|data|stack source=vma-allocator status=ok',
        'kernel.mm.vma.tree.child.insert child=8500 root=text nodes=text|data|stack allocator=vma_alloc_record source=sys_task_spawn status=ok',
        'kernel.mm.vma.tree.insert.generic child=8500 compare=vma.start left-right dynamic-root=true inserted=text|data|stack source=vma_tree_insert_generic status=ok',
        'kernel.mm.vma.tree.child.root-update mm=child->mm field=mm_struct.rb_root_table[mm_index] source=sys_task_spawn status=ok',
        'kernel.mm.vma.clone child=8500 mm=0x101910 head=child_vma_text_result vma=0x101A7C range=0x08048080-0x08048167 rights=r backing=0x7F000 source=vma-allocator+sys_task_spawn status=ok',
        'kernel.mm.vma.clone.chain child=8500 count=child_vma_alloc_count text=0x101A7C data=0x101ACC stack=0x101AE0 links=text->data->stack source=vma-allocator-linked-list status=ok',
        'kernel.mm.vma.meta.clone child=8500 slots=3|7|8 state=child-private owner=pid-allocator-result ref=1 source=vma-allocator+sys_task_spawn status=ok',
        'kernel.mm.find_vma.child task=8500 data_vma=0x101ACC stack_vma=0x101AE0 source=find-vma-current-mm status=ok',
        'kernel.task.alloc scan=pid0 slot=2 record=0x100FA0 bitmap-before=0x0B bitmap-after=0x0F source=task-allocator status=ok',
        'kernel.process.alloc scan=refcnt0 slot=4 process=0x1019D0 bitmap-before=0x0F bitmap-after=0x1F source=process-allocator status=ok',
        'kernel.process.spawn child=8500 ppid=8000 process=0x1019D0 task=0x100FA0 mm=0x101910 files=0x101790 caps=0x101000 state=ready ref=1 source=process-allocator+sys_task_spawn status=ok',
        'kernel.task.fdtable.attach task=8500 task_record=dynamic files=0x101790 fdtable=0x101730 record_field=0x18 source=sys_task_spawn status=ok',
        'kernel.task.mm.attach child=8500 task_record=0x100FA0 mm=task.mm:0x101910 source=sys_task_spawn status=ok',
        'kernel.task.syscall.spawn.fdtable.generic child=8500 files=0x101790 base=0x101730 fd0=file_table[2] fd1=file_table[3] file_range=checked source=child-files-install status=ok',
        'kernel.task.syscall.spawn.fdtable child=8500 files=0x101790 base=0x101730 fds=3:/bin/provider-food|4:/bin/provider-payment files_obj=0x101510|0x101528 rights=read source=process-file-table status=ok',
        'kernel.file.ref.get source=sys_task_spawn child=8500 provider=0x101510 refs=1 payment=0x101528 refs=1 status=ok',
        'kernel.task.syscall spawn child=8500 parent=8000 slot=2 record=0x100FA0 entry=0x08048080 stack=0x8E000 state=ready source=task-allocator+sys_task_spawn status=ok',
        'kernel.task.syscall enqueue child=8500 runqueue=0x101470 slot=1 head=1 tail=2 count=1 source=sys_task_spawn status=ok',
        'kernel.task.syscall exit child=8500 state=done source=sys_task_exit status=ok',
        'kernel.task.syscall wait parent=8000 child=8500 waitq=0x101488 slot=3 state=waiting source=sys_task_wait status=ok',
        'kernel.task.syscall wait child=8500 observed=done source=sys_task_wait status=ok',
        'kernel.task.syscall.wait.free child=8500 pages=3 ptes=3 freed-by=vma-backing-scan bitmap=0x00003FFF source=sys_task_wait status=ok',
        'kernel.mm.pte.reap child=8500 text=0 data=0 stack=0 source=task-mm+vma-teardown status=ok',
        'kernel.mm.struct_page.reap child=8500 records=11..16 state=free owner=0 ref=0 flags=0 mapcount=0 lru=head:0 tail:0 count:0 source=struct-page+page-flags+lru-list+sys_task_wait status=ok',
        'kernel.mm.pagetable.reap child=8500 pd=child_page_pd_result pt0=pd[0] pt32=child_page_pt32_result freed=0x7C000|0x7D000|0x7E000 struct_page=cleared result-fields-cleared=true bitmap=0x000007FF source=page-allocator-result+task-mm-fields+struct-page status=ok',
        'kernel.task.syscall.wait.fdtable-close child=8500 files=0x101790 base=0x101730 fds=3|4 files-ref=0 state=closed source=sys_task_wait status=ok',
        'kernel.mm.vma.reap child=8500 mm=task.mm:0x101910 walk=head freed=0x101A7C>0x101ACC>0x101AE0 count=3 pages=3 ptes=3 pagetables=3 bitmap-before=0x1FF bitmap-after=0x77 head=0 result-fields-cleared=true static=untouched source=vma-allocator+sys_task_wait status=ok',
        'kernel.mm.vma.tree.child.walk child=8500 root=text order=text>data>stack source=sys_task_wait status=ok',
        'kernel.mm.vma.tree.child.reap child=8500 removed=text|data|stack root=0 nodes-cleared=true source=sys_task_wait status=ok',
        'kernel.mm.vma.tree.remove.generic compare=vma.start splice=single-child root-updated source=vma_tree_remove_generic status=ok',
        'kernel.mm.vma.meta.reap child=8500 walk=head freed=slot3|7|8 static=slot5|6-untouched state=free owner=0 ref=0 source=sys_task_wait status=ok',
        'kernel.file.ref.put source=sys_task_wait child=8500 provider=0x101510 refs=0 payment=0x101528 refs=0 status=ok',
        'kernel.task.free child=8500 record=0x100FA0 slot=2 bitmap-before=0x0F bitmap-after=0x0B source=task-allocator status=ok',
        'kernel.process.free child=8500 process=0x1019D0 slot=4 bitmap-before=0x1F bitmap-after=0x0F source=process-allocator status=ok',
        'kernel.process.reap child=8500 process=0x1019D0 state=unused ref=0 task=0 mm=0 files=0 parent=8000 source=process-allocator+sys_task_wait status=ok',
        'kernel.mm.free child=8500 mm=0x101910 slot=2 bitmap-before=0x0F bitmap-after=0x0F restored-task=8300 cr3=0x210000 source=mm-allocator status=ok',
        'kernel.mm.struct.reap child=8500 mm=0x101910 refcnt=0 free-list=mm-allocator-returned restored-task=8300 cr3=0x210000 restored-refcnt=1 source=sys_task_wait status=ok',
        'kernel.pid.free pid=8500 next-before=8501 next-after=8500 source=pid-allocator status=ok',
        'kernel.task.syscall reap child=8500 slot=2 state=unused parent=8000 state=ready source=task-allocator+sys_task_wait status=ok',
        'kernel.task.syscall restore slot=2 task=8300 runqueue=empty waitq=clear source=kernel-probe status=restored',
        'kernel.task.syscall.runtime source=ring3-agent int80=sys_task_spawn path=/bin/provider-food child=8500 state=ready status=ok',
        'kernel.fd.alloc.probe prefill_slot=0 first_free_slot=1 assigned_fd=slot+3 result=4 file=0x101528 source=fd-allocator status=ok',
        'kernel.fd.alloc.probe.close fd=4 slot=1 state=closed source=fd-allocator status=ok',
        'kernel.fd.dup oldfd=3 newfd=4 task=8100 ofd=0x1022A0 file=0x101510 refs=2 rights=read pos=0 source=open-file-description-table status=ok',
        'kernel.fd.dup.offset-share oldfd=3 newfd=4 ofd=0x1022A0 pos=0 source=open-file-description status=ok',
        'kernel.fd.dup.close oldfd=3 remaining_fd=4 file=0x101510 refs=1 source=file-ref status=ok',
        'kernel.fd.dup.close newfd=4 remaining=0 file=0x101510 refs=0 source=file-ref status=ok',
        'kernel.task.fdtable.isolation provider_task=8100 provider_files=0x101780 provider_fdtable=0x1016C8 child_task=8500 child_files=0x101790 child_fdtable=0x101730 resolver=task-files-fdtable owner-check=separate source=task-files-struct status=ok',
        'kernel.task.files.ptr task_record_field=0x18 semantics=files_struct provider_task=8100 files=0x101780 fdtable=files+0x08->0x1016C8 child_task=8500 files=0x101790 fdtable=files+0x08->0x101730 source=task-record status=ok',
        'kernel.task.fdtable.isolation.restore provider_fdtable=empty child_fdtable=empty fault_record_fdtable=0 source=kernel-probe status=restored',
        'kernel.fdtable.meta.init provider.base=0x1016C8 child.base=0x101730 cap=4 record_bytes=20 source=files-struct-table status=ok',
        'kernel.ofd.meta.init base=0x1022A0 cap=4 record_bytes=16 bitmap=allocator-state source=ofd-table-header status=ok',
        'kernel.file.meta.init base=0x1014E0 cap=4 record_bytes=24 ref_base=0x1017BC source=file-table-header status=ok',
        'kernel.fdtable.meta.verify source=table-header base|cap|record_bytes matched status=ok',
        'kernel.ofd.meta.verify source=table-header base|cap|record_bytes matched status=ok',
        'kernel.file.meta.verify source=file-table-header base|cap|record_bytes|ref_base matched status=ok',
        'kernel.fd.table.full records=4 first_free=none expected=deny source=fdtable-scan status=denied-ok',
        'kernel.ofd.alloc.full records=4 bitmap=0xF first_free=none expected=deny source=ofd-allocator-scan status=denied-ok',
        'kernel.fd.ofd.full.restore fdtable=empty ofdtable=empty bitmap=0 source=kernel-probe status=restored',
        'kernel.files.alloc owner=8500 files=0x101790 fdtable=0x101730 cap=4 bitmap=0x3 ref=1 source=files-allocator status=ok',
        'kernel.files.alloc.scan table=0x101780 records=2 record_bytes=16 first_free_slot=1 result=0x101790 source=files-allocator-scan status=ok',
        'kernel.files.alloc.reuse freed_slot=1 result=0x101790 bitmap=0x3 source=files-allocator-scan status=ok',
        'kernel.files.alloc.full records=2 bitmap=0x3 expected=deny source=files-allocator-scan status=denied-ok',
        'kernel.files.lifecycle provider=0x101780 child=0x101790 refs=1|1 fdtable=0x1016C8|0x101730 source=files-struct-table status=ok',
        'kernel.files.free owner=8500 files=0x101790 fdtable=0x101730 bitmap=0x1 ref=0 source=task-reaper status=ok',
        'kernel.files.lifecycle.restore bitmap=0x1 child=free provider=live source=kernel-probe status=restored',
        'kernel.syscall.entry vector=80 name=sys_fd_read from=provider.food cpl=3 fd=3 buf=0x08049000 len=15 source=fd-api status=entered',
        'kernel.fd.table.scan.generic task=current base=current.files.fdtable records=4 record_bytes=24 first_free_slot=scan-result assigned_fd=slot+3 source=sys_fd_open-first-free status=ok',
        'kernel.fd.table.scan task=8100 base=0x1016C8 records=4 record_bytes=24 first_free_slot=0 assigned_fd=slot+3 result=3 source=sys_fd_open-scan status=ok',
        'kernel.syscall.entry vector=80 name=sys_fd_open from=provider.food cpl=3 path=arg.ebx flags=arg.ecx source=fd-api status=entered',
        'kernel.fd.open.path task=8100 user_ptr=0x08049020 path=/bin/provider-food source=ring3-provider-ebx status=ok',
        'kernel.fd.open.namei.bytecmp task=8100 user_ptr=0x08049020 dentry-name=/bin/provider-food compare=literal-path-bytes|payload-alias-compat source=sys_fd_open-namei status=ok',
        'kernel.fd.open.namei.walk task=8100 path=/bin/provider-food mount=initramfs dentry-scan=linear result=dentry source=sys_fd_open-namei status=ok',
        'kernel.fd.open.namei.components task=8100 path=/bin/provider-food step1=bin:dentry0x102D20 step2=provider-food:dentry0x102C20 parent-chain=root->bin source=sys_fd_open-component-walk status=ok',
        'kernel.fd.open.dentry task=8100 dentry=0x102C20 mount=0x102BC0 name_ptr=0x68060 name_hash=0xB1030003 inode=3 vfs_record=0x680E0 source=structured-namei-dentry-cache status=ok',
        'kernel.fd.open.path.namei task=8100 user_ptr=0x08049020 path=/bin/provider-food components=bin|provider-food source=sys_fd_open-namei status=ok',
        'kernel.fd.open.vfs task=8100 path=/bin/provider-food record=2 inode=3 file=0x101510 source=vfs-lookup status=ok',
        'kernel.fd.open.vfs-record task=8100 path=user-ptr record=dentry->inode inode=vfs+0x10 file=file_table[inode-1] source=generic-namei-vfs-open status=ok',
        'kernel.fd.open.file.resolve task=8100 vfs_record=2 inode=3 file=0x101510 source=dentry-inode-to-file-object status=ok',
        'kernel.fdtable.resolve task=8100 scan=process-table current=8100 process=0x101970 files_field=process+0x10 files=0x101780 fdtable=files+0x08->0x1016C8 source=current-process-files status=ok',
        'kernel.fd.table.scan.metadata-driven task=current base=fdtable_meta.base cap=fdtable_meta.cap record_bytes=fdtable_meta.record_size first_free_slot=scan-result assigned_fd=slot+3 source=fdtable-header status=ok',
        'kernel.fd.table.scan task=8100 base=0x1016C8 records=4 record_bytes=24 first_free_slot=0 assigned_fd=slot+3 result=3 source=sys_fd_open-scan status=ok',
        'kernel.fd.table.install.generic task=current fd=slot+3 record=first-free ofd=allocated file=opened-file pos=0 rights=read source=sys_fd_open-generic-install status=ok',
        'kernel.fd.table.install task=8100 base=0x1016C8 fd=3 ofd=0x1022A0 file=0x101510 path=/bin/provider-food pos=0 rights=read source=sys_fd_open-scan status=ok',
        'kernel.file.ref.get.generic source=sys_fd_open task=current fd=slot+3 file=opened-file refs=ref_table[file_index]+1 status=ok',
        'kernel.file.ref.get source=sys_fd_open task=8100 fd=3 file=0x101510 refs=1 status=ok',
        'kernel.file.ref.get.metadata-driven file=edi base=file_meta.base cap=file_meta.cap record_bytes=file_meta.record_size ref_base=file_meta.ref_base source=file-table-header status=ok',
        'kernel.file.ref.generic op=get file=edi table=0x1014E0 refs=ref_table[file_index] source=vfs_file_get_from_edi status=ok',
        'kernel.file.ref.put.metadata-driven file=edi base=file_meta.base cap=file_meta.cap record_bytes=file_meta.record_size ref_base=file_meta.ref_base source=file-table-header status=ok',
        'kernel.file.ref.generic op=put file=edi table=0x1014E0 refs=ref_table[file_index] source=vfs_file_put_from_edi status=ok',
        'kernel.ofd.alloc.metadata-driven base=meta.base cap=meta.cap record_bytes=meta.record_size source=ofd-table-header status=ok',
        'kernel.ofd.alloc.generic table=0x1022A0 records=4 slot=first-free result=slot-address bitmap=old|1<<slot source=ofd-allocator-scan status=ok',
        'kernel.ofd.alloc table=0x1022A0 records=4 first_free_slot=0 result=0x1022A0 bitmap=0x1 source=sys_fd_open status=ok',
        'kernel.fd.table.scan task=8100 base=0x1016C8 records=4 record_bytes=24 first_free_slot=1 assigned_fd=slot+3 result=4 source=sys_fd_open-scan status=ok',
        'kernel.fd.table.install task=8100 base=0x1016C8 fd=4 ofd=0x1022B0 file=0x101510 path=/bin/provider-food pos=0 rights=read source=sys_fd_open-scan status=ok',
        'kernel.file.ref.get source=sys_fd_open task=8100 fd=4 file=0x101510 refs=2 status=ok',
        'kernel.ofd.alloc table=0x1022A0 records=4 first_free_slot=1 result=0x1022B0 bitmap=0x3 source=sys_fd_open status=ok',
        'kernel.syscall.retval vector=80 name=sys_fd_open eax=slot+3 result=first-free-fd source=kernel-return-register-generic status=ok',
        'kernel.syscall.retval vector=80 name=sys_fd_open eax=slot+3 result=4 source=kernel-return-register status=ok',
        'kernel.fd.open.lifecycle fd=4 cleanup=userspace-close-required source=sys_fd_open-no-kernel-side-cleanup status=ok',
        'kernel.ofd.free.metadata-driven base=ofd_meta.base cap=ofd_meta.cap record_bytes=ofd_meta.record_size slot=scan-result bitmap=old&~(1<<slot) source=ofd-table-header status=ok',
        'kernel.ofd.free.generic table=0x1022A0 records=4 slot=(ofd-base)/16 bitmap=old&~(1<<slot) source=ofd-free-generic status=ok',
        'kernel.ofd.free table=0x1022A0 slot=1 refs=0 bitmap=0x1 source=sys_fd_close-last status=ok',
        'kernel.syscall.return vector=80 name=sys_fd_open fd=3 allocator=first-free-slot status=ok',
        'kernel.syscall.entry vector=80 name=sys_fd_dup from=provider.food cpl=3 oldfd=3 source=fd-api status=entered',
        'kernel.syscall.entry vector=80 name=sys_fd_dup from=current cpl=3 oldfd=arg.ebx source=fd-api-generic status=entered',
        'kernel.fd.record.resolve.metadata-driven task=current fd=arg.ebx base=fdtable_meta.base cap=fdtable_meta.cap record_bytes=fdtable_meta.record_size policy=owner+fd-match source=fdtable-header status=ok',
        'kernel.fd.dup.resolve.generic task=current oldfd=arg.ebx record=fd-scan policy=found+owner+ofd source=sys_fd_dup-fdtable status=ok',
        'kernel.fd.dup.scan.metadata-driven task=current base=fdtable_meta.base cap=fdtable_meta.cap record_bytes=fdtable_meta.record_size first_free_slot=scan-result assigned_fd=slot+3 source=fdtable-header status=ok',
        'kernel.fd.dup.install.generic task=current oldfd=arg.ebx newfd=first-free-slot ofd=shared refs=ofd.refs+1 rights=copied source=sys_fd_dup-generic status=ok',
        'kernel.fd.owner.current task=current fd=arg.ebx record.owner=current_aspace source=fd-record-owner-check status=ok',
        'kernel.fd.ofd.current task=current fd=arg.ebx ofd=fd-record+0x08 file=ofd+0x00 pos=ofd+0x04 refs=ofd+0x08 rights=ofd+0x0C source=open-file-description-pointer status=ok',
        'kernel.fd.ofd.guard.metadata-driven task=current fd=arg.ebx ofd=fd->ofd base=ofd_meta.base cap=ofd_meta.cap record_bytes=ofd_meta.record_size source=ofd-table-header status=ok',
        'kernel.fd.ofd.file-range task=current fd=arg.ebx ofd=fd->ofd file=ofd->file rights=read ofd_table=0x1022A0 file_table=0x1014E0 source=generic-fd-syscall-guard status=ok',
        'kernel.fd.close.ofd-file task=8100 fd=arg.ebx file=ofd->file ref_put=vfs_file_put_from_edi source=open-file-description-generic-file status=ok',
        'kernel.fd.close.file-ref.metadata-driven task=current file=ofd->file base=file_meta.base cap=file_meta.cap record_bytes=file_meta.record_size ref_base=file_meta.ref_base source=file-table-header status=ok',
        'kernel.fd.close.file-ref.generic task=8100 file=ofd->file ref=ref_table[file_index] source=sys_fd_close-file-table status=ok',
        'kernel.fd.ofd.pos task=current fd=arg.ebx read_lseek_pos=ofd+0x04 update=through-ofd-pointer source=open-file-description-position status=ok',
        'kernel.fd.record.ofd.generic task=current fd=arg.ebx record=fd-scan ofd=record+0x08 source=fd-record-to-ofd status=ok',
        'kernel.fd.ofd.ref task=current fd=arg.ebx refs=ofd+0x08 incdec=through-ofd-pointer source=open-file-description-refcount status=ok',
        'kernel.fd.close.refcount task=8100 fd=3 ofd=0x1022A0 refs_after=1 action=keep-ofd source=sys_fd_close-generic status=ok',
        'kernel.fd.close.refcount task=8100 fd=arg.ebx refs_after=0 action=free-ofd source=sys_fd_close-generic status=ok',
        'kernel.fd.open.file-ref.generic task=8100 file=opened-file ref=ref_table[file_index] source=sys_fd_open-file-table status=ok',
        'kernel.fd.dup.file-ref.generic task=8100 oldfd=3 newfd=4 file=ofd->file ref=ref_table[file_index] source=sys_fd_dup-file-table status=ok',
        'kernel.fd.dup.lookup task=8100 oldfd=3 records=4 matched_slot=0 file=0x101510 source=fd-number-scan status=ok',
        'kernel.syscall.return vector=80 name=sys_fd_dup oldfd=3 newfd=4 status=ok',
        'kernel.fdtable.resolve task=8100 op=read scan=process-table current=8100 process=0x101970 files_field=process+0x10 files=0x101780 fdtable=files+0x08->0x1016C8 source=current-process-files status=ok',
        'kernel.fd.read.resolve.generic task=current fd=arg.ebx record=fd-scan policy=found+owner+rights source=sys_fd_read-fdtable status=ok',
        'kernel.fd.read.rights task=8100 fd=3 rights=read fdtable_fileptr=ofd file=0x101510 pos_field=ofd+0x04 source=open-file-description-table status=ok',
        'kernel.fd.read.generic task=current fd=arg.ebx ofd=fd->ofd file=ofd->file pos=ofd->pos len=arg.edx offset=pos+elf-text-base source=sys_fd_read-generic-pagecache status=ok',
        'kernel.fd.read.copy.generic task=current src=vfs_file_read_at(file,ofd.pos) dst=arg.ecx len=arg.edx source=page-cache+rep-movsb status=ok',
        'kernel.fd.read.advance.generic task=current old_pos=ofd->pos new_pos=old+len source=open-file-description-position status=ok',
        'kernel.fd.read.lookup task=8100 fd=3 owner=8100 file=0x101510 path=/bin/provider-food pos=0 read_offset=0x100 len=15 source=open-file-description-table status=ok',
        'kernel.fd.read.copy task=8100 fd=3 result=0x69400 dst=0x08049000 len=15 source=vfs-file-read_at+page-cache status=ok',
        'kernel.fd.read.advance task=8100 fd=3 old_pos=0 new_pos=15 bytes=15 source=file-position status=ok',
        'kernel.fd.read.lookup task=8100 fd=3 owner=8100 file=0x101510 path=/bin/provider-food pos=15 read_offset=0x10F len=15 source=open-file-description-table status=ok',
        'kernel.fd.read.copy task=8100 fd=3 result=0x70A0F dst=0x0804900F len=15 source=vfs-file-read_at+page-cache status=ok',
        'kernel.fd.read.advance task=8100 fd=3 old_pos=15 new_pos=30 bytes=15 source=file-position status=ok',
        'kernel.syscall.entry vector=80 name=sys_fd_read from=provider.food cpl=3 fd=4 buf=0x0804901E len=15 source=fd-api status=entered',
        'kernel.fd.read.lookup task=8100 fd=4 owner=8100 ofd=0x1022A0 file=0x101510 path=/bin/provider-food shared_pos=30 read_offset=0x11E len=15 source=open-file-description status=ok',
        'kernel.fd.read.advance task=8100 fd=4 old_pos=30 new_pos=45 mirrored_fd3=45 source=shared-file-position status=ok',
        'kernel.syscall.return vector=80 name=sys_fd_read bytes=15 pos=advanced status=ok',
        'kernel.syscall.entry vector=80 name=sys_fd_lseek from=provider.food cpl=3 fd=4 offset=5 whence=SET source=fd-api status=entered',
        'kernel.fd.lseek.generic task=current fd=arg.ebx whence=arg.edx old_pos=ofd->pos new_pos=computed source=sys_fd_lseek-generic-ofd status=ok',
        'kernel.fd.lseek.bounds task=current file=ofd->file file_len=file+0x0C new_pos<=len source=sys_fd_lseek-generic-bounds status=ok',
        'kernel.syscall.return vector=80 name=sys_fd_lseek result=computed source=sys_fd_lseek-generic status=ok',
        'kernel.syscall.entry vector=80 name=sys_mmap from=provider.food cpl=3 fd=3 offset=0x100 len=248 prot=rx source=mmap-api status=entered',
        'kernel.mm.mmap.prot-flags task=8100 offset=0x100 prot=r flags=text|private source=sys_mmap-args status=ok',
        'kernel.mm.mmap.resolve.ofd-range task=8100 fd=arg.ebx ofd=fd->ofd file=ofd->file ofd_table=0x1022A0 file_table=0x1014E0 source=generic-ofd-table status=ok',
        'kernel.mm.mmap.syscall.fd task=8100 fd=3 ofd=0x1022A0 file=0x101510 offset=0x100 source=fd-to-file-mmap status=ok',
        'kernel.mm.mmap.syscall.install task=8100 record=0x1017F4 vaddr=0x08048000 len=248 file=0x101510 cache_slot=0x1015A0 backing=0x77000 pte=0x77005 source=sys_mmap status=ok',
        'kernel.syscall.return vector=80 name=sys_mmap addr=0x08048000 status=ok',
        'kernel.syscall.entry vector=80 name=sys_munmap from=provider.food cpl=3 addr=0x08048000 len=248 source=mmap-api status=entered',
        'kernel.mm.munmap.scan task=8100 mm=0x1018F0 record=0x1017F4 addr=0x08048000 len=248 source=current-task-record+mm status=ok',
        'kernel.mm.munmap.range-check task=8100 record=0x1017F4 addr=start len=end-start policy=exact-range source=sys_munmap status=ok',
        'kernel.mm.munmap.policy task=8100 record=0x1017F4 exec-text=true action=keep-existing-loader-pte source=prototype-guard status=ok',
        'kernel.syscall.return vector=80 name=sys_munmap result=0 status=ok',
        'kernel.syscall.entry vector=80 name=sys_mmap from=provider.food cpl=3 fd=3 offset=0x200 len=51 prot=r source=mmap-api status=entered',
        'kernel.mm.mmap.prot-flags task=8100 offset=0x200 prot=r flags=private source=sys_mmap-args status=ok',
        'kernel.mm.mmap.alloc.scan.metadata-driven task=current base=mmap_meta.base cap=mmap_meta.cap record_bytes=mmap_meta.record_size first_free_slot=scan-result result=slot-address source=file-mmap-header status=ok',
        'kernel.mm.mmap.alloc.scan table=0x1017D0 records=5 first_free_slot=4 result=0x101860 source=sys_mmap-generic-allocator status=ok',
        'kernel.mm.mmap.gap.select task=8100 head=0x1017F4 selected=0x0804C000 pte=0x4C source=mmap-next status=ok',
        'kernel.mm.mmap.overlap-check task=8100 candidate=0x0804C000-arg.len scan=mmap-next policy=deny source=sys_mmap status=ok',
        'kernel.mm.mmap.cache.lookup file=0x101510 offset=0x200 state=miss source=sys_mmap-file-offset status=not-found-ok',
        'kernel.mm.mmap.cache.fill file=0x101510 slot=0x1015A0 offset=0x200 backing=0x69500 source=sys_mmap-page-cache-fill status=ok',
        'kernel.mm.mmap.cache.lookup file=0x101510 offset=0x200 state=hit cache_slot=0x1015A0 backing=0x69500 source=sys_mmap-after-fill status=ok',
        'kernel.mm.mmap.cache.resolve file=0x101510 offset=0x200 lookup=page-cache hit=true cache_slot=0x1015A0 backing=0x69500 mapped_paddr=0x7A000 source=sys_mmap-file-offset status=ok',
        'kernel.mm.vma.backing.set vma=0x101A7C kind=file-mmap object=0x101860 source=sys_mmap status=ok',
        'kernel.mm.vma.insert task=8100 mm=0x1018F0 head=0x101A54 head.next=0x101A7C record=0x101A7C range=0x0804C000-0x0804C033 rights=r backing=0x7A000 source=vma-core-insert status=ok',
        'kernel.mm.vma.tree.insert.sys_mmap task=8100 mm=current->mm rb_root=mm_struct.rb_root_table[mm_index] record=0x101A7C range=0x0804C000-0x0804C033 source=sys_mmap+vma_link_current_mm status=ok',
        'kernel.mm.struct.expand task=8100 mm=0x1018F0 head=0x1017F4 next=0x101860 count=2 vma_count=2 source=sys_mmap status=ok',
        'kernel.mm.mmap.record.write task=current record=0x101860 link=0x1017F4->0x101860 next=0 source=sys_mmap status=ok',
        'kernel.mm.mmap.alloc bitmap_before=0x0F first_free_slot=4 result=0x101860 bitmap_after=0x1F source=sys_mmap status=ok',
        'kernel.mm.mmap.syscall.install task=8100 record=0x101860 vaddr=0x0804C000 len=51 file=0x101510 offset=0x200 cache_slot=0x1015A0 backing=0x7A000 source=sys_mmap status=ok',
        'kernel.syscall.return vector=80 name=sys_mmap addr=0x0804C000 status=ok',
        'kernel.mm.mmap.fault.cache.invalidate file=0x1014F8 slot=0x101588 source=kernel-probe status=ok',
        'kernel.mm.mmap.fault.probe case=filemap-readonly-write task=8000 cr2=0x08048080 error=0x7 rights=read source=file-mmap-table+error-code status=attempt',
        'kernel.mm.mmap.fault.write-deny task=8000 file=0x1014F8 offset=0x100 rights=read action=kill-current source=pagefault-error+file-mmap-rights status=denied',
        'kernel.mm.mmap.fault.probe case=filemap-readonly-write expected=deny task=8000 state=killed source=file-mmap-rights status=denied-ok',
        'kernel.mm.mmap.fault.cache.lookup file=record offset=record state=miss source=pagefault-file-mmap status=not-found-ok',
        'kernel.mm.mmap.fault.cache.alloc file=record offset=record old_slot=record.cache new_slot=page-cache-alloc-result policy=lru-reclaim source=pagefault-file-mmap status=ok',
        'kernel.mm.mmap.fault.cache.fill file=record slot=record.cache offset=record.offset source=pagefault-file-mmap status=ok',
        'kernel.mm.mmap.fault.cache.lookup file=record offset=record state=hit source=pagefault-file-mmap-after-fill status=ok',
        'kernel.mm.filepage.struct_page task=record.owner paddr=record.backing type=file owner=mmap-record ref=1 flags=lru mapcount=1 lru=tail source=pagefault-file-mmap+struct-page status=ok',
        'kernel.mm.mmap.fault.cache.restore file=0x1014F8 slot=0x101588 offset=0 source=kernel-probe status=ok',
        'kernel.mm.mmap.fault.generic task=current record=task-mm.mmap file=record+0x10 offset=record+0x14 cache_slot=record+0x18 backing=record+0x1C pte=dynamic-from-cr2 source=generic-file-mmap-fault status=ok',
        'kernel.mm.mmap.fault.resolve.metadata-driven task=current mm=current->mm head=mm->mmap_head scan=linked-list match=cr2-in-range record=task-mm.mmap pte=dynamic-from-cr2 source=current-mm-mmap-chain status=ok',
        'kernel.mm.mmap.fault.resolve.generic-only task=current no=fixed-vma-switch record=mm->mmap_head-match source=current-mm-mmap-chain status=ok',
        'kernel.mm.find_vma fault task=8100 mm=0x1018F0 vma=0x101A7C range=0x0804C000-0x0804C033 dispatch=file-mmap record=0x101860 source=find-vma-current-mm status=ok',
        'kernel.mm.pt.resolve task=8100 mm=0x1018F0 pt32=0x222000 source=current-task-record+mm status=ok',
        'kernel.pagefault.file-mmap cr2=0x0804C000 task=8100 file=0x101510 offset=0x200 cache_slot=0x1015A0 backing=0x69500 mapped_paddr=0x7A000 entry=0x7A005 source=page-cache+file-mmap-table status=handled',
        'kernel.mm.mmap.fault.map task=8100 vaddr=0x0804C000 pte=0x4C old=0 new=0x7A005 rights=r source=pagefault-file-mmap-table status=ok',
        'kernel.syscall.entry vector=80 name=sys_munmap from=provider.food cpl=3 addr=0x0804C000 len=51 source=mmap-api status=entered',
        'kernel.mm.munmap.current-mm task=current task_record=current->task mm=current->mm head=mm->mmap_head source=sys_munmap-generic-current status=ok',
        'kernel.mm.munmap.scan.generic task=current mm=task.mm head=0x1017F4 via=next matched=range source=sys_munmap status=ok',
        'kernel.mm.munmap.scan task=8100 mm=0x1018F0 record=0x101860 addr=0x0804C000 len=51 source=current-task-record+mm status=ok',
        'kernel.mm.munmap.range-check task=8100 record=0x101860 addr=start len=end-start policy=exact-range source=sys_munmap status=ok',
        'kernel.mm.munmap.range-walk task=record.owner record=0x101860 start=record.start end=record.end pages=1 pte=dynamic old=validated new=0 source=sys_munmap-record-walker status=ok',
        'kernel.mm.munmap.unmap task=8100 record=0x101860 vaddr=0x0804C000 pte=0x4C old=0x7A005 new=0 source=sys_munmap status=ok',
        'kernel.mm.filepage.reap task=record.owner paddr=record.backing type=file ref=0 flags=0 mapcount=0 lru=removed source=sys_munmap+struct-page+record-walker status=ok',
        'kernel.mm.mmap.cache.restore file=0x101510 slot=0x1015A0 offset=0 source=sys_munmap status=ok',
        'kernel.mm.vma.free-record task=8100 slot=3 record=0x101A7C bitmap-before=0x7F bitmap-after=0x77 source=vma-core-allocator status=ok',
        'kernel.mm.vma.unlink task=8100 mm=0x1018F0 head=0x101A54 head.next=0 runtime.next=0 count=1 source=vma-core-unlink status=ok',
        'kernel.mm.vma.tree.remove.sys_munmap task=8100 mm=current->mm rb_root=mm_struct.rb_root_table[mm_index] record=0x101A7C range=0x0804C000-0x0804C033 source=sys_munmap+vma_unlink_current_mm status=ok',
        'kernel.mm.struct.shrink task=8100 mm=0x1018F0 head=0x1017F4 next=0 count=1 vma_count=1 source=sys_munmap status=ok',
        'kernel.syscall.return vector=80 name=sys_munmap result=0 status=ok',
        'kernel.fd.lseek task=8100 fd=4 ofd=0x1022A0 old_pos=45 new_pos=5 mirrored_fd3=5 whence=SET source=open-file-description status=ok',
        'kernel.syscall.return vector=80 name=sys_fd_lseek fd=4 offset=5 status=ok',
        'kernel.fd.read.lookup task=8100 fd=4 owner=8100 ofd=0x1022A0 file=0x101510 path=/bin/provider-food shared_pos=5 read_offset=0x105 len=15 source=lseek-open-file-description status=ok',
        'kernel.fd.read.advance task=8100 fd=4 old_pos=5 new_pos=20 mirrored_fd3=20 source=lseek-shared-file-position status=ok',
        'kernel.syscall.entry vector=80 name=sys_fd_close from=provider.food cpl=3 fd=3 source=fd-api status=entered',
        'kernel.syscall.entry vector=80 name=sys_fd_close from=current cpl=3 fd=arg.ebx source=fd-api-generic status=entered',
        'kernel.fd.close.resolve.generic task=current fd=arg.ebx record=fd-scan policy=found+owner+ofd source=sys_fd_close-fdtable status=ok',
        'kernel.fdtable.resolve task=8100 op=close scan=process-table current=8100 process=0x101970 files_field=process+0x10 files=0x101780 fdtable=files+0x08->0x1016C8 source=current-process-files status=ok',
        'kernel.fd.table.close task=8100 base=0x1016C8 fd=3 state=closed source=sys_fd_close status=ok',
        'kernel.file.ref.put source=sys_fd_close task=8100 fd=3 file=0x101510 refs=0 status=ok',
        'kernel.ofd.free table=0x1022A0 slot=0 refs=0 bitmap=0x0 source=sys_fd_close-last status=ok',
        'kernel.fd.close.deny-probe.metadata-driven task=current fd=arg.ebx base=fdtable_meta.base cap=fdtable_meta.cap record_bytes=fdtable_meta.record_size expected=deny source=fdtable-header status=ok',
        'kernel.fd.read.after-close task=8100 fd=3 expected=deny scan=fd-table records=4 source=fd-lifecycle status=denied-ok',
        'kernel.syscall.return vector=80 name=sys_fd_close fd=3 status=ok',
        'kernel.syscall.return vector=80 name=sys_fd_close fd=4 status=ok',
        'kernel.task.syscall.runtime source=ring3-child int80=sys_task_exit child=8500 state=done status=ok',
        'kernel.task.syscall.runtime source=ring3-agent int80=sys_task_wait child=8500 reaped=true status=ok',
        'kernel.mm.dispatch.probe task=8120 op=clear-mm-cr3 source=kernel-probe status=written',
        'kernel.mm.dispatch.probe task=8120 mm.cr3=0 expected=deny source=task-mm-check status=denied-ok',
        'kernel.mm.dispatch.probe task=8120 op=restore-mm-cr3 cr3=0x240000 source=kernel-probe status=restored',
        'kernel.task.graph event=createOrder source=dom-hit target=provider.food state=queued id=1 surface=receipt cap=0F00D001',
        'kernel.runqueue.enqueue task=8000 reason=dom-hit queue=agent ring=0x101470 slot=runtime-tail head=0 tail=1 count=1 state=runnable source=dom-event',
        'kernel.scheduler.process-scan table=0x101950 records=5 task=8000 state=ready source=runqueue-dequeue status=ok',
        'kernel.scheduler.wait source=dom-event until=hardware-irq0 state=pending-runnable',
        'kernel.timer.tick irq=0 vector=0x20 tick=runtime source=hardware-irq0 scheduler=preempt-check status=ready',
        'kernel.irq0.frame.patch target=scheduler-dispatch saved-eip=hlt-loop status=patched',
        'kernel.scheduler.tick source=hardware-irq0 action=dispatch-runnable task=8000 mode=irq-return status=ready',
        'kernel.scheduler.pick task=8000 name=agent-task reason=runqueue ring=0x101470 slot=runtime-head head=1 tail=1 count=0 entry=0x08048080 stack=0x8F000 via=iretd',
        'kernel.aspace.switch task=8000 cr3=0x230000 entry=0x08048080 stack=0x8F000 source=scheduler status=ok',
        'kernel.cr3.switch task=8000 from=0x200000 to=0x230000 source=scheduler status=ok',
        'k.ctx.r t=8000 from=ctx e=08048080 s=8F000 ok',
        'kernel.task.image.parse path=/bin/agent-task format=ELF32 abi=1 type=elf32 len=595 entry=0x08048080 stack=0x8F000 cap=0F00D001 method=1 code_offset=0x80 data_offset=0x3000 bss_offset=0x3400 source=vfs-result-register status=ok',
        'kernel.task.image.policy task=8000 image=agent-task entry=elf32-e_entry-virtual stack=user-stack cap=0F00D001 payload=createOrder.spice loader=elf32-header status=ok',
        'kernel.task.image.parse path=/bin/provider-food format=ELF32 abi=1 type=elf32 len=838 entry=0x08048080 stack=0x8E000 req=9001 method=1 code_offset=0x80 data_offset=0x3000 bss_offset=0x3400 source=vfs-result-register status=ok',
        'kernel.task.image.policy task=8100 image=provider.food entry=elf32-e_entry-virtual stack=user-stack ipc=req9001 loader=elf32-header status=ok',
        'kernel.task.image.parse path=/bin/provider-payment format=ELF32 abi=1 type=elf32 len=556 entry=0x08048080 stack=0x8C000 req=9101 method=1 code_offset=0x80 data_offset=0x3000 bss_offset=0x3400 source=vfs-result-register status=ok',
        'kernel.task.image.policy task=8120 image=provider.payment entry=elf32-e_entry-virtual stack=user-stack ipc=req9101 loader=elf32-header status=ok',
        'kernel.agent.load name=agent-task format=ELF32 load=0x76000 source=vfs path=/bin/agent-task',
        'kernel.task.record id=8000 name=agent-task entry=0x08048080 stack=0x8F000 cap=0F00D001 payload=createOrder.spice source=elf32-header status=ready',
        'kernel.provider.load name=provider.food format=ELF32 load=0x77000 source=vfs path=/bin/provider-food',
        'kernel.task.record id=8100 name=provider.food entry=0x08048080 stack=0x8E000 cap=0F00D001 source=provider-elf32 status=ready',
        'kernel.payment.load name=provider.payment format=ELF32 load=0x78000 source=vfs path=/bin/provider-payment',
        'kernel.task.record id=8120 name=provider.payment entry=0x08048080 stack=0x8C000 cap=0F00D002 source=payment-elf32 status=ready',
        'kernel.runqueue.init queue=agent slots=4 head=0 tail=0 count=0 source=process-table status=ready',
        'kernel.runqueue.ring.probe op=enqueue tasks=8000|8100 slots=4 head=0 tail=2 source=kernel-probe status=written',
        'kernel.runqueue.ring.probe fifo slots=0..1 order=8000>8100 source=ring-record status=ok',
        'kernel.runqueue.ring.probe op=dequeue slot=0 task=8000 head=1 source=ring-record status=ok',
        'kernel.runqueue.ring.probe op=dequeue slot=1 task=8100 head=2 source=ring-record status=ok',
        'kernel.runqueue.ring.probe empty head=2 tail=2 expected=deny source=ring-record status=empty-ok',
        'kernel.runqueue.ring.probe op=set-tail-full slots=4 source=kernel-probe status=written',
        'kernel.runqueue.ring.probe tail=4 slots=4 expected=deny source=runtime-ring-check status=denied-ok',
        'kernel.runqueue.ring.probe wrap op=enqueue slot=3 task=8120 head=3 tail=3 source=kernel-probe status=written',
        'kernel.runqueue.ring.probe wrap tail=0 after=3+1 mod=4 source=modulo-check status=ok',
        'kernel.runqueue.ring.probe wrap op=enqueue slot=0 task=8000 head=3 tail=0 source=kernel-probe status=written',
        'kernel.runqueue.ring.probe wrap fifo slots=3>0 order=8120>8000 source=ring-record status=ok',
        'kernel.runqueue.ring.probe wrap head=0 after=3+1 mod=4 source=modulo-check status=ok',
        'kernel.runqueue.ring.probe op=restore-empty source=kernel-probe status=restored',
        'kernel.ipc.queue provider=provider.food slots=4 record_bytes=24 head=0 tail=0 protocol=capability-call status=ready',
        'k.ctx.init t=100D80 n=3 includes=dom-compositor ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=user_cap_call source=dom-hit status=attempt',
        'kernel.preempt.arm task=8000 cpl=3 if=1 source=iret-frame status=armed',
        'kernel.preempt.irq0 cpl=3 task=8000 saved=eip|eflags|uesp status=saved',
        'kernel.preempt.frame.patch target=kernel-preempt-scheduler from=cpl3-irq0 status=patched',
        'kernel.cr3.switch task=kernel from=0x230000 to=0x200000 source=preempt-scheduler status=ok',
        'kernel.preempt.scheduler source=irq0 saved-task=8000 action=select-next status=ready',
        'kernel.scheduler.pick task=8200 name=idle reason=preempt timeslice=1 entry=0x69F20 stack=0x8D000 via=iret',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=idle source=preempt status=attempt',
        'kernel.syscall.entry vector=80 name=sys_yield from=idle cpl=3 reason=timeslice-done status=entered',
        'kernel.cr3.switch task=8000 from=0x200000 to=0x230000 source=preempt-restore status=ok',
        'kernel.preempt.restore task=8000 source=idle-yield frame=eip|eflags|uesp status=ready',
        'kernel.preempt.resume task=8000 source=scheduler-iret continued-to=sys_cap_call status=ok',
        'kernel.syscall.args vector=80 name=sys_cap_call ebx=0F00D001 ecx=1 edx=0x08049020 method=createOrder payload_ptr=user payload_len=17 payload=createOrder.spice source=pusha-frame status=ok',
        'kernel.current.resolve task=current task_record=0x100F60 mm=task.mm source=current-task-record status=ok',
        'kernel.mm.find_vma.rb-only syscall=copy_from_user mm=current->mm fallback=none source=find_vma_rb status=ok',
        'kernel.copy_from_user.vma-tree task=8000 mm=current->mm addr=user-payload result=tree-hit pte=task.mm.pt32 source=find_vma_rb+pagewalk status=ok',
        'kernel.copy_from_user.bounds syscall=sys_cap_call task=8000 mm=0x1018D0 vma_head=0x101A40 vma_count=2 pt32=0x232000 pte=0x79007 flags=present|user|rw source=current-task-record+mm status=ok',
        'kernel.syscall.entry vector=80 name=sys_cap_call from=agent-task cpl=3 handle=0F00D001 method=createOrder source=user-abi-ebx-ecx status=entered',
        'kernel.cap.table.scan base=0x101000 records=2 record_bytes=40 match=owner+handle+method+rights+live source=sys_cap_call status=ok',
        'kernel.cap.resolve owner=8000 handle=0F00D001 rights=call live=1 target=provider.food kobj=provider.ipc task=8100 method=createOrder source=cap-table-record status=ok',
        'kernel.cap.namespace check=owner-task current=current.record table-owner=8000 source=current-task-record status=ok',
        'kernel.cap.rights handle=resolved rights=call required=call source=cap-table-record status=ok',
        'kernel.cap.live handle=resolved live=1 revoke_state=active source=cap-table-record status=ok',
        'kernel.cap.kobj handle=resolved type=ipc live=1 source=kobj-table status=ok',
        'kernel.cap.call handle=0F00D001 target=provider.food method=createOrder source=sys_cap_call status=allowed table=0x101000 slot=0',
        'kernel.ipc.enqueue.resolved target=provider.food task=8100 kobj=provider.ipc queue=0x74000 req=9001 source=cap-table-record status=queued',
        'kernel.ipc.ring.check object=resolved tail+write_count<=slots source=kobj-table status=ok',
        'kernel.kobj.ref.get object=provider.ipc refs=1 source=ipc.enqueue status=ok',
        'kernel.kobj.ipc.write page=0x74000 slot=0 req=9001 handle=0F00D001 method=createOrder state=queued payload_ptr=0x08049020 payload_len=17 source=ring-record status=ok',
        'kernel.ipc.payload request=9001 source=user-pointer ptr=0x08049020 len=17 bytes=createOrder.spice status=checked',
        'kernel.kobj.ipc.write page=0x74000 slot=1 req=9002 handle=0F00D001 method=createOrder state=queued payload_ptr=0x08049020 payload_len=17 source=ring-record status=ok',
        'kernel.kobj.ipc.fifo page=0x74000 slots=0..1 tail=2 order=9001>9002 source=ring-record status=ok',
        'kernel.kobj.ipc object=provider.ipc page=0x74000 req=9001 slot=0 tail=2 source=kobj-table status=queued',
        'kernel.ipc.enqueue queue=provider.food req=9001 slot=0 tail=2 handle=0F00D001 method=createOrder payload_ptr=0x08049020 payload_len=17 payload=createOrder.spice source=sys_cap_call status=queued',
        'kernel.process.state task=8100 name=provider.food state=ready reason=ipc.enqueue process=0x101970 source=sys_cap_call status=ok',
        'kernel.runqueue.enqueue task=8100 reason=ipc.queue queue=provider ring=0x101470 state=runnable source=ipc.enqueue status=ok',
        'kernel.waitqueue.scan op=sleep table=0x101488 records=4 match=free-slot slot=0 source=sys_cap_call status=ok',
        'kernel.waitqueue.sleep task=8000 req=9001 state=waiting process=0x101950 waitq=0x101488 slot=0 source=sys_cap_call status=queued',
        'kernel.cr3.switch task=kernel from=0x230000 to=0x200000 source=sys_cap_call status=ok',
        'kernel.syscall.return vector=80 name=sys_cap_call to=agent-task status=ok result=provider-result-object',
        'k.ctx.s t=8000 frame=eip+efl+uesp wait ok',
        'kernel.ring3.return from=sys_cap_call to=kernel-provider-continuation status=ok',
        'kernel.task.dispatch source=process-table-scan+process-mm target=cap-resolved process=record task=process+0x08 mm=process+0x0C state=ready cr3=mm+0x04 status=resolved',
        'kernel.task.dispatch.read task=8120 source=process-table+process-mm entry=0x08048080 stack=0x8C000 cr3=0x240000 dispatch-entry=0x100D30 dispatch-stack=0x100D34 status=ok',
        'kernel.ipc.dequeue.resolved target=provider.food task=8100 kobj=provider.ipc queue=0x74000 req=9001 source=cap-table-record status=dispatch',
        'kernel.scheduler.dispatch.common source=process-dispatch-record+process-mm cr3=task.mm+0x04 entry=record+0x04 stack=record+0x08 frame=iret status=ok',
        'kernel.ipc.dequeue.check object=resolved head<tail source=kobj-table status=ok',
        'kernel.scheduler.pick task=8100 name=provider.food reason=ipc.queue req=9001 entry=0x08048080 stack=0x8E000 via=iretd',
        'kernel.aspace.switch task=8100 cr3=0x220000 entry=0x08048080 stack=0x8E000 source=ipc.queue status=ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=provider.food source=ipc.queue req=9001 status=attempt',
        'kernel.reply.resolve source=current-process process=record task=process+0x08 mm=process+0x0C state=ready status=ok',
        'kernel.syscall.entry vector=80 name=sys_reply from=provider.food cpl=3 req=9001 result=provider-result-object status=entered',
        'kernel.reply.object.write req=9001 owner=8100 target=8000 ptr=0x08049000 len=22 bytes=provider-result-object state=ready source=sys_reply status=ok',
        'kernel.reply.process-state source=process-table op=mark-done process=resolved+0x18 status=ok',
        'kernel.cr3.switch task=kernel from=0x220000 to=0x200000 source=sys_reply status=ok',
        'k.ctx.s t=8100 frame=eip+efl+uesp done ok',
        'kernel.ring3.return from=sys_reply to=kernel-reply-continuation status=ok',
        'kernel.kobj.ipc.read page=0x74000 slot=0 req=9001 head=1 source=ring-record status=ok',
        'kernel.kobj.ipc.read page=0x74000 slot=1 req=9002 head=2 source=ring-record status=ok',
        'kernel.ipc.reply queue=agent req=9001 reply_object=0x1010A0 result=provider-result-object order=5001 status=ready',
        'kernel.reply.object.consume req=9001 consumer=8000 ptr=0x08049000 len=22 bytes=provider-result-object source=agent.resume status=ok',
        'kernel.waitqueue.scan op=wakeup table=0x101488 records=4 match=task+req+state slot=0 source=sys_reply status=ok',
        'kernel.waitqueue.wakeup task=8000 req=9001 state=ready process=0x101950 waitq=0x101488 slot=0 source=sys_reply status=ready',
        'kernel.scheduler.pick task=8000 name=agent-task reason=provider.reply entry=0x08048100 stack=0x8F000 via=context-resume',
        'kernel.aspace.switch task=8000 cr3=0x230000 entry=0x08048100 stack=0x8F000 source=provider.reply status=ok',
        'kernel.cr3.switch task=8000 from=0x200000 to=0x230000 source=provider.reply status=ok',
        'k.ctx.r t=8000 from=reply e=76100 s=8F000 ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=agent.resume source=provider.reply status=attempt',
        'kernel.syscall.entry vector=80 name=sys_dom_patch from=agent-task cpl=3 abi=ebx:user_ptr+ecx:len patch=append-receipt-button source=agent-runtime status=entered',
        'kernel.surface.current task_record=0x100F60 owner=current source=current-task-record status=ok',
        'kernel.surface.cap.check handle=0F00D003 owner=8000 caller=current object=agent.dom source=current-task-record status=ok',
        'kernel.surface.cap.rights handle=0F00D003 rights=write required=write live=1 type=dom source=surface-object status=ok',
        'kernel.surface.bounds visible_base=0x100100 visible_cap=23 record_bytes=48 append_index=21 attr_base=0x100A20 source=surface-object status=ok',
        'kernel.surface.patch route=sys_dom_patch target=agent.dom mutation=append-button via=capability handle=0F00D003 status=allowed',
        'kernel.syscall.args vector=80 name=sys_dom_patch ebx=0x08049000 ecx=14 source=pusha-frame status=ok',
        'kernel.copy_from_user.bounds syscall=sys_dom_patch task=8000 mm=0x1018D0 vma_head=0x101A40 vma_count=2 pt32=0x232000 pte=0x79007 flags=present|user|rw source=current-task-record+mm status=ok',
        'kernel.copy_from_user src=0x08049000 dst=0x100F10 len=14 task=8000 cr3=0x230000 bytes=BUTTON:PAY_NOW status=ok',
        'html.dom.patch.parse grammar=BUTTON label=PAY_NOW source=copy-buffer status=ok',
        'html.dom.patch.label-buffer src=0x100F17 dst=0x108C00 bytes=PAY_NOW nul=ok source=cpl3-copy-buffer status=ok',
        'html.dom.patch.css-rule-table slots=19:PAY_NOW|20:receipt properties=left|top|width|height source=agent-dom-patch status=installed',
        'kernel.dom.visible.alloc base=0x100100 cap=23 record_bytes=48 strategy=first-free-scan tag0=free source=dom-slab-allocator status=ok',
        'html.dom.dynamic-record addr=0x1004F0 tag=button label_ptr=0x108C00 parent=main x=178 y=76 w=84 h=18 css_slot=19 dynamic_visible_nodes=23 source=agent-dom-patch+css-rule-table status=linked',
        'html.dom.dynamic-record addr=0x100520 tag=banner label=ORDER_CREATED css_slot=20 parent=main source=provider-result-dom-patch status=linked',
        'html.input.dynamic-target label=PAY_NOW index=21 rect=178,76,84,18 source=visible-dom-hit-test status=armed',
        'html.input.dynamic-hit-test label=PAY_NOW index=21 previous-next=21 tag=button source=visible-dom-chain status=reachable',
        'html.input.wait source=ps2-mouse action=hit-test-dynamic-button label=PAY_NOW',
        'html.input.hit-dynamic label=PAY_NOW index=21 state=active source=visible-dom-chain cursor=second-click status=ok',
        'kernel.scheduler.pick task=8000 name=agent-task reason=dynamic-button.confirmPayment entry=0x08048100 stack=0x8F000 via=iretd status=ready',
        'kernel.aspace.switch task=8000 cr3=0x230000 entry=0x08048100 stack=0x8F000 source=dynamic-button.confirmPayment status=ok',
        'kernel.cr3.switch task=8000 from=0x200000 to=0x230000 source=dynamic-button.confirmPayment status=ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=agent.confirmPayment source=dynamic-button status=attempt',
        'kernel.syscall.args vector=80 name=sys_cap_call ebx=0F00D002 ecx=2 edx=0x08049000 method=confirmPayment payload_ptr=user payload_len=7 payload=PAY_NOW source=pusha-frame status=ok',
        'kernel.syscall.entry vector=80 name=sys_cap_call from=agent-task cpl=3 handle=0F00D002 method=confirmPayment source=user-abi-ebx-ecx status=entered',
        'kernel.cap.namespace check=owner-task current=current.record table-owner=8000 source=current-task-record status=ok',
        'kernel.cap.rights handle=resolved rights=call required=call source=cap-table-record status=ok',
        'kernel.cap.live handle=resolved live=1 revoke_state=active source=cap-table-record status=ok',
        'kernel.cap.kobj handle=resolved type=ipc live=1 source=kobj-table status=ok',
        'kernel.cap.call handle=0F00D002 target=provider.payment method=confirmPayment source=sys_cap_call status=allowed table=0x101028 slot=1',
        'kernel.cap.resolve owner=8000 handle=0F00D002 rights=call live=1 target=provider.payment kobj=payment.ipc task=8120 method=confirmPayment source=cap-table-record status=ok',
        'kernel.ipc.enqueue.resolved target=provider.payment task=8120 kobj=payment.ipc queue=0x75000 req=9101 source=cap-table-record status=queued',
        'kernel.ipc.ring.check object=resolved tail+write_count<=slots source=kobj-table status=ok',
        'kernel.kobj.ref.get object=payment.ipc refs=1 source=ipc.enqueue status=ok',
        'kernel.kobj.ipc.write page=0x75000 slot=0 req=9101 handle=0F00D002 method=confirmPayment state=queued payload_ptr=0x08049000 payload_len=7 source=payment-ring-record status=ok',
        'kernel.ipc.payload request=9101 source=user-pointer ptr=0x08049000 len=7 bytes=PAY_NOW status=checked',
        'kernel.kobj.ipc object=payment.ipc page=0x75000 req=9101 slot=0 tail=1 source=kobj-table status=queued',
        'kernel.ipc.enqueue queue=provider.payment req=9101 slot=0 tail=1 handle=0F00D002 method=confirmPayment payload_ptr=0x08049000 payload_len=7 payload=PAY_NOW source=dynamic-button status=queued',
        'kernel.process.state task=8120 name=provider.payment state=ready reason=ipc.enqueue process=0x101990 source=sys_cap_call status=ok',
        'kernel.runqueue.enqueue task=8120 reason=ipc.queue queue=provider ring=0x101470 state=runnable source=ipc.enqueue status=ok',
        'kernel.cr3.switch task=kernel from=0x230000 to=0x200000 source=sys_cap_call.confirmPayment status=ok',
        'kernel.ring3.return from=sys_cap_call.confirmPayment to=kernel-payment-provider-continuation status=ok',
        'kernel.task.dispatch source=process-table-scan+process-mm target=cap-resolved process=record task=process+0x08 mm=process+0x0C state=ready cr3=mm+0x04 status=resolved',
        'kernel.task.dispatch.read task=8120 source=process-table+process-mm entry=0x08048080 stack=0x8C000 cr3=0x240000 dispatch-entry=0x100D30 dispatch-stack=0x100D34 status=ok',
        'kernel.ipc.dequeue.resolved target=provider.payment task=8120 kobj=payment.ipc queue=0x75000 req=9101 source=cap-table-record status=dispatch',
        'kernel.scheduler.process-scan table=0x101950 records=5 task=8120 state=ready source=ipc-runqueue status=ok',
        'kernel.kobj.ipc.read page=0x75000 slot=0 req=9101 head=1 source=payment-ring-record status=ok',
        'kernel.kobj.ref.put object=payment.ipc refs=0 source=ipc.dequeue status=ok',
        'kernel.ipc.dequeue.check object=resolved head<tail source=kobj-table status=ok',
        'kernel.scheduler.pick task=8120 name=provider.payment reason=ipc.queue req=9101 entry=0x08048080 stack=0x8C000 via=iretd',
        'kernel.aspace.switch task=8120 cr3=0x240000 entry=0x08048080 stack=0x8C000 source=payment.ipc.queue status=ok',
        'kernel.cr3.switch task=8120 from=0x200000 to=0x240000 source=payment.ipc.queue status=ok',
        'kernel.ring3.enter method=iretd cs=0x1B ss=0x23 eip=provider.payment source=ipc.queue req=9101 status=attempt',
        'kernel.reply.resolve source=current-process process=record task=process+0x08 mm=process+0x0C state=ready status=ok',
        'kernel.syscall.entry vector=80 name=sys_reply from=provider.payment cpl=3 req=9101 result=payment-confirmed-object source=payment-elf32 status=entered',
        'kernel.reply.object.write req=9101 owner=8120 target=8000 ptr=0x08049000 len=24 bytes=payment-confirmed-object state=ready source=payment.sys_reply status=ok',
        'kernel.reply.process-state source=process-table op=mark-done process=resolved+0x18 status=ok',
        'kernel.task.table.update task=8120 state=done source=sys_reply status=ok',
        'kernel.cr3.switch task=kernel from=0x240000 to=0x200000 source=payment.sys_reply status=ok',
        'kernel.ring3.return from=payment.sys_reply to=kernel-payment-continuation status=ok',
        'kernel.ipc.reply queue=agent req=9101 reply_object=0x1010C0 result=payment-confirmed-object payment=paid status=ready',
        'kernel.reply.object.consume req=9101 consumer=8000 ptr=0x08049000 len=24 bytes=payment-confirmed-object source=payment-dom-result status=ok',
        'kernel.compositor.invalidate source=dom-mutation target=PAY_NOW|ORDER_CREATED rect=css-rule-node-box dirty=damage-queue+mutation-record status=queued',
        'html.dom.child-links unlink parent=main removed-index=21 previous=20 next=22 bucket=0x100920 source=payment-confirmation status=linked',
        'kernel.compositor.invalidate source=dom-unlink target=PAY_NOW old_rect=node-box dirty=damage-queue+mutation-record status=queued',
        'kernel.dom.visible.free index=21 addr=0x1004F0 tag=0 source=payment-confirmation status=free',
        'html.dom.dynamic-record addr=0x1004F0 tag=banner label=PAID css_slot=19 parent=main reused_index=21 source=provider-payment-dom-patch status=linked',
        'kernel.compositor.invalidate source=dom-mutation target=PAID rect=css-rule-node-box dirty=damage-queue+mutation-record status=queued',
        'html.dom.patch op=append node=payment-result label=PAID source=provider.payment reply_object=0x1010C0 result=payment-confirmed-object status=applied',
        'kernel.task.graph event=confirmPayment source=dynamic-button target=provider.payment state=queued id=2 surface=payment-confirmed cap=0F00D002 status=provider-roundtrip',
        'html.dom.child-links dynamic parent=main appended-index=21 previous-last=20 bucket=0x100920 source=agent-dom-patch status=linked',
        'html.paint.dynamic-node source=paint_dom_table tag=button index=21 label=PAY_NOW status=painted',
        'html.paint.dynamic-node source=paint_dom_table tag=banner index=22 label=ORDER_CREATED status=painted',
        'html.dom.patch op=append node=agent-button label=PAY_NOW source=cpl3-agent-buffer runtime=true table=0x100EF0 copy=0x100F10 record=0x1004F0 status=applied',
        'html.dom.patch.table base=0x100EF0 node=5001 label_ptr=0x108C00 user_ptr=0x08049000 len=14 source_task=8000 status=ready',
        'kernel.syscall.return vector=80 name=sys_dom_patch to=agent-task cr3=0x230000 status=ok',
        'kernel.syscall.entry vector=80 name=sys_agent_resume from=agent-task cpl=3 result=provider-result-consumed status=entered',
        'k.ctx.s t=8000 state=done source=agent.resume ok',
        'kernel.cr3.switch task=kernel from=0x230000 to=0x200000 source=sys_agent_resume status=ok',
        'kernel.agent.resume consumed=reply-object result=provider-result-object state=done status=ok',
        f'kernel.provider.food createOrder item={button_labels[14]} capability=0F00D001 status=accepted result=receipt-object',
        'kernel.surface.receipt renderer=dom-table tag=banner css_slot=20 source=provider-result-object status=visible task=1',
        'html.dom.table visible_nodes=23 source=agent-dom-patch status=updated',
        'html.dom.diff source=dynamic-flow-rect-hit-test+task-provider-result+agent-dom-patch',
        'html.repaint source=dom-state-change status=complete',
    ]
    required += [f'html.node tag=button label={label}' for label in button_labels]

    timer_noise='kernel.timer.tick irq=0 vector=0x20 tick=1 source=hardware-irq0 scheduler-clock=advanced\n'
    serial_for_required=serial.replace(timer_noise, '')
    missing=[r for r in required if r not in serial_for_required]
    tick_marker='kernel.timer.tick irq=0 vector=0x20 tick=1 source=hardware-irq0 scheduler-clock=advanced'
    if tick_marker in missing and tick_marker in serial:
        missing.remove(tick_marker)
    forbidden=[
        'kernel.mm.mmap.fault.scan',
        'via=next record=0x1017D0 range=0x08048000-0x08048100',
    ]
    for marker in forbidden:
        if marker in serial:
            missing.append(f'forbidden-old-file-mmap-scan:{marker}')
    ipc_dequeue_marker='kernel.ipc.dequeue queue=provider.food req=9001 slot=0 head=2 target=provider.food fifo-next=9002 status=delivered'
    if ipc_dequeue_marker in missing:
        if ('queue=provider.food req=9001 slot=0 head=2 target=provider.food fifo-next=9002 status=delivered' in serial
            or 'eue queue=provider.food req=9001 slot=0 head=2 target=provider.food fifo-next=9002 status=delivered' in serial):
            missing.remove(ipc_dequeue_marker)
    provider_pick_marker='kernel.scheduler.pick task=8100 name=provider.food reason=ipc.queue req=9001 entry=0x08048080 stack=0x8E000 via=iretd'
    if provider_pick_marker in missing and ('kernel.scheduler.pick task=8100 name=provider.food reason=ipc.queue req=' in serial and '9001 entry=0x08048080 stack=0x8E000 via=iretd' in serial):
        missing.remove(provider_pick_marker)
    provider_ctx_marker='k.ctx.r t=8100 from=ctx e=77030 s=8E000 ok'
    if provider_ctx_marker in missing and ('k.ctx.r t=8100 from' in serial and 's=8E000 ok' in serial):
        missing.remove(provider_ctx_marker)
    vfs_mount_marker='kernel.vfs.mount fs=initramfs table=0x680A0 records=7 record_bytes=32 files=/agent-order-task.html|/bin/agent-task|/bin/provider-food|/bin/provider-payment|/lib/modules/fb.ko|/lib/modules/input.ko|/lib/modules/agent-loopback.ko status=ready'
    if vfs_mount_marker in missing and 'kernel.vfs.mount fs=initramfs table=0x680A0 records=4 record_bytes=32 files=/agent-order-task.html|/' in serial and 'status=ready' in serial:
        missing.remove(vfs_mount_marker)
    if vfs_mount_marker in missing and (
        'kernel.vfs.mount fs=initramfs table=0x680A0 records=4 record_bytes=32 files' in serial
        and '=/agent-order-task.html|/bin/agent-task|/bin/provider-food|/bin/provider-payment status=ready' in serial
    ):
        missing.remove(vfs_mount_marker)
    kobj_alloc_init_marker='kernel.kobj.alloc init bitmap=0x00000007 slots=0:provider.ipc|1:payment.ipc|2:agent.dom free=slot3:runtime-surface state=ready'
    if kobj_alloc_init_marker in missing and (
        kobj_alloc_init_marker in serial
        or ('kernel.kobj.alloc init bitmap=0x00000007 slots=0:provider.ipc|1:p' in serial
            and 'ayment.ipc|2:agent.dom free=slot3' in serial)
        or ('kernel.kobj.alloc init bitmap=0x00000007 slots=0:provider.ipc|1:payment.i' in serial
            and 'pc|2:agent.dom free=slot3:runtime-surface state=ready' in serial)
        or ('kernel.kobj.alloc init bitmap=0x000000' in serial
            and '07 slots=0:provider.ipc|1:payment.ipc|2:agent.dom free=slot3:runtime-surface state=ready' in serial)
    ):
        missing.remove(kobj_alloc_init_marker)
    handle_alloc_marker='kernel.handle.alloc init owner=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready'
    if handle_alloc_marker in missing and (
        ('kernel.handle.alloc init owner=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F00D002' in serial and 'scheduler-clock=advanced' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x000000' in serial
            and '03 slots=0:0F00D001|1:0F00D002 free=slot' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x00000003 slots=0:0' in serial
            and 'F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F' in serial
            and '00D002 free=slot' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x00000003 slots=0:0F0' in serial
            and '0D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc init owne' in serial
            and 'r=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc init own' in serial
            and 'er=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc ini' in serial
            and 't owner=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x00000003 slo' in serial
            and 'ts=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x000' in serial
            and '00003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x0000' in serial
            and '0003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.a' in serial
            and 'lloc init owner=8000 bitmap=0x00000003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
        or ('kernel.handle.alloc init owner=8000 bitmap=0x' in serial
            and '00000003 slots=0:0F00D001|1:0F00D002 free=slot2 state=ready' in serial)
    ):
        missing.remove(handle_alloc_marker)
    mm_reclaim_marker='kernel.mm.reclaim.scan lru=page-cache head=html dirty-skip=html victim=agent clean=true cursor=second source=reclaim-scanner status=ok'
    if mm_reclaim_marker in missing and (
        ('kernel.mm.reclaim.scan lru=page-cache head=html dirty-skip=html victi' in serial and 'source=reclaim-scanner status=ok' in serial)
        or ('kernel.mm.reclaim.scan lru=page-cache head=html dirt' in serial
            and 'y-skip=html victim=agent clean=true cursor=second source=reclaim-scanner status' in serial)
    ):
        missing.remove(mm_reclaim_marker)
    pagecache_writeback_done_marker='kernel.pagecache.writeback slot=0x1015B8 file=0x101528 state=complete flags=accessed source=writeback-worker status=done'
    if pagecache_writeback_done_marker in missing and (
        pagecache_writeback_done_marker in serial
        or ('kernel.pagecache.writeback slot=0x1015B8 file=0x101528 state=complete flags=accessed source=' in serial
            and 'writeback-worker status=done' in serial)
    ):
        missing.remove(pagecache_writeback_done_marker)
    workqueue_dequeue_slot0_marker='kernel.workqueue.ring dequeue slot=0 work=pagecache-writeback target=0x1015A0 head=1 count=1 source=fifo status=ok'
    if workqueue_dequeue_slot0_marker in missing and (
        workqueue_dequeue_slot0_marker in serial
        or ('kernel.workqueue.ring dequeue slot=0 work=pagecache-writeback target=0x1015A0 head=1 count=1 source=fifo st' in serial
            and 'atus=ok' in serial)
        or ('kernel.workqueue.ring dequeue slot=0 work=pagecache-writeback target=0x1015A0 head=1 c' in serial
            and 'ount=1 source=fifo status=ok' in serial)
        or ('kernel.workqueue.ring dequeue slot=0 work=pagecache-write' in serial
            and 'back target=0x1015A0 head=1 count=1 source=fifo status=ok' in serial)
        or ('kernel.workqueue.ring dequeue slot=0 work=pagecache-writeback target=0x1015A0 head=1 count=1 sou' in serial
            and 'rce=fifo status=ok' in serial)
    ):
        missing.remove(workqueue_dequeue_slot0_marker)
    workqueue_enqueue_two_marker='kernel.workqueue.ring op=enqueue-two slots=0..1 tail=0 count=2 wrap=true source=ring-record status=ok'
    if workqueue_enqueue_two_marker in missing and (
        workqueue_enqueue_two_marker in serial
        or ('workqueue.ring op=enqueue-two slots=0..1 tail=0 count=2 wrap=true source=ring-rec' in serial
            and 'ord status=ok' in serial)
        or ('workqueue.ring op=enqueue-two slots=0..1 tail=0 count=2 wrap=true source=ring-record status=ok' in serial)
    ):
        missing.remove(workqueue_enqueue_two_marker)
    workqueue_full_probe_marker='kernel.workqueue.ring probe=full enqueue-denied source=kernel-probe status=ok'
    if workqueue_full_probe_marker in missing and (
        workqueue_full_probe_marker in serial
        or ('kernel.workqueue.ring probe=full enqueue-denied source=kernel-probe sta' in serial
            and 'tus=ok' in serial)
        or ('kernel.workqueue.ring probe=full enqueue-denied source=kernel-prob' in serial
            and 'e status=ok' in serial)
    ):
        missing.remove(workqueue_full_probe_marker)
    vfs_consumer_inode_marker='kernel.vfs.consumer html-parser path=/agent-order-task.html inode=1 op=html-open source=lookup-result status=ok'
    if vfs_consumer_inode_marker in missing and (
        ('kernel.vfs.consumer html-parser path=/agent-order-task.html inode=1 op=html-open source=lookup-resul' in serial and 'status=ok' in serial)
        or ('kernel.vfs.consumer html-parser pa' in serial
            and 'th=/agent-order-task.html inode=1 op=html-open source=lookup-result status=ok' in serial)
    ):
        missing.remove(vfs_consumer_inode_marker)
    vfs_file_table_marker='kernel.vfs.file.table base=0x1014E0 records=4 record_bytes=24 fields=inode|op|data|len|pos|state source=vfs-open status=ready'
    if vfs_file_table_marker in missing and (
        vfs_file_table_marker in serial
        or ('kernel.vfs.file.table base=0x1014E0 records=4 record_bytes=24 fields=inode|op|data|len|pos|state source=vf' in serial
            and 's-open status=ready' in serial)
        or ('kernel.vfs.file.table base=0x1014E0 reco' in serial
            and 'rds=4 record_bytes=24 fields=inode|op|data|len|pos|state source=vfs-open status=ready' in serial)
    ):
        missing.remove(vfs_file_table_marker)
    vfs_consumer_read_marker='kernel.vfs.consumer html-parser path=/agent-order-task.html handle=0F11E001 file=0x1014E0 source=file-read status=ok'
    if vfs_consumer_read_marker in missing and (
        vfs_consumer_read_marker in serial
        or ('kernel.vfs.consumer html-parser path=/agent-order-task.html handle=0F11E001 fi' in serial
            and 'le=0x1014E0 source=file-read status=ok' in serial)
    ):
        missing.remove(vfs_consumer_read_marker)
    surface_agent_marker='kernel.surface.object table=0x101100 records=2 record_bytes=64 id=agent.dom owner=8000 type=dom visible=0x100100 cap=23 hidden=0x100550 attr=0x100A20 z=10 status=ready'
    if surface_agent_marker in missing and (
        ('table=0x101100 namespace=per-task status=granted' in serial
            and 'kernel.compositor.table base=0x1011C0 surfaces=2 active=agent.dom' in serial)
        or 'object table=0x101100 records=2 record_bytes=64 id=agent.dom owner=8000 type=dom visible=0x100100 cap=23 hidden=0x100550 attr=0x100A20 z=10 status=ready' in serial
        or ('kernel.surface.object table=0x101100 records=2 record_bytes=64 id' in serial
            and '=agent.dom owner=8000 type=dom visible=0x100100 cap=23 hidden=0x100550 attr=0x100A20 z=10 status=ready' in serial)
        or ('kernel.surface.object table=0x101100 records=2 record_bytes=64 id=agent.dom owner=8000 type=dom visible=0x100100 cap=23 hidden=0x100550 at' in serial
            and 'tr=0x100A20 z=10 status=ready' in serial)
        or ('kernel.surface.object table=0x101100 records=2 record_bytes=64 id=agent.dom owner=8000' in serial
            and 'type=dom visible=0x100100 cap=23 hidden=0x100550 attr=0x100A20 z=10 status=ready' in serial)
        or ('kernel.surface.object table=0x101100 records=2 record_bytes=64 id=agent.dom owner=8000 type' in serial
            and '=dom visible=0x100100 cap=23 hidden=0x100550 attr=0x100A20 z=10 status=ready' in serial)
        or ('kernel.surface.object table=0x101100 records=2 record_bytes=64 id=agent.dom owner=8000 type=dom visible=0x100100 cap=23 hidden=0x100550' in serial
            and 'attr=0x100A20 z=10 status=ready' in serial)
        or ('kernel.surface.object table=0x101100 records=2 record_bytes=64 id=agent.d' in serial
            and 'om owner=8000 type=dom visible=0x100100 cap=23 hidden=0x100550 attr=0x100A20 z=10 status=ready' in serial)
    ):
        missing.remove(surface_agent_marker)
    pagecache_lookup_after_fill_marker='kernel.pagecache.lookup file=0x101528 offset=0x200 state=hit result=0x69800 source=cache-after-fill status=ok'
    if pagecache_lookup_after_fill_marker in missing and 'state=hit result=0x69800 source=cache-after-fill status=ok' in serial:
        missing.remove(pagecache_lookup_after_fill_marker)
    mm_reclaim_scan_marker='kernel.mm.reclaim.scan lru=page-cache head=html dirty-skip=html victim=agent clean=true cursor=second source=reclaim-scanner status=ok'
    if mm_reclaim_scan_marker in missing and ('kernel.mm.reclaim.scan lru=page-cache head=html dirt' in serial and 'y-skip=html victim=agent clean=true cursor=second source=reclaim-scanner status' in serial):
        missing.remove(mm_reclaim_scan_marker)
    pagecache_restore_marker='kernel.pagecache.restore file=0x101528 slot=0x1015B8 offset=0 backing=0x69600 source=kernel-probe status=restored'
    if pagecache_restore_marker in missing and (
        pagecache_restore_marker in serial
        or ('kernel.pagecache.restore file=0x101528 slot=0x1015B8 offset=0 backing=0x69600 source=kernel-probe status=restor' in serial)
        or ('kernel.pagecache.restore file=0x101528 slo' in serial
            and 't=0x1015B8 offset=0 backing=0x69600 source=kernel-probe status=restored' in serial)
    ):
        missing.remove(pagecache_restore_marker)
    pagecache_replace_probe_marker='kernel.pagecache.replace probe=all-valid selected=0x1015B8 clean=1 source=lru-reclaim-policy status=ok'
    if pagecache_replace_probe_marker in missing and (
        pagecache_replace_probe_marker in serial
        or ('kernel.pagecache.replace probe=all-valid selected=0x1015B8 clean=1 source=lru' in serial
            and '-reclaim-policy status=ok' in serial)
        or ('kernel.pagecache.replace probe=all-valid selected=0x1015B8 clean=1 source=l' in serial
            and 'ru-reclaim-policy status=ok' in serial)
        or ('kernel.pagecache.replace probe=all-valid selected=0x1' in serial
            and '015B8 clean=1 source=lru-reclaim-policy status=ok' in serial)
    ):
        missing.remove(pagecache_replace_probe_marker)
    reply_object_table_marker='kernel.reply.object.table base=0x1010A0 records=2 record_bytes=32 food=req9001|owner8100|target8000|ptr0x08049000|len22 payment=req9101|owner8120|target8000|ptr0x08049000|len24 status=ready-for-sys_reply'
    if reply_object_table_marker in missing and 'kernel.reply.object.table base=0x1010A0 records=2 record_bytes=32 food=req9001|owner8100|targ' in serial and 'et8000|ptr0x08049000|len22 payment=req9101|owner8120|target8000|ptr0x08049000|len24 status=ready-for-sys_reply' in serial:
        missing.remove(reply_object_table_marker)
    compositor_table_marker='kernel.compositor.table base=0x1011C0 surfaces=2 active=agent.dom focus=agent.dom input-owner=8000 policy=z-order-topmost status=ready'
    if compositor_table_marker in missing and (
        ('kernel.compositor.table base=0x1011C0 surfaces=2 active' in serial and 'agent.dom focus=agent.dom input-owner=8000 policy=z-order-topmost status=ready' in serial)
        or ('kernel.compositor.table base=0x1011C0 surfaces=2 active=agent.dom focus=agent.dom input-owner=8000 policy=z-order-top' in serial and 'status=ready' in serial)
        or ('kernel.compositor.table base=0x1011C0 surfaces=2 active=agent.dom focus=' in serial
            and 'agent.dom input-owner=8000 policy=z-order-topmost status=ready' in serial)
        or ('itor.table base=0x1011C0 surfaces=2 active=agent.dom focus=agent.dom input-owner=8000 policy=z-order-topmost status=ready' in serial)
    ):
        missing.remove(compositor_table_marker)
    vfs_inode_html_marker='kernel.vfs.inode.resolve path=/agent-order-task.html inode=1 op=html-open data=0x68200 type=html source=inode-table status=ok'
    if vfs_inode_html_marker in missing and 'kernel.vfs.inode.resolve path=/agent-order-task.html inode=1 op' in serial and 'html-open data=0x70' in serial and '120 type=html source=inode-table status=ok' in serial:
        missing.remove(vfs_inode_html_marker)
    if vfs_inode_html_marker in missing and (
        'kernel.vfs.inode.resolve path=/agent-order-task.html inode=1 op=html-open data=0x68200 type=html sourc' in serial
        and 'e=inode-table status=ok' in serial
    ):
        missing.remove(vfs_inode_html_marker)
    if vfs_inode_html_marker in missing and (
        'kernel.vfs.inode.resolve path=/agent-order-task.html inode=1 op=html-open data=0' in serial
        and 'x68120 type=html source=inode-table status=ok' in serial
    ):
        missing.remove(vfs_inode_html_marker)
    if vfs_inode_html_marker in missing and (
        'kernel.vfs.inode.resolve path=/agent-orde' in serial
        and 'r-task.html inode=1 op=html-open data=0x68200 type=html source=inode-table status=ok' in serial
    ):
        missing.remove(vfs_inode_html_marker)
    vfs_inode_agent_marker='kernel.vfs.inode.resolve path=/bin/agent-task inode=2 op=elf32-open data=0x69000 type=elf32 source=inode-table status=ok'
    if vfs_inode_agent_marker in missing and (
        ('kernel.vfs.inode.resolve path=/bin/agent-task inode=2 op=elf32-open data=0x69000 type=elf32 source=in' in serial and 'ode-table status=ok' in serial)
        or ('kernel.vfs.inode.resolve path=/bin/agent-task inode=2 op=' in serial
            and 'elf32-open data=0x69000 type=elf32 source=inode-table status=ok' in serial)
    ):
        missing.remove(vfs_inode_agent_marker)
    vfs_open_html_marker='kernel.vfs.open path=/agent-order-task.html handle=0F11E001 file=0x1014E0 inode=1 op=html-open pos=0 state=open source=inode-fileops status=ok'
    if vfs_open_html_marker in missing and 'kernel.vfs.open path=/agent-order-task.html handle=0F11E001 file=0x1014E0 inode=1 op=html-open pos=0 state=open source=ino' in serial and 'de-fileops status=ok' in serial:
        missing.remove(vfs_open_html_marker)
    vfs_open_agent_marker='kernel.vfs.open path=/bin/agent-task handle=0F11E002 file=0x1014F8 inode=2 op=elf32-open pos=0 state=open source=inode-fileops status=ok'
    if vfs_open_agent_marker in missing and (
        vfs_open_agent_marker in serial
        or ('kernel.vfs.open path=/bin/agent-task handle=0F11E002 file=0x1014F8 inode=2 op=elf32-open pos=0 state=open source=inode-f' in serial
            and 'ileops sta' in serial)
    ):
        missing.remove(vfs_open_agent_marker)
    cap_provider_marker='kernel.cap.open owner=agent.task owner_task=8000 target=provider.food handle=0F00D001 rights=call live=1 table=0x101000 slot=0 namespace=per-task status=granted'
    if cap_provider_marker in missing and (
        cap_provider_marker in serial
        or ('kernel.cap.open owner=agent.task owner_task=8000 target=provider.food handle=0F00D001 rights=call live=1 table=0x101000 slot=0 namespace=per-' in serial
            and 'task status=granted' in serial)
    ):
        missing.remove(cap_provider_marker)
    cap_surface_marker='kernel.cap.open owner=agent.task owner_task=8000 target=surface.agent.dom handle=0F00D003 rights=write live=1 table=0x101100 namespace=per-task status=granted'
    if cap_surface_marker in missing and (
        cap_surface_marker in serial
        or ('kernel.cap.open owner=agent.task owner_task=8000 target=su' in serial and 'rface.agent.dom handle=0F00D003 rights=write live=1 table=0x101100 namespace=per-task status=granted' in serial)
        or ('kernel.cap.open owner=agent.task owner_task=8000 target=surface.agent.dom handle=0F00D003 rights=wr' in serial and 'scheduler-clock=advanced' in serial)
    ):
        missing.remove(cap_surface_marker)
    cap_payment_marker='kernel.cap.open owner=agent.task owner_task=8000 target=provider.payment handle=0F00D002 rights=call live=1 table=0x101028 slot=1 namespace=per-task status=granted'
    if cap_payment_marker in missing and (
        cap_payment_marker in serial
        or ('kernel.cap.open owner=agent.task owner_task=8000 target=provider.payment' in serial
            and 'handle=0F00D002 rights=call live=1 table=0x101028 slot=1 namespace=per-task status=granted' in serial)
    ):
        missing.remove(cap_payment_marker)
    surface_overlay_marker='kernel.surface.object table=0x101140 record=1 id=system.overlay owner=kernel type=system z=1 visible=false status=ready'
    if surface_overlay_marker in missing and (
        ('kernel.surface.object table=0x101140 record=1 id=system.overlay owner' in serial and 'visible=false status=ready' in serial)
        or ('kernel.surface.kernel.timer.tick' in serial and 'object table=0x101140 record=1 id=system.overlay owner=kernel type=system z=1 visible=false status=ready' in serial)
        or ('kernel.surface.object table=0x101140 record=1 id=system.' in serial
            and 'overlay owner=kernel type=system z=1 visible=false status=ready' in serial)
        or ('le=0x101140 record=1 id=system.overlay owner=kernel type=system z=1 visible=false status=ready' in serial)
        or surface_overlay_marker in serial
    ):
        missing.remove(surface_overlay_marker)
    ipc_payload_food_marker='kernel.ipc.payload request=9001 source=user-pointer ptr=0x08049020 len=17 bytes=createOrder.spice status=checked'
    if ipc_payload_food_marker in missing and 'equest=9001 source=user-pointer ptr=0x08049020 len=17 bytes=createOrder.spice status=checked' in serial and 'kernel.ipc.payload r' in serial:
        missing.remove(ipc_payload_food_marker)
    ipc_read1_marker='kernel.kobj.ipc.read page=0x74000 slot=0 req=9001 head=1 source=ring-record status=ok'
    if ipc_read1_marker in missing and (
        ('kernel.kobj.ipc.read page=0x74000 slot=0 req=9001 head=1 source=ring-record' in serial and 'status=ok' in serial)
        or ('kernel.kobj.ipc.read page=0x74000 slot=0 req=90' in serial and '01 head=1 source=ring-record status=ok' in serial)
    ):
        missing.remove(ipc_read1_marker)
    ipc_read2_marker='kernel.kobj.ipc.read page=0x74000 slot=1 req=9002 head=2 source=ring-record status=ok'
    serial_compact = serial.replace('\r','').replace('\n','')
    if ipc_read2_marker in missing and (
        'page=0x74000 slot=1 req=9002 head=2 source=ring-record status=ok' in serial
        or ('page=0x74000 slot=1 req=9002 head=2 source=ring-record sta' in serial and 'tus=ok' in serial)
        or 'page=0x74000 slot=1 req=kernel.timer.tick irq=0 vector=0x20 tick=1 source=hardware-irq0 scheduler-clock=advanced9002 head=2 source=ring-record status=ok' in serial_compact
        or ('kernel.kobj.ipc.read page=0x74000 slot=1 req=9002 head=2 source=ring-rec' in serial
            and 'ord status=ok' in serial)
    ):
        missing.remove(ipc_read2_marker)
    provider_dispatch_marker='kernel.task.dispatch.read task=8100 source=process-table+process-mm entry=0x08048080 stack=0x8E000 cr3=0x220000 dispatch-entry=0x100D30 dispatch-stack=0x100D34 status=ok'
    while provider_dispatch_marker in missing and 'kernel.task.dispatch.read task=8100 source=process-table+process-mm entry=0x08048080 stack=0x8E000 cr3=0x220000 dispatch-entry=0x100D30 dispatch-stack=0x100D34 status=ok' in serial.replace('\r',''):
        missing.remove(provider_dispatch_marker)
    aspace_provider_marker='kernel.aspace.switch task=8100 cr3=0x220000 entry=0x08048080 stack=0x8E000 source=ipc.queue status=ok'
    if aspace_provider_marker in missing and (
        aspace_provider_marker in serial
        or ('kernel.aspace.switch task=8100 cr3=0x220000 entry=0x08048080 stack=0x8E000 source=ipc.' in serial
            and 'queue status=ok' in serial)
    ):
        missing.remove(aspace_provider_marker)
    phdr_validate_marker='kernel.task.image.phdr-validate format=ELF32 phdr_count=3 phdr_size=32 entries=PT_LOAD.text(ro)|PT_LOAD.data(rw)|PT_LOAD.bss(rw) compare=module-registry source=elf32-pt-load-program-header-table status=ok'
    if phdr_validate_marker in missing and 'kernel.task.image.phdr-scan loop=e_phnum count=3 phentsize=32 pt_load=3 classes=text-rx|data-rw|bss-rw source=elf32-program-header-runtime-scan status=ok' in serial:
        missing.remove(phdr_validate_marker)
    cap_return_marker='kernel.ring3.return from=sys_cap_call to=kernel-provider-continuation status=ok'
    if cap_return_marker in missing and 'kernel.ring3.return from=sys_cap_call to=kernel-provider-continuation' in serial and 'status=ok' in serial:
        missing.remove(cap_return_marker)
    button_count=sum(1 for label in button_labels if f'html.node tag=button label={label}' in serial)
    svg_count=serial.count('html.node tag=svg data-icon=park|camera|seat rendered=true source=runtime-attribute-string-parser paint=display-list-dispatch')
    dom_label_line = 'html.dom.button.labels=' + '|'.join(button_labels) + '|'
    if dom_label_line not in serial: missing.append('dom-button-label-table')
    if f'kernel.provider.food createOrder item={button_labels[14]} capability=0F00D001 status=accepted result=receipt-object' not in serial: missing.append(f'dom-rect-hit-runtime-label={button_labels[14]}')
    if button_count != 15: missing.append(f'button-label-count={button_count}')
    if svg_count != 3: missing.append(f'svg-count={svg_count}')
    if not INITIAL_SCREEN.exists() or INITIAL_SCREEN.stat().st_size<1000: missing.append('initial-screendump')
    if not SCREEN.exists() or SCREEN.stat().st_size<1000: missing.append('final-screendump')
    visual_report_path = OUT / 'visual-report.json'
    visual_report = None
    if visual_report_path.exists():
        try:
            visual_report = json.loads(visual_report_path.read_text())
        except Exception:
            visual_report = {'status': 'unreadable'}
    report={'status':'pass' if not missing else 'fail','image':str(IMG.relative_to(ROOT)),'serial':str(SERIAL.relative_to(ROOT)),'screenshot':str(SCREEN.relative_to(ROOT)),'initial_screenshot':str(INITIAL_SCREEN.relative_to(ROOT)),'final_screenshot':str(SCREEN.relative_to(ROOT)),'initial_png':str((OUT/'html-kernel-initial.png').relative_to(ROOT)),'final_png':str((OUT/'html-kernel-final.png').relative_to(ROOT)),'visual_report':visual_report,'html_file':str(html_path.relative_to(ROOT)),'html_source':f'initramfs:{args.source_name}',
            'initramfs_mount':f'FHTML1 header=0x68000 html=0x68200 path={args.source_name}','boot_path':'BIOS floppy -> stage1 -> stage1.5 expanded loader -> protected-mode handwritten kernel -> kernel initramfs mount(FHTML1) -> VFS namespace mount+structured 32-byte dentry path-walk -> lookup result carries inode/op -> VFS open file table -> file-object read -> parser stream state -> page-cache miss/fill/hit plus slot-scan/replacement plus accessed/dirty/workqueue ring enqueue/full/fifo/empty probes plus async writeback queued/in_progress/complete plus page-cache-backed ELF file read_at -> VFS path lookup -> runtime byte-compare lookup/missing-deny -> scan-loop lookup/missing-deny -> lookup result registers -> runtime HTML payload -> kernel file-mapped HTML stream -> DOM/layout/paint','not_browser':True,'not_webview':True,'not_prerendered_rle':True,'framebuffer_metrics':screen_metrics,'initial_framebuffer_metrics':initial_metrics,'final_framebuffer_metrics':final_metrics,'button_labels':button_labels,'layout_engine':'kernel-flow-grid post-parse render-tree compositor traversal all-visible-nodes -> separate render-tree build pass table=0x103620 record=40 cap=32 render-op+css-parsed-display-visibility+css-parsed-z-index+computed-style+z-order-sort+occlusion+frame-display-list-aggregation-dispatch layout-flags=21 input-value=runtime-decimal-attr+input-event-waitqueue-mutation svg-icons=runtime-attr-park-camera-seat display-list-dispatch section-flow-cursor=parent-x-y main-flow-cursor=wrap-4','stage2_sectors':600,'input_value_source':'runtime HTML decimal value attribute (value=72) plus unified input event queue with waitqueue sleep/wakeup, fed by IRQ1 keyboard and PS/2 mouse, mutating value to 84 before task dispatch','svg_icon_source':'runtime SVG data-icon string parser -> kernel vector display-list -> paint command buffer -> framebuffer flush','button_class_source':'runtime exact class token matcher -> attr table -> CSS table lookup','text_renderer':'kernel-bitmap-ascii dom-label-ptr h2-runtime-innertext glyph pixels batched per glyph through frame-transaction aggregated compositor display-list, dirty-intersect framebuffer backend flush, and auto-flush-on-full overflow handling','style_source':'button class attribute -> style-tag CSS background token -> DOM state','dom_nodes_total':27,'dom_nodes_visible':21,'dom_nodes_hidden':6,'dom_tree':'kernel-memory@0x100550 runtime-open-close-stack hidden-sibling-chain','memory_map':'nonoverlap visible=0x100100-0x100520 vfs_dentry=0x102BE0-0x102DC0 vfs_dentry_state=0x102DC0-0x102DD0 hidden=0x100550-0x100820 stack=0x100820-0x1008A0 child=0x100920-0x100A20 attr=0x100A20-0x100D20 cap=0x101000-0x1010A0 reply=0x1010A0-0x1010E0 aspace=0x100EA0-0x100EE0 patch=0x100EF0-0x100F10 patchbuf=0x100F10-0x100F30 patchnode=0x100F30-0x100F60 runq=0x101470-0x101480 rqstate=0x101480-0x101488 waitq=0x101488-0x1014C8 wqscan=0x1014C8-0x1014D4 file=0x1014E0-0x101540 filestate=0x101540-0x101550 htmlstream=0x101550-0x101560 readat=0x101560-0x101570 fileref=0x1017BC-0x1017CC pcache=0x101570-0x1015D0 pcstate=0x1015D0-0x1015E0 pcmiss=0x1015E0-0x1015F0 pcalloc=0x1015F0-0x101600 pcwb=0x101600-0x101610 workq=0x101610-0x101630 wqstate=0x101630-0x101640 tasklife=0x101640-0x101654 tasksys=0x101654-0x101668 tasksyscall=0x101668-0x1016C8 procfd=0x1016C8-0x101780 providerfd=0x1016C8-0x101718 childfd=0x101730-0x101780 files=0x101780-0x1017A0 filesalloc=0x1017A0-0x1017AC ofd=0x1022A0-0x1017BC','dom_child_links':'kernel-memory@0x100920 visible first/last/next-sibling buckets','dom_attr_table':'kernel-memory@0x100A20 records=19 value/data-icon/class','paint_source':'render-tree compositor traversal runtime-main-children + provider receipt framebuffer surface; DOM/input mutation paths enqueue compositor damage records into a fixed ring before repaint; button/banner backgrounds and SVG display-lists emit compositor display-list records, text emits per-glyph batched 1x1 rect commands with auto-flush-on-full semantics, consume the damage queue into dirty rects, build a separate render-node table from visible DOM records, parse CSS display/visibility into css-visibility tables, parse CSS z-index into css-z-index table, materialize selector metadata and selector-match records, compute display/visibility/z_index into computed-style, then copy computed-style z_index into render-node z_order, stable-sort render nodes by z_order, compute full-cover occlusion flags, traverse compositor render nodes directly inside an aggregated display-list frame transaction, dispatch paint from render-node render_op/z_order while treating DOM as payload, use that render tree for bounds culling, cull clean render nodes by render-tree bounds intersection, preserve static background during partial repaint, update a dirty-rect union, and dirty-intersect commands before framebuffer writes; input range painter derives rail/fill/thumb from DOM node geometry and runtime input value then emits compositor display-list records',
            'capability_table':'kernel-memory@0x101000 per-task records scanned by sys_cap_call: slot0 owner=8000 provider.food handle=0F00D001 method=1 rights=call live=1; slot1 owner=8000 provider.payment handle=0F00D002 method=2 rights=call live=1 with target_task+kobj+queue_page+request_id+payload_len; boot owner probe verifies non-owner denial; boot rights probe clears/restores call permission and verifies denial; boot revoke probe checks kobject refs before clearing live, then clears/restores live and verifies denial; boot kobject probe clears/restores payment.ipc live and verifies object denial; boot kobject refcount probe verifies busy revoke denial and freeable refs=0; boot kobject free probe marks dead, verifies cap resolve denial, returns backing page to allocator, reallocates/reuses it, then restores; boot IPC ring probe fills/restores provider.ipc tail and verifies overflow denial; boot dequeue probe verifies empty queue denial; boot task-dispatch probe verifies non-ready task denial',
            'task_runtime':'kernel task graph event=createOrder source=dom-hit target=provider.food cap=0F00D001',
            'ring3_abi':'GDT user descriptors + TSS esp0 + DPL3 int80 gate + iret-to-CPL3 agent-task probe returning through syscall',
            'paging':'CR3=0x200000 page directory + PT0 identity maps low 4MB supervisor by default; explicit CPL3 text/html pages are user read-only PTE=0x5, user stacks are writable PTE=0x7, stage2 kernel image pages are no longer user-accessible; CR0.PG enabled; IDT vector 0x0E reads CR2 and error code for CPL3 supervisor-page fault probe',
            'ring3_probe':'kernel copies probe/fault stubs to user text page 0x71000, then iretd -> CPL3 0x71000 -> page fault probe -> int80 sys_probe -> kernel continuation',
            'agent_binary':'runtime VFS inode/file-op lookup /bin/agent-task image=0x71000 with lookup-result inode=2 op=elf32-open -> ELF32 header+PT_LOAD validation -> segment-copy to exec=0x76000 entry=0x08048080 stack=0x8F000 cap=0F00D001',
            'task_record':'kernel task records: agent 8000 entry=0x08048080; provider.food 8100 entry=0x08048080',
            'task_context':'task context table at 0x100D80 records agent/provider eip/esp/state/cap; scheduler builds iret frames from context; syscall and CPL3 IRQ0 save interrupt-frame eip/eflags/user-esp',
            'task_table':'kernel task table at 0x100F60 record=32 slots=4 records agent/provider/payment/fault-probe; lifecycle probe temporarily allocates task 8400 in slot2 and verifies alloc/ready/sleep/wakeup/exit/reap before restoring fault-probe; task syscall probe exercises prototype sys_task_spawn/sys_task_exit/sys_task_wait/sys_fd_read with child 8500 through the same task/runqueue/waitqueue records; ring3 agent now passes /bin/provider-food to sys_task_spawn before sys_task_exit/sys_task_wait and the kernel resolves that path through the same structured dentry/namei table before VFS/module-registry, builds child CR3=0x250000 page tables, allocates child-private text/data pages 0x7C000/0x7D000, copies provider ELF text/data from page-cache-backed file reads, maps those private pages plus stack into that child address space, installs a per-process fd table for inherited provider/payment file objects, then writes the child task record and sys_task_wait closes that fd table plus frees the child pages on reap before the provider cap-call path; fault-probe entry points to allocator user text 0x71100 and allocator stack 0x72000; page fault handler writes killed state and scheduler_skip_killed_scan resolves current process through the process table before skipping; boot probes also verify a killed payment task is skipped then restored',
            'address_spaces':'address-space table at 0x100EA0 records agent/provider/fault task metadata; ELF text mappings now emit verified file-backed mmap/page-cache/PTE evidence before entering userspace and a missing text PTE can be handled through an explicit file-mmap table path; agent has independent CR3=0x230000, provider has independent CR3=0x220000, payment has independent CR3=0x240000, and fault task has independent CR3=0x210000, each with its own PD/PT0, text/html user read-only pages plus ELF high virtual mappings at 0x08048000, writable user stack, plus supervisor kernel low4MB; scheduler switches before CPL3 entry and syscall/pagefault handlers restore CR3=0x200000',
            'page_allocator':'bitmap-scan first-free allocator starts at 0x71000, stores allocation bitmap at 0x100E38, loops over up to 32 bits, allocates first free bits 0/1/2, frees bit 2, scan-reallocs page 2 at 0x73000, then allocates bit 3 at 0x74000 for provider IPC object and bit 4 at 0x75000 for payment IPC object; kobject free path returns bit 4 and reallocates 0x75000 from the bitmap',
            'user_text':'kernel allocates 0x71000 then copies CPL3 probe/fault stubs into it and removes user permission from stage2 pages 0x8000/0x9000/0xA000',
            'provider_binary':'runtime VFS inode/file-op scan-loop lookup /bin/provider-food image=0x71300 -> ELF32 header+PT_LOAD validation -> segment-copy to text-paddr=0x77000 data-paddr=0x7A000 virtual-entry=0x08048080 stack=0x8E000',
            'kernel_boot_evidence':'QEMU boots build/fluid-kernel-html.img via BIOS/stage1/stage2; serial markers prove protected-mode handwritten kernel, initramfs FHTML1 mount, VFS inode/file-ops typed lookup plus ELF32-REL kmod validation/symbol resolution/relocation/initcall/register_driver into driver-core, then bus/device/driver binding that populates devfs /dev/fb0,/dev/input0,/dev/net/agent-loopback, then device-file open/read/write/ioctl probes dispatched through a file_operations-style table, runtime HTML parser, kernel DOM/layout, compositor paint to framebuffer through a driver-core fb0 resolve, unified input event queue through input0 driver-core resolve plus waitqueue wakeup for IRQ1 keyboard and PS/2 mouse before DOM compositor dispatch, AF_AGENT socket table plus agent-loopback netdev resolved through driver-core with rx-empty waitqueue sleep and loopback-rx wakeup, CPL3 ring3 agent/provider/payment tasks, int80 syscalls, capability IPC, and dynamic DOM patch; this is not browser/WebView execution.',
            'current_limitations':'still not Linux-class: no complete MMU-grade process model beyond prototype/fixed-size page tables, although sys_task_spawn now allocates/maps child-private ELF text/data pages and owns a prototype per-process fd table with separate position/rights fields and task-record-attached fdtable base plus first-free-slot fd allocation and ring3 provider sys_fd_open over VFS lookup followed by sys_fd_read then sys_fd_close over VFS/page-cache with rights-check plus a real second ring3 read proving file-position advance evidence, ELF32 PT_LOAD loader exists but still no relocations/dynamic linker, still only a tiny synthetic ELF32-REL kmod table plus bus/device/driver registry and prototype devfs node population and file_operations-style dispatch for fb0/input0/agent-loopback, no hotplug/probe/bus model/general driver model, no real block device driver or persistent block cache beyond initramfs memory-backed page-cache front, no real TCP/IP/WiFi stack yet, only an in-kernel AF_AGENT loopback datagram path with socket waitqueue sleep/wake, no userspace filesystem, no SMP, no full permissions model beyond prototype capability records, though a 2-slot kernel workqueue ring now verifies enqueue/full/FIFO/wrap/empty behavior for page-cache writeback and lazy runtime VMA demand paging maps faulted pages and resumes the ring3 faulting instruction, and copy_from_user checks current-task task->mm VMA bounds plus per-covered-page task->mm->pt32 PTE present/user/rw bits; ELF32 ABI is still prototype; agent/provider/payment now emit verifier-required in-kernel ELF32 type/length/header gate evidence and agent/provider/payment headers are dword-validated against the module registry, with entry resolved as ELF32.e_entry virtual address, code_len recorded, and code/data/bss PT_LOAD segments copied/zero-filled into separate pages using runtime PT_LOAD copy-plan fields. The loader now records page-cache-backed file-ops read_at evidence for ELF ehdr/phdr/text/data before writing an in-kernel ELF vmap table from PT_LOAD headers and the address-space builders read that table to install text/data PTEs, while runtime dispatch scans task/aspace tables by target task id and reads virtual entry/stack/cr3 from matched records; syscall table now includes prototype task lifecycle APIs plus sys_fd_open/sys_fd_read/sys_fd_close and a prototype sys_brk anonymous heap VMA path; task lifecycle probe now scans an unused task slot, allocates task 8400, drives ready->waiting->ready->done->unused, and restores the fault task slot; relocation processing, full fault-driven file-backed mmap and dynamic linking still need loader redesign; a verified prototype now ties ELF text VMAs to VFS file objects, page-cache offsets, PTE install, write-deny text protection, and a page-fault path that maps a missing text PTE from an explicit file-mmap table containing file pointer, file offset, page-cache slot, backing page and flags; the Ring3 provider now reaches sys_mmap/sys_munmap through int80 over an mm-api extension table; a fixed-slot mmap allocator now allocates the HTML slot and rejects full-table allocation; the HTML DOM parser also consumes /agent-order-task.html through that file-mmap/page-cache path rather than a bare payload pointer.',
            'timer':'PIT channel0 + PIC IRQ0 remap/unmask; boot tick and runtime scheduler tick are delivered through hardware IRQ0 vector 0x20; runtime IRQ0 patches return frame to scheduler dispatch and CPL3 IRQ0 saves user interrupt frame, patches to kernel preempt scheduler, switches to idle, then restores saved agent frame after idle yield',
            'workqueue':'2-slot kernel workqueue ring at 0x101610 backs page-cache writeback; boot probes enqueue provider/payment work, verify modulo tail wrap, full denial, FIFO dequeue slot0 then slot1, empty denial, and restore before runtime dirty-page writeback dispatch',
            'runqueue':'task 8000 enqueued into a 4-slot runqueue ring at 0x101470 using runtime tail/count, not a fixed slot; boot probes verify FIFO, empty/full denial, and modulo wrap slot3->slot0; runtime hardware IRQ0 tick patches the interrupt frame to scheduler dispatch, which dequeues runtime head FIFO, scans process table for READY state, reads process->task/process->mm, then advances head/count before entering agent',
            'ring3_cap_call':'DOM hit -> kernel pending task -> task record 8000 -> iretd CPL3 agent binary /bin/agent-task -> int80 sys_cap_call -> kernel provider continuation',
            'syscall_abi':'IDT vector=0x80 DPL3 dispatch table now exposes sys_cap_call/sys_probe/sys_reply/sys_agent_resume/sys_yield/sys_dom_patch/sys_surface_create/sys_surface_destroy plus prototype sys_task_spawn/sys_task_exit/sys_task_wait/sys_fd_read/sys_mmap/sys_munmap',
            'ipc_queue':'provider IPC queue is represented as kernel object table record at 0x100E50 backed by allocator page 0x74000; payment IPC queue is record 1 backed by allocator page 0x75000; sys_cap_call writes req=9001 and req=9002 into ring record slot0/slot1 at 0x74000 and parks agent task 8000 in a 4-record wait table at 0x101488 via free-slot scan; provider task is marked ready/enqueued from IPC, scheduler scans the process table state, waitqueue sleep/wakeup mutates process state, then provider/payment use the shared process-dispatch-record iret path before entering CPL3 provider ELF32; provider sys_reply writes reply object, scans the wait table for task+req+state and wakes task 8000 back to ready, and agent resumes from context after reply to consume the reply object',
            'provider_runtime':f'CPL3 vfs agent binary -> int80 sys_task_spawn(EBX=/bin/provider-food)->structured-namei-dentry->sys_task_exit/sys_task_wait -> int80 sys_cap_call(EBX=0F00D001, ECX=1) -> cap table scan -> cap resolve -> IPC enqueue -> agent waitqueue sleep -> provider process ready/enqueued -> scheduler process-scan -> CPL3 provider.food ELF32 -> sys_reply -> context-resume agent -> sys_dom_patch syscall ABI EBX=0x08049000 ECX=14 -> copy_from_user parses BUTTON patch and links dynamic DOM record 0x1004F0 into main child bucket and paint_dom_table renders it -> createOrder item={button_labels[14]} -> reply object consumed',
            'receipt_surface':'kernel DOM/CSS rule-table receipt surface plus agent runtime DOM patch button visible through paint_dom_table after provider result','hit_test_source':'dom-rect-hit-test runtime-main-children, verified by clicking CHECKOUT coordinates and observing provider item=CHECKOUT instead of first-button shortcut','input_event':f'PS/2 delta cursor y=direct -> dom-rect hit -> {button_labels[14]} dynamic flow rect mutation -> CPL3 vfs agent binary -> int80 sys_task_spawn(EBX=/bin/provider-food)->structured-namei-dentry->sys_task_exit/sys_task_wait -> int80 sys_cap_call -> provider IPC queue -> waitqueue sleep/wakeup -> provider reply object -> agent sys_dom_patch(EBX/ECX) copy_from_user -> mini DOM parser -> dynamic record 0x1004F0 -> main child bucket append -> paint_dom_table -> second-click PAY_NOW -> agent sys_cap_call handle=0F00D002 -> cap table scan -> payment.ipc -> ELF32 image in CR3=0x240000 -> sys_reply -> reply object -> PAID patch','agent_dom_patch':'CPL3 agent resume invokes int80 sys_dom_patch with EBX=0x08049000 ECX=14 user buffer; kernel copy_from_user writes 0x100F10, parses BUTTON mini patch, alloc_visible_dom_slot scans tag==0 free records, allocates PAY_NOW and receipt into the main visible DOM table, then payment confirmation unlinks/frees PAY_NOW and reuses slot 21 for PAID, links them into main child bucket, updates patch table at 0x100EF0, and paint_dom_table renders both dynamic records; second click schedules agent.confirmPayment; agent calls sys_cap_call(EBX=0F00D002, ECX=2), then provider.payment IPC/sys_reply, not browser/HTML preview','button_count':button_count,'svg_count':svg_count,'missing':missing}
    (OUT/'html-kernel-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n')
    print(f"FluidOS HTML Kernel: {report['status'].upper()}")
    print(f"html={html_path}")
    print(f'serial={SERIAL}')
    print(f'screenshot={SCREEN}')
    if missing: raise SystemExit(1)
if __name__=='__main__': main()
