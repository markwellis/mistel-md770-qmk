import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_firmware import Stock
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

s = Stock(Path('mistel_md770rgb_bt_right_stock.bin').read_bytes())
s.ready()
for pad in (2, 3, 4, 5):
    s.hardware.pin(1, pad, pad == 2)
s.hardware.pin(1, 12, True)
s.hardware.pin(0, 10, False)
s.write(0x2000001F, 3, 1)
s.write(0x20000020, 1, 1)
s.write(0x20000601, 5, 1)
s.write(0x20000603, 4, 1)
s.write(0x20000623, 13, 1)
s.write(0x20000624, 13, 1)
s.write(0x20000625, 13, 1)
s.write(0x20000626, 0x10, 1)
s.write(0x20000628, 0)
s.write(0x200001E4, 4, 1)
s.write(0x20000219, 4, 1)
s.write(0x20000218, 0x20, 1)
s.write(0x20000216, 0, 2)
s.write(0x2000068C, 2, 1)
trace = []
def trace_entry(cpu, address, size, context):
    if address in (0x40A4, 0x36B8, 0x84FC, 0xC9A4, 0xC87C, 0xC7F0):
        trace.append([hex(address), cpu.reg_read(UC_ARM_REG_R0), cpu.reg_read(UC_ARM_REG_R1)])
s.cpu.hook_add(UC_HOOK_CODE, trace_entry)
def state():
    return {'supply':s.read(0x2000001F,1), 'output':s.read(0x2000068C,1), 'pending':s.read(0x20000218,1), 'callback':s.read(0x20000219,1), 'PD1':s.hardware.output(3,1), 'power_pending':s.read(0x20000628), 'power_target':s.read(0x20000623,1), 'power_level':s.read(0x20000624,1)}
results = {'before':state()}
try:
    s.call(0xDA78, budget=1000000)
    results['first_service'] = state()
    for tick in range(3):
        s.write(0x2000061C, 1)
        s.call(0xDA78, budget=1000000)
    results['three_later_services'] = state()
except Exception as error:
    results['error'] = str(error)
    results['state_at_error'] = state()
results['trace'] = trace
print(json.dumps(results, indent=2))
