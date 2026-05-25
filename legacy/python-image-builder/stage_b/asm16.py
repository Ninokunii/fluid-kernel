from __future__ import annotations

class Asm16:
    def __init__(self, org: int):
        self.org = org
        self.code = bytearray()
        self.labels: dict[str, int] = {}
        self.patches: list[tuple[int, str, int, str]] = []

    def emit(self, *bs: int) -> None:
        self.code.extend(bs)

    def imm16(self, value: int) -> None:
        self.emit(value & 0xFF, (value >> 8) & 0xFF)

    def label(self, name: str) -> None:
        self.labels[name] = len(self.code)

    def abs16(self, label: str) -> None:
        self.patches.append((len(self.code), label, 2, "abs"))
        self.emit(0, 0)

    def rel8(self, opcode: int, label: str) -> None:
        self.emit(opcode)
        self.patches.append((len(self.code), label, 1, "rel"))
        self.emit(0)

    def jmp(self, label: str) -> None:
        self.rel8(0xEB, label)

    def jmp_near(self, label: str) -> None:
        self.emit(0xE9)
        self.patches.append((len(self.code), label, 2, "call"))
        self.emit(0, 0)

    def jz(self, label: str) -> None:
        self.rel8(0x74, label)

    def jnz(self, label: str) -> None:
        self.rel8(0x75, label)

    def jc(self, label: str) -> None:
        self.rel8(0x72, label)

    def call(self, label: str) -> None:
        self.emit(0xE8)
        self.patches.append((len(self.code), label, 2, "call"))
        self.emit(0, 0)

    def cmp_mem8_imm8(self, label: str, value: int) -> None:
        self.emit(0x80, 0x3E)
        self.abs16(label)
        self.emit(value & 0xFF)

    def cmp_mem16_imm16(self, label: str, value: int) -> None:
        self.emit(0x81, 0x3E)
        self.abs16(label)
        self.imm16(value)


    def text(self, s: str) -> None:
        self.code.extend(s.encode("ascii") + b"\0")

    def patch(self) -> bytes:
        for pos, target, size, kind in self.patches:
            if target not in self.labels:
                raise SystemExit(f"missing label {target}")
            if size == 1:
                rel = self.labels[target] - (pos + 1)
                if not -128 <= rel <= 127:
                    raise SystemExit(f"short jump out of range {target}: {rel}")
                self.code[pos] = rel & 0xFF
            elif kind == "call":
                rel = self.labels[target] - (pos + 2)
                self.code[pos] = rel & 0xFF
                self.code[pos + 1] = (rel >> 8) & 0xFF
            else:
                addr = self.org + self.labels[target]
                self.code[pos] = addr & 0xFF
                self.code[pos + 1] = (addr >> 8) & 0xFF
        return bytes(self.code)


def add_serial_routines(a: Asm16) -> None:
    a.label("serial_print")
    a.emit(0xAC)              # lodsb
    a.emit(0x84, 0xC0)        # test al, al
    a.jz("serial_print_done")
    a.call("serial_putc")
    a.jmp("serial_print")
    a.label("serial_print_done")
    a.emit(0xC3)

    a.label("serial_putc")
    a.emit(0x50)              # push ax
    a.emit(0xBA); a.imm16(0x03FD)
    a.label("serial_wait")
    a.emit(0xEC)              # in al, dx
    a.emit(0xA8, 0x20)        # test al, 0x20
    a.jz("serial_wait")
    a.emit(0x58)              # pop ax
    a.emit(0xBA); a.imm16(0x03F8)
    a.emit(0xEE)              # out dx, al
    a.emit(0xC3)


def add_bios_print(a: Asm16) -> None:
    a.label("bios_print")
    a.emit(0xAC)
    a.emit(0x84, 0xC0)
    a.jz("bios_done")
    a.emit(0xB4, 0x0E)        # mov ah, 0e
    a.emit(0xBB, 0x00, 0x0A)  # mov bx, green
    a.emit(0xCD, 0x10)
    a.jmp("bios_print")
    a.label("bios_done")
    a.emit(0xC3)
