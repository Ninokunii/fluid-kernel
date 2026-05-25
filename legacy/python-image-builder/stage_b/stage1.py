from __future__ import annotations
from asm16 import Asm16, add_serial_routines

STAGE2_LOAD = 0x8000
STAGE2_SECTORS = 16


def build_stage1() -> bytes:
    a = Asm16(0x7C00)
    a.emit(0xFA, 0x31, 0xC0, 0x8E, 0xD8, 0x8E, 0xC0, 0x8E, 0xD0)
    a.emit(0xBC); a.imm16(0x7C00); a.emit(0xFB)
    for port, val in [(0x03F9,0),(0x03FB,0x80),(0x03F8,3),(0x03F9,0),(0x03FB,3),(0x03FA,0xC7),(0x03FC,0x0B)]:
        a.emit(0xBA); a.imm16(port); a.emit(0xB0, val, 0xEE)
    a.emit(0xB2, 0x00)                         # mov dl,0 (floppy A)
    a.emit(0x88, 0x16); a.abs16("boot_drive")  # mov [boot_drive], dl
    a.emit(0xBE); a.abs16("boot_msg"); a.call("serial_print")
    a.emit(0xB4, 0x00)                         # reset disk
    a.emit(0x8A, 0x16); a.abs16("boot_drive")
    a.emit(0xCD, 0x13)
    a.emit(0x31, 0xC0, 0x8E, 0xC0)             # es=0
    a.emit(0xBB); a.imm16(STAGE2_LOAD)
    a.emit(0xB4, 0x02)                         # read sectors
    a.emit(0xB0, STAGE2_SECTORS)
    a.emit(0xB5, 0x00, 0xB1, 0x02, 0xB6, 0x00) # CHS 0/0/2
    a.emit(0x8A, 0x16); a.abs16("boot_drive")
    a.emit(0xCD, 0x13)
    a.jc("disk_error")
    a.emit(0xEA); a.imm16(STAGE2_LOAD); a.imm16(0x0000)
    a.label("disk_error")
    a.emit(0xBE); a.abs16("err_msg"); a.call("serial_print")
    a.label("hang"); a.emit(0xF4); a.jmp("hang")
    add_serial_routines(a)
    a.label("boot_msg"); a.text("Fluid stage1 loading stage2\r\n")
    a.label("err_msg"); a.text("graph boot.disk_error\r\n")
    a.label("boot_drive"); a.emit(0)
    data = bytearray(a.patch())
    if len(data) > 510:
        raise SystemExit(f"stage1 too large: {len(data)}")
    data.extend(b"\0" * (510 - len(data)))
    data.extend(b"\x55\xAA")
    return bytes(data)
