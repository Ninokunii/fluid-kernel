#!/usr/bin/env python3
from __future__ import annotations
from pathlib import Path
import sys
THIS = Path(__file__).resolve().parent
if str(THIS) not in sys.path:
    sys.path.insert(0, str(THIS))
from asm16 import Asm16, add_serial_routines
from dashboard_rle import DASHBOARD_RLE
ROOT = THIS.parents[1]
OUT = ROOT / 'build' / 'fluid-kernel-dom-dashboard.img'
STAGE2_LOAD = 0x8000
STAGE2_SECTORS = 18

def build_stage1() -> bytes:
    a=Asm16(0x7C00)
    a.emit(0xFA,0x31,0xC0,0x8E,0xD8,0x8E,0xC0,0x8E,0xD0,0xBC); a.imm16(0x7C00); a.emit(0xFB)
    for port,val in [(0x03F9,0),(0x03FB,0x80),(0x03F8,3),(0x03F9,0),(0x03FB,3),(0x03FA,0xC7),(0x03FC,0x0B)]:
        a.emit(0xBA); a.imm16(port); a.emit(0xB0,val,0xEE)
    a.emit(0xB2, 0x00)
    a.emit(0x88,0x16); a.abs16('boot_drive')
    a.emit(0xBE); a.abs16('boot_msg'); a.call('serial_print')
    a.emit(0xB4,0x00,0x8A,0x16); a.abs16('boot_drive'); a.emit(0xCD,0x13)
    a.emit(0x31,0xC0,0x8E,0xC0,0xBB); a.imm16(STAGE2_LOAD)
    a.emit(0xB4,0x02,0xB0,STAGE2_SECTORS,0xB5,0x00,0xB1,0x02,0xB6,0x00)
    a.emit(0x8A,0x16); a.abs16('boot_drive'); a.emit(0xCD,0x13); a.jc('disk_error')
    a.emit(0xEA); a.imm16(STAGE2_LOAD); a.imm16(0)
    a.label('disk_error'); a.emit(0xBE); a.abs16('err_msg'); a.call('serial_print')
    a.label('hang'); a.emit(0xF4); a.jmp('hang')
    add_serial_routines(a)
    a.label('boot_msg'); a.text('Fluid DOM dashboard stage1 loading\r\n')
    a.label('err_msg'); a.text('domdash.disk_error\r\n')
    a.label('boot_drive'); a.emit(0)
    data=bytearray(a.patch()); data.extend(b'\0'*(510-len(data))); data.extend(b'\x55\xAA'); return bytes(data)

def emit32(a,*bs): a.emit(*bs)
def relpatch(a, patches, label):
    patches.append((len(a.code), label)); a.emit(0,0,0,0)

def build_stage2() -> bytes:
    a=Asm16(STAGE2_LOAD); rel=[]
    def call(label): a.emit(0xE8); relpatch(a,rel,label)
    def mov_esi(label): a.emit(0xBE); abs_patches.append((len(a.code),label)); a.emit(0,0,0,0)
    abs_patches=[]
    def print_label(label): mov_esi(label); call('serial_print32')
    # real mode set mode13 then pm
    a.emit(0xBE); a.abs16('real_msg'); a.call('serial_print')
    a.emit(0xB8,0x13,0x00,0xCD,0x10,0xFA)
    a.emit(0x0F,0x01,0x16); a.abs16('gdt_desc')
    a.emit(0x0F,0x20,0xC0,0x66,0x83,0xC8,0x01,0x0F,0x22,0xC0)
    a.emit(0xEA); a.imm16(0); a.imm16(0x0008); far=len(a.code)-4
    add_serial_routines(a)
    a.label('real_msg'); a.text('Fluid DOM dashboard preparing protected mode\r\n')
    a.label('gdt'); a.emit(*([0]*8)); a.emit(0xFF,0xFF,0,0,0,0x9A,0xCF,0); a.emit(0xFF,0xFF,0,0,0,0x92,0xCF,0)
    a.label('gdt_end'); a.label('gdt_desc'); a.emit((24-1)&255,0); gdt_base=len(a.code); a.emit(0,0,0,0)
    a.label('pm_entry'); pm_off=len(a.code); a.code[far]=(STAGE2_LOAD+pm_off)&255; a.code[far+1]=((STAGE2_LOAD+pm_off)>>8)&255
    a.emit(0x66,0xB8,0x10,0x00)
    for r in [0xD8,0xC0,0xD0,0xE0,0xE8]: a.emit(0x8E,r)
    a.emit(0xBC,0x00,0x00,0x09,0x00)
    # load VGA DAC palette 0..15
    a.emit(0xBA,0xC8,0x03,0,0,0xB0,0,0xEE) # dx=3c8; al=0; out
    for r,g,b in [(0,0,0),(10,13,20),(18,23,34),(45,52,68),(48,54,68),(60,70,80),(120,135,150),(150,160,175),(210,220,230),(255,255,255),(6,182,212),(34,211,238),(239,68,68),(249,115,22),(245,158,11),(80,80,80)]:
        a.emit(0xBA,0xC9,0x03,0,0)
        for v in (r,g,b): a.emit(0xB0, min(63, v//4), 0xEE)
    print_label('boot_ok')
    # RLE decode: esi=rle, edi=A0000, ebx=end
    mov_esi('rle_data'); a.emit(0xBF,0,0,0x0A,0); a.emit(0xBB); a.emit(*((0xA0000+64000).to_bytes(4,'little')))
    a.label('rle_loop')
    a.emit(0x39,0xDF)              # cmp edi, ebx
    a.emit(0x0F,0x83); relpatch(a,rel,'rle_done')
    a.emit(0xAC)                   # lodsb count
    a.emit(0x0F,0xB6,0xC8)         # movzx ecx, al
    a.emit(0xAC)                   # lodsb color
    a.emit(0xF3,0xAA)              # rep stosb
    a.emit(0xE9); relpatch(a,rel,'rle_loop')
    a.label('rle_done')
    print_label('surface_msg'); print_label('projection_msg'); print_label('text_msg'); print_label('image_msg'); print_label('click_msg')
    a.label('halt'); a.emit(0xF4,0xEB,0xFD)
    a.label('serial_print32')
    a.label('spl'); a.emit(0xAC,0x84,0xC0,0x74,0x07); cp=len(a.code); a.emit(0xE8,0,0,0,0); a.emit(0xEB,0xF4,0xC3)
    a.label('putc'); a.emit(0x50,0xBA,0xFD,0x03,0,0); a.label('wait'); a.emit(0xEC,0xA8,0x20,0x74,0xFB,0x58,0xBA,0xF8,0x03,0,0,0xEE,0xC3)
    # data
    a.label('boot_ok'); a.text('domdash.boot protected-mode online\r\n')
    a.label('surface_msg'); a.text('domdash.surface framebuffer=320x200 source=projection-ir page=smart-car-dashboard\r\n')
    a.label('projection_msg'); a.text('domdash.projection nodes=109 interactive=16 text=45 leaf_text=19 image=17\r\n')
    a.label('text_msg'); a.text('domdash.text visible labels=car-light,brightness,auto-park,trunk\r\n')
    a.label('image_msg'); a.text('domdash.image visible type=svg-icons count=17\r\n')
    a.label('click_msg'); a.text('domdash.click target=auto-park state=available rect=124,376,270,94\r\n')
    a.label('rle_data'); a.emit(*DASHBOARD_RLE)
    # patch gdt/rel/abs/call_putc
    base=STAGE2_LOAD
    a.code[gdt_base:gdt_base+4]=(base+a.labels['gdt']).to_bytes(4,'little')
    for pos,label in abs_patches: a.code[pos:pos+4]=(base+a.labels[label]).to_bytes(4,'little')
    for pos,label in rel: a.code[pos:pos+4]=((base+a.labels[label])-(base+pos+4)).to_bytes(4,'little',signed=True)
    a.code[cp+1:cp+5]=((base+a.labels['putc'])-(base+cp+5)).to_bytes(4,'little',signed=True)
    data=bytearray(a.patch()); max_len=STAGE2_SECTORS*512
    if len(data)>max_len: raise SystemExit(f'dom dashboard stage2 too large: {len(data)} > {max_len}')
    data.extend(b'\0'*(max_len-len(data))); return bytes(data)

def main():
    img=bytearray(build_stage1()+build_stage2()); img.extend(b'\0'*(1440*1024-len(img)))
    OUT.parent.mkdir(exist_ok=True); OUT.write_bytes(img); print(f'built {OUT} ({len(img)} bytes)')
if __name__=='__main__': main()
