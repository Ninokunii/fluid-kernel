BITS 16
ORG 0x7C00

KERNEL_LOAD equ 0x1000
KERNEL_SECTORS equ 16

start:
    cli
    xor ax, ax
    mov ds, ax
    mov es, ax
    mov ss, ax
    mov sp, 0x7C00
    sti

    mov [boot_drive], dl
    call serial_init
    mov si, msg_stage1
    call serial_puts

    mov bx, KERNEL_LOAD
    mov dh, KERNEL_SECTORS
    mov dl, [boot_drive]
    mov cl, 2
.load_loop:
    push dx
    push cx
    mov ah, 0x02
    mov al, 0x01
    mov ch, 0x00
    mov dh, 0x00
    int 0x13
    jc disk_error
    pop cx
    pop dx
    add bx, 512
    inc cl
    dec dh
    jnz .load_loop

    mov ax, 0x0013
    int 0x10

    cli
    lgdt [gdt_desc]
    mov eax, cr0
    or eax, 1
    mov cr0, eax
    jmp 0x08:protected_entry

disk_error:
    mov si, msg_disk
    call serial_puts
.hang:
    hlt
    jmp .hang

serial_init:
    mov dx, 0x3F8 + 1
    xor al, al
    out dx, al
    mov dx, 0x3F8 + 3
    mov al, 0x80
    out dx, al
    mov dx, 0x3F8
    mov al, 0x03
    out dx, al
    mov dx, 0x3F8 + 1
    xor al, al
    out dx, al
    mov dx, 0x3F8 + 3
    mov al, 0x03
    out dx, al
    mov dx, 0x3F8 + 2
    mov al, 0xC7
    out dx, al
    mov dx, 0x3F8 + 4
    mov al, 0x0B
    out dx, al
    ret

serial_putc:
    push ax
    push dx
    mov ah, al
.wait:
    mov dx, 0x3F8 + 5
    in al, dx
    test al, 0x20
    jz .wait
    mov dx, 0x3F8
    mov al, ah
    out dx, al
    pop dx
    pop ax
    ret

serial_puts:
    lodsb
    test al, al
    jz .done
    call serial_putc
    jmp serial_puts
.done:
    ret

BITS 32
protected_entry:
    mov ax, 0x10
    mov ds, ax
    mov es, ax
    mov fs, ax
    mov gs, ax
    mov ss, ax
    mov esp, 0x90000
    call KERNEL_LOAD
.halt:
    hlt
    jmp .halt

BITS 16
boot_drive db 0
msg_stage1 db 'fluid.stage1 asm boot ok', 13, 10, 0
msg_disk db 'fluid.stage1 disk read failed', 13, 10, 0

gdt:
    dq 0
    dq 0x00CF9A000000FFFF
    dq 0x00CF92000000FFFF
gdt_desc:
    dw gdt_desc - gdt - 1
    dd gdt

times 510-($-$$) db 0
dw 0xAA55
