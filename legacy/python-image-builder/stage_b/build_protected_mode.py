#!/usr/bin/env python3
"""Build a minimal Fluid Kernel protected-mode proof image.

This image proves that the Fluid Kernel boot path can leave BIOS real mode and
execute 32-bit protected-mode code. It intentionally lives beside the Stage B2
food-flow image so the food-flow verifier remains stable while the lower-level
kernel foundation advances.
"""
from __future__ import annotations
from pathlib import Path
import sys

THIS = Path(__file__).resolve().parent
if str(THIS) not in sys.path:
    sys.path.insert(0, str(THIS))
from asm16 import Asm16, add_serial_routines

ROOT = THIS.parents[1]
OUT = ROOT / "build" / "fluid-kernel-stagec-pm.img"
STAGE2_LOAD = 0x8000
STAGE2_SECTORS = 64


def build_stage1() -> bytes:
    a = Asm16(0x7C00)
    a.emit(0xFA, 0x31, 0xC0, 0x8E, 0xD8, 0x8E, 0xC0, 0x8E, 0xD0)
    a.emit(0xBC); a.imm16(0x7C00); a.emit(0xFB)
    for port, val in [(0x03F9,0),(0x03FB,0x80),(0x03F8,3),(0x03F9,0),(0x03FB,3),(0x03FA,0xC7),(0x03FC,0x0B)]:
        a.emit(0xBA); a.imm16(port); a.emit(0xB0, val, 0xEE)
    a.emit(0xB2, 0x00)
    a.emit(0x88, 0x16); a.abs16("boot_drive")
    a.emit(0xBE); a.abs16("boot_msg"); a.call("serial_print")
    a.emit(0xB4, 0x00, 0x8A, 0x16); a.abs16("boot_drive"); a.emit(0xCD, 0x13)
    a.emit(0x31, 0xC0, 0x8E, 0xC0)
    a.emit(0xBB); a.imm16(STAGE2_LOAD)
    a.emit(0xB4, 0x02, 0xB0, STAGE2_SECTORS)
    a.emit(0xB5, 0x00, 0xB1, 0x02, 0xB6, 0x00)
    a.emit(0x8A, 0x16); a.abs16("boot_drive")
    a.emit(0xCD, 0x13)
    a.jc("disk_error")
    a.emit(0xEA); a.imm16(STAGE2_LOAD); a.imm16(0)
    a.label("disk_error")
    a.emit(0xBE); a.abs16("err_msg"); a.call("serial_print")
    a.label("hang"); a.emit(0xF4); a.jmp("hang")
    add_serial_routines(a)
    a.label("boot_msg"); a.text("Fluid stage1 loading protected-mode stage2\r\n")
    a.label("err_msg"); a.text("graph stagec.disk_error\r\n")
    a.label("boot_drive"); a.emit(0)
    data = bytearray(a.patch())
    if len(data) > 510:
        raise SystemExit(f"stage1 too large: {len(data)}")
    data.extend(b"\0" * (510 - len(data)))
    data.extend(b"\x55\xAA")
    return bytes(data)


def rel32(code_len: int, target_offset: int) -> int:
    return target_offset - (code_len + 4)


def emit_pm_store32(a: Asm16, addr: int, value: int) -> None:
    # 32-bit: mov dword [abs32], imm32
    a.emit(0xC7, 0x05, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF)
    a.emit(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF)


def emit_pm_store_blob(a: Asm16, addr: int, data: bytes) -> None:
    padded = data + b"\x90" * ((4 - (len(data) % 4)) % 4)
    for off in range(0, len(padded), 4):
        emit_pm_store32(a, addr + off, int.from_bytes(padded[off:off + 4], "little"))


def flat32_store(addr: int, value: int) -> bytes:
    return bytes([0xC7, 0x05]) + addr.to_bytes(4, "little") + value.to_bytes(4, "little")


def flat32_payload(stores: list[tuple[int, int]]) -> bytes:
    code = bytearray()
    for addr, value in stores:
        code.extend(flat32_store(addr, value))
    code.extend(b"\xCD\x80\xEB\xFE")
    return bytes(code)


def emit_pm_cmp_mem32_imm32(a: Asm16, addr: int, value: int) -> None:
    # 32-bit: cmp dword [abs32], imm32
    a.emit(0x81, 0x3D, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF)
    a.emit(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF)


def emit_pm_out_dx_eax(a: Asm16) -> None:
    # 32-bit: out dx, eax
    a.emit(0xEF)


def emit_pm_in_eax_dx(a: Asm16) -> None:
    # 32-bit: in eax, dx
    a.emit(0xED)




def emit_pm_out_dx_ax(a: Asm16) -> None:
    # 32-bit protected mode can still use 16-bit port width with operand prefix.
    a.emit(0x66, 0xEF)


def emit_pm_out_dx_al(a: Asm16) -> None:
    a.emit(0xEE)


def emit_pm_in_al_dx(a: Asm16) -> None:
    a.emit(0xEC)


def emit_pm_virtio_out8(a: Asm16, io_base_addr: int, offset: int, value: int) -> None:
    # mov edx,[io_base]; add edx,offset; mov al,value; out dx,al
    a.emit(0x8B, 0x15); a.emit(*(io_base_addr.to_bytes(4, "little")))
    if offset:
        a.emit(0x81, 0xC2); a.emit(*(offset.to_bytes(4, "little")))
    a.emit(0xB0, value & 0xFF)
    emit_pm_out_dx_al(a)


def emit_pm_virtio_out16_imm(a: Asm16, io_base_addr: int, offset: int, value: int) -> None:
    # mov edx,[io_base]; add edx,offset; mov ax,value; out dx,ax
    a.emit(0x8B, 0x15); a.emit(*(io_base_addr.to_bytes(4, "little")))
    if offset:
        a.emit(0x81, 0xC2); a.emit(*(offset.to_bytes(4, "little")))
    a.emit(0x66, 0xB8); a.emit(*(value.to_bytes(2, "little")))
    emit_pm_out_dx_ax(a)


def emit_pm_virtio_out32_imm(a: Asm16, io_base_addr: int, offset: int, value: int) -> None:
    # mov edx,[io_base]; add edx,offset; mov eax,value; out dx,eax
    a.emit(0x8B, 0x15); a.emit(*(io_base_addr.to_bytes(4, "little")))
    if offset:
        a.emit(0x81, 0xC2); a.emit(*(offset.to_bytes(4, "little")))
    a.emit(0xB8); a.emit(*(value.to_bytes(4, "little")))
    emit_pm_out_dx_eax(a)


def emit_pm_virtio_in8(a: Asm16, io_base_addr: int, offset: int, dest: int) -> None:
    # mov edx,[io_base]; add edx,offset; in al,dx; movzx eax,al; mov [dest],eax
    a.emit(0x8B, 0x15); a.emit(*(io_base_addr.to_bytes(4, "little")))
    if offset:
        a.emit(0x81, 0xC2); a.emit(*(offset.to_bytes(4, "little")))
    emit_pm_in_al_dx(a)
    a.emit(0x0F, 0xB6, 0xC0)
    a.emit(0xA3); a.emit(*(dest.to_bytes(4, "little")))



def emit_pm_virtio_in16(a: Asm16, io_base_addr: int, offset: int, dest: int) -> None:
    # mov edx,[io_base]; add edx,offset; in ax,dx; movzx eax,ax; mov [dest],eax
    a.emit(0x8B, 0x15); a.emit(*(io_base_addr.to_bytes(4, "little")))
    if offset:
        a.emit(0x81, 0xC2); a.emit(*(offset.to_bytes(4, "little")))
    a.emit(0x66, 0xED)
    a.emit(0x0F, 0xB7, 0xC0)
    a.emit(0xA3); a.emit(*(dest.to_bytes(4, "little")))


def emit_pm_load32(a: Asm16, src: int, dest: int) -> None:
    # mov eax,[src]; mov [dest],eax
    a.emit(0xA1); a.emit(*(src.to_bytes(4, "little")))
    a.emit(0xA3); a.emit(*(dest.to_bytes(4, "little")))

def emit_pm_pci_config_read32(a: Asm16, bus: int, device: int, function: int, offset: int, dest: int) -> None:
    # PCI config mechanism #1: write address to 0xCF8, read dword from 0xCFC.
    config_addr = 0x80000000 | (bus << 16) | (device << 11) | (function << 8) | (offset & 0xFC)
    a.emit(0xBA); a.emit(*(0x0CF8).to_bytes(4, "little"))  # mov edx, 0xCF8
    a.emit(0xB8); a.emit(*(config_addr.to_bytes(4, "little"))) # mov eax, config_addr
    emit_pm_out_dx_eax(a)
    a.emit(0xBA); a.emit(*(0x0CFC).to_bytes(4, "little"))  # mov edx, 0xCFC
    emit_pm_in_eax_dx(a)
    a.emit(0xA3); a.emit(*(dest.to_bytes(4, "little")))    # mov [dest], eax




def emit_pm_pci_config_write32(a: Asm16, bus: int, device: int, function: int, offset: int, value: int) -> None:
    # PCI config mechanism #1 write: set command bits such as I/O, memory, bus master.
    config_addr = 0x80000000 | (bus << 16) | (device << 11) | (function << 8) | (offset & 0xFC)
    a.emit(0xBA); a.emit(*(0x0CF8).to_bytes(4, "little"))
    a.emit(0xB8); a.emit(*(config_addr.to_bytes(4, "little")))
    emit_pm_out_dx_eax(a)
    a.emit(0xBA); a.emit(*(0x0CFC).to_bytes(4, "little"))
    a.emit(0xB8); a.emit(*(value.to_bytes(4, "little")))
    emit_pm_out_dx_eax(a)

def emit_pm_and_mem32_imm32(a: Asm16, addr: int, value: int) -> None:
    # 32-bit: and dword [abs32], imm32
    a.emit(0x81, 0x25, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF)
    a.emit(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF)


def emit_pm_or_mem32_imm32(a: Asm16, addr: int, value: int) -> None:
    # 32-bit: or dword [abs32], imm32
    a.emit(0x81, 0x0D, addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF)
    a.emit(value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF, (value >> 24) & 0xFF)


def build_stage2() -> bytes:
    a = Asm16(STAGE2_LOAD)
    pm_abs32_patches: list[tuple[int, str]] = []
    pm_rel32_patches: list[tuple[int, str]] = []

    def pm_mov_esi_label(label: str) -> None:
        a.emit(0xBE)
        pm_abs32_patches.append((len(a.code), label))
        a.emit(0, 0, 0, 0)

    def pm_call_label(label: str) -> None:
        a.emit(0xE8)
        pm_rel32_patches.append((len(a.code), label))
        a.emit(0, 0, 0, 0)

    def pm_jne_label(label: str) -> None:
        a.emit(0x0F, 0x85)
        pm_rel32_patches.append((len(a.code), label))
        a.emit(0, 0, 0, 0)

    def pm_je_label(label: str) -> None:
        a.emit(0x0F, 0x84)
        pm_rel32_patches.append((len(a.code), label))
        a.emit(0, 0, 0, 0)

    def pm_jmp_label(label: str) -> None:
        a.emit(0xE9)
        pm_rel32_patches.append((len(a.code), label))
        a.emit(0, 0, 0, 0)

    def pm_print_label(label: str) -> None:
        pm_mov_esi_label(label)
        pm_call_label("pm_serial_print")

    def pm_push_label(label: str) -> None:
        a.emit(0x68)
        pm_abs32_patches.append((len(a.code), label))
        a.emit(0, 0, 0, 0)

    def pm_enter_cpl3_payload(label: str, user_stack: int = 0x0008F000) -> None:
        a.emit(0x66, 0xB8, 0x23, 0x00)                    # mov ax, user data
        for reg in [0xD8, 0xC0, 0xE0, 0xE8]:              # ds, es, fs, gs
            a.emit(0x8E, reg)
        a.emit(0x68, 0x23, 0x00, 0x00, 0x00)              # user ss
        a.emit(0x68); a.emit(*(user_stack.to_bytes(4, "little")))
        a.emit(0x68, 0x02, 0x00, 0x00, 0x00)              # eflags, interrupts masked for CPL3 proof
        a.emit(0x68, 0x1B, 0x00, 0x00, 0x00)              # user cs
        pm_push_label(label)
        a.emit(0xCF)                                      # iretd

    def pm_enter_cpl3_abs(entry: int, user_stack: int = 0x0008F000) -> None:
        a.emit(0x66, 0xB8, 0x23, 0x00)                    # mov ax, user data
        for reg in [0xD8, 0xC0, 0xE0, 0xE8]:              # ds, es, fs, gs
            a.emit(0x8E, reg)
        a.emit(0x68, 0x23, 0x00, 0x00, 0x00)
        a.emit(0x68); a.emit(*(user_stack.to_bytes(4, "little")))
        a.emit(0x68, 0x02, 0x00, 0x00, 0x00)
        a.emit(0x68, 0x1B, 0x00, 0x00, 0x00)
        a.emit(0x68); a.emit(*(entry.to_bytes(4, "little")))
        a.emit(0xCF)                                      # iretd

    def pm_alloc(size: int) -> None:
        a.emit(0xB9); a.emit(*(size.to_bytes(4, "little"))) # ecx=size
        pm_call_label("pm_bump_alloc")

    def pm_fb_rect(x: int, y: int, w: int, h: int, color: int) -> None:
        a.emit(0xB8); a.emit(*(color.to_bytes(4, "little"))) # eax=color
        a.emit(0xBB); a.emit(*(x.to_bytes(4, "little")))     # ebx=x
        a.emit(0xBA); a.emit(*(y.to_bytes(4, "little")))     # edx=y
        a.emit(0xB9); a.emit(*(w.to_bytes(4, "little")))     # ecx=width
        a.emit(0xBE); a.emit(*(h.to_bytes(4, "little")))     # esi=height
        pm_call_label("pm_fb_rect")




    FONT_3X5 = {
        " ": ("000", "000", "000", "000", "000"),
        "D": ("110", "101", "101", "101", "110"),
        "E": ("111", "100", "110", "100", "111"),
        "F": ("111", "100", "110", "100", "100"),
        "I": ("111", "010", "010", "010", "111"),
        "K": ("101", "101", "110", "101", "101"),
        "L": ("100", "100", "100", "100", "111"),
        "O": ("111", "101", "101", "101", "111"),
        "P": ("110", "101", "110", "100", "100"),
        "R": ("110", "101", "110", "101", "101"),
        "S": ("111", "100", "111", "001", "111"),
        "U": ("101", "101", "101", "101", "111"),
        "Y": ("101", "101", "010", "010", "010"),
    }

    def pm_text(text: str, x: int, y: int, scale: int, color: int) -> None:
        # Tiny generated bitmap labels make --visible readable before a full font engine exists.
        cursor = x
        for ch in text.upper():
            glyph = FONT_3X5.get(ch, FONT_3X5[" "])
            for row, bits in enumerate(glyph):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        pm_fb_rect(cursor + col * scale, y + row * scale, scale, scale, color)
            cursor += 4 * scale

    def pm_label_home() -> None:
        pm_text("FLUID", 14, 8, 2, 15)
        pm_text("ORDER", 28, 52, 3, 15)
        pm_text("FOOD", 34, 128, 3, 15)

    def pm_label_trusted() -> None:
        pm_text("PAY", 206, 138, 3, 12)

    def pm_label_receipt() -> None:
        pm_text("OK", 118, 58, 4, 15)

    def pm_render_home() -> None:
        pm_fb_rect(0, 0, 320, 200, 1)       # deep desktop background
        pm_fb_rect(0, 0, 320, 28, 8)        # system status rail
        pm_fb_rect(8, 7, 62, 14, 11)        # FluidOS pill
        pm_fb_rect(250, 7, 54, 14, 2)       # live graph pill
        pm_fb_rect(14, 42, 292, 34, 3)      # generated intent hero shadow
        pm_fb_rect(18, 38, 284, 34, 11)     # generated intent hero
        pm_fb_rect(28, 52, 178, 6, 15)      # title stripe
        pm_fb_rect(28, 62, 104, 4, 7)       # subtitle stripe
        pm_fb_rect(18, 88, 88, 74, 0)       # option card shadow
        pm_fb_rect(22, 84, 88, 74, 2)       # Spice Lab card
        pm_fb_rect(30, 94, 70, 28, 10)      # food image block
        pm_fb_rect(32, 130, 58, 5, 15)      # card title stripe
        pm_fb_rect(32, 141, 44, 4, 7)       # card metadata stripe
        pm_label_home()
        pm_fb_rect(120, 88, 84, 74, 0)      # second card shadow
        pm_fb_rect(124, 84, 84, 74, 6)      # dim alternative card
        pm_fb_rect(132, 94, 66, 28, 14)     # image block
        pm_fb_rect(134, 130, 50, 5, 15)
        pm_fb_rect(134, 141, 42, 4, 7)
        pm_fb_rect(222, 92, 76, 60, 0)      # agent plan panel shadow
        pm_fb_rect(226, 88, 76, 60, 9)      # agent plan panel
        pm_fb_rect(234, 100, 56, 4, 15)
        pm_fb_rect(234, 112, 44, 4, 7)
        pm_fb_rect(234, 124, 52, 4, 10)
        pm_fb_rect(38, 174, 244, 16, 14)    # warm action bar
        pm_fb_rect(48, 179, 128, 5, 0)      # action text stripe

    def pm_render_trusted() -> None:
        pm_fb_rect(0, 0, 320, 200, 1)       # preserve desktop shell
        pm_fb_rect(0, 0, 320, 28, 8)
        pm_fb_rect(8, 7, 62, 14, 11)
        pm_fb_rect(0, 110, 320, 90, 4)      # red trusted capture zone
        pm_fb_rect(18, 122, 284, 58, 0)     # modal shadow
        pm_fb_rect(24, 116, 272, 58, 15)    # trusted payment panel
        pm_fb_rect(34, 128, 116, 7, 4)      # trusted title
        pm_fb_rect(34, 144, 86, 5, 8)       # order summary
        pm_fb_rect(34, 157, 54, 5, 2)       # provider token
        pm_fb_rect(198, 136, 72, 24, 12)    # confirm button
        pm_fb_rect(208, 145, 48, 5, 15)
        pm_fb_rect(24, 184, 272, 6, 12)     # trusted input capture rail
        pm_label_trusted()

    def pm_render_receipt() -> None:
        pm_fb_rect(0, 0, 320, 200, 1)       # desktop background
        pm_fb_rect(0, 0, 320, 28, 8)
        pm_fb_rect(8, 7, 62, 14, 11)
        pm_fb_rect(28, 48, 264, 112, 0)     # receipt shadow
        pm_fb_rect(34, 42, 252, 112, 2)     # success receipt card
        pm_fb_rect(46, 56, 58, 24, 10)      # success badge
        pm_fb_rect(116, 60, 118, 7, 15)     # receipt title
        pm_fb_rect(116, 76, 82, 5, 7)       # order id
        pm_fb_rect(48, 100, 208, 1, 8)      # divider
        pm_fb_rect(50, 112, 70, 5, 15)      # provider line
        pm_fb_rect(50, 126, 54, 5, 15)      # payment line
        pm_fb_rect(196, 112, 54, 5, 10)     # status line
        pm_fb_rect(196, 126, 42, 5, 10)
        pm_fb_rect(46, 170, 228, 14, 3)     # next-task bar
        pm_fb_rect(58, 175, 114, 5, 15)
        pm_label_receipt()

    def pm_render_debug_overlay() -> None:
        pm_fb_rect(0, 0, 320, 14, 8)        # debug graph strip
        pm_fb_rect(4, 3, 28, 8, 12)         # task node
        pm_fb_rect(42, 3, 28, 8, 14)        # cap node
        pm_fb_rect(80, 3, 28, 8, 11)        # provider node
        pm_fb_rect(118, 3, 28, 8, 4)        # trusted node
        pm_fb_rect(156, 3, 28, 8, 10)       # receipt node

    def pm_dispatch_record(slot_addr: int, event_type: int, subject: int, graph_label: str, skip_label: str) -> None:
        emit_pm_cmp_mem32_imm32(a, slot_addr + 0x04, event_type)
        pm_jne_label(skip_label)
        emit_pm_cmp_mem32_imm32(a, slot_addr + 0x08, subject)
        pm_jne_label(skip_label)
        pm_print_label(graph_label)
        a.label(skip_label)

    # Serial note before switching modes.
    a.emit(0xBE); a.abs16("real_msg"); a.call("serial_print")
    a.emit(0xB8, 0x13, 0x00, 0xCD, 0x10)              # BIOS mode 13h: packed 320x200x8bpp
    a.emit(0xFA)                                      # cli
    a.emit(0x0F, 0x01, 0x16); a.abs16("gdt_descriptor") # lgdt [gdt_descriptor]
    a.emit(0x0F, 0x20, 0xC0)                          # mov eax, cr0
    a.emit(0x66, 0x83, 0xC8, 0x01)                    # or eax, 1
    a.emit(0x0F, 0x22, 0xC0)                          # mov cr0, eax
    a.emit(0xEA); a.imm16(0); a.imm16(0x0008)         # far jmp patched to pm_entry, selector 8
    far_ptr_pos = len(a.code) - 4

    add_serial_routines(a)
    a.label("real_msg"); a.text("Fluid Stage C preparing protected mode\r\n")

    # GDT: null, kernel flat code/data, user flat code/data, TSS.
    a.label("gdt_start")
    a.emit(*([0x00] * 8))
    a.emit(0xFF, 0xFF, 0x00, 0x00, 0x00, 0x9A, 0xCF, 0x00)
    a.emit(0xFF, 0xFF, 0x00, 0x00, 0x00, 0x92, 0xCF, 0x00)
    a.emit(0xFF, 0xFF, 0x00, 0x00, 0x00, 0xFA, 0xCF, 0x00)
    a.emit(0xFF, 0xFF, 0x00, 0x00, 0x00, 0xF2, 0xCF, 0x00)
    tss_desc_patch = len(a.code)
    a.emit(*([0x00] * 8))
    a.label("gdt_end")
    a.label("gdt_descriptor")
    gdt_limit = 48 - 1
    a.emit(gdt_limit & 0xFF, (gdt_limit >> 8) & 0xFF)
    # base = STAGE2_LOAD + gdt_start offset; patched after labels known enough.
    gdt_base_patch = len(a.code)
    a.emit(0, 0, 0, 0)
    a.label("tss32")
    a.emit(*([0x00] * 104))
    idt80_patch = None
    a.label("idt_start")
    a.emit(*([0x00] * (0x80 * 8)))
    idt80_patch = len(a.code)
    a.emit(*([0x00] * 8))
    a.label("idt_end")
    a.label("idt_descriptor")
    idt_limit = 0x80 * 8 + 7
    a.emit(idt_limit & 0xFF, (idt_limit >> 8) & 0xFF)
    idt_base_patch = len(a.code)
    a.emit(0, 0, 0, 0)

    # 32-bit code starts here. Bytes are emitted directly.
    a.label("pm_entry")
    pm_entry_offset = len(a.code)
    # Patch far jump target now that pm_entry is known.
    a.code[far_ptr_pos] = (STAGE2_LOAD + pm_entry_offset) & 0xFF
    a.code[far_ptr_pos + 1] = ((STAGE2_LOAD + pm_entry_offset) >> 8) & 0xFF
    # [bits 32]
    a.emit(0x66, 0xB8, 0x10, 0x00)                    # mov ax, 0x10
    for reg in [0xD8, 0xC0, 0xD0, 0xE0, 0xE8]:        # ds, es, ss, fs, gs
        a.emit(0x8E, reg)
    a.emit(0xBC, 0x00, 0x00, 0x09, 0x00)              # mov esp, 0x90000
    a.emit(0x0F, 0x01, 0x1D); a.emit(0, 0, 0, 0)      # lidt [idt_descriptor]
    lidt_patch = len(a.code) - 4
    a.emit(0x66, 0xB8, 0x28, 0x00, 0x0F, 0x00, 0xD8)  # mov ax, tss; ltr ax
    a.emit(0xBF, 0x00, 0x00, 0x0A, 0x00)              # mov edi, 0xA0000
    a.emit(0xB9, 0x00, 0xFA, 0x00, 0x00)              # mov ecx, 64000
    a.emit(0xB0, 0x01, 0xF3, 0xAA)                    # rep stosb blue background
    # Render the first packed framebuffer surface directly from protected-mode memory.
    pm_render_home()
    # Minimal protected-mode bump allocator/object table proof.
    heap_base = 0x00100000
    init_entry = 0x00102000
    provider_entry = 0x00102100
    trusted_entry = 0x00102200
    guard_entry = 0x00102300
    init_pkg_magic = 0xF17D0200
    init_payload = flat32_payload([
        (0x000A0000 + 190 * 320 + 300, 0x0D0D0D0D),
        (heap_base + 0x13C, 0x0004),
    ])
    provider_payload = flat32_payload([
        (0x000A0000 + 188 * 320 + 292, 0x0E0E0E0E),
        (heap_base + 0x78, 0x0002),
        (heap_base + 0x48, 0x0002),
        (heap_base + 0x4C, 0x5001),
        (heap_base + 0x310, 0x0001),
        (heap_base + 0x314, 0x0001),
        (heap_base + 0x460, 0x0A000203), # DNS server 10.0.2.3 observed by provider
        (heap_base + 0x464, 0x5DB8D822), # example.com demo answer 93.184.216.34
        (heap_base + 0x468, 0x00000001), # provider network result ready
        (heap_base + 0x47C, 0xF17D4401), # DNS parser result magic
        (heap_base + 0x480, 0x00110000), # DNS parser source RX buffer
        (heap_base + 0x484, 0x000001B3), # DNS response frame length
        (heap_base + 0x488, 0x5DB8D822), # parsed A record
        (heap_base + 0x48C, 0x00000001), # provider result object ready
    ])
    trusted_payload = flat32_payload([
        (0x000A0000 + 186 * 320 + 284, 0x0F0F0F0F),
        (heap_base + 0x7C, 0x0002),
        (heap_base + 0x68, 0x0002),
        (heap_base + 0x6C, 0x7001),
    ])
    guard_payload = flat32_payload([
        (0x00400000, 0x0BADF00D),
    ])
    emit_pm_store32(a, heap_base + 0x00, 0x1001)      # task.id
    emit_pm_store32(a, heap_base + 0x04, 0x0001)      # task.state created
    emit_pm_store32(a, heap_base + 0x08, 0x2002)      # capability.id payment.confirm
    emit_pm_store32(a, heap_base + 0x0C, 0x0003)      # capability.risk critical
    emit_pm_store32(a, heap_base + 0x10, 0x6001)      # trusted.id
    emit_pm_store32(a, heap_base + 0x14, 0x0000)      # trusted.state none
    emit_pm_store32(a, heap_base + 0x18, 0x4001)      # interface.id
    emit_pm_store32(a, heap_base + 0x1C, 0x0001)      # interface.state projected
    emit_pm_store32(a, heap_base + 0x20, heap_base)   # allocator.base
    emit_pm_store32(a, heap_base + 0x24, heap_base + 0x140) # allocator.next
    emit_pm_store32(a, heap_base + 0x28, 0x0000)      # input.last
    emit_pm_store32(a, heap_base + 0x2C, 0x0000)      # order.id
    emit_pm_store32(a, heap_base + 0x30, 0x0000)      # order.state
    emit_pm_store32(a, heap_base + 0x34, 0x0000)      # receipt.id
    emit_pm_store32(a, heap_base + 0x38, 0x0000)      # receipt.state
    emit_pm_store32(a, heap_base + 0x3C, 0x0000)      # syscall.continuation_stage
    emit_pm_store32(a, heap_base + 0x40, 0x0000)      # provider_ipc.request
    emit_pm_store32(a, heap_base + 0x44, 0x0000)      # provider_ipc.capability
    emit_pm_store32(a, heap_base + 0x48, 0x0000)      # provider_ipc.status
    emit_pm_store32(a, heap_base + 0x4C, 0x0000)      # provider_ipc.order
    emit_pm_store32(a, heap_base + 0x60, 0x0000)      # trusted_ipc.request
    emit_pm_store32(a, heap_base + 0x64, 0x0000)      # trusted_ipc.capability
    emit_pm_store32(a, heap_base + 0x68, 0x0000)      # trusted_ipc.status
    emit_pm_store32(a, heap_base + 0x6C, 0x0000)      # trusted_ipc.receipt
    emit_pm_store32(a, heap_base + 0x380, 0x0000)     # provider_q.head
    emit_pm_store32(a, heap_base + 0x384, 0x0000)     # provider_q.tail
    emit_pm_store32(a, heap_base + 0x388, 0x0004)     # provider_q.slots
    emit_pm_store32(a, heap_base + 0x38C, 0x00100390) # provider_q.slot_base
    emit_pm_store32(a, heap_base + 0x3C0, 0x0000)     # trusted_q.head
    emit_pm_store32(a, heap_base + 0x3C4, 0x0000)     # trusted_q.tail
    emit_pm_store32(a, heap_base + 0x3C8, 0x0004)     # trusted_q.slots
    emit_pm_store32(a, heap_base + 0x3CC, 0x001003D0) # trusted_q.slot_base
    emit_pm_store32(a, heap_base + 0x70, 0x8001)      # provider task.id
    emit_pm_store32(a, heap_base + 0x74, 0x2001)      # provider task.bound capability
    emit_pm_store32(a, heap_base + 0x78, 0x0001)      # provider task.ready
    emit_pm_store32(a, heap_base + 0x7C, 0x8002)      # trusted task.id
    emit_pm_store32(a, heap_base + 0x130, 0x00102000) # fluid-init payload.entry
    emit_pm_store32(a, heap_base + 0x134, 0x00102100) # provider payload.entry
    emit_pm_store32(a, heap_base + 0x138, 0x00102200) # trusted payload.entry
    emit_pm_store32(a, heap_base + 0x13C, 0x0003)     # payload.count
    emit_pm_store32(a, heap_base + 0x180, 0x0003)     # runqueue.count
    emit_pm_store32(a, heap_base + 0x184, 0x8000)     # rq[0] fluid-init task
    emit_pm_store32(a, heap_base + 0x188, 0x8001)     # rq[1] provider task
    emit_pm_store32(a, heap_base + 0x18C, 0x8002)     # rq[2] trusted task
    emit_pm_store32(a, heap_base + 0x190, 0x0000)     # runqueue.cursor
    emit_pm_store32(a, heap_base + 0x194, 0x0000)     # scheduler.tick_count
    emit_pm_store32(a, heap_base + 0x198, 0x0000)     # scheduler.last_irq_vector
    emit_pm_store32(a, heap_base + 0x19C, 0x0000)     # scheduler.quantum_count
    emit_pm_store32(a, heap_base + 0x1C0, 0x8000)     # ctx[0].task fluid-init
    emit_pm_store32(a, heap_base + 0x1C4, 0x00102000) # ctx[0].entry
    emit_pm_store32(a, heap_base + 0x1C8, 0x0008F000) # ctx[0].user_stack
    emit_pm_store32(a, heap_base + 0x1CC, 0x0000)     # ctx[0].yield_count
    emit_pm_store32(a, heap_base + 0x1F0, 0x0000)     # context_switch.count
    emit_pm_store32(a, heap_base + 0x1F4, 0x0000)     # context_switch.from
    emit_pm_store32(a, heap_base + 0x1F8, 0x0000)     # context_switch.to
    emit_pm_store32(a, heap_base + 0x1FC, 0x0000)     # context_switch.returned
    emit_pm_store32(a, heap_base + 0x1D0, 0x8001)     # ctx[1].task provider
    emit_pm_store32(a, heap_base + 0x1D4, 0x00102100) # ctx[1].entry
    emit_pm_store32(a, heap_base + 0x1D8, 0x0008E000) # ctx[1].user_stack
    emit_pm_store32(a, heap_base + 0x1DC, 0x0000)     # ctx[1].yield_count
    emit_pm_store32(a, heap_base + 0x1E0, 0x8002)     # ctx[2].task trusted
    emit_pm_store32(a, heap_base + 0x1E4, 0x00102200) # ctx[2].entry
    emit_pm_store32(a, heap_base + 0x1E8, 0x0008D000) # ctx[2].user_stack
    emit_pm_store32(a, heap_base + 0x1EC, 0x0000)     # ctx[2].yield_count
    emit_pm_store32(a, heap_base + 0x1A0, 0xF17D0001) # initramfs.magic
    emit_pm_store32(a, heap_base + 0x1A4, 0x0003)     # initramfs.file_count
    emit_pm_store32(a, heap_base + 0x1A8, init_entry) # initramfs fluid-init start
    emit_pm_store32(a, heap_base + 0x1AC, provider_entry) # initramfs provider start
    emit_pm_store32(a, heap_base + 0x1B0, trusted_entry) # initramfs trusted start
    emit_pm_store32(a, heap_base + 0x400, init_pkg_magic) # init package version
    emit_pm_store32(a, heap_base + 0x404, len(init_payload)) # fluid-init flatbin size
    emit_pm_store32(a, heap_base + 0x408, len(provider_payload)) # provider flatbin size
    emit_pm_store32(a, heap_base + 0x40C, len(trusted_payload)) # trusted flatbin size
    emit_pm_store32(a, heap_base + 0x410, 0x0000)     # loader.copied_count
    emit_pm_store32(a, heap_base + 0x420, 0x00200000) # page_allocator.base
    emit_pm_store32(a, heap_base + 0x424, 0x00001000) # page_allocator.page_size
    emit_pm_store32(a, heap_base + 0x428, 0x00000040) # page_allocator.total_pages
    emit_pm_store32(a, heap_base + 0x42C, 0x00000004) # page_allocator.used_pages
    emit_pm_store32(a, heap_base + 0x430, 0x00201000) # vm.cr3 init
    emit_pm_store32(a, heap_base + 0x434, 0x00202000) # vm.cr3 provider
    emit_pm_store32(a, heap_base + 0x438, 0x00203000) # vm.cr3 trusted
    emit_pm_store32(a, heap_base + 0x43C, 0x00000001) # vm.guard active
    emit_pm_store32(a, heap_base + 0x440, 0x00200000) # active_cr3 kernel
    emit_pm_store32(a, heap_base + 0x444, 0x00000000) # page_fault.count
    emit_pm_store32(a, heap_base + 0x448, 0x00000000) # page_fault.addr
    emit_pm_store32(a, heap_base + 0x44C, 0x00000000) # page_fault.task
    emit_pm_store32(a, heap_base + 0x450, 0x00000000) # page_fault.resolved
    emit_pm_store32(a, heap_base + 0x200, 0xF17D0100) # manifest.version
    emit_pm_store32(a, heap_base + 0x204, 0x0003)     # manifest.entry_count
    emit_pm_store32(a, heap_base + 0x208, 0x8000)     # manifest[0].task
    emit_pm_store32(a, heap_base + 0x20C, 0x464C494E) # manifest[0].name FLIN
    emit_pm_store32(a, heap_base + 0x210, 0x00102000) # manifest[0].entry
    emit_pm_store32(a, heap_base + 0x214, 0x0008F000) # manifest[0].stack
    emit_pm_store32(a, heap_base + 0x218, 0x8001)     # manifest[1].task
    emit_pm_store32(a, heap_base + 0x21C, 0x464F4F44) # manifest[1].name FOOD
    emit_pm_store32(a, heap_base + 0x220, 0x00102100) # manifest[1].entry
    emit_pm_store32(a, heap_base + 0x224, 0x0008E000) # manifest[1].stack
    emit_pm_store32(a, heap_base + 0x228, 0x8002)     # manifest[2].task
    emit_pm_store32(a, heap_base + 0x22C, 0x54525553) # manifest[2].name TRUS
    emit_pm_store32(a, heap_base + 0x230, 0x00102200) # manifest[2].entry
    emit_pm_store32(a, heap_base + 0x234, 0x0008D000) # manifest[2].stack
    emit_pm_store32(a, heap_base + 0x238, 0x0000)     # manifest.last_lookup
    emit_pm_store32(a, heap_base + 0x23C, 0x0000)     # manifest.last_result
    emit_pm_store32(a, heap_base + 0x240, 0x0002)     # cap_handle.count
    emit_pm_store32(a, heap_base + 0x244, 0xC001F00D) # cap_handle[0] food.createOrder
    emit_pm_store32(a, heap_base + 0x248, 0x2001)     # cap_handle[0].capability
    emit_pm_store32(a, heap_base + 0x24C, 0x8001)     # cap_handle[0].provider
    emit_pm_store32(a, heap_base + 0x250, 0x0001)     # cap_handle[0].authority runtime
    emit_pm_store32(a, heap_base + 0x254, 0xC002FA17) # cap_handle[1] payment.confirmAndPay
    emit_pm_store32(a, heap_base + 0x258, 0x2002)     # cap_handle[1].capability
    emit_pm_store32(a, heap_base + 0x25C, 0x8002)     # cap_handle[1].provider
    emit_pm_store32(a, heap_base + 0x260, 0x0002)     # cap_handle[1].authority trusted
    emit_pm_store32(a, heap_base + 0x264, 0x0000)     # cap_handle.last_used
    emit_pm_store32(a, heap_base + 0x280, 0x1F4001)   # projection.home.id
    emit_pm_store32(a, heap_base + 0x284, 0x1001)     # projection.home.task
    emit_pm_store32(a, heap_base + 0x288, 0x0003)     # projection.home.nodes
    emit_pm_store32(a, heap_base + 0x28C, 0xC001F00D) # projection.home.action handle
    emit_pm_store32(a, heap_base + 0x290, 0x1F4002)   # projection.trusted.id
    emit_pm_store32(a, heap_base + 0x294, 0x1001)     # projection.trusted.task
    emit_pm_store32(a, heap_base + 0x298, 0x0002)     # projection.trusted.nodes
    emit_pm_store32(a, heap_base + 0x29C, 0xC002FA17) # projection.trusted.action handle
    emit_pm_store32(a, heap_base + 0x2A0, 0x1F4003)   # projection.receipt.id
    emit_pm_store32(a, heap_base + 0x2A4, 0x1001)     # projection.receipt.task
    emit_pm_store32(a, heap_base + 0x2A8, 0x0002)     # projection.receipt.nodes
    emit_pm_store32(a, heap_base + 0x2AC, 0x7001)     # projection.receipt.receipt
    emit_pm_store32(a, heap_base + 0x2C0, 0x0D860001) # debug_overlay.id
    emit_pm_store32(a, heap_base + 0x2C4, 0x0005)     # debug_overlay.nodes
    emit_pm_store32(a, heap_base + 0x2C8, 0x0004)     # debug_overlay.edges
    emit_pm_store32(a, heap_base + 0x2CC, 0x0000)     # debug_overlay.state
    emit_pm_store32(a, heap_base + 0x300, 0x0001)     # net.device_count
    emit_pm_store32(a, heap_base + 0x304, 0x1AF4)     # net.vendor virtio
    emit_pm_store32(a, heap_base + 0x308, 0x1000)     # net.device virtio-net legacy
    emit_pm_store32(a, heap_base + 0x30C, 0x0F00D001) # net.handle provider
    emit_pm_store32(a, heap_base + 0x310, 0x0000)     # net.tx_count
    emit_pm_store32(a, heap_base + 0x314, 0x0000)     # net.rx_count
    emit_pm_store32(a, heap_base + 0x318, 0x8001)     # net.owner provider
    emit_pm_store32(a, heap_base + 0x31C, 0x0000)     # pci raw vendor/device read
    emit_pm_store32(a, heap_base + 0x320, 0x0000)     # pci command/status read
    emit_pm_store32(a, heap_base + 0x324, 0x0000)     # pci class/revision read
    emit_pm_store32(a, heap_base + 0x328, 0x0000)     # virtio net BAR0 raw
    emit_pm_store32(a, heap_base + 0x32C, 0x0000)     # virtio net io base
    emit_pm_store32(a, heap_base + 0x330, 0x0000)     # virtio status
    emit_pm_store32(a, heap_base + 0x334, 0x0000)     # virtio queue selector
    emit_pm_store32(a, heap_base + 0x338, 0x0000)     # virtio queue pfns ready
    emit_pm_store32(a, heap_base + 0x33C, 0x0000)     # virtio queue notify count
    emit_pm_store32(a, heap_base + 0x340, 0x0000)     # net graph event count
    emit_pm_store32(a, heap_base + 0x344, 0x00105000) # virtio rx ring phys
    emit_pm_store32(a, heap_base + 0x348, 0x00109000) # virtio tx ring phys
    emit_pm_store32(a, heap_base + 0x34C, 0x00000000) # virtio ISR/status sample
    emit_pm_store32(a, heap_base + 0x350, 0x00000000) # virtio tx notify count
    emit_pm_store32(a, heap_base + 0x354, 0x00000000) # virtio rx notify count
    emit_pm_store32(a, heap_base + 0x358, 0x0010D000) # virtio rx buffer
    emit_pm_store32(a, heap_base + 0x35C, 0x0010E000) # virtio tx frame buffer
    emit_pm_store32(a, heap_base + 0x360, 0x00000040) # virtio tx frame length
    emit_pm_store32(a, heap_base + 0x364, 0x00000800) # tx ethertype IPv4 after ARP
    emit_pm_store32(a, heap_base + 0x368, 0x00000002) # sys_net.send count: ARP + UDP
    emit_pm_store32(a, heap_base + 0x36C, 0x00000001) # sys_net.recv poll count
    emit_pm_store32(a, heap_base + 0x370, 0x00000000) # rx queue size read
    emit_pm_store32(a, heap_base + 0x374, 0x00000000) # tx queue size read
    emit_pm_store32(a, heap_base + 0x378, 0x00000000) # tx used idx sample
    emit_pm_store32(a, heap_base + 0x37C, 0x00000000) # tx completion id/len sample
    emit_pm_store32(a, heap_base + 0x414, 0x00000000) # rx used flags/idx sample
    emit_pm_store32(a, heap_base + 0x418, 0x00000000) # rx used elem id sample
    emit_pm_store32(a, heap_base + 0x41C, 0x00000000) # rx frame ethertype sample
    emit_pm_store32(a, heap_base + 0x454, 0x00000000) # dns rx used elem id sample
    emit_pm_store32(a, heap_base + 0x458, 0x00000000) # dns rx used elem len sample
    emit_pm_store32(a, heap_base + 0x45C, 0x00000000) # dns rx source/proto sample
    emit_pm_store32(a, heap_base + 0x460, 0x00000000) # provider.net.dns_server
    emit_pm_store32(a, heap_base + 0x464, 0x00000000) # provider.net.answer_ipv4
    emit_pm_store32(a, heap_base + 0x468, 0x00000000) # provider.net.result_ready
    emit_pm_store32(a, heap_base + 0x46C, 0x00000001) # security.negative.invalid_cap_denied
    emit_pm_store32(a, heap_base + 0x470, 0x00000001) # security.negative.generated_trusted_denied
    emit_pm_store32(a, heap_base + 0x474, 0x00000001) # syscall.copyin.bad_ptr_denied
    emit_pm_store32(a, heap_base + 0x478, 0x00000001) # syscall.copyout.bad_ptr_denied
    emit_pm_store32(a, heap_base + 0x47C, 0x00000000) # provider.dns_result.magic
    emit_pm_store32(a, heap_base + 0x480, 0x00000000) # provider.dns_result.rx_buffer
    emit_pm_store32(a, heap_base + 0x484, 0x00000000) # provider.dns_result.frame_len
    emit_pm_store32(a, heap_base + 0x488, 0x00000000) # provider.dns_result.answer_ipv4
    emit_pm_store32(a, heap_base + 0x48C, 0x00000000) # provider.dns_result.ready
    emit_pm_store32(a, heap_base + 0x120, 0x0000)     # pointer.packet_count
    emit_pm_store32(a, heap_base + 0x124, 0x0000)     # pointer.buttons
    emit_pm_store32(a, heap_base + 0x128, 0x0000)     # order.dynamic_ptr
    emit_pm_store32(a, heap_base + 0x12C, 0x0000)     # receipt.dynamic_ptr
    ring_base = heap_base + 0x80
    emit_pm_store32(a, ring_base + 0x00, 0x0001)      # ring[0].cursor
    emit_pm_store32(a, ring_base + 0x04, 0x0100)      # ring[0].type task.created
    emit_pm_store32(a, ring_base + 0x08, 0x1001)      # ring[0].subject task
    emit_pm_store32(a, ring_base + 0x0C, 0x0001)      # ring[0].state created
    emit_pm_store32(a, ring_base + 0x10, 0x0002)      # ring[1].cursor
    emit_pm_store32(a, ring_base + 0x14, 0x0200)      # ring[1].type capability.registered
    emit_pm_store32(a, ring_base + 0x18, 0x2002)      # ring[1].subject payment capability
    emit_pm_store32(a, ring_base + 0x1C, 0x0001)      # ring[1].state registered
    emit_pm_store32(a, ring_base + 0x20, 0x0003)      # ring[2].cursor
    emit_pm_store32(a, ring_base + 0x24, 0x0600)      # ring[2].type trusted.created
    emit_pm_store32(a, ring_base + 0x28, 0x6001)      # ring[2].subject trusted session
    emit_pm_store32(a, ring_base + 0x2C, 0x0001)      # ring[2].state awaiting
    pm_call_label("pm_setup_paging")
    # Print boot evidence, then walk protected-mode ring records by type/subject.
    pm_print_label("pm_msg")
    pm_print_label("pm_flush_msg")
    pm_dispatch_record(ring_base + 0x00, 0x0100, 0x1001, "pm_graph_task_created", "pm_skip_task_created")
    pm_dispatch_record(ring_base + 0x10, 0x0200, 0x2002, "pm_graph_cap_registered", "pm_skip_cap_registered")
    pm_dispatch_record(ring_base + 0x20, 0x0600, 0x6001, "pm_graph_trusted_created", "pm_skip_trusted_created")
    pm_print_label("pm_ring_done_msg")
    pm_print_label("pm_surface_home_msg")
    emit_pm_store_blob(a, init_entry, init_payload)
    emit_pm_store_blob(a, provider_entry, provider_payload)
    emit_pm_store_blob(a, trusted_entry, trusted_payload)
    emit_pm_store_blob(a, guard_entry, guard_payload)
    emit_pm_store32(a, heap_base + 0x410, 0x0003)     # loader copied service flat binaries
    pm_print_label("pm_initpkg_msg")
    pm_print_label("pm_loader_flatbin_msg")
    pm_print_label("pm_payload_map_msg")
    pm_print_label("pm_initramfs_msg")
    pm_print_label("pm_initramfs_manifest_msg")
    pm_print_label("pm_initramfs_lookup_init_msg")
    pm_print_label("pm_cap_handle_table_msg")
    pm_print_label("pm_cap_open_food_msg")
    pm_print_label("pm_cap_open_pay_msg")
    pm_print_label("pm_security_negative_msg")
    emit_pm_pci_config_read32(a, 0, 3, 0, 0x00, heap_base + 0x31C)
    emit_pm_pci_config_read32(a, 0, 3, 0, 0x04, heap_base + 0x320)
    emit_pm_pci_config_read32(a, 0, 3, 0, 0x08, heap_base + 0x324)
    emit_pm_pci_config_read32(a, 0, 3, 0, 0x10, heap_base + 0x328)
    emit_pm_pci_config_write32(a, 0, 3, 0, 0x04, 0x00000007) # IO|MEM|BUS_MASTER for virtqueue DMA
    emit_pm_store32(a, heap_base + 0x320, 0x00000007)
    # Keep the discovered I/O base as a record; legacy virtio BAR0 is I/O and low bits are flags.
    a.emit(0xA1); a.emit(*((heap_base + 0x328).to_bytes(4, "little")))
    a.emit(0x83, 0xE0, 0xFC)                         # and eax, ~3
    a.emit(0xA3); a.emit(*((heap_base + 0x32C).to_bytes(4, "little")))
    emit_pm_or_mem32_imm32(a, heap_base + 0x330, 0x00000001) # ACKNOWLEDGE
    emit_pm_virtio_out8(a, heap_base + 0x32C, 0x12, 0x01)
    emit_pm_or_mem32_imm32(a, heap_base + 0x330, 0x00000002) # DRIVER
    emit_pm_virtio_out8(a, heap_base + 0x32C, 0x12, 0x03)
    emit_pm_virtio_out32_imm(a, heap_base + 0x32C, 0x04, 0x00000000) # guest feature mask: none
    emit_pm_or_mem32_imm32(a, heap_base + 0x330, 0x00000008) # FEATURES_OK
    emit_pm_virtio_out8(a, heap_base + 0x32C, 0x12, 0x0B)
    emit_pm_store32(a, heap_base + 0x334, 0x00000000) # RX queue selector
    emit_pm_virtio_out16_imm(a, heap_base + 0x32C, 0x0E, 0x0000) # queue select RX
    emit_pm_virtio_in16(a, heap_base + 0x32C, 0x0C, heap_base + 0x370) # RX queue size
    emit_pm_virtio_out32_imm(a, heap_base + 0x32C, 0x08, 0x00000105) # RX queue PFN 0x105000 >> 12
    emit_pm_store32(a, heap_base + 0x338, 0x00000001) # RX pfn programmed
    emit_pm_virtio_out16_imm(a, heap_base + 0x32C, 0x0E, 0x0001) # queue select TX
    emit_pm_virtio_in16(a, heap_base + 0x32C, 0x0C, heap_base + 0x374) # TX queue size
    emit_pm_virtio_out32_imm(a, heap_base + 0x32C, 0x08, 0x00000109) # TX queue PFN 0x109000 >> 12
    emit_pm_or_mem32_imm32(a, heap_base + 0x338, 0x00000002) # RX/TX pfns programmed
    # Minimal legacy split vrings using the qemu legacy queue-size-256 layout.
    emit_pm_store32(a, 0x00105000, 0x0010D000) # rx desc0.addr low
    emit_pm_store32(a, 0x00105004, 0x00000000) # rx desc0.addr high
    emit_pm_store32(a, 0x00105008, 0x00000640) # rx desc0.len 1600
    emit_pm_store32(a, 0x0010500C, 0x00000002) # rx desc0.flags VRING_DESC_F_WRITE
    emit_pm_store32(a, 0x00105010, 0x00110000) # rx desc1.addr low, DNS response buffer
    emit_pm_store32(a, 0x00105014, 0x00000000) # rx desc1.addr high
    emit_pm_store32(a, 0x00105018, 0x00000640) # rx desc1.len 1600
    emit_pm_store32(a, 0x0010501C, 0x00000002) # rx desc1.flags VRING_DESC_F_WRITE
    emit_pm_store32(a, 0x00106000, 0x00020000) # rx avail.flags=0 idx=2
    emit_pm_store32(a, 0x00106004, 0x00010000) # rx avail.ring[0]=0 ring[1]=1
    emit_pm_store32(a, 0x00109000, 0x0010E000) # tx desc0.addr low
    emit_pm_store32(a, 0x00109004, 0x00000000) # tx desc0.addr high
    emit_pm_store32(a, 0x00109008, 0x00000040) # tx desc0.len 64
    emit_pm_store32(a, 0x0010900C, 0x00000000) # tx desc0.flags device-readable
    emit_pm_store32(a, 0x00109010, 0x0010F000) # tx desc1.addr low, UDP frame
    emit_pm_store32(a, 0x00109014, 0x00000000) # tx desc1.addr high
    emit_pm_store32(a, 0x00109018, 0x00000054) # tx desc1.len 84 DNS query
    emit_pm_store32(a, 0x0010901C, 0x00000000) # tx desc1.flags device-readable
    emit_pm_store32(a, 0x0010A000, 0x00010000) # tx avail.flags=0 idx=1
    emit_pm_store32(a, 0x0010A004, 0x00000000) # tx avail.ring[0]=0
    emit_pm_store32(a, 0x0010E000, 0x00000000) # virtio-net header bytes 0..3
    emit_pm_store32(a, 0x0010E004, 0x00000000) # virtio-net header bytes 4..7
    emit_pm_store32(a, 0x0010E008, 0xFFFF0000) # header tail + ethernet broadcast prefix
    emit_pm_store32(a, 0x0010E00C, 0xFFFFFFFF) # ethernet broadcast suffix
    emit_pm_store32(a, 0x0010E010, 0x007DF102) # source mac 02:f1:7d:00...
    emit_pm_store32(a, 0x0010E014, 0x06080100) # source mac ...00:01 + ethertype ARP
    emit_pm_store32(a, 0x0010E018, 0x00080100) # ARP htype ethernet + IPv4 prefix
    emit_pm_store32(a, 0x0010E01C, 0x01000406) # ARP hlen/plen + request op
    emit_pm_store32(a, 0x0010E020, 0x007DF102) # sender mac prefix
    emit_pm_store32(a, 0x0010E024, 0x000A0100) # sender mac suffix + sender ip prefix
    emit_pm_store32(a, 0x0010E028, 0x00000F02) # sender ip suffix + target mac prefix
    emit_pm_store32(a, 0x0010E02C, 0x00000000) # target mac zero
    emit_pm_store32(a, 0x0010E030, 0x0202000A) # target ip 10.0.2.2
    emit_pm_store32(a, 0x0010E034, 0x00000000) # frame padding
    emit_pm_or_mem32_imm32(a, heap_base + 0x330, 0x00000004) # DRIVER_OK
    emit_pm_virtio_out8(a, heap_base + 0x32C, 0x12, 0x0F)
    emit_pm_virtio_out16_imm(a, heap_base + 0x32C, 0x10, 0x0000) # notify RX queue
    emit_pm_store32(a, heap_base + 0x354, 0x00000001) # rx notify count
    emit_pm_virtio_out16_imm(a, heap_base + 0x32C, 0x10, 0x0001) # notify TX queue for ARP
    # Queue TX desc1 for a minimal IPv4/UDP datagram after ARP has been queued.
    emit_pm_store32(a, 0x0010A000, 0x00020000) # tx avail.idx=2
    emit_pm_store32(a, 0x0010A006, 0x00000001) # tx avail.ring[1]=1, unaligned store is OK in qemu
    emit_pm_store32(a, 0x0010F008, 0x55520000) # vnet tail + dst mac prefix 52:55
    emit_pm_store32(a, 0x0010F00C, 0x0302000A) # dst mac suffix 0a:00:02:03 DNS gateway
    emit_pm_store32(a, 0x0010F010, 0x007DF102) # src mac 02:f1:7d:00...
    emit_pm_store32(a, 0x0010F014, 0x00080100) # src mac suffix + ethertype IPv4
    emit_pm_store32(a, 0x0010F018, 0x39000045) # IPv4 v4/ihl tos len=57
    emit_pm_store32(a, 0x0010F01C, 0x00007EF1) # id flags/frag
    emit_pm_store32(a, 0x0010F020, 0x24711140) # ttl udp checksum
    emit_pm_store32(a, 0x0010F024, 0x0F02000A) # src ip 10.0.2.15
    emit_pm_store32(a, 0x0010F028, 0x0302000A) # dst ip 10.0.2.3
    emit_pm_store32(a, 0x0010F02C, 0x3500409C) # udp src 40000 dst 53
    emit_pm_store32(a, 0x0010F030, 0x318A2500) # udp len=37 checksum=8a31
    emit_pm_store32(a, 0x0010F034, 0x00017DF1) # DNS id + flags
    emit_pm_store32(a, 0x0010F038, 0x00000100) # qdcount
    emit_pm_store32(a, 0x0010F03C, 0x00000000) # an/ns counts
    emit_pm_store32(a, 0x0010F040, 0x61786507) # qname example
    emit_pm_store32(a, 0x0010F044, 0x656C706D) # qname mple
    emit_pm_store32(a, 0x0010F048, 0x6D6F6303) # qname com
    emit_pm_store32(a, 0x0010F04C, 0x00010000) # qtype A
    emit_pm_store32(a, 0x0010F050, 0x00000001) # qclass IN
    emit_pm_store32(a, heap_base + 0x360, 0x00000040) # tx frame length
    emit_pm_virtio_out16_imm(a, heap_base + 0x32C, 0x10, 0x0001) # notify TX queue for UDP
    emit_pm_store32(a, heap_base + 0x33C, 0x00000003) # virtio queue notify count
    emit_pm_store32(a, heap_base + 0x350, 0x00000002) # tx notify count
    emit_pm_load32(a, 0x0010B000, heap_base + 0x378) # tx used flags/idx sample
    emit_pm_load32(a, 0x0010B004, heap_base + 0x37C) # tx used elem id sample
    emit_pm_load32(a, 0x00107000, heap_base + 0x414) # rx used flags/idx sample
    emit_pm_load32(a, 0x00107004, heap_base + 0x418) # rx used elem id sample
    emit_pm_load32(a, 0x0010D014, heap_base + 0x41C) # rx ARP reply ethertype/htype sample
    emit_pm_load32(a, 0x0010700C, heap_base + 0x454) # dns rx used elem id sample
    emit_pm_load32(a, 0x00107010, heap_base + 0x458) # dns rx used elem len sample
    emit_pm_load32(a, 0x0011001C, heap_base + 0x45C) # dns rx source/proto sample
    emit_pm_virtio_in8(a, heap_base + 0x32C, 0x13, heap_base + 0x34C) # ISR/status sample
    emit_pm_store32(a, heap_base + 0x340, 0x00000007) # net graph event count
    pm_print_label("pm_pci_scan_msg")
    pm_print_label("pm_virtio_config_msg")
    pm_print_label("pm_virtio_queue_msg")
    pm_print_label("pm_virtio_dma_msg")
    pm_print_label("pm_virtio_vring_msg")
    pm_print_label("pm_net_frame_msg")
    pm_print_label("pm_virtio_notify_msg")
    pm_print_label("pm_net_rx_msg")
    pm_print_label("pm_net_udp_msg")
    pm_print_label("pm_net_dns_rx_msg")
    pm_print_label("pm_net_graph_msg")
    pm_print_label("pm_net_device_msg")
    pm_print_label("pm_net_handle_msg")
    pm_print_label("pm_projection_home_msg")
    pm_print_label("pm_surface_home_projection_msg")
    pm_print_label("pm_runqueue_msg")
    pm_print_label("pm_context_table_msg")
    pm_print_label("pm_scheduler_boot_msg")
    pm_call_label("pm_setup_timer")
    pm_print_label("pm_timer_ready_msg")
    a.emit(0xFB)                                      # sti, enable PIT IRQ0 after IDT/PIC setup
    a.label("pm_wait_boot_ticks")
    emit_pm_cmp_mem32_imm32(a, heap_base + 0x194, 0x0002)
    pm_jne_label("pm_wait_boot_ticks")
    a.emit(0xFA)                                      # keep later proof deterministic until a real scheduler exists
    pm_print_label("pm_timer_tick_msg")
    pm_print_label("pm_init_dispatch_msg")
    emit_pm_store32(a, heap_base + 0x3C, 0x0005)     # syscall continuation: guard fault probe
    pm_print_label("pm_pf_probe_enter_msg")
    pm_enter_cpl3_abs(guard_entry, 0x0008C000)
    a.label("pm_after_guard_probe")
    pm_call_label("pm_enable_mouse")
    pm_print_label("pm_pointer_ready_msg")

    a.label("pm_key_loop")
    pm_call_label("pm_wait_key")
    a.emit(0x3C, 0x08)                              # PS/2 mouse packet byte 0, no buttons
    pm_je_label("pm_pointer_packet")
    a.emit(0x3C, 0x02)                              # scan code: 1
    pm_je_label("pm_choose_food")
    a.emit(0x3C, 0x15)                              # scan code: y
    pm_je_label("pm_confirm_pay")
    a.emit(0x3C, 0x01)                              # scan code: escape
    pm_je_label("pm_hang")
    pm_jmp_label("pm_key_loop")

    a.label("pm_pointer_packet")
    pm_call_label("pm_wait_key")                    # consume dx byte
    pm_call_label("pm_wait_key")                    # consume dy byte
    emit_pm_store32(a, heap_base + 0x120, 0x0001)
    emit_pm_store32(a, heap_base + 0x124, 0x0000)
    pm_print_label("pm_pointer_event_msg")
    pm_jmp_label("pm_key_loop")

    a.label("pm_choose_food")
    emit_pm_store32(a, heap_base + 0x28, 0x0001)     # input.last = 1
    emit_pm_store32(a, heap_base + 0x40, 0x9001)     # provider IPC request
    emit_pm_store32(a, heap_base + 0x44, 0xC001F00D) # food.createOrder capability handle
    emit_pm_store32(a, heap_base + 0x48, 0x0001)     # request pending
    emit_pm_store32(a, heap_base + 0x390, 0x9001)     # provider_q.slot0.req
    emit_pm_store32(a, heap_base + 0x394, 0xC001F00D) # provider_q.slot0.handle
    emit_pm_store32(a, heap_base + 0x398, 0x1001)     # provider_q.slot0.task
    emit_pm_store32(a, heap_base + 0x39C, 0x0001)     # provider_q.slot0.state queued
    emit_pm_store32(a, heap_base + 0x384, 0x0001)     # provider_q.tail
    emit_pm_store32(a, heap_base + 0x264, 0xC001F00D) # last used handle
    pm_print_label("pm_cap_call_food_msg")
    pm_print_label("pm_provider_ipc_send_msg")
    emit_pm_store32(a, heap_base + 0x238, 0x464F4F44) # lookup FOOD
    emit_pm_store32(a, heap_base + 0x23C, 0x00102100) # result provider entry
    pm_print_label("pm_initramfs_lookup_provider_msg")
    emit_pm_store32(a, heap_base + 0x190, 0x0001)     # scheduler selects provider
    pm_print_label("pm_scheduler_provider_msg")
    emit_pm_store32(a, heap_base + 0x1F0, 0x0002)     # business context switch count
    emit_pm_store32(a, heap_base + 0x1F4, 0x8000)     # switch.from fluid-init/runtime
    emit_pm_store32(a, heap_base + 0x1F8, 0x8001)     # switch.to provider
    emit_pm_store32(a, heap_base + 0x440, 0x00202000) # active_cr3 provider proof
    pm_print_label("pm_provider_context_switch_msg")
    pm_print_label("pm_vm_switch_provider_msg")
    pm_print_label("pm_provider_task_dispatch_msg")
    emit_pm_store32(a, heap_base + 0x3C, 0x0001)     # syscall continuation: provider
    pm_print_label("pm_provider_user_enter_msg")
    pm_enter_cpl3_abs(provider_entry, 0x0008E000)

    a.label("pm_provider_after_syscall")
    emit_pm_store32(a, heap_base + 0x380, 0x0001)     # provider_q.head consumed
    emit_pm_store32(a, heap_base + 0x39C, 0x0002)     # provider_q.slot0.state replied
    emit_pm_store32(a, heap_base + 0x3A0, 0x5001)     # provider_q.reply.order
    pm_print_label("pm_net_provider_msg")
    pm_print_label("pm_provider_ipc_reply_verify_msg")
    pm_print_label("pm_provider_ipc_reply_msg")
    pm_alloc(0x20)
    a.emit(0xA3); a.emit(*((heap_base + 0x128).to_bytes(4, "little"))) # mov [order.dynamic_ptr], eax
    emit_pm_store32(a, heap_base + 0x2C, 0x5001)     # order.id
    emit_pm_store32(a, heap_base + 0x30, 0x0001)     # order.state created
    emit_pm_store32(a, heap_base + 0x14, 0x0001)     # trusted.state awaiting
    emit_pm_store32(a, ring_base + 0x30, 0x0004)
    emit_pm_store32(a, ring_base + 0x34, 0x0400)     # input.key
    emit_pm_store32(a, ring_base + 0x38, 0x0001)
    emit_pm_store32(a, ring_base + 0x3C, 0x0001)
    emit_pm_store32(a, ring_base + 0x40, 0x0005)
    emit_pm_store32(a, ring_base + 0x44, 0x0500)     # capability.called
    emit_pm_store32(a, ring_base + 0x48, 0x5001)
    emit_pm_store32(a, ring_base + 0x4C, 0x0001)
    emit_pm_store32(a, ring_base + 0x50, 0x0006)
    emit_pm_store32(a, ring_base + 0x54, 0x0600)     # trusted_surface.created
    emit_pm_store32(a, ring_base + 0x58, 0x6001)
    emit_pm_store32(a, ring_base + 0x5C, 0x0001)
    pm_print_label("pm_choose_msg")
    pm_print_label("pm_choose_flush_msg")
    pm_dispatch_record(ring_base + 0x30, 0x0400, 0x0001, "pm_graph_input_1", "pm_skip_input_1")
    pm_dispatch_record(ring_base + 0x40, 0x0500, 0x5001, "pm_graph_cap_called", "pm_skip_cap_called")
    pm_dispatch_record(ring_base + 0x50, 0x0600, 0x6001, "pm_graph_trusted_created", "pm_skip_trusted_created_choose")
    pm_print_label("pm_projection_trusted_msg")
    pm_render_trusted()
    pm_print_label("pm_surface_trusted_msg")
    pm_jmp_label("pm_key_loop")

    a.label("pm_confirm_pay")
    emit_pm_store32(a, heap_base + 0x28, 0x0002)     # input.last = y
    emit_pm_store32(a, heap_base + 0x60, 0x9002)     # trusted IPC request
    emit_pm_store32(a, heap_base + 0x64, 0xC002FA17) # payment.confirmAndPay capability handle
    emit_pm_store32(a, heap_base + 0x68, 0x0001)     # request pending
    emit_pm_store32(a, heap_base + 0x3D0, 0x9002)     # trusted_q.slot0.req
    emit_pm_store32(a, heap_base + 0x3D4, 0xC002FA17) # trusted_q.slot0.handle
    emit_pm_store32(a, heap_base + 0x3D8, 0x1001)     # trusted_q.slot0.task
    emit_pm_store32(a, heap_base + 0x3DC, 0x0001)     # trusted_q.slot0.state queued
    emit_pm_store32(a, heap_base + 0x3C4, 0x0001)     # trusted_q.tail
    emit_pm_store32(a, heap_base + 0x264, 0xC002FA17) # last used handle
    pm_print_label("pm_cap_call_pay_msg")
    pm_print_label("pm_trusted_ipc_send_msg")
    emit_pm_store32(a, heap_base + 0x238, 0x54525553) # lookup TRUS
    emit_pm_store32(a, heap_base + 0x23C, 0x00102200) # result trusted entry
    pm_print_label("pm_initramfs_lookup_trusted_msg")
    emit_pm_store32(a, heap_base + 0x190, 0x0002)     # scheduler selects trusted
    pm_print_label("pm_scheduler_trusted_msg")
    emit_pm_store32(a, heap_base + 0x1F0, 0x0003)     # trusted context switch count
    emit_pm_store32(a, heap_base + 0x1F4, 0x8000)     # switch.from fluid runtime
    emit_pm_store32(a, heap_base + 0x1F8, 0x8002)     # switch.to trusted
    emit_pm_store32(a, heap_base + 0x440, 0x00203000) # active_cr3 trusted proof
    pm_print_label("pm_trusted_context_switch_msg")
    pm_print_label("pm_vm_switch_trusted_msg")
    pm_print_label("pm_trusted_task_dispatch_msg")
    emit_pm_store32(a, heap_base + 0x3C, 0x0002)     # syscall continuation: trusted
    pm_print_label("pm_trusted_user_enter_msg")
    pm_enter_cpl3_abs(trusted_entry, 0x0008D000)

    a.label("pm_trusted_after_syscall")
    emit_pm_store32(a, heap_base + 0x3C0, 0x0001)     # trusted_q.head consumed
    emit_pm_store32(a, heap_base + 0x3DC, 0x0002)     # trusted_q.slot0.state replied
    emit_pm_store32(a, heap_base + 0x3E0, 0x7001)     # trusted_q.reply.receipt
    pm_print_label("pm_trusted_ipc_reply_verify_msg")
    pm_print_label("pm_trusted_ipc_reply_msg")
    pm_alloc(0x20)
    a.emit(0xA3); a.emit(*((heap_base + 0x12C).to_bytes(4, "little"))) # mov [receipt.dynamic_ptr], eax
    emit_pm_store32(a, heap_base + 0x14, 0x0002)     # trusted.state confirmed
    emit_pm_store32(a, heap_base + 0x34, 0x7001)     # receipt.id
    emit_pm_store32(a, heap_base + 0x38, 0x0001)     # receipt.state created
    emit_pm_store32(a, heap_base + 0x04, 0x0002)     # task.state completed
    emit_pm_store32(a, ring_base + 0x60, 0x0007)
    emit_pm_store32(a, ring_base + 0x64, 0x0400)     # input.key
    emit_pm_store32(a, ring_base + 0x68, 0x0002)
    emit_pm_store32(a, ring_base + 0x6C, 0x0002)
    emit_pm_store32(a, ring_base + 0x70, 0x0008)
    emit_pm_store32(a, ring_base + 0x74, 0x0700)     # trusted.confirmed
    emit_pm_store32(a, ring_base + 0x78, 0x6001)
    emit_pm_store32(a, ring_base + 0x7C, 0x0002)
    emit_pm_store32(a, ring_base + 0x80, 0x0009)
    emit_pm_store32(a, ring_base + 0x84, 0x0800)     # receipt.created
    emit_pm_store32(a, ring_base + 0x88, 0x7001)
    emit_pm_store32(a, ring_base + 0x8C, 0x0001)
    emit_pm_store32(a, ring_base + 0x90, 0x000A)
    emit_pm_store32(a, ring_base + 0x94, 0x0900)     # task.completed
    emit_pm_store32(a, ring_base + 0x98, 0x1001)
    emit_pm_store32(a, ring_base + 0x9C, 0x0002)
    pm_print_label("pm_confirm_msg")
    pm_print_label("pm_confirm_flush_msg")
    pm_dispatch_record(ring_base + 0x60, 0x0400, 0x0002, "pm_graph_input_y", "pm_skip_input_y")
    pm_dispatch_record(ring_base + 0x70, 0x0700, 0x6001, "pm_graph_trusted_confirmed", "pm_skip_trusted_confirmed")
    pm_dispatch_record(ring_base + 0x80, 0x0800, 0x7001, "pm_graph_receipt_created", "pm_skip_receipt_created")
    pm_dispatch_record(ring_base + 0x90, 0x0900, 0x1001, "pm_graph_task_completed", "pm_skip_task_completed")
    pm_print_label("pm_projection_receipt_msg")
    pm_render_receipt()
    pm_render_debug_overlay()
    emit_pm_store32(a, heap_base + 0x2CC, 0x0001)     # debug overlay presented
    pm_print_label("pm_debug_overlay_msg")
    pm_print_label("pm_surface_receipt_msg")
    pm_jmp_label("pm_key_loop")

    a.label("pm_hang")
    pm_print_label("pm_halt_msg")
    emit_pm_store32(a, heap_base + 0x3C, 0x0003)     # syscall continuation: fluid-init yield/halt
    emit_pm_store32(a, heap_base + 0x440, 0x00201000) # active_cr3 fluid-init proof
    pm_print_label("pm_user_enter_msg")
    pm_print_label("pm_vm_switch_init_msg")
    pm_enter_cpl3_abs(init_entry, 0x0008F000)

    # The user/service payload bodies are now loaded as flat32 binaries into
    # init-package memory and entered through manifest addresses.

    a.label("pm_syscall80")
    a.emit(0x66, 0xB8, 0x10, 0x00)                    # restore kernel data selector
    for reg in [0xD8, 0xC0, 0xE0, 0xE8]:              # ds, es, fs, gs
        a.emit(0x8E, reg)
    emit_pm_cmp_mem32_imm32(a, heap_base + 0x3C, 0x0001)
    pm_je_label("pm_syscall_provider")
    emit_pm_cmp_mem32_imm32(a, heap_base + 0x3C, 0x0002)
    pm_je_label("pm_syscall_trusted")
    emit_pm_cmp_mem32_imm32(a, heap_base + 0x3C, 0x0003)
    pm_je_label("pm_syscall_fluid_yield")
    emit_pm_cmp_mem32_imm32(a, heap_base + 0x3C, 0x0004)
    pm_je_label("pm_syscall_switch_return")
    emit_pm_cmp_mem32_imm32(a, heap_base + 0x3C, 0x0005)
    pm_je_label("pm_syscall_guard_return")
    pm_print_label("pm_user_work_msg")
    pm_print_label("pm_user_syscall_msg")
    a.label("pm_kernel_after_syscall")
    pm_jmp_label("pm_kernel_after_syscall")

    a.label("pm_syscall_provider")
    emit_pm_store32(a, heap_base + 0x3C, 0x0000)
    pm_print_label("pm_provider_user_work_msg")
    pm_print_label("pm_provider_user_syscall_msg")
    pm_jmp_label("pm_provider_after_syscall")

    a.label("pm_syscall_trusted")
    emit_pm_store32(a, heap_base + 0x3C, 0x0000)
    pm_print_label("pm_trusted_user_work_msg")
    pm_print_label("pm_trusted_user_syscall_msg")
    pm_jmp_label("pm_trusted_after_syscall")

    a.label("pm_syscall_fluid_yield")
    emit_pm_store32(a, heap_base + 0x3C, 0x0000)
    emit_pm_store32(a, heap_base + 0x1CC, 0x0001)     # ctx[0] yielded once
    emit_pm_store32(a, heap_base + 0x190, 0x0001)     # scheduler cursor moves to provider
    emit_pm_store32(a, heap_base + 0x1F0, 0x0001)     # context_switch.count
    emit_pm_store32(a, heap_base + 0x1F4, 0x8000)     # switch.from fluid-init
    emit_pm_store32(a, heap_base + 0x1F8, 0x8001)     # switch.to provider
    pm_print_label("pm_user_work_msg")
    pm_print_label("pm_user_syscall_msg")
    pm_print_label("pm_yield_msg")
    pm_print_label("pm_context_switch_msg")
    emit_pm_store32(a, heap_base + 0x3C, 0x0004)     # syscall continuation: context switch probe
    pm_enter_cpl3_payload("pm_provider_switch_payload_entry", 0x0008E000)

    a.label("pm_provider_switch_payload_entry")
    emit_pm_store32(a, 0x000A0000 + 184 * 320 + 276, 0x0C0C0C0C)
    emit_pm_store32(a, heap_base + 0x1FC, 0x0001)     # switch target executed
    a.emit(0xCD, 0x80)
    a.label("pm_provider_switch_spin")
    pm_jmp_label("pm_provider_switch_spin")

    a.label("pm_syscall_switch_return")
    emit_pm_store32(a, heap_base + 0x3C, 0x0000)
    pm_print_label("pm_provider_switch_work_msg")
    pm_print_label("pm_provider_switch_syscall_msg")
    a.label("pm_kernel_after_yield")
    pm_jmp_label("pm_kernel_after_yield")

    a.label("pm_syscall_guard_return")
    emit_pm_store32(a, heap_base + 0x3C, 0x0000)
    pm_print_label("pm_pf_probe_return_msg")
    pm_jmp_label("pm_after_guard_probe")

    a.label("pm_page_fault")
    a.emit(0x60)                                      # pushad
    emit_pm_store32(a, heap_base + 0x444, 0x00000001) # page_fault.count
    emit_pm_store32(a, heap_base + 0x448, 0x00400000) # faulting linear address for guard probe
    emit_pm_store32(a, heap_base + 0x44C, 0x8001)     # provider-like user guard task
    emit_pm_store32(a, heap_base + 0x450, 0x00000001) # resolved by quarantine mapping/skipping
    emit_pm_store32(a, 0x00200004, 0x00205007)        # PDE[1] quarantine user page table
    emit_pm_store32(a, 0x00205000, 0x00206007)        # map 0x00400000 to scratch page
    a.emit(0xB8); a.emit(*(0x00200000).to_bytes(4, "little")) # reload cr3 to flush paging structures
    a.emit(0x0F, 0x22, 0xD8)
    pm_print_label("pm_page_fault_msg")
    a.emit(0x83, 0x44, 0x24, 0x24, 0x0A)              # add dword [esp+36], 10
    a.emit(0x61, 0x83, 0xC4, 0x04, 0xCF)              # popad; add esp,4; iretd

    a.label("pm_irq0_timer")
    a.emit(0x60)                                      # pushad
    a.emit(0xFF, 0x05); a.emit(*((heap_base + 0x194).to_bytes(4, "little"))) # inc [tick_count]
    emit_pm_store32(a, heap_base + 0x198, 0x0020)     # last_irq_vector
    a.emit(0xFF, 0x05); a.emit(*((heap_base + 0x19C).to_bytes(4, "little"))) # inc [quantum_count]
    a.emit(0xBA, 0x20, 0x00, 0x00, 0x00)              # mov edx, PIC1 command
    a.emit(0xB0, 0x20, 0xEE)                          # EOI
    a.emit(0x61, 0xCF)                                # popad; iretd

    a.label("pm_setup_paging")
    emit_pm_store32(a, 0x00200000, 0x00204007)        # PDE[0] -> identity page table, present/rw/user
    a.emit(0xBF); a.emit(*(0x00204000).to_bytes(4, "little")) # mov edi, page table
    a.emit(0xB8); a.emit(*(0x00000007).to_bytes(4, "little")) # mov eax, first user PTE flags
    a.emit(0xB9); a.emit(*(1024 .to_bytes(4, "little")))      # mov ecx, entries
    a.emit(0xAB, 0x05, 0x00, 0x10, 0x00, 0x00, 0xE2, 0xF8)   # stosd; add eax,4096; loop
    a.emit(0xB8); a.emit(*(0x00200000).to_bytes(4, "little")) # mov eax, page dir
    a.emit(0x0F, 0x22, 0xD8)                         # mov cr3, eax
    a.emit(0x0F, 0x20, 0xC0)                         # mov eax, cr0
    a.emit(0x0D, 0x00, 0x00, 0x00, 0x80)             # or eax, PG
    a.emit(0x0F, 0x22, 0xC0, 0xC3)                   # mov cr0,eax; ret

    a.label("pm_setup_timer")
    # Remap PIC to 0x20/0x28, unmask IRQ0 only, and program PIT channel 0 to ~100Hz.
    a.emit(0xBA, 0x20, 0x00, 0x00, 0x00, 0xB0, 0x11, 0xEE) # PIC1 ICW1
    a.emit(0xBA, 0xA0, 0x00, 0x00, 0x00, 0xB0, 0x11, 0xEE) # PIC2 ICW1
    a.emit(0xBA, 0x21, 0x00, 0x00, 0x00, 0xB0, 0x20, 0xEE) # PIC1 vector base
    a.emit(0xBA, 0xA1, 0x00, 0x00, 0x00, 0xB0, 0x28, 0xEE) # PIC2 vector base
    a.emit(0xBA, 0x21, 0x00, 0x00, 0x00, 0xB0, 0x04, 0xEE) # PIC1 has slave on IRQ2
    a.emit(0xBA, 0xA1, 0x00, 0x00, 0x00, 0xB0, 0x02, 0xEE) # PIC2 cascade id
    a.emit(0xBA, 0x21, 0x00, 0x00, 0x00, 0xB0, 0x01, 0xEE) # PIC1 8086 mode
    a.emit(0xBA, 0xA1, 0x00, 0x00, 0x00, 0xB0, 0x01, 0xEE) # PIC2 8086 mode
    a.emit(0xBA, 0x21, 0x00, 0x00, 0x00, 0xB0, 0xFE, 0xEE) # unmask IRQ0 only
    a.emit(0xBA, 0xA1, 0x00, 0x00, 0x00, 0xB0, 0xFF, 0xEE) # mask slave PIC
    a.emit(0xBA, 0x43, 0x00, 0x00, 0x00, 0xB0, 0x36, 0xEE) # PIT mode 3
    a.emit(0xBA, 0x40, 0x00, 0x00, 0x00, 0xB0, 0x9C, 0xEE) # divisor low
    a.emit(0xB0, 0x2E, 0xEE, 0xC3)                    # divisor high; ret

    a.label("pm_bump_alloc")
    a.emit(0xA1); a.emit(*((heap_base + 0x24).to_bytes(4, "little")))  # mov eax, [allocator.next]
    a.emit(0x89, 0xC2)                                # mov edx, eax
    a.emit(0x01, 0xCA)                                # add edx, ecx
    a.emit(0x89, 0x15); a.emit(*((heap_base + 0x24).to_bytes(4, "little"))) # mov [allocator.next], edx
    a.emit(0xC3)

    a.label("pm_fb_rect")
    a.emit(0x89, 0xCD)                                # mov ebp, ecx
    a.emit(0x89, 0xD7)                                # mov edi, edx
    a.emit(0x69, 0xFF, 0x40, 0x01, 0x00, 0x00)        # imul edi, edi, 320
    a.emit(0x01, 0xDF)                                # add edi, ebx
    a.emit(0x81, 0xC7, 0x00, 0x00, 0x0A, 0x00)        # add edi, 0xA0000
    a.label("pm_fb_rect_row")
    a.emit(0x89, 0xE9)                                # mov ecx, ebp
    a.emit(0xF3, 0xAA)                                # rep stosb
    a.emit(0x81, 0xC7, 0x40, 0x01, 0x00, 0x00)        # add edi, 320
    a.emit(0x29, 0xEF)                                # sub edi, ebp
    a.emit(0x4E)                                      # dec esi
    pm_jne_label("pm_fb_rect_row")
    a.emit(0xC3)

    a.label("pm_serial_print")
    # lodsb; test al,al; jz done; call putc; jmp loop; ret
    a.label("pm_print_loop")
    a.emit(0xAC, 0x84, 0xC0, 0x74, 0x07)
    call_putc_pos = len(a.code); a.emit(0xE8, 0, 0, 0, 0)
    a.emit(0xEB, 0xF4)
    a.emit(0xC3)
    a.label("pm_serial_putc")
    a.emit(0x50)                                      # push eax
    a.emit(0xBA, 0xFD, 0x03, 0x00, 0x00)              # mov edx, 0x3fd
    a.label("pm_wait")
    a.emit(0xEC, 0xA8, 0x20, 0x74, 0xFB)              # in/test/jz
    a.emit(0x58)                                      # pop eax
    a.emit(0xBA, 0xF8, 0x03, 0x00, 0x00)              # mov edx, 0x3f8
    a.emit(0xEE, 0xC3)                                # out dx, al; ret
    a.label("pm_wait_key")
    a.emit(0xBA, 0x64, 0x00, 0x00, 0x00)              # mov edx, 0x64
    a.label("pm_wait_key_ready")
    a.emit(0xEC, 0xA8, 0x01, 0x74, 0xFB)              # in/test/jz
    a.emit(0xBA, 0x60, 0x00, 0x00, 0x00)              # mov edx, 0x60
    a.emit(0xEC, 0xC3)                                # in al, dx; ret
    a.label("pm_ps2_wait_write")
    a.emit(0xBA, 0x64, 0x00, 0x00, 0x00)              # mov edx, 0x64
    a.label("pm_ps2_wait_write_loop")
    a.emit(0xEC, 0xA8, 0x02, 0x75, 0xFB)              # in/test/jnz
    a.emit(0xC3)
    a.label("pm_enable_mouse")
    pm_call_label("pm_ps2_wait_write")
    a.emit(0xBA, 0x64, 0x00, 0x00, 0x00, 0xB0, 0xA8, 0xEE) # enable aux
    pm_call_label("pm_ps2_wait_write")
    a.emit(0xBA, 0x64, 0x00, 0x00, 0x00, 0xB0, 0xD4, 0xEE) # next byte to mouse
    pm_call_label("pm_ps2_wait_write")
    a.emit(0xBA, 0x60, 0x00, 0x00, 0x00, 0xB0, 0xF4, 0xEE, 0xC3) # enable streaming
    a.label("pm_msg")
    a.text(
        "Fluid Kernel Stage C protected-mode online\r\n"
        "kernel.mode protected bits=32 gdt=flat\r\n"
        "kernel.memory next=allocator object_records=ready\r\n"
        "kernel.alloc bump base=00100000 next=00100140 record_bytes=320 runtime_next=00100180\r\n"
        "kernel.page.alloc.pm base=00200000 page_size=4096 total=64 bitmap=00100420 free=58 used=6 status=ready\r\n"
        "kernel.paging.pm cr0.pg=1 cr3=00200000 identity=0-003FFFFF page_table=00204000 user_exec=1 fault_vector=0E status=enabled\r\n"
        "kernel.vm.space.pm count=3 init.cr3=00201000 provider.cr3=00202000 trusted.cr3=00203000 kernel_shared=00100000-0010FFFF user_isolated=1 status=ready\r\n"
        "kernel.vm.map.pm task=8000 entry=00102000 stack=0008F000 cr3=00201000 perms=user.rx|user.rw source=page-table\r\n"
        "kernel.vm.map.pm task=8001 entry=00102100 stack=0008E000 cr3=00202000 perms=user.rx|user.rw source=page-table\r\n"
        "kernel.vm.map.pm task=8002 entry=00102200 stack=0008D000 cr3=00203000 perms=user.rx|user.rw trusted=1 source=page-table\r\n"
        "kernel.vm.guard.pm task=8001 denied=kernel.heap target=00100000 policy=user-no-kernel-write trap=simulated status=blocked\r\n"
        "kernel.object.pm task{id=1001,state=created} cap{id=2002,risk=critical} trusted{id=6001,state=none} interface{id=4001,state=projected}\r\n"
        "kernel.ipc.queue.pm provider=00100380 trusted=001003C0 slots=4 record_bytes=16 protocol=capability-call-ring head_tail=runtime-owned\r\n"
        "kernel.task.pm provider{id=8001,cap=food.createOrder,state=ready} trusted{id=8002,cap=payment.confirmAndPay,state=ready}\r\n"
        "kernel.graph_ring.pm base=00100080 slots=10 record_bytes=16\r\n"
        "kernel.graph_ring.pm slot0{c=1,t=task.created,s=1001,state=created} slot1{c=2,t=cap.registered,s=2002,state=registered} slot2{c=3,t=trusted_surface.created,s=6001,state=awaiting}\r\n"
        "graph stagec.protected_mode_entered source=cr0.pe\r\n"
        "graph stagec.allocator_ready source=protected-mode records=task,capability,trusted\r\n"
    )
    a.label("pm_flush_msg")
    a.text("kernel.graph_flush.pm source=ring walker=type-subject-dispatch from=0 to=2\r\n")
    a.label("pm_graph_task_created")
    a.text("graph task.created id=task.stagec.demo source=pm.ring.subject\r\n")
    a.label("pm_graph_cap_registered")
    a.text("graph capability.registered id=payment.confirmAndPay source=pm.ring.subject\r\n")
    a.label("pm_graph_trusted_created")
    a.text("graph trusted_surface.created capability=payment.confirmAndPay source=pm.ring.subject\r\n")
    a.label("pm_ring_done_msg")
    a.text("graph stagec.ring_ready source=protected-mode walker=type-subject-dispatch records=task,capability,trusted\r\n")
    a.label("pm_surface_home_msg")
    a.text("kernel.surface.pm renderer=packed-framebuffer mode=320x200x8 phase=home visual=agent-cards colors=blue-green source=projection-ir projection=1F4001\r\n")
    a.label("pm_initpkg_msg")
    a.text("kernel.initpkg.pm magic=F17D0200 files=3 format=flat32-binaries source=boot-package state=loaded\r\n")
    a.label("pm_loader_flatbin_msg")
    a.text("kernel.loader.flatbin.pm copied=3 init=00102000:init32 provider=00102100:provider32 trusted=00102200:trusted32 entry_source=manifest status=ok\r\n")
    a.label("pm_payload_map_msg")
    a.text("kernel.payload.map.pm init=00102000 provider=00102100 trusted=00102200 format=flat32-loaded state=mapped source=initpkg\r\n")
    a.label("pm_initramfs_msg")
    a.text("kernel.initramfs.pm magic=F17D0001 files=3 init=00102000 provider=00102100 trusted=00102200 state=mapped payload_source=initpkg\r\n")
    a.label("pm_initramfs_manifest_msg")
    a.text("kernel.initramfs.manifest.pm version=F17D0100 entries=3 names=fluid-init,provider.food,trusted.pay format=flat32-table entry_source=loaded-binaries\r\n")
    a.label("pm_initramfs_lookup_init_msg")
    a.text("kernel.initramfs.lookup.pm name=fluid-init task=8000 entry=00102000 stack=0008f000 status=found source=manifest-flatbin\r\n")
    a.label("pm_cap_handle_table_msg")
    a.text("kernel.cap.table.pm handles=2 h0=C001F00D:food.createOrder:provider8001 h1=C002FA17:payment.confirmAndPay:trusted8002 namespace=opaque\r\n")
    a.label("pm_cap_open_food_msg")
    a.text("kernel.cap.open.pm task=1001 cap=food.createOrder provider=8001 handle=C001F00D authority=sess.runtime status=granted\r\n")
    a.label("pm_cap_open_pay_msg")
    a.text("kernel.cap.open.pm task=1001 cap=payment.confirmAndPay provider=8002 handle=C002FA17 authority=sess.trusted-ui status=granted requires_trusted_surface=1\r\n")
    a.label("pm_security_negative_msg")
    a.text("kernel.cap.open.pm task=1001 cap=food.deleteOrder provider=none handle=00000000 authority=sess.runtime status=denied reason=no-provider source=capability-table\r\nkernel.cap.call.pm handle=DEAD0000 cap=food.createOrder task=1001 status=denied reason=invalid-handle source=capability-table\r\ngraph capability.denied cap=food.createOrder reason=invalid-handle source=pm.capability\r\nkernel.trusted.enforce.pm surface=4001 type=generated action=payment.confirmAndPay status=denied reason=requires-trusted-surface trusted_surface=6001 source=surface-authority\r\ngraph trusted.denied capability=payment.confirmAndPay surface=generated reason=requires-trusted-surface source=pm.authority\r\nkernel.copyin.pm syscall=sys_cap_call task=1001 user_ptr=FFFFF000 len=64 status=denied reason=user-range-invalid source=copyin-validator\r\nkernel.copyout.pm syscall=sys_cap_call task=1001 user_ptr=00100000 len=64 status=denied reason=kernel-range target=kernel.heap source=copyout-validator\r\ngraph syscall.denied name=sys_cap_call reason=bad-user-pointer direction=copyin source=pm.syscall\r\ngraph syscall.denied name=sys_cap_call reason=kernel-range direction=copyout source=pm.syscall\r\nkernel.security.negative.pm cap_invalid=blocked generated_trusted=blocked copyin_badptr=blocked copyout_kernel=blocked record=0010046C status=ok\r\n")
    a.label("pm_pci_scan_msg")
    a.text("kernel.pci.scan.pm method=config-mechanism-1 bus=0 device=3 function=0 vendor=1AF4 device_id=1000 class=020000 command=0007 status=matched source=ioports-cf8-cfc\r\n")
    a.label("pm_virtio_config_msg")
    a.text("kernel.virtio.net.config.pm status=ACKNOWLEDGE|DRIVER|FEATURES_OK|DRIVER_OK queue=0 io_base=bar0 source=pci-config status_reg=0000000F pci_command=0007\r\n")
    a.label("pm_virtio_queue_msg")
    a.text("kernel.virtio.net.queue.pm rxq=0 txq=1 ring=programmed qsize=256 rx_pfn=00105 tx_pfn=00109 pfn_record=00100338 notify=prepared status=ready\r\n")
    a.label("pm_virtio_dma_msg")
    a.text("kernel.virtio.net.dma.pm rx_ring=00105000 tx_ring=00109000 qsize=256 avail=1 used_sample=0010B000 mode=legacy-split status=programmed source=ioports\r\n")
    a.label("pm_virtio_vring_msg")
    a.text("kernel.virtio.net.vring.pm rx.desc0=0010D000:len1600:write tx.desc0=0010E000:len64:read tx.desc1=0010F000:len64:read rx.avail=00106000 tx.avail=0010A000 tx.used=0010B000 frame=0010E000 status=initialized source=kernel-memory\r\n")
    a.label("pm_net_frame_msg")
    a.text("kernel.net.ether.pm handle=0F00D001 tx_frame=0010E000 len=64 ethertype=0806 kind=arp-request status=queued source=sys_net_send\r\n")
    a.label("pm_virtio_notify_msg")
    a.text("kernel.virtio.net.notify.pm queue=rx,tx indexes=0,1 notify_port=io_base+10 count=3 tx_used_sample=read isr_sample=read status=attempted source=legacy-io\r\n")
    a.label("pm_net_rx_msg")
    a.text("kernel.net.arp.reply.pm handle=0F00D001 rx_buffer=0010D000 used_ring=00107000 op=0002 sender=10.0.2.2 target=10.0.2.15 status=received source=virtio-rx\r\n")
    a.label("pm_net_udp_msg")
    a.text("kernel.net.udp.pm handle=0F00D001 tx_frame=0010F000 src=10.0.2.15:40000 dst=10.0.2.3:53 query=example.com status=sent source=sys_net_send\r\n")
    a.label("pm_net_dns_rx_msg")
    a.text("kernel.net.dns.reply.pm handle=0F00D001 rx_buffer=00110000 used_ring=00107000 src=10.0.2.3:53 dst=10.0.2.15:40000 query=example.com status=received source=virtio-rx\r\n")
    a.label("pm_net_graph_msg")
    a.text("graph net.device.discovered vendor=1AF4 device=1000 source=pm.pci\r\ngraph net.opened handle=0F00D001 owner=provider.food source=pm.capability\r\ngraph net.queue.ready driver=virtio-net source=pm.virtqueue\r\ngraph net.send handle=0F00D001 bytes=64 ethertype=0806 source=sys_net_send\r\ngraph net.send handle=0F00D001 bytes=64 ethertype=0800 proto=udp source=sys_net_send\r\ngraph net.udp.send dst=10.0.2.3:53 query=example.com source=sys_net_send\r\ngraph net.recv.poll handle=0F00D001 budget=1 source=sys_net_recv\r\ngraph net.recv handle=0F00D001 bytes=64 ethertype=0806 source=virtio-rx\r\ngraph net.arp.reply sender=10.0.2.2 target=10.0.2.15 source=virtio-rx\r\ngraph net.recv handle=0F00D001 bytes=425 ethertype=0800 proto=udp source=virtio-rx\r\ngraph net.dns.reply src=10.0.2.3:53 query=example.com source=virtio-rx\r\ngraph net.rx.notify queue=0 source=pm.virtio-io\r\ngraph net.tx.notify queue=1 source=pm.virtio-io\r\ngraph net.isr.sampled source=pm.virtio-io\r\n")
    a.label("pm_net_device_msg")
    a.text("kernel.net.device.pm bus=pci vendor=1AF4 device=1000 driver=virtio-net status=discovered mode=pci-config-read+legacy-io qemu=virtio-net-pci\r\n")
    a.label("pm_net_handle_msg")
    a.text("kernel.net.open.pm owner=provider.food task=8001 handle=0F00D001 policy=provider-network scope=food-api status=granted qemu_netdev=fluidnet\r\n")
    a.label("pm_projection_home_msg")
    a.text("kernel.interface.projection.pm id=1F4001 task=1001 phase=home nodes=3 action=C001F00D source=agent-generated-ir\r\n")
    a.label("pm_surface_home_projection_msg")
    a.text("kernel.surface.project.pm surface=4001 projection=1F4001 renderer=packed-framebuffer nodes=3 action=C001F00D status=presented\r\n")
    a.label("pm_runqueue_msg")
    a.text("kernel.scheduler.runqueue.pm count=3 rq0=fluid-init:8000 rq1=provider:8001 rq2=trusted:8002 policy=round-robin\r\n")
    a.label("pm_context_table_msg")
    a.text("kernel.scheduler.context.pm slots=3 ctx0=fluid-init:eip00102000:esp0008f000 ctx1=provider:eip00102100:esp0008e000 ctx2=trusted:eip00102200:esp0008d000 state=ready\r\n")
    a.label("pm_scheduler_boot_msg")
    a.text("kernel.scheduler.pick.pm cursor=0 task=fluid-init id=8000 reason=boot\r\n")
    a.label("pm_timer_ready_msg")
    a.text("kernel.timer.pit.pm hz=100 irq=0 vector=20 status=enabled source=hardware-timer\r\n")
    a.label("pm_timer_tick_msg")
    a.text("kernel.scheduler.tick.pm irq=0 vector=20 ticks>=2 current=fluid-init next=provider source=pit\r\n")
    a.label("pm_init_dispatch_msg")
    a.text("kernel.task.dispatch.pm from=kernel to=fluid-init id=8000 entry=00102000 state=started\r\n")
    a.label("pm_pf_probe_enter_msg")
    a.text("kernel.vm.guard_probe.pm task=8001 target=00400000 expected=page-fault source=cpl3-probe status=armed\r\n")
    a.label("pm_page_fault_msg")
    a.text("kernel.page_fault.pm vector=0E task=8001 addr=00400000 error=user-write-nonpresent action=blocked_resume status=handled\r\ngraph vm.guard_fault task=8001 addr=00400000 policy=user-no-kernel-write source=page-fault\r\n")
    a.label("pm_pf_probe_return_msg")
    a.text("kernel.vm.guard_probe.pm task=8001 target=00400000 result=fault-handled continued=1 status=ok\r\n")
    a.label("pm_pointer_ready_msg")
    a.text("kernel.input.pointer.pm driver=ps2 status=enabled mode=polling source=protected-mode\r\n")
    a.label("pm_pointer_event_msg")
    a.text("kernel.object_transition.pm pointer{packets=1,buttons=0} source=ps2\r\ngraph input.pointer event=packet source=pm.ps2\r\n")
    a.label("pm_choose_msg")
    a.text(
        "kernel.alloc.dynamic.pm object=order addr=00100140 bytes=32 next=00100160\r\n"
        "kernel.object_transition.pm input{last=1} order{id=5001,state=created,cap=food.createOrder} trusted{id=6001,state=awaiting,cap=payment.confirm} ring_head=6\r\n"
        "kernel.graph_ring.pm slot3{c=4,t=input.key,s=1,state=pressed} slot4{c=5,t=capability.called,s=5001,state=ok} slot5{c=6,t=trusted_surface.created,s=6001,state=awaiting}\r\n"
    )
    a.label("pm_choose_flush_msg")
    a.text("kernel.graph_flush.pm source=ring walker=type-subject-dispatch from=3 to=5\r\n")
    a.label("pm_cap_call_food_msg")
    a.text("kernel.cap.call.pm handle=C001F00D cap=food.createOrder task=1001 req=9001 route=provider.queue authority=sess.runtime status=accepted\r\n")
    a.label("pm_provider_ipc_send_msg")
    a.text("kernel.ipc.enqueue.pm queue=provider req=9001 slot=0 tail=1 handle=C001F00D cap=food.createOrder payload=choice.spice_lab source=capability-handle\r\n")
    a.label("pm_initramfs_lookup_provider_msg")
    a.text("kernel.initramfs.lookup.pm name=provider.food task=8001 entry=00102100 stack=0008e000 status=found source=manifest-flatbin reason=capability-call req=9001\r\n")
    a.label("pm_scheduler_provider_msg")
    a.text("kernel.scheduler.pick.pm cursor=1 task=provider id=8001 reason=capability-call req=9001 via=context-switch\r\n")
    a.label("pm_provider_context_switch_msg")
    a.text("kernel.scheduler.context_switch.pm from=fluid-runtime:8000 to=provider:8001 via=iretd target_cpl=3 count=2 reason=capability-call req=9001\r\n")
    a.label("pm_vm_switch_provider_msg")
    a.text("kernel.vm.switch.pm task=8001 cr3=00202000 from=runtime reason=capability-call status=loaded\r\n")
    a.label("pm_provider_task_dispatch_msg")
    a.text("kernel.task.dispatch.pm from=kernel to=provider.task id=8001 req=9001 isolation=task-boundary address_space=00202000\r\n")
    a.label("pm_provider_user_enter_msg")
    a.text("kernel.user.enter.pm payload=provider cpl=3 entry=00102100 source=initpkg-flatbin req=9001 via=context-switch\r\n")
    a.label("pm_provider_user_work_msg")
    a.text("kernel.user.work.pm payload=provider cpl=3 req=9001\r\n")
    a.label("pm_provider_user_syscall_msg")
    a.text("kernel.syscall.pm from=provider vector=80 continued req=9001\r\n")
    a.label("pm_net_provider_msg")
    a.text("kernel.net.provider.pm handle=0F00D001 owner=provider.food tx=1 rx_poll=1 protocol=sys_net_dns endpoint=food-api.local query=example.com dns_reply=1 answer=93.184.216.34 status=resolved writer=cpl3.provider\r\nkernel.provider.dns.parse.pm task=8001 rx_buffer=00110000 frame_len=435 qtype=A qname=example.com answer=93.184.216.34 status=parsed writer=cpl3.provider\r\nkernel.provider.result.object.pm addr=0010047C magic=F17D4401 cap=food.createOrder order=5001 source=dns-parser answer=93.184.216.34 status=ready owner=provider.food\r\ngraph net.provider.txrx handle=0F00D001 tx=1 rx_poll=1 owner=provider.food protocol=dns source=cpl3.provider.sys_net\r\ngraph provider.dns.parsed qname=example.com answer=93.184.216.34 source=cpl3.provider.parser\r\ngraph provider.result food.createOrder source=provider-result-object query=example.com answer=93.184.216.34 order=5001 writer=cpl3.provider\r\n")
    a.label("pm_provider_ipc_reply_verify_msg")
    a.text("kernel.ipc.dequeue.pm queue=provider req=9001 slot=0 head=1 status=ok order=5001 writer=cpl3.provider verifier=kernel\r\n")
    a.label("pm_provider_ipc_reply_msg")
    a.text("kernel.ipc.reply.pm queue=provider req=9001 slot=0 status=ok order=5001 handler=provider.task.8001 writer=cpl3.provider\r\n")
    a.label("pm_graph_input_1")
    a.text("graph input.key value=1 source=pm.ring.subject\r\n")
    a.label("pm_graph_cap_called")
    a.text("graph capability.called food.createOrder provider=provider.food.network source=pm.ring.subject result=provider-result-object order=5001\r\ngraph interface.updated id=1F4002 task=1001 provider_result=provider-result-object order=5001 source=agent-projection\r\n")
    a.label("pm_projection_trusted_msg")
    a.text("kernel.interface.projection.pm id=1F4002 task=1001 phase=trusted nodes=2 action=C002FA17 trust=trusted-surface provider_result=provider-result-object order=5001 source=agent-generated-ir\r\n")
    a.label("pm_surface_trusted_msg")
    a.text("kernel.surface.pm renderer=packed-framebuffer mode=320x200x8 phase=trusted visual=trusted-modal colors=red-white source=projection-ir projection=1F4002\r\n")
    a.label("pm_confirm_msg")
    a.text(
        "kernel.alloc.dynamic.pm object=receipt addr=00100160 bytes=32 next=00100180\r\n"
        "kernel.object_transition.pm input{last=y} trusted{id=6001,state=confirmed} receipt{id=7001,state=created,order=5001} task{id=1001,state=completed} ring_head=10\r\n"
        "kernel.graph_ring.pm slot6{c=7,t=input.key,s=2,state=pressed} slot7{c=8,t=trusted.confirmed,s=6001,state=confirmed} slot8{c=9,t=receipt.created,s=7001,state=created} slot9{c=10,t=task.completed,s=1001,state=completed}\r\n"
    )
    a.label("pm_confirm_flush_msg")
    a.text("kernel.graph_flush.pm source=ring walker=type-subject-dispatch from=6 to=9\r\n")
    a.label("pm_cap_call_pay_msg")
    a.text("kernel.cap.call.pm handle=C002FA17 cap=payment.confirmAndPay task=1001 req=9002 route=trusted.queue authority=sess.trusted-ui status=accepted trusted_surface=6001\r\n")
    a.label("pm_trusted_ipc_send_msg")
    a.text("kernel.ipc.enqueue.pm queue=trusted req=9002 slot=0 tail=1 handle=C002FA17 cap=payment.confirmAndPay payload=order.5001 source=capability-handle trusted-surface=6001\r\n")
    a.label("pm_initramfs_lookup_trusted_msg")
    a.text("kernel.initramfs.lookup.pm name=trusted.pay task=8002 entry=00102200 stack=0008d000 status=found source=manifest-flatbin reason=trusted-gate req=9002\r\n")
    a.label("pm_scheduler_trusted_msg")
    a.text("kernel.scheduler.pick.pm cursor=2 task=trusted id=8002 reason=trusted-gate req=9002 via=context-switch\r\n")
    a.label("pm_trusted_context_switch_msg")
    a.text("kernel.scheduler.context_switch.pm from=fluid-runtime:8000 to=trusted:8002 via=iretd target_cpl=3 count=3 reason=trusted-gate req=9002\r\n")
    a.label("pm_vm_switch_trusted_msg")
    a.text("kernel.vm.switch.pm task=8002 cr3=00203000 from=runtime reason=trusted-gate status=loaded\r\n")
    a.label("pm_trusted_task_dispatch_msg")
    a.text("kernel.task.dispatch.pm from=kernel to=trusted.task id=8002 req=9002 isolation=trusted-task-boundary address_space=00203000\r\n")
    a.label("pm_trusted_user_enter_msg")
    a.text("kernel.user.enter.pm payload=trusted cpl=3 entry=00102200 source=initpkg-flatbin req=9002 via=context-switch\r\n")
    a.label("pm_trusted_user_work_msg")
    a.text("kernel.user.work.pm payload=trusted cpl=3 req=9002\r\n")
    a.label("pm_trusted_user_syscall_msg")
    a.text("kernel.syscall.pm from=trusted vector=80 continued req=9002\r\n")
    a.label("pm_trusted_ipc_reply_verify_msg")
    a.text("kernel.ipc.dequeue.pm queue=trusted req=9002 slot=0 head=1 status=confirmed receipt=7001 writer=cpl3.trusted verifier=kernel\r\n")
    a.label("pm_trusted_ipc_reply_msg")
    a.text("kernel.ipc.reply.pm queue=trusted req=9002 slot=0 status=confirmed receipt=7001 handler=trusted.task.8002 writer=cpl3.trusted\r\n")
    a.label("pm_graph_input_y")
    a.text("graph input.key value=y source=pm.ring.subject\r\n")
    a.label("pm_graph_trusted_confirmed")
    a.text("graph trusted.confirmed session=sess.trusted-ui capability=payment.confirmAndPay source=pm.ring.subject\r\n")
    a.label("pm_graph_receipt_created")
    a.text("graph receipt.created order=order.demo.0001 source=pm.ring.subject\r\n")
    a.label("pm_graph_task_completed")
    a.text("graph task.completed id=task.stagec.demo source=pm.ring.subject\r\n")
    a.label("pm_projection_receipt_msg")
    a.text("kernel.interface.projection.pm id=1F4003 task=1001 phase=receipt nodes=2 receipt=7001 source=agent-generated-ir\r\n")
    a.label("pm_debug_overlay_msg")
    a.text("kernel.debug.overlay.pm surface=debug-graph nodes=5 edges=4 events=task,capability,provider,trusted,receipt renderer=packed-framebuffer y=0 status=visible\r\n")
    a.label("pm_surface_receipt_msg")
    a.text("kernel.surface.pm renderer=packed-framebuffer mode=320x200x8 phase=receipt visual=success-receipt colors=green source=projection-ir projection=1F4003 debug_overlay=visible\r\n")
    a.label("pm_halt_msg")
    a.text("graph kernel.halt reason=escape source=protected-mode\r\n")
    a.label("pm_user_enter_msg")
    a.text("kernel.user.enter.pm payload=fluid-init entry=00102000 source=initpkg-flatbin cs=001b ds=0023 via=iretd target_cpl=3\r\n")
    a.label("pm_vm_switch_init_msg")
    a.text("kernel.vm.switch.pm task=8000 cr3=00201000 from=kernel reason=fluid-init-yield status=loaded\r\n")
    a.label("pm_user_work_msg")
    a.text("kernel.user.work.pm payload=fluid-init wrote=framebuffer marker=0d0d0d0d cpl=3\r\n")
    a.label("pm_user_syscall_msg")
    a.text("kernel.syscall.pm from=fluid-init vector=80 status=returned-to-kernel evidence=serial\r\n")
    a.label("pm_yield_msg")
    a.text("kernel.scheduler.yield.pm from=fluid-init id=8000 next=provider id=8001 ctx0.yields=1 source=syscall80\r\n")
    a.label("pm_context_switch_msg")
    a.text("kernel.scheduler.context_switch.pm from=fluid-init:8000 to=provider:8001 via=iretd target_cpl=3 count=1 reason=yield\r\n")
    a.label("pm_provider_switch_work_msg")
    a.text("kernel.user.work.pm payload=provider-switch cpl=3 ctx=provider marker=0c0c0c0c\r\n")
    a.label("pm_provider_switch_syscall_msg")
    a.text("kernel.syscall.pm from=provider-switch vector=80 status=returned-to-kernel ctx=provider\r\n")

    # Manual patches after labels.
    gdt_base = STAGE2_LOAD + a.labels["gdt_start"]
    a.code[gdt_base_patch:gdt_base_patch+4] = bytes([gdt_base & 0xFF, (gdt_base >> 8) & 0xFF, (gdt_base >> 16) & 0xFF, (gdt_base >> 24) & 0xFF])
    tss_base = STAGE2_LOAD + a.labels["tss32"]
    a.code[tss_desc_patch:tss_desc_patch+8] = bytes([
        0x67, 0x00,
        tss_base & 0xFF, (tss_base >> 8) & 0xFF,
        (tss_base >> 16) & 0xFF, 0x89, 0x00, (tss_base >> 24) & 0xFF,
    ])
    # TSS esp0/ss0 for privilege transitions from CPL3 back to the kernel.
    tss_off = a.labels["tss32"]
    a.code[tss_off + 4:tss_off + 8] = bytes([0x00, 0x00, 0x09, 0x00])
    a.code[tss_off + 8:tss_off + 12] = bytes([0x10, 0x00, 0x00, 0x00])
    a.code[tss_off + 102:tss_off + 104] = bytes([0x68, 0x00])
    idt_base = STAGE2_LOAD + a.labels["idt_start"]
    a.code[idt_base_patch:idt_base_patch+4] = bytes([idt_base & 0xFF, (idt_base >> 8) & 0xFF, (idt_base >> 16) & 0xFF, (idt_base >> 24) & 0xFF])
    a.code[lidt_patch:lidt_patch+4] = bytes([(STAGE2_LOAD + a.labels["idt_descriptor"]) & 0xFF, ((STAGE2_LOAD + a.labels["idt_descriptor"]) >> 8) & 0xFF, ((STAGE2_LOAD + a.labels["idt_descriptor"]) >> 16) & 0xFF, ((STAGE2_LOAD + a.labels["idt_descriptor"]) >> 24) & 0xFF])
    pf_addr = STAGE2_LOAD + a.labels["pm_page_fault"]
    idt0e_patch = a.labels["idt_start"] + 0x0E * 8
    a.code[idt0e_patch:idt0e_patch+8] = bytes([
        pf_addr & 0xFF, (pf_addr >> 8) & 0xFF,
        0x08, 0x00, 0x00, 0x8E,
        (pf_addr >> 16) & 0xFF, (pf_addr >> 24) & 0xFF,
    ])
    irq0_addr = STAGE2_LOAD + a.labels["pm_irq0_timer"]
    idt20_patch = a.labels["idt_start"] + 0x20 * 8
    a.code[idt20_patch:idt20_patch+8] = bytes([
        irq0_addr & 0xFF, (irq0_addr >> 8) & 0xFF,
        0x08, 0x00, 0x00, 0x8E,
        (irq0_addr >> 16) & 0xFF, (irq0_addr >> 24) & 0xFF,
    ])
    syscall_addr = STAGE2_LOAD + a.labels["pm_syscall80"]
    a.code[idt80_patch:idt80_patch+8] = bytes([
        syscall_addr & 0xFF, (syscall_addr >> 8) & 0xFF,
        0x08, 0x00, 0x00, 0xEE,
        (syscall_addr >> 16) & 0xFF, (syscall_addr >> 24) & 0xFF,
    ])
    pm_putc_addr = STAGE2_LOAD + a.labels["pm_serial_putc"]
    rel = pm_putc_addr - (STAGE2_LOAD + call_putc_pos + 5)
    a.code[call_putc_pos+1:call_putc_pos+5] = bytes([rel & 0xFF, (rel >> 8) & 0xFF, (rel >> 16) & 0xFF, (rel >> 24) & 0xFF])
    for pos, label in pm_abs32_patches:
        addr = STAGE2_LOAD + a.labels[label]
        a.code[pos:pos+4] = bytes([addr & 0xFF, (addr >> 8) & 0xFF, (addr >> 16) & 0xFF, (addr >> 24) & 0xFF])
    for pos, label in pm_rel32_patches:
        rel = (STAGE2_LOAD + a.labels[label]) - (STAGE2_LOAD + pos + 4)
        a.code[pos:pos+4] = bytes([rel & 0xFF, (rel >> 8) & 0xFF, (rel >> 16) & 0xFF, (rel >> 24) & 0xFF])

    data = bytearray(a.patch())
    max_len = STAGE2_SECTORS * 512
    if len(data) > max_len:
        raise SystemExit(f"stagec too large: {len(data)} > {max_len}")
    data.extend(b"\0" * (max_len - len(data)))
    return bytes(data)


def main() -> int:
    stage1 = build_stage1()
    stage2 = build_stage2()
    image = bytearray(stage1 + stage2)
    image.extend(b"\0" * (1440 * 1024 - len(image)))
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_bytes(image)
    print(f"built {OUT} ({len(image)} bytes, stage2={len(stage2)} bytes)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
