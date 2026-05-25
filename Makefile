LLVM_PREFIX ?= /opt/homebrew/opt/llvm/bin
CC := $(LLVM_PREFIX)/clang
LD := /opt/homebrew/opt/lld/bin/ld.lld
OBJCOPY := $(LLVM_PREFIX)/llvm-objcopy
NASM ?= nasm
QEMU ?= qemu-system-i386

BUILD := build
CFLAGS := --target=i386-elf -ffreestanding -fno-stack-protector -fno-pic -fno-pie -m32 -march=i386 -nostdlib -nostdinc -Iinclude -Wall -Wextra -O2
LDFLAGS := -m elf_i386 -T linker.ld -nostdlib

KERNEL_OBJS := \
	$(BUILD)/kernel/main.o \
	$(BUILD)/kernel/serial.o \
	$(BUILD)/kernel/fb.o \
	$(BUILD)/kernel/font.o \
	$(BUILD)/kernel/html.o \
	$(BUILD)/assets/order_agent_html.o

.PHONY: all clean run verify legacy-verify
all: $(BUILD)/fluid-kernel.img

$(BUILD):
	mkdir -p $(BUILD)/boot $(BUILD)/kernel $(BUILD)/assets

$(BUILD)/boot/stage1.bin: boot/stage1.asm | $(BUILD)
	$(NASM) -f bin $< -o $@

$(BUILD)/assets/order_agent_html.o: kernel/assets/order-agent.html | $(BUILD)
	$(OBJCOPY) -I binary -O elf32-i386 -B i386 $< $@

$(BUILD)/kernel/%.o: kernel/%.c | $(BUILD)
	$(CC) $(CFLAGS) -c $< -o $@

$(BUILD)/kernel.bin: $(KERNEL_OBJS) linker.ld | $(BUILD)
	$(LD) $(LDFLAGS) $(KERNEL_OBJS) -o $(BUILD)/kernel.elf
	$(OBJCOPY) -O binary $(BUILD)/kernel.elf $@

$(BUILD)/fluid-kernel.img: $(BUILD)/boot/stage1.bin $(BUILD)/kernel.bin
	dd if=/dev/zero of=$@ bs=512 count=2880 >/dev/null 2>&1
	dd if=$(BUILD)/boot/stage1.bin of=$@ conv=notrunc >/dev/null 2>&1
	dd if=$(BUILD)/kernel.bin of=$@ bs=512 seek=1 conv=notrunc >/dev/null 2>&1

run: $(BUILD)/fluid-kernel.img
	$(QEMU) -fda $< -serial stdio -display cocoa -no-reboot -no-shutdown

verify: $(BUILD)/fluid-kernel.img
	python3 tools/run-c-kernel.py

legacy-verify:
	python3 legacy/python-image-builder/tools/run-fluid-kernel-html.py
	python3 legacy/python-image-builder/tools/compare-fluid-html-visual.py

clean:
	rm -rf $(BUILD)
