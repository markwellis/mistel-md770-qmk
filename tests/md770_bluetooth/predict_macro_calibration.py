"""Export macro timing and USB wake predictions from the paired verification build."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from emulator_abi import firmware_binary, layout
from emulator_macros import MacroQmk
from emulator_usb import UsbQmk


EVENTS = [(0xE1, True), (4, True), (4, False), (0xE1, False),
          (5, True), (5, False), (6, True), (6, False), (7, True), (7, False)]
GAPS = [40, 40, 40, 15, 40, 140, 40, 540, 40]


def macro_bytes(abi):
    data = bytearray()
    for index, (code, down) in enumerate(EVENTS):
        data.extend([abi['string_prefix'], abi['string_down' if down else 'string_up'], code])
        if index < len(GAPS):
            data.extend([abi['string_prefix'], abi['string_delay']])
            data.extend(str(GAPS[index]).encode() + b'|')
    return bytes(data) + b'\0'


def event_times(reports):
    result, previous_mods, previous_keys = [], 0, set()
    for stamp, report in reports:
        mods, keys = report[0], set(report[2:]) - {0}
        result.extend((key, False, stamp) for key in sorted(previous_keys - keys))
        result.extend((0xE0 + bit, bool(mods & (1 << bit)), stamp) for bit in range(8)
                      if (previous_mods ^ mods) & (1 << bit))
        result.extend((key, True, stamp) for key in sorted(keys - previous_keys))
        previous_mods, previous_keys = mods, keys
    first = result[0][2]
    return [(code, down, stamp - first) for code, down, stamp in result]


def predict(image, abi, transport):
    machine = MacroQmk(image, abi)
    machine.start()
    machine.output_mode(transport == 'bluetooth')
    reports = []
    driver = machine.symbol('chibios_driver')
    send = machine.read(driver + abi['driver_keyboard']) & ~1
    original = machine.hooks[send]

    def timed_send():
        before = len(machine.usb_reports)
        original()
        reports.extend((machine.ms, r) for r in machine.usb_reports[before:])

    machine.hooks[send] = timed_send
    machine.load_macro(macro_bytes(abi))
    machine.play(row=11, col=1)
    for _ in range(5000):
        machine.macro_step(1)
        if transport == 'bluetooth':
            machine.task()
            if machine.hardware.output(2, 14):
                packet = machine.transfer(bytes(machine.read(machine.symbol('tx_length'), 1)))
                if packet[0] == 0xA1:
                    reports.append((machine.ms, bytes(packet[1:])))
        if not machine.playing() and not machine.queued():
            break
    else:
        raise ValueError('Macro failed to finish within the supplied time bound')
    predicted = event_times(reports)
    assert [(code, down) for code, down, _ in predicted] == EVENTS, predicted
    nominal = [0]
    for gap in GAPS:
        nominal.append(nominal[-1] + gap)
    assert [stamp for _, _, stamp in predicted] == nominal, predicted
    return {'key_events': [(code, down) for code, down, _ in predicted],
            'relative_event_times_ms': [stamp for _, _, stamp in predicted],
            'keyboard_reports': [report.hex(' ') for _, report in reports]}


def wake_prediction(image, abi):
    machine = UsbQmk(image, abi)
    machine.suspend(remote_wakeup=True)
    machine.call('usb_event_queue_task')
    asleep = bool(machine.call('md770_power_usb_suspended'))
    dark = not bool(machine.call('md770_power_rgb_allowed'))
    requests = []
    machine.hook('usbWakeupHost', lambda: requests.append(machine.ms))
    machine.call('md770_power_usb_wake')
    machine.resume()
    machine.call('usb_event_queue_task')
    resumed = not bool(machine.call('md770_power_usb_suspended'))
    assert asleep and dark and resumed and len(requests) == 1
    return {'suspend_recognised': asleep, 'lighting_suspended': dark,
            'remote_wake_requests_with_permission': len(requests), 'resume_recognised': resumed,
            'post_resume_macro_expected': 'A fresh invocation has the normal macro output and delays'}


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
    verification = json.loads(Path('docs/mistel-md770-conformance-checks-markwellis.json').read_text())
    installed = json.loads(Path('docs/mistel-md770-simplified-flash-right.json').read_text())
    assert verification['passed'] and verification['macro_elf_sha256'] == hashlib.sha256(image).hexdigest()
    checks = json.loads(Path('docs/mistel-md770-simplification-checks.json').read_text())
    qmk = args.qmk_home
    for name, expected in checks['source_sha256'].items():
        assert hashlib.sha256((qmk / name).read_bytes()).hexdigest() == expected, name
    cases = []
    for transport in ('usb', 'bluetooth'):
        prediction = predict(image, abi, transport)
        cases.append({'id': 'MT-USB' if transport == 'usb' else 'MT-BT', 'transport': transport,
                      'expected_key_events': EVENTS, 'emulator_prediction': prediction,
                      'expected_event_times_ms': prediction['relative_event_times_ms'],
                      'timing_limits': {'minimum_scale': 0.98 if transport == 'usb' else 0.95,
                                        'maximum_scale': 1.02 if transport == 'usb' else 1.05,
                                        'maximum_event_error_ms': 10 if transport == 'usb' else 45}})
    result = {'date': datetime.now(timezone.utc).isoformat(),
              'scope': 'One recorded text/modifier/delay macro and USB suspend/wake',
              'recording': 'F3: Left Shift+A, release Shift; Fn+T, B; Fn+G, C; Fn+B, D',
              'macro_bytes_hex': macro_bytes(abi).hex(),
              'prediction_build': {'validation_elf': args.elf.name,
                                   'validation_elf_sha256': hashlib.sha256(image).hexdigest(),
                                   'verification_binary_sha256': hashlib.sha256(binary).hexdigest(),
                                   'validation_binary_sha256': installed['application_sha256'],
                                   'build_kind': 'Paired verification link with the same verified keyboard sources; hardware remains on production',
                                   'abi_provenance': provenance},
              'wake_prediction': wake_prediction(image, abi),
              'timing_method': 'Native player serviced every supplied millisecond; SPI transactions complete when requested',
              'nominal_inter_event_gaps_ms': GAPS, 'cases': cases}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    print('Macro order, 935 ms duration, programmed delays and USB wake predictions passed.')


if __name__ == '__main__':
    main()
