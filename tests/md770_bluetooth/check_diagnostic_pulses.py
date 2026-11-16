"""Check diagnostic key pulses using the compiled Bluetooth and QMK paths."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from emulator_abi import layout
from emulator_macros import MacroQmk
from test_emulator_macros import key_events


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qmk-home', type=Path, default=Path('../qmk_firmware'))
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--json', type=Path, required=True)
    args = parser.parse_args()
    provenance = {}
    abi = layout(args.qmk_home.resolve(), args.elf, provenance=provenance)
    image = args.elf.read_bytes()
    cases = []
    for mode, state in ((1, 4), (2, 4), (3, 4), (1, 5), (3, 5)):
        machine = MacroQmk(image, abi)
        machine.start()
        machine.output_mode(mode != 2)
        machine.write(machine.symbol('radio_state'), state, 1)
        assert machine.call('md770_radio_test', mode) == 1
        packets = []
        for _ in range(100):
            machine.ms += 10
            machine.call('bluetooth_task')
            if machine.hardware.output(2, 14):
                length = machine.read(machine.symbol('current_length'), 1)
                packets.append(machine.transfer(bytes(length)))
            if not machine.read(machine.symbol('diagnostic_test_mode'), 1):
                break
        else:
            raise AssertionError('Diagnostic pulse did not complete')
        reports = [bytes(packet[1:]) for packet in packets if packet[0] == 0xA1]
        events = key_events(reports)
        usage = 13 if mode == 2 else 4
        expected = [] if (mode, state) == (1, 5) else [(usage, True), (usage, False)]
        assert events == expected, (mode, state, events)
        assert key_events(machine.usb_reports) == []
        assert machine.read(machine.symbol('diagnostic_test_completed')) == 1
        cases.append({'mode': mode, 'supplied_radio_state': state, 'events': events,
                      'keyboard_calls': machine.read(machine.symbol('diagnostic_keyboard_calls')),
                      'keyboard_drops': machine.read(machine.symbol('diagnostic_keyboard_drops'))})
    record = {'date': datetime.now(timezone.utc).isoformat(), 'passed': True,
              'scope': 'Compiled diagnostic pulse construction and routing with supplied radio acceptance; not a physical result',
              'elf_sha256': hashlib.sha256(image).hexdigest(), 'abi_provenance': provenance, 'cases': cases}
    args.json.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'passed': True, 'cases': cases}, indent=2))


if __name__ == '__main__':
    main()
