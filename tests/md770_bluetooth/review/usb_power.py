import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk, Stock
from emulator_macros import MacroQmk
from emulator import STOP
from stock_trace import Trace
from capstone import Cs, CS_ARCH_ARM, CS_MODE_THUMB
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R4

qhome = Path('../qmk_firmware').resolve()

for _review_name, _review_sha in (
    ("mistel_md770rgb_bt_right_markwellis_validation", "181c40b170487b210dc817f0956505be21770b570cd067b6179f0a4d359dc484"),
    ("mistel_md770rgb_bt_right_markwellis_validation_stock_parity", "4cdac0829403d0be725c9b3bfeeedf670172f502790d2992f779649c88482846"),
):
    import hashlib
    if hashlib.sha256((qhome / ".build" / (_review_name + ".elf")).read_bytes()).hexdigest() != _review_sha:
        raise ValueError("This historical review requires its recorded ELF images")
image = Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()

def new_stock():
    s = Stock(image)
    s.hardware.registers[0x40088040] = 0
    regs = {a: 0 for a in (0x400A8000, 0x400A8004, 0x400A8008, 0x400A8010, 0x400A8028, 0x400A803C)}
    access = s.hardware.access
    def usb_access(address, size, value=None):
        if address in regs:
            if value is None:
                return regs[address]
            if address == 0x400A8008:
                regs[address] &= ~value
            else:
                regs[address] = value
            return 0
        return access(address, size, value)
    s.hardware.access = usb_access
    s.hardware.pin(1, 12, True)
    s.hardware.pin(2, 13, True)
    s.hardware.pin(0, 10, False)
    s.write(0x200001E4, 2, 1)
    s.write(0x2000001F, 4, 1)
    s.write(0x20000020, 1, 1)
    s.write(0x20000601, 5, 1)
    s.write(0x20000603, 4, 1)
    s.write(0x20000624, 13, 1)
    s.write(0x2000068C, 2, 1)
    s.write(0x2000158E, 2, 1)
    s.write(0x20000860, 2, 1)
    return s, regs

def irq(s, regs, flag):
    regs[0x400A8004] |= flag
    regs[0x400A8008] = flag
    s.call(0x989C)

out = {}
for label, name in [('installed', 'mistel_md770rgb_bt_right_markwellis_validation'), ('candidate', 'mistel_md770rgb_bt_right_markwellis_validation_stock_parity')]:
    path = qhome / '.build' / (name + '.elf')
    abi = layout(qhome, path)
    q = Qmk(path.read_bytes(), abi)
    q.hardware.pin(1, 12, True)
    q.hardware.pin(2, 13, True)
    q.call('md770_power_init')
    q.usb(True)
    q.matrix()
    q.call('connection_set_host_noeeprom', abi['host_bluetooth'])
    s, regs = new_stock()
    irq(s, regs, 0x10)
    s.power()
    s.indicators()
    q.usb(True, suspended=True)
    q.matrix()
    q.indicators()
    record = {'suspended': {
        'stock_usb_public_state': s.read(0x20000601, 1),
        'stock_usb_configured_getter': s.call(0x987C),
        'stock_charge_eligible': s.read(0x20000020, 1),
        'stock_selected_output': s.read(0x2000068C, 1),
        'stock_blue': s.hardware.registers[0x4002C09C],
        'qmk_usb_configuration': q.read(q.symbol('USBD1') + abi['usb_configuration'], 1),
        'qmk_charge_eligible': q.read(q.symbol('eligible'), 1),
        'qmk_selected_output': q.read(q.symbol('config'), 1),
        'qmk_blue': q.hardware.registers[0x4002C09C],
    }}
    irq(s, regs, 0x08)
    record['stock_resume_interrupt_state'] = s.read(0x20000601, 1)
    irq(s, regs, 0x02)
    s.power()
    q.usb(True)
    q.matrix()
    record['resumed'] = {
        'stock_usb_public_state': s.read(0x20000601, 1),
        'stock_selected_output': s.read(0x2000068C, 1),
        'stock_saved_output': s.read(0x2000158E, 1),
        'stock_persistent_writes': s.persistent_writes,
        'qmk_selected_output': q.read(q.symbol('config'), 1),
        'qmk_persistent_writes': q.persistent_writes,
        'qmk_usb_enum': abi['host_usb'],
        'qmk_bluetooth_enum': abi['host_bluetooth'],
    }
    q = MacroQmk(path.read_bytes(), abi)
    q.set_host('host_usb')
    q.write(q.symbol('active_host'), abi['host_usb'], 1)
    q.usb(True, suspended=True)
    q.call('register_code', 0xE1)
    q.call('register_code', 4)
    q.write(q.symbol('matrix_previous'), 3, 1)
    before = q.usb_reports[-1].hex(' ')
    q.usb_reports.clear()
    q.usb(True)
    decoder = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
    decoder.detail = True
    begin = q.symbol('main')
    target = q.symbol('suspend_wakeup_init_quantum')
    payload = bytes(q.cpu.mem_read(begin, 0x10000-begin))
    candidates = []
    for offset in range(0, len(payload)-4, 2):
        ins = next(decoder.disasm(payload[offset:offset+4], begin+offset, count=1), None)
        if ins and ins.mnemonic == 'bl' and ins.operands[0].imm == target:
            candidates.append(ins.address)
    assert len(candidates) == 1, candidates
    call = candidates[0]
    def stop_wake(cpu, address, size, unused):
        cpu.reg_write(UC_ARM_REG_PC, STOP)
    handle = q.cpu.hook_add(UC_HOOK_CODE, stop_wake, begin=call+4, end=call+4)
    q.cpu.reg_write(UC_ARM_REG_R4, 0)
    q.call(call-8)
    q.cpu.hook_del(handle)
    q.call('register_code', 5)
    record['qmk_actual_inline_usb_wakeup_branch'] = {
        'report_before_resume': before,
        'report_after_resume_and_B_press': q.usb_reports[-1].hex(' '),
        'real_mods': q.read(q.symbol('real_mods'), 1),
        'matrix_previous': q.read(q.symbol('matrix_previous'), 1),
        'slice_start': hex(call-8),
        'slice_end': hex(call+4),
    }
    q = Qmk(path.read_bytes(), abi)
    q.hardware.pin(1, 12, True)
    q.hardware.pin(0, 10, False)
    q.call('md770_power_init')
    q.usb(True)
    q.matrix()
    s, regs = new_stock()
    s.write(0x2000068C, 1, 1)
    s.write(0x2000158E, 1, 1)
    q.usb(True, suspended=True)
    q.hardware.pin(1, 12, False)
    q.matrix()
    s.hardware.pin(1, 12, False)
    s.power()
    record['usb_host_power_removed'] = {
        'stock_selected_output': s.read(0x2000068C, 1),
        'stock_usb_public_state': s.read(0x20000601, 1),
        'stock_usb_control': s.read(0x20000603, 1),
        'qmk_selected_output': q.read(q.symbol('config'), 1),
        'qmk_usb_configuration': q.read(q.symbol('USBD1') + abi['usb_configuration'], 1),
    }
    q.hardware.pin(1, 12, True)
    q.matrix()
    s.hardware.pin(1, 12, True)
    s.power()
    record['powerbank_inserted_without_new_usb_enumeration'] = {
        'stock_selected_output': s.read(0x2000068C, 1),
        'stock_usb_public_state': s.read(0x20000601, 1),
        'stock_usb_control': s.read(0x20000603, 1),
        'qmk_selected_output': q.read(q.symbol('config'), 1),
        'qmk_usb_configuration': q.read(q.symbol('USBD1') + abi['usb_configuration'], 1),
    }
    out[label] = record

s, regs = new_stock()
s.write(0x2000068C, 1, 1)
s.write(0x20000604, 2, 1)
s.cpu.mem_write(0x200005D8, bytes.fromhex('02 00 04 00 00 00 00 00'))
s.write(0x200005B6, 1, 1)
irq(s, regs, 0x10)
s.call(0x9A44)
out['stock_usb_pending_report_during_suspend'] = {
    'keys': bytes(s.cpu.mem_read(0x200005D8, 8)).hex(' '),
    'dirty': s.read(0x200005B6, 1),
    'resume_requested': bool(regs[0x400A8000] & 0x20),
}
irq(s, regs, 0x08)
irq(s, regs, 0x02)
out['stock_usb_pending_report_after_resume'] = {
    'keys': bytes(s.cpu.mem_read(0x200005D8, 8)).hex(' '),
    'dirty': s.read(0x200005B6, 1),
    'usb_public_state': s.read(0x20000601, 1),
}
print(json.dumps(out, indent=2))
