"""Check host-capture scoring and prevent replay files counting as hardware evidence."""

import importlib.util
import hashlib
import json
from pathlib import Path
import io
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/md770_calibrate.py'
SPEC = importlib.util.spec_from_file_location('md770_calibrate', SOURCE)
calibrate = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(calibrate)
CASE = {'id': 'HC01', 'transport': 'usb', 'expected_key_events': [[4, True], [4, False]]}
EVENTS = [{'type': 1, 'code': 30, 'value': 1}, {'type': 1, 'code': 30, 'value': 0}]


class CalibrationTests(unittest.TestCase):
    def quick_fixture(self):
        plan = json.loads((SOURCE.parent.parent / 'docs/mistel-md770-hardware-calibration.json').read_text())
        captures = []
        for case in plan['cases']:
            case['emulator_prediction'] = {'key_events': case['expected_key_events']}
            if case['id'] in calibrate.QUICK_CASES:
                events = [{'type': 1, 'code': calibrate.HID_TO_EVDEV[usage], 'value': int(pressed)}
                          for usage, pressed in case['expected_key_events']]
                captures.append({'case': case, 'passed': True, 'capture_mode': 'live', 'events': events,
                                 'plan_sha256': 'current', 'reference_firmware_sha256': 'candidate',
                                 'devices': [{'name': 'Mistel MD770', 'bus': 3 if case['transport'] == 'usb' else 5}]})
        observations = dict.fromkeys(('usb_key_wake', 'connection_media_indicators', 'sleep_output_handover'), True)
        return plan, captures, observations

    def test_emulator_prediction_must_also_match_the_independent_oracle(self):
        case = CASE | {'emulator_prediction': {'key_events': [[5, True], [5, False]]}}
        result = calibrate.score(case, EVENTS)
        self.assertFalse(result['passed'])
        self.assertFalse(result['emulator_events_match'])
        self.assertFalse(result['oracle_matches_emulator'])

    def test_quick_report_separates_observations_from_emulator_agreement(self):
        plan, captures, observations = self.quick_fixture()
        result = calibrate.quick_summary(plan, 'current', 'candidate', captures, observations)
        self.assertTrue(result['passed'])
        observations['sleep_output_handover'] = False
        result = calibrate.quick_summary(plan, 'current', 'candidate', captures, observations)
        self.assertFalse(result['bluetooth_functional']['passed'])
        self.assertTrue(result['emulator_agreement']['passed'])
        self.assertFalse(result['passed'])
        self.assertIn('Timing and auto-repeat', result['emulator_agreement']['uncalibrated'])

    def test_quick_report_requires_all_three_matching_live_predictions(self):
        plan, captures, observations = self.quick_fixture()
        for change in ({'capture_mode': 'replay'}, {'events': []}, {'plan_sha256': 'old'},
                       {'reference_firmware_sha256': 'wrong'}, {'devices': []}):
            with self.subTest(change=change):
                altered = [captures[0] | change, *captures[1:]]
                result = calibrate.quick_summary(plan, 'current', 'candidate', altered, observations)
                self.assertFalse(result['passed'])
                self.assertFalse(result['emulator_agreement']['passed'])

    def test_correct_bluetooth_keys_can_pass_while_the_emulator_prediction_fails(self):
        for usage in (5, 7):
            with self.subTest(predicted_usage=usage):
                plan, captures, observations = self.quick_fixture()
                case = next(case for case in plan['cases'] if case['id'] == 'HC08')
                case['emulator_prediction']['key_events'] = [[usage, True], [usage, False]]
                result = calibrate.quick_summary(plan, 'current', 'candidate', captures, observations)
                self.assertTrue(result['bluetooth_functional']['passed'])
                self.assertFalse(result['emulator_agreement']['passed'])
                self.assertFalse(result['passed'])

    def test_quick_selection_rejects_different_case_factors(self):
        plan, _, _ = self.quick_fixture()
        plan['cases'][0]['transport'] = 'bluetooth'
        with self.assertRaisesRegex(ValueError, 'differs'):
            calibrate.selected_cases(plan)

    def test_live_capture_requires_an_exported_prediction_before_opening_devices(self):
        with patch.object(calibrate, 'capture') as capture:
            with self.assertRaisesRegex(ValueError, 'exported emulator predictions'):
                calibrate.capture_result(CASE, 'current', 'candidate', [], 1)
        capture.assert_not_called()

    def test_guided_run_saves_captures_and_reports_a_mismatch(self):
        plan, captures, _ = self.quick_fixture()
        for failed in (False, True):
            with self.subTest(failed=failed), TemporaryDirectory(prefix='md770-guided-') as temporary:
                output = Path(temporary) / 'quick.json'

                def capture(paths, timeout, case):
                    result = next(item for item in captures if item['case']['id'] == case['id'])
                    events = [] if failed and case['id'] == 'HC11' else result['events']
                    return events, result['devices']

                with patch('builtins.input', side_effect=['', 'yes', '', '', 'yes']):
                    with patch.object(calibrate, 'keyboard_devices', return_value=['supplied-event-device']):
                        with patch.object(calibrate, 'capture', side_effect=capture):
                            with patch.object(calibrate.time, 'sleep'), patch('sys.stdout', new=io.StringIO()):
                                result = calibrate.run_quick(plan, 'current', 'candidate', 1, output)
                self.assertEqual(result['passed'], not failed)
                self.assertEqual(result['emulator_agreement']['passed'], not failed)
                self.assertEqual({path.name for path in output.parent.glob('HC*.json')},
                                 {'HC01.json', 'HC08.json', 'HC11.json'})
                self.assertEqual('error' in result, failed)

    def test_device_discovery_selects_the_requested_mistel_keyboard_transport(self):
        devices = []
        for name, bus, keys in (('Mistel MD770', 3, [30]), ('Mistel MD770', 5, [30]),
                                ('Another keyboard', 3, [30]), ('Mistel media', 3, [115])):
            device = Mock(name='device')
            device.name, device.info = name, SimpleNamespace(bustype=bus)
            device.capabilities.return_value = {1: keys}
            devices.append(device)
        evdev = SimpleNamespace(list_devices=lambda: list(range(4)), InputDevice=lambda path: devices[path],
                                ecodes=SimpleNamespace(KEY_A=30, EV_KEY=1))
        with patch.dict(sys.modules, {'evdev': evdev}):
            self.assertEqual(calibrate.keyboard_devices('usb'), [0])
            self.assertEqual(calibrate.keyboard_devices('bluetooth'), [1])
        for device in devices:
            self.assertEqual(device.close.call_count, 2)

    def test_changed_candidate_binary_is_rejected(self):
        with TemporaryDirectory(prefix='md770-calibration-binary-') as temporary:
            path = Path(temporary) / 'candidate.bin'
            data = b'verified candidate'
            plan = {'prediction_build': {'validation_binary_sha256': hashlib.sha256(data).hexdigest()}}
            path.write_bytes(data)
            self.assertEqual(calibrate.verify_firmware(plan, path), hashlib.sha256(data).hexdigest())
            path.write_bytes(data + b'changed')
            with self.assertRaisesRegex(ValueError, 'differs'):
                calibrate.verify_firmware(plan, path)

    def test_ordered_keys_pass_with_unscored_repeat_and_sync_events(self):
        events = [EVENTS[0], {'type': 1, 'code': 30, 'value': 2},
                  {'type': 0, 'code': 0, 'value': 0}, EVENTS[1]]
        self.assertTrue(calibrate.score(CASE, events)['passed'])

    def test_missing_release_extra_key_and_wrong_order_fail(self):
        for events in (EVENTS[:1], EVENTS[::-1], EVENTS + EVENTS):
            with self.subTest(events=events):
                result = calibrate.score(CASE, events)
                self.assertFalse(result['passed'])
                self.assertIsNotNone(result['first_mismatch'])

    def test_empty_expected_trace_is_rejected(self):
        with self.assertRaises(ValueError):
            calibrate.score({'expected_key_events': []}, [])

    def test_lost_input_events_prevent_a_passing_score(self):
        events = [EVENTS[0], {'type': 0, 'code': 3, 'value': 0}, EVENTS[1]]
        result = calibrate.score(CASE, events)
        self.assertFalse(result['passed'])
        self.assertTrue(result['lost_events'])

    def test_summary_requires_live_consistent_captures_from_the_same_plan(self):
        with TemporaryDirectory(prefix='md770-calibration-') as temporary:
            directory = Path(temporary)
            path = directory / 'result.json'
            result = {'case': CASE, 'passed': True, 'capture_mode': 'replay', 'events': EVENTS,
                      'plan_sha256': 'current', 'devices': [{'name': 'Mistel MD770', 'bus': 3}],
                      'reference_firmware_sha256': 'candidate'}
            plan = {'cases': [CASE], 'prediction_build': {'validation_binary_sha256': 'candidate'}}
            for changes in ({}, {'capture_mode': 'live', 'plan_sha256': 'old'},
                            {'capture_mode': 'live', 'events': []},
                            {'capture_mode': 'live', 'events': EVENTS + [{'type': 0, 'code': 3, 'value': 0}]},
                            {'capture_mode': 'live', 'reference_firmware_sha256': 'different'},
                            {'capture_mode': 'live', 'devices': [{'name': 'Mistel MD770', 'bus': 5}]}):
                with self.subTest(changes=changes):
                    path.write_text(json.dumps(result | changes))
                    summary = calibrate.summarise(plan, 'current', directory)
                    self.assertFalse(summary['passed'])
                    self.assertEqual(summary['remaining_cases'], ['HC01'])
            path.write_text(json.dumps(result | {'capture_mode': 'live'}))
            summary = calibrate.summarise(plan, 'current', directory)
            self.assertTrue(summary['passed'])
            self.assertEqual(summary['live_cases_passed'], ['HC01'])

    def test_wrong_transport_is_rejected_before_grabbing(self):
        device = Mock(name='device')
        device.name = 'Mistel MD770'
        device.info = SimpleNamespace(bustype=5)
        with patch.dict(sys.modules, {'evdev': SimpleNamespace(InputDevice=lambda path: device)}):
            with self.assertRaisesRegex(ValueError, 'different transport'):
                calibrate.capture(['supplied-event-device'], 1, CASE)
        device.grab.assert_not_called()
        device.close.assert_called_once()

    def test_capture_error_releases_the_device_grab(self):
        device = Mock(name='device')
        device.name = 'Mistel MD770'
        device.info = SimpleNamespace(bustype=3, vendor=0x04D9, product=0x0419)
        device.active_keys.return_value = []
        device.read.side_effect = OSError('Device removed')
        with patch.dict(sys.modules, {'evdev': SimpleNamespace(InputDevice=lambda path: device)}):
            with patch.object(calibrate.select, 'select', return_value=([device], [], [])):
                with self.assertRaisesRegex(OSError, 'Device removed'):
                    calibrate.capture(['supplied-event-device'], 1, CASE)
        device.ungrab.assert_called_once()
        device.close.assert_called_once()

    def test_initially_held_keys_and_lost_live_events_release_the_grab(self):
        for held in ([29], []):
            with self.subTest(held=held):
                device = Mock(name='device')
                device.name = 'Mistel MD770'
                device.info = SimpleNamespace(bustype=3, vendor=0x04D9, product=0x0419)
                device.active_keys.return_value = held
                device.read.return_value = [SimpleNamespace(type=0, code=3)]
                with patch.dict(sys.modules, {'evdev': SimpleNamespace(InputDevice=lambda path: device)}):
                    with patch.object(calibrate.select, 'select', return_value=([device], [], [])):
                        with self.assertRaisesRegex(ValueError, 'Release all keys' if held else 'SYN_DROPPED'):
                            calibrate.capture(['supplied-event-device'], 1, CASE)
                device.ungrab.assert_called_once()
                device.close.assert_called_once()

    def test_cli_replay_is_labelled_and_does_not_complete_hardware_calibration(self):
        with TemporaryDirectory(prefix='md770-calibration-cli-') as temporary:
            directory = Path(temporary)
            plan, events, result = (directory / name for name in ('plan.json', 'events.json', 'result.json'))
            plan.write_text(json.dumps({'cases': [CASE]}))
            events.write_text(json.dumps({'events': EVENTS}))
            process = subprocess.run([sys.executable, str(SOURCE), '--plan', str(plan),
                                      '--case', 'HC01', '--events', str(events), '--out', str(result)],
                                     capture_output=True, text=True, check=True)
            self.assertTrue(json.loads(process.stdout)['passed'])
            self.assertEqual(json.loads(result.read_text())['capture_mode'], 'replay')
            summary = subprocess.run([sys.executable, str(SOURCE), '--plan', str(plan),
                                      '--results', str(directory)], capture_output=True, text=True)
            self.assertEqual(summary.returncode, 1)
            self.assertEqual(json.loads(summary.stdout)['remaining_cases'], ['HC01'])


if __name__ == '__main__':
    unittest.main()
