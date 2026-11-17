#!/usr/bin/env python3
"""Replay stock output shortcuts and their radio packets without hardware."""

import hashlib
import json
from pathlib import Path
import sys

import unicorn
from unicorn import UC_HOOK_CODE
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_R0

ROOT = Path(__file__).resolve().parents[3]
FIXTURES = ROOT / 'tests/md770_bluetooth'
sys.path.insert(0, str(FIXTURES))
from emulator_firmware import Stock


def replay(image, configured):
    stock = Stock(image)
    stock.usb(configured)
    stock.hardware.pin(1, 12, True)
    commands = []

    def dispatch(cpu, address, size, context):
        commands.append({
            'caller': hex((cpu.reg_read(UC_ARM_REG_LR) & ~1) - 4),
            'command': hex(cpu.reg_read(UC_ARM_REG_R0)),
        })

    stock.cpu.hook_add(UC_HOOK_CODE, dispatch, begin=0x36B8, end=0x36B8)
    stock.call(0x43A0, 2, 0)
    stock.call(0x40A4, 2, 3)
    stock.task()
    stock.task(2000)
    stock.task(3000)
    stock.task(20)
    assert stock.hardware.output(2, 14)
    startup = stock.transfer(bytes(4))
    assert startup == [0xA7, 2, 0, 1 if configured else 2], startup
    stock.task(20)
    stock.transfer(bytes.fromhex('b6 00 03'))
    stock.task(20)
    assert stock.read(0x200001E4, 1) == 5

    # Deferred selection requires stable, released matrices on both halves.
    stock.cpu.mem_write(0x20000229, bytes([0xFF] * 23))
    for index in range(7):
        stock.cpu.mem_write(0x2000025F + index * 3, bytes([0, 0, 0xFF]))
    assert stock.call(0x5490) == 1
    assert stock.call(0x5C04) == 1

    def shortcut(code, output):
        stock.cpu.mem_write(0x20003E00, bytes([code, 1, 0, 1]))
        stock.call(0x5EF8, 0x20003E00)
        stock.call(0x634C)
        assert stock.read(0x2000068C, 1) == output
        packets = []
        lengths = {0x41: 3, 0x80: 4, 0xF0: 9, 0xF1: 5, 0xF2: 2}
        for _ in range(10):
            stock.task(20)
            if stock.hardware.output(2, 14):
                command = stock.read(0x20000218, 1)
                packets.append(stock.transfer(bytes(lengths[command])))
        assert stock.read(0x20000218, 1) == 0x20
        return packets

    usb_select = shortcut(0x3B, 1)
    bluetooth_select = shortcut(0x3A, 2)
    slot_select = shortcut(0x31, 2)
    assert usb_select == []
    assert bluetooth_select == []
    assert slot_select == [
        [0xAA, 3, 1], [0xA1, *bytes(8)], [0xA3, 0], [0xA2, *bytes(4)],
    ], slot_select
    assert commands == [
        {'caller': '0x419e', 'command': '0x80'},
        {'caller': '0x6482', 'command': '0x41'},
    ], commands
    assert stock.read(0x200001E4, 1) == 2
    return {
        'usb_configured': configured,
        'startup': bytes(startup).hex(' '),
        'pn_2': usb_select,
        'pn_1': bluetooth_select,
        'short_pn_f1': [bytes(packet).hex(' ') for packet in slot_select],
        'dispatcher_calls': commands,
        'final_public_state': stock.read(0x200001E4, 1),
    }


def main():
    stock_path = ROOT / 'mistel_md770rgb_bt_right_stock.bin'
    image = stock_path.read_bytes()
    cases = [replay(image, configured) for configured in (False, True)]
    sources = [Path(__file__).resolve(), *(FIXTURES / name for name in (
        'emulator.py', 'emulator_firmware.py', 'stock_probe.py',
    ))]
    print(json.dumps({
        'scope': 'Native stock radio power-event and shortcut routines; no full boot or RF/HID validation',
        'assumptions': [
            'Existing Stock fixture supplies initial RAM, GPIO, IRQ and FIFO state; flash persistence is stubbed.',
            'PB12 is high; USB state is supplied as 0 or 5; elapsed radio callbacks are supplied at nominal 0.5 ms.',
            'SPI clocks and zero receive bytes complete outgoing transactions; b6 00 03 is supplied explicitly.',
            'Both matrix histories are supplied stable and released; internal shortcut events enter at 0x5ef8.',
            'Each shortcut is observed for 200 radio callbacks; no connected status or real radio is supplied.',
            'Absence of A4 is established for these executed paths only; this probe does not scan every caller.',
        ],
        'stock_sha256': hashlib.sha256(image).hexdigest(),
        'source_sha256': {
            str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in sources
        },
        'unicorn': unicorn.__version__,
        'passed': True,
        'cases': cases,
    }, indent=2))


if __name__ == '__main__':
    main()
