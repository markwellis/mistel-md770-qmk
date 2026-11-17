"""Predict two short physical-input captures using the installed production ELF."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct

from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

from emulator_abi import firmware_binary, layout
from emulator_firmware import Qmk
from test_emulator_macros import key_events


KEYS = {
    'a': (12, 2, 4),
    'j': (1, 2, 0x0D),
    'left_shift': (14, 2, 0xE1),
    'right_shift': (5, 3, 0xE5),
    'left_space': (11, 4, 0x2C),
    'right_space': (0, 4, 0x2C),
}
SEQUENCE = [
    ('a', True), ('a', False), ('j', True), ('j', False),
    ('left_shift', True), ('j', True), ('j', False), ('left_shift', False),
    ('right_shift', True), ('a', True), ('a', False), ('right_shift', False),
    ('left_space', True), ('left_space', False), ('right_space', True), ('right_space', False),
    *[('j', down) for _ in range(4) for down in (True, False)],
]


def predict(image, abi, transport):
    qmk = Qmk(image, abi)
    qmk.start()
    qmk.hardware.pin(1, 12, True)
    qmk.usb(transport == 'usb')
    host = abi['host_usb' if transport == 'usb' else 'host_bluetooth']
    qmk.write(qmk.symbol('config'), host, 1)
    qmk.write(qmk.symbol('active_host'), host, 1)
    qmk.write(qmk.symbol('default_layer_state'), 1)
    rows = [0] * abi['matrix_rows']
    qmk.hook('matrix_get_row', lambda: rows[qmk.cpu.reg_read(UC_ARM_REG_R0)])

    def compiled_key():
        layer = qmk.cpu.reg_read(UC_ARM_REG_R0) & 255
        position = qmk.cpu.reg_read(UC_ARM_REG_R1)
        row, col = (position >> 8) & 255, position & 255
        offset = ((layer * abi['matrix_rows'] + row) * abi['matrix_cols'] + col) * 2
        return qmk.read(qmk.symbol('keymaps') + offset, 2)

    qmk.hook('keymap_key_to_keycode', compiled_key)
    usb_reports, packets, reports = [], [], []

    def usb_keyboard():
        report = qmk.cpu.reg_read(UC_ARM_REG_R0)
        mods = qmk.read(report + abi['report_mods'], 1)
        keys = qmk.cpu.mem_read(report + abi['report_keys'], 6)
        usb_reports.append(bytes([mods, 0, *keys]))

    driver = qmk.symbol('chibios_driver')
    qmk.write(qmk.symbol('driver'), driver)
    qmk.hooks[qmk.read(driver + abi['driver_keyboard']) & ~1] = usb_keyboard
    for index, (name, down) in enumerate(SEQUENCE):
        row, col, usage = KEYS[name]
        offset = (row * abi['matrix_cols'] + col) * 2
        assert qmk.read(qmk.symbol('keymaps') + offset, 2) == usage, name
        rows[row] = rows[row] | (1 << col) if down else rows[row] & ~(1 << col)
        qmk.ms += 1
        event = bytearray(abi['event_bytes'])
        for field, value in [('record_row', row), ('record_col', col),
                             ('record_pressed', int(down)), ('record_type', abi['key_event'])]:
            event[abi[field] - abi['record_event']] = value
        struct.pack_into('<H', event, abi['event_time'], qmk.ms & 65535)
        event += bytes(-len(event) % 4)
        words = struct.unpack('<' + 'I' * (len(event) // 4), event)
        qmk.call('action_exec', *words)
        if transport == 'bluetooth' and (index < 16 or index == len(SEQUENCE) - 1):
            packets.extend(qmk.drain())
    if transport == 'bluetooth':
        assert all(packet[0] == 0xA1 for packet in packets), packets
        reports = [bytes(packet[1:]) for packet in packets]
    else:
        reports = usb_reports
    expected = [(KEYS[name][2], down) for name, down in SEQUENCE]
    observed = key_events(reports)
    assert observed == expected, (transport, expected, observed)
    return {'key_events': observed, 'keyboard_reports': [r.hex(' ') for r in reports],
            'radio_packets': packets}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qmk-home', type=Path, default=Path('../qmk_firmware'))
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    provenance = {}
    abi = layout(args.qmk_home.resolve(), args.elf.resolve(), provenance=provenance)
    image = args.elf.read_bytes()
    binary = firmware_binary(args.elf, image)
    installed = json.loads(Path('docs/mistel-md770-simplified-flash-right.json').read_text())
    assert hashlib.sha256(binary).hexdigest() == installed['application_sha256']
    cases = []
    for transport in ('bluetooth', 'usb'):
        cases.append({'id': 'DP-BT' if transport == 'bluetooth' else 'DP-USB',
                      'transport': transport, 'connection': 'connected',
                      'expected_key_events': [(KEYS[name][2], down) for name, down in SEQUENCE],
                      'physical_actions': [{'key': name, 'pressed': down, 'matrix': KEYS[name][:2]}
                                           for name, down in SEQUENCE],
                      'emulator_prediction': predict(image, abi, transport)})
    result = {'date': datetime.now(timezone.utc).isoformat(),
              'scope': 'Physical key/report ordering on the installed production binary',
              'prediction_build': {'validation_elf': args.elf.name,
                                   'validation_elf_sha256': hashlib.sha256(image).hexdigest(),
                                   'validation_binary_sha256': hashlib.sha256(binary).hexdigest(),
                                   'build_kind': 'installed production firmware; no diagnostic flags',
                                   'abi_provenance': provenance},
              'boundaries': ['Scan/debounce events and compiled base keymap are supplied',
                             'USB submissions are captured at the native driver callback',
                             'Bluetooth executes the radio SPI engine with supplied module transactions',
                             'Timing, repeat rate, IRQ/register accuracy and analogue power are not calibrated'],
              'cases': cases}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Both transports predict the same 24 ordered press/release events.')


if __name__ == '__main__':
    main()
