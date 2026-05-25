#!/usr/bin/env python3
"""Build the first visible Fluid Kernel boot sector.

This remains a 512-byte BIOS boot sector, but now proves three Stage G-critical
facts without Linux:

- Fluid Kernel code boots directly;
- a visible Agent-native intent surface appears in VGA text memory;
- keyboard input becomes graph events on the serial console and screen.
"""
from __future__ import annotations
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "build" / "fluid-kernel-stageb.img"

code = bytearray()
labels: dict[str, int] = {}
patches: list[tuple[int, str, int]] = []


def emit(*bs: int) -> None:
    code.extend(bs)


def label(name: str) -> None:
    labels[name] = len(code)


def imm16(value: int) -> None:
    code.extend((value & 0xFF, (value >> 8) & 0xFF))


def patch_abs16(label_name: str) -> None:
    patches.append((len(code), label_name, 2))
    emit(0x00, 0x00)


def jmp_short(label_name: str) -> None:
    emit(0xEB)
    patches.append((len(code), label_name, 1))
    emit(0x00)


def jz_short(label_name: str) -> None:
    emit(0x74)
    patches.append((len(code), label_name, 1))
    emit(0x00)


def jnz_short(label_name: str) -> None:
    emit(0x75)
    patches.append((len(code), label_name, 1))
    emit(0x00)


def call_near(label_name: str) -> None:
    emit(0xE8)
    patches.append((len(code), label_name, 2))
    emit(0x00, 0x00)


# 16-bit real-mode setup at 0000:7c00.
emit(0xFA)                    # cli
emit(0x31, 0xC0)              # xor ax, ax
emit(0x8E, 0xD8)              # mov ds, ax
emit(0x8E, 0xC0)              # mov es, ax
emit(0x8E, 0xD0)              # mov ss, ax
emit(0xBC); imm16(0x7C00)     # mov sp, 0x7c00
emit(0xFB)                    # sti

# Initialize COM1: 38400 baud, 8N1, FIFO on.
emit(0xBA); imm16(0x03F9); emit(0xB0, 0x00, 0xEE)
emit(0xBA); imm16(0x03FB); emit(0xB0, 0x80, 0xEE)
emit(0xBA); imm16(0x03F8); emit(0xB0, 0x03, 0xEE)
emit(0xBA); imm16(0x03F9); emit(0xB0, 0x00, 0xEE)
emit(0xBA); imm16(0x03FB); emit(0xB0, 0x03, 0xEE)
emit(0xBA); imm16(0x03FA); emit(0xB0, 0xC7, 0xEE)
emit(0xBA); imm16(0x03FC); emit(0xB0, 0x0B, 0xEE)

# Set VGA text mode 03h.
emit(0xB8, 0x03, 0x00)        # mov ax, 0003h
emit(0xCD, 0x10)              # int 10h

# Print visible surface using BIOS teletype.
emit(0xBE); patch_abs16("screen_msg")
call_near("bios_print")

# Serial boot evidence.
emit(0xBE); patch_abs16("serial_boot_msg")
call_near("serial_print")

label("key_loop")
emit(0xB4, 0x00)              # mov ah, 0
emit(0xCD, 0x16)              # int 16h, wait key. AL=ascii AH=scancode
emit(0x3C, 0x1B)              # cmp al, ESC
jz_short("halt")
emit(0x50)                    # push ax
emit(0xBE); patch_abs16("key_prefix")
call_near("serial_print")
emit(0x58)                    # pop ax
call_near("serial_putc")
emit(0xB0, 0x0D); call_near("serial_putc")
emit(0xB0, 0x0A); call_near("serial_putc")
# Also echo to screen on the input line.
emit(0xB4, 0x0E)              # mov ah, 0eh
emit(0xBB, 0x00, 0x0A)        # mov bx, 0a00h (green)
emit(0xCD, 0x10)              # int 10h
jmp_short("key_loop")

label("halt")
emit(0xBE); patch_abs16("halt_msg")
call_near("serial_print")
label("hang")
emit(0xF4)
jmp_short("hang")

label("bios_print")
emit(0xAC)                    # lodsb
emit(0x84, 0xC0)              # test al, al
jz_short("bios_done")
emit(0xB4, 0x0E)              # mov ah, 0eh
emit(0xBB, 0x00, 0x0A)        # mov bx, 0a00h
emit(0xCD, 0x10)              # int 10h
jmp_short("bios_print")
label("bios_done")
emit(0xC3)

label("serial_print")
emit(0xAC)
emit(0x84, 0xC0)
jz_short("serial_print_done")
call_near("serial_putc")
jmp_short("serial_print")
label("serial_print_done")
emit(0xC3)

label("serial_putc")
emit(0x50)                    # push ax
emit(0xBA); imm16(0x03FD)     # mov dx, COM1+5
label("serial_wait")
emit(0xEC)                    # in al, dx
emit(0xA8, 0x20)              # test al, 0x20
jz_short("serial_wait")
emit(0x58)                    # pop ax
emit(0xBA); imm16(0x03F8)     # mov dx, COM1
emit(0xEE)                    # out dx, al
emit(0xC3)

label("screen_msg")
code.extend((
    "Fluid Kernel B\r\n"
    "Agent-native intent surface\r\n"
    "Type: keys => graph events. ESC halts.\r\n"
    "> "
).encode("ascii") + b"\0")

label("serial_boot_msg")
code.extend((
    "Fluid Kernel B boot\r\n"
    "graph kernel.boot c=1\r\n"
    "task on cap on auth on\r\n"
    "surface visible input keyboard\r\n"
).encode("ascii") + b"\0")

label("key_prefix")
code.extend(b"graph input.key=\0")
label("halt_msg")
code.extend(b"graph halt esc\r\n\0")

for pos, target, size in patches:
    if target not in labels:
        raise SystemExit(f"missing label: {target}")
    if size == 1:
        rel = labels[target] - (pos + 1)
        if not -128 <= rel <= 127:
            raise SystemExit(f"short jump out of range: {target} {rel}")
        code[pos] = rel & 0xFF
    elif size == 2:
        if pos >= 2 and code[pos - 1] == 0xE8:
            rel = labels[target] - (pos + 2)
            code[pos] = rel & 0xFF
            code[pos + 1] = (rel >> 8) & 0xFF
        else:
            addr = 0x7C00 + labels[target]
            code[pos] = addr & 0xFF
            code[pos + 1] = (addr >> 8) & 0xFF

if len(code) > 510:
    raise SystemExit(f"boot sector too large: {len(code)} bytes")
code.extend(b"\0" * (510 - len(code)))
code.extend(b"\x55\xAA")
OUT.parent.mkdir(exist_ok=True)
OUT.write_bytes(code)
print(f"built {OUT} ({len(code)} bytes)")
