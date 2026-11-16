import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk, Stock
from unicorn.arm_const import UC_ARM_REG_R0

qhome = Path('../qmk_firmware').resolve()

for _review_name, _review_sha in (
    ("mistel_md770rgb_bt_right_markwellis_validation", "181c40b170487b210dc817f0956505be21770b570cd067b6179f0a4d359dc484"),
    ("mistel_md770rgb_bt_right_markwellis_validation_stock_parity", "4cdac0829403d0be725c9b3bfeeedf670172f502790d2992f779649c88482846"),
):
    import hashlib
    if hashlib.sha256((qhome / ".build" / (_review_name + ".elf")).read_bytes()).hexdigest() != _review_sha:
        raise ValueError("This historical review requires its recorded ELF images")
stock_image = Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
results = {}
for label, name in [('installed', 'mistel_md770rgb_bt_right_markwellis_validation'), ('candidate', 'mistel_md770rgb_bt_right_markwellis_validation_stock_parity')]:
    path = qhome / '.build' / (name + '.elf')
    abi = layout(qhome, path)
    q = Qmk(path.read_bytes(), abi)
    s = Stock(stock_image)
    q.matrix()
    s.power()
    q.hardware.voltage_mv = s.hardware.voltage_mv = 3100
    q.matrix()
    s.voltage_tick(20)
    q.ms = 10
    q.hardware.voltage_mv = s.hardware.voltage_mv = 3300
    s.voltage_tick(20)
    q.ms = 20
    q.hardware.voltage_mv = s.hardware.voltage_mv = 3100
    s.voltage_tick(20)
    q.ms = 30
    q.matrix()
    s.power()
    record = {'lvd_low_10ms_high_10ms_low_10ms_main_poll_at_0_and_30ms': {
        'stock_battery_level': s.read(0x2000001E, 1),
        'stock_lvd_filter_remaining_ticks': s.read(0x2000001C, 2),
        'qmk_battery_level': q.read(q.symbol('battery_level'), 1),
    }}

    q = Qmk(path.read_bytes(), abi)
    s = Stock(stock_image)
    q.matrix()
    s.power()
    q.hardware.pin(1, 12, True)
    q.hardware.pin(0, 10, True)
    q.write(q.symbol('radio_state'), 4, 1)
    q.ms = 600000
    q.matrix()
    s.hardware.pin(1, 12, True)
    s.hardware.pin(0, 10, True)
    s.write(0x200001E4, 4, 1)
    s.write(0x200023EC, 0)
    requested = []
    s.hooks[0x8688] = lambda: requested.append(s.cpu.reg_read(UC_ARM_REG_R0)) or 0
    s.power()
    record['powered_transition_deferred_by_PA10_at_idle_deadline'] = {
        'stock_deep_idle_requests': requested,
        'stock_supply_state': s.read(0x2000001F, 1),
        'qmk_scan_reload': q.hardware.registers[0x4007600C],
    }
    results[label] = record
print(json.dumps(results, indent=2))
