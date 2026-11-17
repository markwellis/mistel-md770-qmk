#!/usr/bin/env python3
"""Compare a bounded Linux input capture with a software-verified calibration case."""

import argparse
from contextlib import ExitStack, closing
from datetime import datetime, timezone
import hashlib
from itertools import combinations
import json
import os
from pathlib import Path
import select
import time

SOURCE_ROOT = Path(__file__).resolve().parents[1]
HID_TO_EVDEV = {4: 30, 5: 48, 6: 46, 7: 32, 0x0D: 36, 0x2C: 57, 0xE0: 29, 0xE1: 42, 0xE5: 54}
QUICK_CASES = {
    'HC01': {'transport': 'usb', 'trigger_half': 'left', 'macro_kind': 'text', 'modifier': 'none', 'connection': 'steady'},
    'HC08': {'transport': 'bluetooth', 'trigger_half': 'right', 'macro_kind': 'chord', 'modifier': 'shift', 'connection': 'steady'},
    'HC11': {'transport': 'bluetooth', 'trigger_half': 'left', 'macro_kind': 'delay', 'modifier': 'control', 'connection': 'reconnected'},
}


def score(case, events):
    expected = [[HID_TO_EVDEV[usage], int(pressed)] for usage, pressed in case['expected_key_events']]
    if not expected:
        raise ValueError('A calibration case must contain expected key events')
    actual = [[event['code'], event['value']] for event in events
              if event['type'] == 1 and event['value'] in (0, 1)]
    lost_events = any(event['type'] == 0 and event['code'] == 3 for event in events)
    mismatch = next((index for index, values in enumerate(zip(expected, actual))
                     if values[0] != values[1]), None)
    if mismatch is None and len(expected) != len(actual):
        mismatch = min(len(expected), len(actual))
    result = {'passed': not lost_events and actual == expected, 'lost_events': lost_events,
              'oracle_events_match': not lost_events and actual == expected,
              'expected_evdev_key_events': expected,
              'actual_evdev_key_events': actual, 'first_mismatch': mismatch}
    if 'emulator_prediction' in case:
        predicted = [[HID_TO_EVDEV.get(usage), int(pressed)]
                     for usage, pressed in case['emulator_prediction']['key_events']]
        result['emulator_events_match'] = not lost_events and actual == predicted
        result['oracle_matches_emulator'] = expected == predicted
        result['passed'] &= result['emulator_events_match'] and result['oracle_matches_emulator']
    if 'expected_event_times_ms' in case:
        stamps = [event.get('time') for event in events
                  if event['type'] == 1 and event['value'] in (0, 1)]
        predicted = case['expected_event_times_ms']
        valid = (result['oracle_events_match'] and len(stamps) == len(predicted)
                 and len(stamps) > 1 and all(isinstance(t, (int, float)) for t in stamps))
        timing = {'passed': False}
        if valid:
            relative = [(stamp - stamps[0]) * 1000 for stamp in stamps]
            errors = [actual - target for actual, target in zip(relative, predicted, strict=True)]
            scale = relative[-1] / predicted[-1]
            limits = case['timing_limits']
            timing = {'passed': (limits['minimum_scale'] <= scale <= limits['maximum_scale']
                                  and max(map(abs, errors)) <= limits['maximum_event_error_ms']),
                      'actual_relative_ms': relative, 'predicted_relative_ms': predicted,
                      'event_error_ms': errors, 'duration_scale': scale,
                      'maximum_event_error_ms': max(map(abs, errors)), 'limits': limits}
        result['timing'] = timing
        result['passed'] &= timing['passed']
    return result


def capture(paths, timeout, case):
    import evdev

    events, identities, held = [], [], set()
    with ExitStack() as cleanup:
        devices = []
        for path in paths:
            device = evdev.InputDevice(path)
            cleanup.callback(device.close)
            expected_bus = 3 if case['transport'] == 'usb' else 5
            if device.info.bustype != expected_bus:
                raise ValueError('The selected input device uses a different transport from the case')
            if not any(name in device.name.casefold() for name in ('mistel', 'md770')):
                raise ValueError('The selected input device does not identify as a Mistel keyboard')
            device.grab()
            cleanup.callback(device.ungrab)
            if device.active_keys():
                raise ValueError('Release all keys before starting a capture')
            devices.append(device)
            identities.append({'name': device.name, 'bus': device.info.bustype,
                               'vendor': device.info.vendor, 'product': device.info.product})
        deadline, quiet_since = time.monotonic() + timeout, None
        print('Capture ready. Perform the case and release all keys.', flush=True)
        while time.monotonic() < deadline:
            ready, _, _ = select.select(devices, [], [], min(0.1, max(0, deadline - time.monotonic())))
            for device in ready:
                for event in device.read():
                    if event.type == 0 and event.code == 3:
                        raise ValueError('The input capture lost events (SYN_DROPPED); repeat the case')
                    if event.type != 1:
                        continue
                    events.append({'type': event.type, 'code': event.code,
                                   'value': event.value, 'time': event.timestamp()})
                    if event.value == 1:
                        held.add(event.code)
                    elif event.value == 0:
                        held.discard(event.code)
                    quiet_since = time.monotonic()
            if score(case, events)['oracle_events_match'] and not held and quiet_since is not None:
                if time.monotonic() - quiet_since >= 0.25:
                    break
    return events, identities


def capture_identity_matches(case, result, plan_hash, firmware_hash):
    expected_bus = 3 if case and case['transport'] == 'usb' else 5
    devices = result.get('devices', [])
    matching_devices = bool(devices) and all(
        device.get('bus') == expected_bus
        and any(name in device.get('name', '').casefold() for name in ('mistel', 'md770'))
        for device in devices)
    return bool(result.get('capture_mode') == 'live'
                and result.get('plan_sha256') == plan_hash
                and case and result['case'] == case and matching_devices
                and firmware_hash and result.get('reference_firmware_sha256') == firmware_hash)


def matching_capture(case, result, plan_hash, firmware_hash):
    return bool(result.get('passed') and capture_identity_matches(case, result, plan_hash, firmware_hash)
                and score(case, result.get('events', []))['passed'])


def summarise(plan, plan_hash, directory):
    expected = {case['id']: case for case in plan['cases']}
    firmware_hash = plan.get('prediction_build', {}).get('validation_binary_sha256')
    passed = set()
    ignored = 0
    for path in directory.glob('*.json'):
        result = json.loads(path.read_text())
        identifier = result.get('case', {}).get('id')
        if matching_capture(expected.get(identifier), result, plan_hash, firmware_hash):
            passed.add(identifier)
        else:
            ignored += 1
    return {'passed': passed == set(expected), 'live_cases_passed': sorted(passed),
            'remaining_cases': sorted(set(expected) - passed), 'ignored_results': ignored,
            'plan_sha256': plan_hash, 'cases_passed': len(passed), 'cases_total': len(expected),
            'live_pairs_covered': len({((left, expected[identifier][left]), (right, expected[identifier][right]))
                                       for identifier in passed for left, right in combinations(plan.get('factors', {}), 2)}),
            'required_pairs': plan.get('required_pairs', 0)}


def verify_firmware(plan, path):
    expected = plan['prediction_build']['validation_binary_sha256']
    observed = hashlib.sha256(path.read_bytes()).hexdigest()
    if observed != expected:
        raise ValueError('The supplied firmware binary differs from the software-verified prediction build')
    return observed


def capture_result(case, plan_hash, firmware_hash, paths, timeout):
    if not case.get('emulator_prediction', {}).get('key_events'):
        raise ValueError('Live calibration requires exported emulator predictions; rerun the software suite')
    started = datetime.now(timezone.utc).isoformat()
    events, identities = capture(paths, timeout, case)
    return {'date': datetime.now(timezone.utc).isoformat(), 'case': case,
            'capture_started': started, 'timeout_seconds': timeout,
            'plan_sha256': plan_hash, 'devices': identities, 'capture_mode': 'live',
            'reference_firmware_sha256': firmware_hash, 'events': events,
            'comparison_scope': ('Ordered EV_KEY press/release events and relative timing; repeats are not scored'
                                 if 'expected_event_times_ms' in case else
                                 'Ordered EV_KEY press/release events; repeats and timing are not scored'),
            **score(case, events)}


def keyboard_devices(transport):
    import evdev

    paths = []
    for path in evdev.list_devices():
        with closing(evdev.InputDevice(path)) as device:
            if (device.info.bustype == (3 if transport == 'usb' else 5)
                    and any(name in device.name.casefold() for name in ('mistel', 'md770'))
                    and evdev.ecodes.KEY_A in device.capabilities().get(evdev.ecodes.EV_KEY, [])):
                paths.append(path)
    if not paths:
        raise ValueError(f'No readable Mistel keyboard input device for {transport}')
    return paths


def selected_cases(plan):
    expected = {case['id']: case for case in plan['cases'] if case['id'] in QUICK_CASES}
    if (expected.keys() != QUICK_CASES.keys()
            or any(expected[identifier].get(name) != value
                   for identifier, factors in QUICK_CASES.items() for name, value in factors.items())):
        raise ValueError('The plan differs from the three selected calibration cases')
    return expected


def quick_summary(plan, plan_hash, firmware_hash, captures, observations):
    expected = selected_cases(plan)
    observed = {result['case']['id']: score(expected[result['case']['id']], result.get('events', []))
                for result in captures if result['case']['id'] in expected
                and capture_identity_matches(expected[result['case']['id']], result, plan_hash, firmware_hash)}
    matched = {identifier for identifier, checks in observed.items()
               if checks.get('emulator_events_match') and checks.get('oracle_matches_emulator')}
    functional_cases = {identifier for identifier, checks in observed.items() if checks['oracle_events_match']}
    functional = ({'HC08', 'HC11'} <= functional_cases
                  and all(observations.get(name) is True for name in
                          ('usb_key_wake', 'connection_media_indicators', 'sleep_output_handover')))
    agreement = matched == set(QUICK_CASES)
    return {'date': datetime.now(timezone.utc).isoformat(), 'scope': 'Five-scenario smoke pass',
            'passed': functional and agreement, 'plan_sha256': plan_hash,
            'reference_firmware_sha256': firmware_hash,
            'bluetooth_functional': {'passed': functional, 'operator_observations': observations,
                                     'captured_cases': sorted(functional_cases & {'HC08', 'HC11'})},
            'emulator_agreement': {
                'passed': agreement, 'matched_cases': sorted(matched),
                'scope': 'Macro key/modifier press/release ordering on USB and Bluetooth, including post-reconnection delivery',
                'uncalibrated': ['Timing and auto-repeat', 'CPU/IRQ and peripheral register contracts',
                                 'Internal radio states', 'USB signalling', 'Analogue power behaviour'],
            }, 'captures': captures}


def run_quick(plan, plan_hash, firmware_hash, timeout, output):
    cases = selected_cases(plan)
    captures, observations = [], {}
    output.parent.mkdir(parents=True, exist_ok=True)
    print('Use the plan\'s validation firmware and record Q=text, I=chord, E=delay as described in the guide.')

    def play(identifier, preparation):
        case = cases[identifier]
        if input(preparation + '\nPress Enter when ready, or type fail to stop: ').strip():
            raise ValueError('The operator reported a failed or incomplete preparation')
        if identifier == 'HC01':
            observations['usb_key_wake'] = True
        print(f"Release all keys. After Capture ready: modifier={case['modifier']}, "
              f"tap {case['trigger_key']}, then release the modifier after playback.", flush=True)
        time.sleep(1)
        result = capture_result(case, plan_hash, firmware_hash, keyboard_devices(case['transport']), timeout)
        captures.append(result)
        (output.parent / f'{identifier}.json').write_text(json.dumps(result, indent=2) + '\n')
        print(f"{identifier}: hardware keys={'passed' if result['oracle_events_match'] else 'FAILED'}, "
              f"emulator={'passed' if result['emulator_events_match'] and result['oracle_matches_emulator'] else 'FAILED'}", flush=True)
        if not result['oracle_events_match']:
            raise ValueError(f'{identifier} differs from the expected hardware behaviour')

    def observe(name, prompt):
        observations[name] = input(prompt + '\nDid every listed check work? [y/N] ').strip().casefold() in ('y', 'yes')
        if not observations[name]:
            raise ValueError(f'The operator did not confirm {name}')

    error = None
    try:
        play('HC01', '1/5: Select USB (Pn+2), suspend the host, then wake it with a keyboard key.')
        observe('connection_media_indicators',
                '2/5: Select Bluetooth (Pn+1), pair/select one slot, type a few keys, '
                'try one media key and toggle Caps on/off. Check the blue connection and red Caps indications.')
        play('HC08', '3/5: Keep the Bluetooth connection established.')
        play('HC11', '4/5: Disconnect/reconnect Bluetooth and wait for the host keyboard to return.')
        observe('sleep_output_handover',
                '5/5: Keep USB connected and select Bluetooth. Suspend/resume the host, type over Bluetooth, '
                'switch to USB and type, then switch back and type. Check that no keys remain held.')
    except (OSError, ValueError, EOFError, KeyboardInterrupt) as failure:
        error = str(failure) or type(failure).__name__
    result = quick_summary(plan, plan_hash, firmware_hash, captures, observations)
    if error:
        result['error'] = error
        result['passed'] = False
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true', help='List readable Linux input devices')
    parser.add_argument('--show-plan', action='store_true', help='Show the generated calibration cases')
    parser.add_argument('--plan', type=Path, default=SOURCE_ROOT / 'docs/mistel-md770-hardware-calibration.json')
    parser.add_argument('--case', help='Case identifier, such as HC01')
    parser.add_argument('--results', type=Path, help='Summarise live results belonging to this plan')
    parser.add_argument('--quick', action='store_true', help='Guide the five-scenario pass and report Bluetooth and emulator results separately')
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--device', action='append', help='Mistel event device; repeat for multiple interfaces')
    source.add_argument('--events', type=Path, help='Score a saved capture instead of opening a device')
    parser.add_argument('--timeout', type=float, default=20)
    parser.add_argument('--out', type=Path, help='Write the capture and comparison result')
    parser.add_argument('--firmware', type=Path, help='Candidate binary; defaults to the validation build in QMK_HOME')
    args = parser.parse_args()
    if args.quick and (args.list or args.show_plan or args.results or args.case or args.device or args.events or not args.out):
        parser.error('--quick requires --out and cannot be combined with other capture modes')
    if args.list:
        import evdev
        for path in evdev.list_devices():
            with closing(evdev.InputDevice(path)) as device:
                print(f'{path}: {device.name} (bus {device.info.bustype}, {device.info.vendor:04x}:{device.info.product:04x})')
        return 0
    plan_bytes = args.plan.read_bytes()
    plan = json.loads(plan_bytes)
    plan_hash = hashlib.sha256(plan_bytes).hexdigest()
    if args.show_plan:
        print(f"{len(plan['cases'])} cases; {plan['covered_pairs']}/{plan['required_pairs']} defined pairs; "
              f"{plan['software_combinations']} combinations checked in software")
        for case in plan['cases']:
            print(' '.join(str(case[name]) for name in
                           ('id', 'transport', 'connection', 'trigger_half', 'trigger_key', 'macro_kind', 'modifier')))
        return 0
    if args.results:
        result = summarise(plan, plan_hash, args.results)
        print(json.dumps(result, indent=2))
        return 0 if result['passed'] else 1
    if args.timeout <= 0:
        parser.error('Provide a positive timeout')
    if args.quick or args.device:
        if 'prediction_build' not in plan:
            parser.error('Live capture requires a plan exported by the passing software suite')
        qmk = Path(os.environ.get('QMK_HOME', SOURCE_ROOT.parent / 'qmk_firmware'))
        candidate = args.firmware or qmk / '.build' / Path(plan['prediction_build']['validation_elf']).with_suffix('.bin')
        firmware_hash = verify_firmware(plan, candidate)
    if args.quick:
        result = run_quick(plan, plan_hash, firmware_hash, args.timeout, args.out)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
        print('Bluetooth functional:', 'passed' if result['bluetooth_functional']['passed'] else 'FAILED')
        print('Emulator agreement (macro key events):', 'passed' if result['emulator_agreement']['passed'] else 'FAILED')
        if result.get('error'):
            print(result['error'])
        print(f'Results: {args.out}')
        return 0 if result['passed'] else 1
    if not args.case or not (args.device or args.events):
        parser.error('Provide --case and either --device or --events, with a positive timeout')
    matches = [case for case in plan['cases'] if case['id'] == args.case]
    if len(matches) != 1:
        parser.error('The case identifier must select exactly one plan entry')
    case = matches[0]
    if args.events:
        events = json.loads(args.events.read_text())['events']
        result = {'date': datetime.now(timezone.utc).isoformat(), 'case': case,
                  'plan_sha256': plan_hash, 'devices': [], 'capture_mode': 'replay',
                  'events': events,
                  'comparison_scope': ('Ordered EV_KEY press/release events and relative timing; repeats are not scored'
                                       if 'expected_event_times_ms' in case else
                                       'Ordered EV_KEY press/release events; repeats and timing are not scored'),
                  **score(case, events)}
    else:
        result = capture_result(case, plan_hash, firmware_hash, args.device, args.timeout)
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
