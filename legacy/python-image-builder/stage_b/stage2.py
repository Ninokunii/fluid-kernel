from __future__ import annotations
from asm16 import Asm16, add_bios_print, add_serial_routines
from stage1 import STAGE2_LOAD, STAGE2_SECTORS


def emit_store8(a: Asm16, label: str, value: int) -> None:
    a.emit(0xC6, 0x06); a.abs16(label); a.emit(value & 0xFF)  # mov byte [label], value


def emit_store16(a: Asm16, label: str, value: int) -> None:
    a.emit(0xC7, 0x06); a.abs16(label); a.imm16(value)  # mov word [label], value


def emit_graph_event(a: Asm16, slot: int, cursor: int, event_type: int, subject: int, state: int) -> None:
    emit_store8(a, f"graph_slot_{slot}_cursor", cursor)
    emit_store8(a, f"graph_slot_{slot}_type", event_type)
    emit_store16(a, f"graph_slot_{slot}_subject", subject)
    emit_store8(a, f"graph_slot_{slot}_state", state)



def emit_flush_boot(a: Asm16) -> None:
    a.emit(0xBE); a.abs16("flush_boot_header"); a.call("serial_print")
    for idx in range(4):
        a.call(f"flush_slot_{idx}")


def emit_flush_choose(a: Asm16) -> None:
    a.emit(0xBE); a.abs16("flush_choose_header"); a.call("serial_print")
    for idx in range(4, 7):
        a.call(f"flush_slot_{idx}")


def emit_flush_receipt(a: Asm16) -> None:
    a.emit(0xBE); a.abs16("flush_receipt_header"); a.call("serial_print")
    for idx in range(7, 11):
        a.call(f"flush_slot_{idx}")


def emit_event_subject_dispatch(a: Asm16, idx: int, event_type: int, generic_target: str) -> None:
    if event_type == 2:
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x2001)
        a.jnz(f"slot_{idx}_cap_not_food")
        a.emit(0xBE); a.abs16("graph_cap_food_registered"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_cap_not_food")
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x2002)
        a.jnz(f"slot_{idx}_cap_not_pay")
        a.emit(0xBE); a.abs16("graph_cap_pay_registered"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_cap_not_pay")
    elif event_type == 4:
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x0001)
        a.jnz(f"slot_{idx}_input_not_1")
        a.emit(0xBE); a.abs16("graph_input_key_1"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_input_not_1")
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x0002)
        a.jnz(f"slot_{idx}_input_not_y")
        a.emit(0xBE); a.abs16("graph_input_key_y"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_input_not_y")
    elif event_type == 5:
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x5001)
        a.jnz(f"slot_{idx}_called_not_order")
        a.emit(0xBE); a.abs16("graph_capability_called_order"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_called_not_order")
    elif event_type == 6:
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x6001)
        a.jnz(f"slot_{idx}_trusted_surface_not_payment")
        a.emit(0xBE); a.abs16("graph_trusted_surface_payment"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_trusted_surface_not_payment")
    elif event_type == 7:
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x6001)
        a.jnz(f"slot_{idx}_trusted_confirm_not_payment")
        a.emit(0xBE); a.abs16("graph_trusted_confirmed_payment"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_trusted_confirm_not_payment")
    elif event_type == 8:
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x7001)
        a.jnz(f"slot_{idx}_receipt_not_demo")
        a.emit(0xBE); a.abs16("graph_receipt_demo"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_receipt_not_demo")
    elif event_type == 9:
        a.cmp_mem16_imm16(f"graph_slot_{idx}_subject", 0x1001)
        a.jnz(f"slot_{idx}_task_completed_not_demo")
        a.emit(0xBE); a.abs16("graph_task_completed_demo"); a.call("serial_print")
        a.emit(0xC3)
        a.label(f"slot_{idx}_task_completed_not_demo")
    a.emit(0xBE); a.abs16(generic_target); a.call("serial_print")
    a.emit(0xC3)


def emit_flush_slot_dispatchers(a: Asm16) -> None:
    for idx in range(11):
        a.label(f"flush_slot_{idx}")
        for event_type, target in [
            (1, "graph_task_created"),
            (2, "graph_cap_registered"),
            (3, "graph_interface_projected"),
            (4, "graph_input_key"),
            (5, "graph_capability_called"),
            (6, "graph_trusted_surface_created"),
            (7, "graph_trusted_confirmed"),
            (8, "graph_receipt_created"),
            (9, "graph_task_completed"),
        ]:
            a.cmp_mem8_imm8(f"graph_slot_{idx}_type", event_type)
            a.jnz(f"slot_{idx}_not_{event_type}")
            emit_event_subject_dispatch(a, idx, event_type, target)
            a.label(f"slot_{idx}_not_{event_type}")
        a.emit(0xC3)


def emit_object_bootstrap(a: Asm16) -> None:
    # These bytes are the first kernel-resident object tables. They are tiny, but
    # real mutable state: graph output below is emitted after state transitions.
    emit_store16(a, "task_record_id", 0x1001)
    emit_store8(a, "task_record_state", 1)       # created
    emit_store8(a, "task_record_authority", 1)   # sess.runtime
    emit_store16(a, "cap_food_record_id", 0x2001)
    emit_store8(a, "cap_food_record_state", 1)   # registered
    emit_store8(a, "cap_food_record_risk", 1)    # medium
    emit_store16(a, "cap_pay_record_id", 0x2002)
    emit_store8(a, "cap_pay_record_state", 1)    # registered
    emit_store8(a, "cap_pay_record_risk", 3)     # critical
    emit_store16(a, "authority_record_id", 0x3001)
    emit_store8(a, "authority_record_runtime", 1)
    emit_store8(a, "authority_record_trusted", 1)
    emit_store16(a, "interface_record_id", 0x4001)
    emit_store8(a, "interface_record_state", 1)  # projected
    emit_store8(a, "interface_record_surface", 1)
    emit_graph_event(a, 0, 1, 1, 0x1001, 1)
    emit_graph_event(a, 1, 2, 2, 0x2001, 1)
    emit_graph_event(a, 2, 3, 2, 0x2002, 1)
    emit_graph_event(a, 3, 4, 3, 0x4001, 1)
    emit_store8(a, "graph_ring_head", 4)
    emit_store8(a, "graph_cursor", 4)
    a.emit(0xBE); a.abs16("serial_boot"); a.call("serial_print")
    emit_flush_boot(a)


def emit_choose_transition(a: Asm16) -> None:
    emit_store8(a, "input_record_last_key", ord('1'))
    emit_store16(a, "order_record_id", 0x5001)
    emit_store8(a, "order_record_state", 1)      # created
    emit_store8(a, "order_record_capability", 1) # food.createOrder
    emit_store16(a, "trusted_record_id", 0x6001)
    emit_store8(a, "trusted_record_state", 1)    # awaiting confirmation
    emit_store8(a, "trusted_record_capability", 2)
    emit_graph_event(a, 4, 5, 4, 0x0001, 1)
    emit_graph_event(a, 5, 6, 5, 0x5001, 1)
    emit_graph_event(a, 6, 7, 6, 0x6001, 1)
    emit_store8(a, "graph_ring_head", 7)
    emit_store8(a, "graph_cursor", 7)
    a.emit(0xBE); a.abs16("serial_choose"); a.call("serial_print")
    emit_flush_choose(a)


def emit_confirm_transition(a: Asm16) -> None:
    emit_store8(a, "input_record_last_key", ord('y'))
    emit_store8(a, "trusted_record_state", 2)    # confirmed
    emit_store16(a, "receipt_record_id", 0x7001)
    emit_store8(a, "receipt_record_state", 1)    # receipt created
    emit_store8(a, "receipt_record_order", 1)
    emit_store8(a, "task_record_state", 2)       # completed
    emit_graph_event(a, 7, 8, 4, 0x0002, 2)
    emit_graph_event(a, 8, 9, 7, 0x6001, 2)
    emit_graph_event(a, 9, 10, 8, 0x7001, 1)
    emit_graph_event(a, 10, 11, 9, 0x1001, 2)
    emit_store8(a, "graph_ring_head", 11)
    emit_store8(a, "graph_cursor", 11)
    a.emit(0xBE); a.abs16("serial_receipt"); a.call("serial_print")
    emit_flush_receipt(a)


def emit_key_loop(a: Asm16) -> None:
    a.label("key_loop")
    a.emit(0xB4, 0x00, 0xCD, 0x16)             # wait key, AL ascii
    a.emit(0x3C, ord('1')); a.jnz("not_choose_food"); a.jmp_near("choose_food"); a.label("not_choose_food")
    a.emit(0x3C, ord('y')); a.jnz("not_confirm_pay"); a.jmp_near("confirm_pay"); a.label("not_confirm_pay")
    a.emit(0x3C, 0x1B); a.jnz("not_halt"); a.jmp_near("halt"); a.label("not_halt")
    a.emit(0x50)
    a.emit(0xBE); a.abs16("key_prefix"); a.call("serial_print")
    a.emit(0x58); a.call("serial_putc")
    a.emit(0xB0, 0x0D); a.call("serial_putc"); a.emit(0xB0, 0x0A); a.call("serial_putc")
    a.jmp_near("key_loop")


def emit_food_flow(a: Asm16) -> None:
    a.label("choose_food")
    a.emit(0xBE); a.abs16("screen_trusted"); a.call("bios_print")
    emit_choose_transition(a)
    a.jmp_near("key_loop")

    a.label("confirm_pay")
    a.emit(0xBE); a.abs16("screen_receipt"); a.call("bios_print")
    emit_confirm_transition(a)
    a.jmp_near("key_loop")

    a.label("halt")
    a.emit(0xBE); a.abs16("halt_msg"); a.call("serial_print")
    a.label("hang"); a.emit(0xF4); a.jmp("hang")


def emit_strings(a: Asm16) -> None:
    # Tiny structured records. They are deliberately small real-mode records,
    # but each field is mutable kernel state rather than display text.
    a.label("task_record_id"); a.emit(0, 0)
    a.label("task_record_state"); a.emit(0)       # 0 none, 1 created, 2 completed
    a.label("task_record_authority"); a.emit(0)
    a.label("cap_food_record_id"); a.emit(0, 0)
    a.label("cap_food_record_state"); a.emit(0)
    a.label("cap_food_record_risk"); a.emit(0)
    a.label("cap_pay_record_id"); a.emit(0, 0)
    a.label("cap_pay_record_state"); a.emit(0)
    a.label("cap_pay_record_risk"); a.emit(0)
    a.label("authority_record_id"); a.emit(0, 0)
    a.label("authority_record_runtime"); a.emit(0)
    a.label("authority_record_trusted"); a.emit(0)
    a.label("interface_record_id"); a.emit(0, 0)
    a.label("interface_record_state"); a.emit(0)
    a.label("interface_record_surface"); a.emit(0)
    a.label("input_record_last_key"); a.emit(0)
    a.label("order_record_id"); a.emit(0, 0)
    a.label("order_record_state"); a.emit(0)
    a.label("order_record_capability"); a.emit(0)
    a.label("trusted_record_id"); a.emit(0, 0)
    a.label("trusted_record_state"); a.emit(0)
    a.label("trusted_record_capability"); a.emit(0)
    a.label("receipt_record_id"); a.emit(0, 0)
    a.label("receipt_record_state"); a.emit(0)
    a.label("receipt_record_order"); a.emit(0)
    a.label("graph_ring_head"); a.emit(0)
    a.label("graph_cursor"); a.emit(0)
    for idx in range(12):
        a.label(f"graph_slot_{idx}_cursor"); a.emit(0)
        a.label(f"graph_slot_{idx}_type"); a.emit(0)
        a.label(f"graph_slot_{idx}_subject"); a.emit(0, 0)
        a.label(f"graph_slot_{idx}_state"); a.emit(0)

    a.label("screen_home")
    a.text(
        "Fluid Kernel Stage B2\r\n"
        "Agent-native food task demo\r\n"
        "Intent: dinner under 30 min\r\n"
        "[1] Choose Spice Lab - 26 min - $23\r\n"
        "[y] Confirm trusted payment after choosing\r\n"
        "[esc] halt\r\n> "
    )
    a.label("screen_trusted")
    a.text("\r\nTrusted Payment Gate\r\nCapability: payment.confirmAndPay\r\nPress y to confirm.\r\n> ")
    a.label("screen_receipt")
    a.text("\r\nReceipt: order.demo.0001 paid $23\r\nNo app opened. Task complete.\r\n> ")
    a.label("serial_boot")
    a.text(
        "Fluid Kernel Stage B2 loaded\r\n"
        "kernel.object_records task{id=1001,state=created,auth=runtime} cap_food{id=2001,risk=medium} cap_pay{id=2002,risk=critical} authority{id=3001,runtime=1,trusted=1} interface{id=4001,state=projected} ring_head=4\r\n"
        "kernel.graph_ring slot0{c=1,t=task.created,s=1001,state=created} slot1{c=2,t=cap.registered,s=2001,state=registered} slot2{c=3,t=cap.registered,s=2002,state=registered} slot3{c=4,t=interface.projected,s=4001,state=projected}\r\n"
    )
    a.label("flush_boot_header")
    a.text("kernel.graph_flush source=ring walker=type-dispatch from=0 to=3\r\n")
    a.label("serial_choose")
    a.text(
        "kernel.object_transition input{last=1} order{id=5001,state=created,cap=food.createOrder} trusted{id=6001,state=awaiting,cap=payment.confirm} ring_head=7\r\n"
        "kernel.graph_ring slot4{c=5,t=input.key,s=1,state=pressed} slot5{c=6,t=capability.called,s=5001,state=ok} slot6{c=7,t=trusted_surface.created,s=6001,state=awaiting}\r\n"
    )
    a.label("flush_choose_header")
    a.text("kernel.graph_flush source=ring walker=type-dispatch from=4 to=6\r\n")
    a.label("serial_receipt")
    a.text(
        "kernel.object_transition input{last=y} trusted{id=6001,state=confirmed} receipt{id=7001,state=created,order=5001} task{id=1001,state=completed} ring_head=11\r\n"
        "kernel.graph_ring slot7{c=8,t=input.key,s=2,state=pressed} slot8{c=9,t=trusted.confirmed,s=6001,state=confirmed} slot9{c=10,t=receipt.created,s=7001,state=created} slot10{c=11,t=task.completed,s=1001,state=completed}\r\n"
    )
    a.label("flush_receipt_header")
    a.text("kernel.graph_flush source=ring walker=type-dispatch from=7 to=10\r\n")
    a.label("graph_task_created"); a.text("graph task.created id=task.food.demo\r\n")
    a.label("graph_cap_registered"); a.text("graph capability.registered source=ring\r\n")
    a.label("graph_cap_food_registered"); a.text("graph capability.registered id=food.createOrder source=ring.subject\r\n")
    a.label("graph_cap_pay_registered"); a.text("graph capability.registered id=payment.confirmAndPay source=ring.subject\r\n")
    a.label("graph_interface_projected"); a.text("graph interface.projected id=iface.food.native\r\n")
    a.label("graph_input_key"); a.text("graph input.key from=ring\r\n")
    a.label("graph_input_key_1"); a.text("graph input.key value=1 source=ring.subject\r\n")
    a.label("graph_input_key_y"); a.text("graph input.key value=y source=ring.subject\r\n")
    a.label("graph_capability_called"); a.text("graph capability.called source=ring\r\n")
    a.label("graph_capability_called_order"); a.text("graph capability.called food.createOrder provider=kernel.mock.food source=ring.subject\r\n")
    a.label("graph_trusted_surface_created"); a.text("graph trusted_surface.created source=ring\r\n")
    a.label("graph_trusted_surface_payment"); a.text("graph trusted_surface.created capability=payment.confirmAndPay source=ring.subject\r\n")
    a.label("graph_trusted_confirmed"); a.text("graph trusted.confirmed source=ring\r\n")
    a.label("graph_trusted_confirmed_payment"); a.text("graph trusted.confirmed session=sess.trusted-ui capability=payment.confirmAndPay source=ring.subject\r\n")
    a.label("graph_receipt_created"); a.text("graph receipt.created source=ring\r\n")
    a.label("graph_receipt_demo"); a.text("graph receipt.created order=order.demo.0001 source=ring.subject\r\n")
    a.label("graph_task_completed"); a.text("graph task.completed source=ring\r\n")
    a.label("graph_task_completed_demo"); a.text("graph task.completed id=task.food.demo source=ring.subject\r\n")
    a.label("key_prefix"); a.text("graph input.key=")
    a.label("halt_msg"); a.text("graph kernel.halt reason=escape\r\n")


def build_stage2() -> bytes:
    a = Asm16(STAGE2_LOAD)
    a.emit(0xFA, 0x31, 0xC0, 0x8E, 0xD8, 0x8E, 0xC0, 0x8E, 0xD0)
    a.emit(0xBC); a.imm16(0x7C00); a.emit(0xFB)
    a.emit(0xB8, 0x03, 0x00, 0xCD, 0x10)      # text mode
    a.emit(0xBE); a.abs16("screen_home"); a.call("bios_print")
    emit_object_bootstrap(a)
    emit_key_loop(a)
    emit_food_flow(a)
    emit_flush_slot_dispatchers(a)
    add_bios_print(a)
    add_serial_routines(a)
    emit_strings(a)
    data = bytearray(a.patch())
    max_len = STAGE2_SECTORS * 512
    if len(data) > max_len:
        raise SystemExit(f"stage2 too large: {len(data)} > {max_len}")
    data.extend(b"\0" * (max_len - len(data)))
    return bytes(data)
