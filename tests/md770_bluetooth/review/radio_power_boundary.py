"""Replay complete stock radio power phases, including their foreground service."""

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator_firmware import Stock

image = Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()


def snapshot(machine):
    return {
        'public': machine.read(0x200001E4, 1),
        'pending': machine.read(0x20000218, 1),
        'callback': machine.read(0x20000219, 1),
        'timer_half_ms_ticks': machine.read(0x20000216, 2),
        'request_pin': machine.hardware.output(2, 14),
        'reset_pin': machine.hardware.output(3, 1),
        'spi_clock': bool(machine.hardware.registers[0x4008802C] & 16),
    }


results = []
for kind in ('ready', 'off', 'failed', 'pending50'):
    for timer in (0, 300, 4000):
        machine = Stock(image)
        machine.ready()
        machine.write(0x200001E4, 4, 1)
        if kind == 'off':
            machine.call(0x36B8, 0)
            for _ in range(3):
                machine.task()
        if kind == 'failed':
            machine.write(0x20000219, 2, 1)
            machine.write(0x200001E6, 0, 1)
            machine.write(0x20000216, 0, 2)
            for _ in range(3):
                machine.task()
        if kind == 'pending50':
            machine.write(0x20000218, 0x50, 1)
        machine.write(0x20000216, timer, 2)
        record = {'kind': kind, 'initial_timer_half_ms_ticks': timer, 'before': snapshot(machine)}
        for address, value in ((0x20000624, 4), (0x20000625, 13), (0x20000626, 2)):
            machine.write(address, value, 1)
        for phase in (3, 2, 1, 0):
            machine.call(0x4740, phase)
        record['down'] = snapshot(machine)
        for address, value in ((0x20000624, 13), (0x20000625, 4), (0x20000626, 3)):
            machine.write(address, value, 1)
        for phase in (0, 1, 2, 3):
            machine.call(0x4740, phase)
        machine.task()
        record['up'] = snapshot(machine)
        expected = max(20, timer) if kind == 'pending50' and timer else 4000 if kind == 'pending50' else 20
        assert record['up']['timer_half_ms_ticks'] == expected
        assert record['up']['callback'] == 4
        assert record['up']['pending'] == record['before']['pending']
        assert record['up']['request_pin'] == (kind == 'pending50' and timer == 0)
        assert record['up']['reset_pin'] == record['before']['reset_pin']
        assert not record['down']['spi_clock'] and record['up']['spi_clock']
        results.append(record)

print(json.dumps({
    'stock_sha256': hashlib.sha256(image).hexdigest(),
    'boundary': 'Actual 4740/478c radio power instructions; time, SPI slave and RTOS boundaries supplied; no physical validation',
    'passed': True,
    'cases': results,
}, indent=2))
