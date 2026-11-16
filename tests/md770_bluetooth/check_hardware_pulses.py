"""Measure known diagnostic pulses on the actual USB and Bluetooth inputs."""

import argparse
from contextlib import ExitStack
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.md770_calibrate import keyboard_devices
from scripts.md770_notify import find_device
from read_driver_diagnostics import read_page


def snapshot(fd):
    result = {}
    for page in (0, 1, 3, 4, 6, 10, 11, 12):
        result.update(read_page(fd, page))
    return result


def main():
    import evdev

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    cases, identities, failure, restore = [], [], None, None
    raw_available = False
    try:
        with ExitStack() as cleanup:
            fd = os.open(find_device(), os.O_RDWR | os.O_NONBLOCK)
            cleanup.callback(os.close, fd)
            try:
                devices, raw_devices = [], []
                for transport in ('usb', 'bluetooth'):
                    for path in keyboard_devices(transport):
                        device = evdev.InputDevice(path)
                        cleanup.callback(device.close)
                        device.grab()
                        cleanup.callback(device.ungrab)
                        if device.active_keys():
                            raise ValueError('Release all keys on the test keyboard')
                        devices.append(device)
                        identities.append({'name': device.name, 'bus': device.info.bustype,
                                           'vendor': device.info.vendor, 'product': device.info.product,
                                           'unique': device.uniq})
                bluetooth_ids = {device.uniq.casefold() for device in devices if device.info.bustype == 5 and device.uniq}
                for node in Path('/sys/class/hidraw').glob('hidraw*'):
                    properties = dict(line.split('=', 1) for line in (node / 'device/uevent').read_text().splitlines() if '=' in line)
                    if properties.get('HID_UNIQ', '').casefold() in bluetooth_ids and properties.get('HID_ID', '').startswith('0005:'):
                        raw = os.open(Path('/dev') / node.name, os.O_RDONLY | os.O_NONBLOCK)
                        cleanup.callback(os.close, raw)
                        raw_devices.append(raw)
                raw_available = bool(raw_devices)
                for mode, name, key in ((1, 'driver', 30), (2, 'qmk', 36), (3, 'unguarded', 30)):
                    for device in devices:
                        try:
                            list(device.read())
                        except BlockingIOError:
                            pass
                    for raw in raw_devices:
                        try:
                            os.read(raw, 4096)
                        except BlockingIOError:
                            pass
                    before = snapshot(fd)
                    started = datetime.now(timezone.utc).isoformat()
                    accepted = read_page(fd, 17, mode)
                    if accepted['test_mode'] != mode:
                        raise ValueError('The diagnostic pulse was not accepted')
                    events, raw_reports, finished = [], [], None
                    deadline = time.monotonic() + 8
                    while time.monotonic() < deadline:
                        ready, _, _ = select.select([*devices, *raw_devices], [], [], 0.05)
                        for source in ready:
                            if isinstance(source, int):
                                report = os.read(source, 4096)
                                if not report:
                                    raise ValueError('The Bluetooth raw input endpoint closed')
                                raw_reports.append({'time': time.time(), 'hex': report.hex(' ')})
                                continue
                            incoming = list(source.read())
                            if not incoming:
                                raise ValueError('A keyboard input endpoint closed during the pulse')
                            for event in incoming:
                                if event.type == 0 and event.code == 3:
                                    raise ValueError('The input capture lost events')
                                if event.type == 1:
                                    events.append({'bus': source.info.bustype, 'type': event.type,
                                                   'code': event.code, 'value': event.value, 'time': event.timestamp()})
                        status = read_page(fd, 12)
                        if status['test_completed'] > before['test_completed'] and finished is None:
                            finished = time.monotonic()
                        if finished is not None and time.monotonic() - finished >= 1:
                            break
                    after = snapshot(fd)
                    actual = [[event['code'], event['value']] for event in events if event['bus'] == 5 and event['value'] in (0, 1)]
                    usb = [[event['code'], event['value']] for event in events if event['bus'] == 3 and event['value'] in (0, 1)]
                    expected = [[key, 1], [key, 0]]
                    passed = actual == expected and not usb and after['test_completed'] > before['test_completed']
                    case = {'mode': name, 'capture_started': started, 'date': datetime.now(timezone.utc).isoformat(),
                            'passed': passed, 'expected_bluetooth_events': expected, 'bluetooth_events': actual,
                            'usb_events': usb, 'events': events, 'bluetooth_raw_reports': raw_reports,
                            'before': before, 'after': after}
                    cases.append(case)
                    print(json.dumps({'mode': name, 'passed': passed, 'bluetooth_events': actual, 'usb_events': usb,
                                      'keyboard_calls': after['keyboard_calls'] - before['keyboard_calls'],
                                      'keyboard_drops': after['keyboard_drops'] - before['keyboard_drops'],
                                      'frames_started': after['keyboard_frames_started'] - before['keyboard_frames_started'],
                                      'frames_completed': after['keyboard_frames_completed'] - before['keyboard_frames_completed']}), flush=True)
            finally:
                restore = read_page(fd, 19, 1)
    except (OSError, RuntimeError, ValueError) as error:
        failure = str(error)
    result = {'date': datetime.now(timezone.utc).isoformat(), 'capture_mode': 'live',
              'scope': 'Automated diagnostic pulses; tests routing and radio delivery, not physical keys or macro calibration',
              'passed': len(cases) == 3 and all(case['passed'] for case in cases) and not failure,
              'devices': identities, 'bluetooth_raw_available': raw_available, 'cases': cases,
              'usb_restore': restore}
    if failure:
        result['error'] = failure
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    if os.environ.get('SUDO_UID'):
        os.chown(args.out, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    print(json.dumps({'passed': result['passed'], 'error': failure}), flush=True)
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
