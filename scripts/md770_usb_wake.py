#!/usr/bin/env python3
"""Measure MD770 USB runtime suspend/key wake and restore its power settings."""

from contextlib import ExitStack
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import sys
import time

from md770_calibrate import keyboard_devices
from md770_notify import find_device, notify


def find_usb():
    matches = []
    for path in Path('/sys/bus/usb/devices').iterdir():
        try:
            if ((path / 'idVendor').read_text().strip() == '04d9'
                    and (path / 'idProduct').read_text().strip() == '0419'):
                matches.append(path)
        except FileNotFoundError:
            continue
    if len(matches) != 1:
        raise ValueError('Expected one MD770 right USB device')
    return matches[0]


def main():
    import evdev

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--arm-file', type=Path, help='Wait for this file after showing the controlled notification')
    args = parser.parse_args()
    usb = find_usb()
    power = usb / 'power'
    settings = ('control', 'autosuspend_delay_ms', 'wakeup')
    original = {name: (power / name).read_text().strip() for name in settings}
    number = (usb / 'devnum').read_text().strip()
    report = {'date': datetime.now(timezone.utc).isoformat(),
              'scope': 'USB device runtime suspend/wake; the laptop remains awake',
              'usb_device': usb.name, 'original_power_settings': original,
              'device_number_before': number, 'suspend_observed': False,
              'resume_observed': False, 'settings_restored': False, 'host_state_passed': False,
              'events': [], 'operator_action': 'Tap A once after USB_SUSPENDED'}
    raw = find_device()
    interface = next(parent for parent in (Path('/sys/class/hidraw') / raw.name / 'device').resolve().parents
                     if (parent / 'bInterfaceNumber').exists())
    driver = (interface / 'driver').resolve()
    isolated = False

    def metrics():
        return {name: (power / name).read_text().strip() for name in
                ('runtime_status', 'runtime_active_time', 'runtime_suspended_time',
                 'wakeup_count', 'wakeup_active_count')}

    try:
        fd = os.open(raw, os.O_RDWR | os.O_NONBLOCK)
        try:
            try:
                notify(fd, bytes([255, 0, 0]))
            except RuntimeError:
                notify(fd, bytes([255, 0, 0]))
        finally:
            os.close(fd)
        (driver / 'unbind').write_text(interface.name)
        isolated = True
        report['notification_interface_isolated'] = interface.name
        report['controlled_notification_colour'] = 'red'
        with ExitStack() as cleanup:
            devices = []
            for path in keyboard_devices('usb'):
                device = evdev.InputDevice(path)
                cleanup.callback(device.close)
                device.grab()
                cleanup.callback(device.ungrab)
                if device.active_keys():
                    raise ValueError('Release all keyboard keys before the wake check')
                devices.append(device)
            report['before'] = metrics()
            if args.arm_file:
                print('NOTIFICATION_READY: waiting before USB suspend.', file=sys.stderr, flush=True)
                deadline = time.monotonic() + 90
                while not args.arm_file.exists():
                    if time.monotonic() >= deadline:
                        raise ValueError('The controlled notification was not confirmed')
                    time.sleep(0.05)
            (power / 'wakeup').write_text('enabled')
            (power / 'autosuspend_delay_ms').write_text('1000')
            (power / 'control').write_text('auto')
            deadline = time.monotonic() + 20
            while (power / 'runtime_status').read_text().strip() != 'suspended':
                if time.monotonic() >= deadline:
                    raise ValueError('USB did not enter runtime suspend within twenty seconds')
                time.sleep(0.02)
            started = time.monotonic()
            report['suspend_observed'] = True
            report['at_suspend'] = metrics()
            print('USB_SUSPENDED: tap A once to wake the keyboard.', file=sys.stderr, flush=True)
            deadline = started + 45
            while True:
                ready, _, _ = select.select(devices, [], [], 0.02)
                for device in ready:
                    for event in device.read():
                        if event.type == evdev.ecodes.EV_SYN and event.code == evdev.ecodes.SYN_DROPPED:
                            raise ValueError('Input events were lost during the wake observation')
                        if event.type == evdev.ecodes.EV_KEY:
                            report['events'].append({'code': event.code, 'value': event.value,
                                                     'time': event.timestamp()})
                if (power / 'runtime_status').read_text().strip() == 'active':
                    report['resume_observed'] = True
                    report['observed_suspended_seconds'] = time.monotonic() - started
                    break
                if time.monotonic() >= deadline:
                    raise ValueError('No USB resume observed within forty-five seconds')
            (power / 'control').write_text('on')
            deadline = time.monotonic() + 0.5
            while time.monotonic() < deadline:
                ready, _, _ = select.select(devices, [], [], 0.02)
                for device in ready:
                    report['events'].extend({'code': e.code, 'value': e.value, 'time': e.timestamp()}
                                            for e in device.read() if e.type == evdev.ecodes.EV_KEY)
            report['after'] = metrics()
            report['device_number_after'] = (usb / 'devnum').read_text().strip()
            report['same_usb_enumeration'] = report['device_number_after'] == number
            report['host_state_passed'] = report['same_usb_enumeration']
    except (OSError, ValueError, RuntimeError) as error:
        report['error'] = str(error)
    finally:
        (power / 'control').write_text('on')
        for name in ('autosuspend_delay_ms', 'wakeup', 'control'):
            (power / name).write_text(original[name])
        report['restored_power_settings'] = {name: (power / name).read_text().strip() for name in settings}
        report['settings_restored'] = report['restored_power_settings'] == original
        if isolated:
            (driver / 'bind').write_text(interface.name)
        report['notification_interface_restored'] = (interface / 'driver').exists()
        report['host_state_passed'] &= report['settings_restored'] and report['notification_interface_restored']
        report['wake_key_event_captured'] = any(event['code'] == 30 for event in report['events'])
        report['operator_darkness_and_wake_confirmation_required'] = True
    print(json.dumps(report, indent=2))
    return 0 if report['host_state_passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
