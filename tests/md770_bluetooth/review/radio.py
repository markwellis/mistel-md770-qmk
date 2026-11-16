"""Replay the frozen candidate failure and the corrected stock hold-time oracle."""

import hashlib
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path('tests/md770_bluetooth').resolve()))
from emulator import STOP
from emulator_firmware import Stock
from test_emulator_firmware import FirmwareTests

manifest = json.loads(Path('docs/mistel-md770-stock-parity-candidate-build.json').read_text())
target = 'mistel_md770rgb_bt_right_default_stock_parity'
expected = next(row['elf_sha256'] for row in manifest['images'] if row['target'] == target)
FirmwareTests.elf_path = Path('../qmk_firmware/.build') / (target + '.elf')
if hashlib.sha256(FirmwareTests.elf_path.read_bytes()).hexdigest() != expected:
    raise ValueError('This historical review requires its recorded candidate ELF')
FirmwareTests.setUpClass()
fixture = FirmwareTests()

qmk, stock = fixture.qmk(), fixture.stock()
stock.task()
stock.task(20)
qmk.select(1)
qmk.drain()
stock.call(0x36B8, 0x41)
stock.command(0x41)
assert stock.transfer(bytes(3)) == [0xAA, 3, 1]
stock.task()
stock.task(20)
qmk.hardware.spi.errors = stock.hardware.spi.errors = 8
qmk.poll()
stock.call(STOP - 2)
qmk.task()
stock.task()
qmk.task(1000)
qmk.task(1500)
stock.task(5000)
observed_qmk = [qmk.read(qmk.symbol(name), 1) for name in ('phase', 'radio_state', 'startup_attempts')]
observed_stock = [stock.read(address, 1) for address in (0x20000219, 0x200001E4, 0x200001E6)]
assert observed_qmk == [6, 7, 0], observed_qmk
assert observed_stock == [4, 2, 0], observed_stock
result = {'scope': 'Historical software-only review; no hardware inference',
          'candidate_elf_sha256': expected,
          'single_spi_error_after_short_selection': {
              'qmk_phase_public_attempts': observed_qmk,
              'stock_callback_public_attempts': observed_stock,
              'candidate_rejected': True}}

boundaries = []
for ticks, command in ((5999, 0), (6000, 0x51)):
    stock = Stock(FirmwareTests.stock_image)
    stock.cpu.mem_write(0x20000231, bytes([0xFF] * 15))
    for index in (0x35, 0x68):
        address = 0x20000231 + index // 8
        stock.write(address, stock.read(address, 1) & ~(1 << (index % 8)), 1)
    stock.write(0x200001E4, 2, 1)
    stock.call(0x5884, 0x68, 1)
    initial = stock.read(0x20000682, 2)
    assert initial == 1
    stock.write(0x2000061C, ticks)
    counter = stock.call(0x4F74, initial, 0xFFFF00FF)
    stock.write(0x20000682, counter, 2)
    stock.call(0x5D40)
    actual = stock.read(0x20000218, 1)
    assert actual == command, (ticks, actual)
    boundaries.append({'elapsed_half_ms_ticks': ticks, 'initial_counter': initial,
                       'counter_after_elapsed': counter, 'pending_command': actual})
result['corrected_stock_pairing_boundary'] = boundaries
print(json.dumps(result, indent=2))
