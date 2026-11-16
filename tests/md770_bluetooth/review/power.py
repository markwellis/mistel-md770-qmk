import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_abi import layout
from emulator_firmware import Qmk, Stock
from emulator_macros import MacroQmk

qhome = Path('../qmk_firmware').resolve()

for _review_name, _review_sha in (
    ("mistel_md770rgb_bt_right_markwellis_validation", "181c40b170487b210dc817f0956505be21770b570cd067b6179f0a4d359dc484"),
    ("mistel_md770rgb_bt_right_markwellis_validation_stock_parity", "4cdac0829403d0be725c9b3bfeeedf670172f502790d2992f779649c88482846"),
):
    import hashlib
    if hashlib.sha256((qhome / ".build" / (_review_name + ".elf")).read_bytes()).hexdigest() != _review_sha:
        raise ValueError("This historical review requires its recorded ELF images")
spayload = Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
installed = qhome / '.build/mistel_md770rgb_bt_right_markwellis_validation.elf'
candidate = qhome / '.build/mistel_md770rgb_bt_right_markwellis_validation_stock_parity.elf'

def pair(path):
    abi = layout(qhome, path)
    return Qmk(path.read_bytes(), abi), Stock(spayload)

def indication(q, pairing):
    q.write(q.symbol('radio_started'), q.ms)
    q.write(q.symbol('radio_phases'), 680 if pairing else 4, 2)
    q.write(q.symbol('radio_interval'), 500 if pairing else 250, 2)

results = {}
for label, path in [('installed', installed), ('candidate', candidate)]:
    out = {}
    q, s = pair(path)
    q.hardware.pin(1, 12, True)
    q.hardware.pin(2, 13, True)
    q.call('md770_power_init')
    q.matrix()
    q.indicators()
    s.write(0x2000001F, 3, 1)
    s.write(0x20000020, 1, 1)
    s.hardware.pin(2, 13, True)
    s.indicators()
    q.ms = 1000
    q.hardware.pin(2, 13, False)
    s.hardware.pin(2, 13, False)
    q.indicators()
    s.indicators(2000)
    out['charge_burst_first_requested_at_1000ms'] = {
        'qmk_blue': q.hardware.registers[0x4002C09C],
        'stock_blue': s.hardware.registers[0x4002C09C],
    }

    q, s = pair(path)
    q.write(q.symbol('battery_level'), 4, 1)
    q.matrix()
    indication(q, True)
    q.indicators()
    s.write(0x2000001F, 1, 1)
    s.write(0x2000001E, 4, 1)
    s.write(0x200000C0, 4, 1)
    s.write(0x200000C2, 680, 2)
    s.write(0x200000C8, 1000, 2)
    s.indicators()
    out['pairing_low_battery_priority_at_start'] = {
        'qmk_red_blue': [q.hardware.registers[a] for a in (0x4006E098, 0x4002C09C)],
        'stock_red_blue': [s.hardware.registers[a] for a in (0x4006E098, 0x4002C09C)],
    }

    q, s = pair(path)
    indication(q, False)
    q.indicators()
    s.write(0x200000C0, 4, 1)
    s.write(0x200000C2, 4, 2)
    s.write(0x200000C8, 500, 2)
    s.indicators()
    q.ms = 250
    q.indicators()
    s.indicators(500)
    q.ms = 350
    indication(q, False)
    q.indicators()
    s.indicators(200)
    s.write(0x200000C0, 4, 1)
    s.write(0x200000C2, 4, 2)
    s.write(0x200000C8, 500, 2)
    s.indicators()
    out['slot_reselected_during_off_phase_at_350ms'] = {
        'qmk_blue': q.hardware.registers[0x4002C09C],
        'stock_blue': s.hardware.registers[0x4002C09C],
        'stock_phase_countdown': s.read(0x200000C6, 2),
    }

    q, s = pair(path)
    indication(q, True)
    q.ms = 340000
    q.indicators()
    q.matrix()
    s.write(0x2000068C, 2, 1)
    s.write(0x20000027, 2, 1)
    s.write(0x20000021, 1, 1)
    s.write(0x200000C0, 4, 1)
    s.write(0x200000C2, 0, 2)
    s.write(0x200023EC, 520000)
    s.call(0x634C)
    out['pairing_indicator_timeout'] = {
        'stock_idle_ticks_remaining': s.read(0x200023EC),
        'stock_pair_awake_flag': s.read(0x20000021, 1),
        'qmk_scan_reload': q.hardware.registers[0x4007600C],
        'qmk_activity_ms': q.read(q.symbol('activity')),
        'qmk_ms': q.ms,
    }

    q, s = pair(path)
    out['available_suspend_symbols'] = [name for name in q.symbols if any(term in name for term in ('suspend', 'wakeup', 'matrix_task', 'event_queue', 'keyboard_report', 'real_mod', 'usb_endpoint_in_send', 'matrix_previous'))]

    q, s = pair(path)
    q.start()
    q.transfer(bytes([0xB1, 2]))
    q.select(1)
    q.indicators()
    s.write(0x2000068C, 2, 1)
    s.write(0x2000068B, 2, 1)
    s.write(0x2000002A, 4000, 2)
    s.write(0x200001E4, 4, 1)
    s.write(0x200001E5, 2, 1)
    s.call(0x36B8, 0x41)
    s.indicators()
    out['select_slot_during_active_caps_indication'] = {
        'qmk_red': q.hardware.registers[0x4006E098],
        'stock_red': s.hardware.registers[0x4006E098],
        'qmk_public_leds': q.read(q.symbol('radio_leds'), 1),
        'stock_public_leds': s.read(0x200001E5, 1),
        'stock_cached_leds': s.read(0x2000068B, 1),
    }

    q, s = pair(path)
    q.start()
    q.transfer(bytes([0xB1, 2]))
    q.call('reset_radio')
    q.indicators()
    s.write(0x2000068C, 2, 1)
    s.write(0x2000068B, 2, 1)
    s.write(0x2000002A, 4000, 2)
    s.write(0x200001E4, 4, 1)
    s.write(0x200001E5, 2, 1)
    s.call(0x9F58)
    s.indicators()
    out['transport_restart_during_active_caps_indication'] = {
        'qmk_red': q.hardware.registers[0x4006E098],
        'stock_red': s.hardware.registers[0x4006E098],
        'qmk_public_leds': q.read(q.symbol('radio_leds'), 1),
        'stock_public_leds': s.read(0x200001E5, 1),
        'stock_cached_leds': s.read(0x2000068B, 1),
    }
    results[label] = out

print(json.dumps(results, indent=2))
