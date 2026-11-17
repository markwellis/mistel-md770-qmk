"""Exercise compiled macro playback through real QMK reports and radio transfers."""

from pathlib import Path
import unittest

from emulator_abi import layout
from emulator_firmware import Stock
from emulator_macros import MacroQmk
from emulator_scenarios import MODIFIERS, TRIGGERS, all_cases, expected_events, hardware_plan, macro_data
import test_emulator_firmware


def key_events(reports):
    events = []
    previous_mods, previous_keys = 0, set()
    for report in reports:
        mods, keys = report[0], set(report[2:]) - {0}
        for key in sorted(previous_keys - keys):
            events.append((key, False))
        for bit in range(8):
            if (previous_mods ^ mods) & (1 << bit):
                events.append((0xE0 + bit, bool(mods & (1 << bit))))
        for key in sorted(keys - previous_keys):
            events.append((key, True))
        previous_mods, previous_keys = mods, keys
    return events


class MacroTests(unittest.TestCase):
    qmk_home = test_emulator_firmware.FirmwareTests.qmk_home
    elf_path = None

    @classmethod
    def setUpClass(cls):
        cls.qmk_home = Path(cls.qmk_home).resolve()
        cls.elf_path = cls.elf_path or cls.qmk_home / '.build/mistel_md770rgb_bt_right_default_conformance_validation.elf'
        cls.abi_provenance = {}
        cls.abi = layout(cls.qmk_home, cls.elf_path, provenance=cls.abi_provenance)
        cls.image = cls.elf_path.read_bytes()

    def machine(self, bluetooth=True):
        machine = MacroQmk(self.image, self.abi)
        machine.start()
        machine.output_mode(bluetooth)
        return machine

    def run_macro(self, machine, *, bluetooth=True, limit=2000):
        reports = []
        for _ in range(limit):
            machine.macro_step(1)
            if bluetooth:
                reports.extend(bytes(packet[1:]) for packet in machine.drain() if packet[0] == 0xA1)
            if not machine.playing() and not machine.queued():
                return reports if bluetooth else machine.usb_reports
        self.fail('The compiled macro did not complete within its supplied time bound')

    def command(self, name, code):
        return bytes([self.abi['string_prefix'], self.abi['string_' + name], code])

    def delay(self, milliseconds):
        return bytes([self.abi['string_prefix'], self.abi['string_delay']]) + str(milliseconds).encode() + b'|'

    def test_powered_boot_uses_saved_output_until_initial_usb_configuration(self):
        for saved in ('host_usb', 'host_bluetooth'):
            machine = self.machine()
            machine.hardware.pin(1, 12, True)
            machine.hardware.pin(0, 10, False)
            machine.usb(False)
            machine.set_host(saved)
            machine.matrix()
            machine.call('host_task')
            self.assertEqual(machine.read(machine.symbol('active_host'), 1), self.abi[saved])
            machine.usb(True)
            machine.matrix()
            self.assertEqual(machine.read(machine.symbol('active_host'), 1), self.abi['host_usb'])

    def test_slot_selection_switches_the_real_host_driver_without_usb_configuration(self):
        for saved in ('host_usb', 'host_bluetooth'):
            with self.subTest(saved=saved):
                machine = MacroQmk(self.image, self.abi)
                machine.start()
                machine.hardware.pin(1, 12, True)
                machine.usb(False)
                machine.set_host(saved)
                machine.write(machine.symbol('active_host'), self.abi['host_none'], 1)
                machine.call('md770_power_init')
                machine.matrix()
                machine.call('host_task')
                machine.select(1)
                machine.call('host_task')
                self.assertEqual(machine.read(machine.symbol('active_host'), 1), self.abi['host_bluetooth'])
                for _ in range(10):
                    machine.task(10)
                    if machine.hardware.output(2, 14):
                        size = machine.read(machine.symbol('tx_length'), 1)
                        packet = machine.transfer(bytes(size))
                        if packet[0] == 0xAA:
                            self.assertEqual(packet, [0xAA, 3, 1])
                            break
                else:
                    self.fail('The slot selection did not reach the supplied peer')
                machine.transfer(bytes.fromhex('b6 00 02'))
                machine.drain()
                machine.usb_reports.clear()
                machine.call('register_code', 4)
                reports = [bytes(packet[1:]) for packet in machine.drain() if packet[0] == 0xA1]
                machine.call('unregister_code', 4)
                reports.extend(bytes(packet[1:]) for packet in machine.drain() if packet[0] == 0xA1)
                self.assertEqual(key_events(reports), [(4, True), (4, False)])
                self.assertEqual(machine.usb_reports, [])

    def test_report_delivery_matches_stock_across_radio_statuses(self):
        stock_image = test_emulator_firmware.FirmwareTests.stock_path.read_bytes()
        reports = (
            (4, None, 4, 0xA1, bytes([0, 0, 4, 0, 0, 0, 0, 0])),
            (0xE9, True, 0x81, 0xA3, bytes([1])),
            (0xEC, False, 0x183, 0xA2, bytes([1, 0, 0, 0])),
        )
        for configured, state, report in (
            (configured, state, report)
            for configured in (False, True) for state in range(2, 7) for report in reports
        ):
            code, system, usage, command, payload = report
            with self.subTest(configured=configured, state=state, command=command):
                machine = self.machine()
                machine.usb(configured)
                machine.drain()
                stock = Stock(stock_image)
                stock.ready()
                stock.usb(configured)
                status = bytes([0xB6, 0, state - 2])
                machine.transfer(status)
                stock.transfer(status)
                stock.task()
                stock.task(20)
                stock.write(0x2000068C, 2, 1)
                expected, actual = [], []
                for pressed in (True, False):
                    stock.cpu.mem_write(0x20003E00, bytes([code, 0, 0, int(pressed)]))
                    stock.call(0x56A8, 0x20003E00)
                    stock.command(0x20)
                    expected.append(bytes(stock.transfer(bytes(len(payload) + 1))))
                    if system is None:
                        machine.call('register_code' if pressed else 'unregister_code', usage)
                    else:
                        machine.extra(system, usage if pressed else 0)
                    machine.task(10)
                    if machine.hardware.output(2, 14):
                        size = machine.read(machine.symbol('tx_length'), 1)
                        actual.append(bytes(machine.transfer(bytes(size))))
                self.assertEqual(expected, [bytes([command]) + payload, bytes([command]) + bytes(len(payload))])
                self.assertEqual(actual, expected)
                self.assertEqual(machine.usb_reports, [])

    def test_ascii_playback_matches_expected_key_events_on_usb_and_bluetooth(self):
        for bluetooth in (False, True):
            for text, keys in ((b'abc', (4, 5, 6)), (b'0123456789', (0x27, *range(0x1E, 0x27))),
                               (b' ', (0x2C,)), (b'\n', (0x28,))):
                with self.subTest(bluetooth=bluetooth, text=text):
                    machine = self.machine(bluetooth)
                    machine.load_macro(text + b'\x00')
                    machine.play()
                    reports = self.run_macro(machine, bluetooth=bluetooth)
                    self.assertEqual(key_events(reports),
                                     [event for key in keys for event in ((key, True), (key, False))])
                    self.assertEqual(reports[-1], bytes(8))

    def test_shifted_text_releases_its_modifiers_on_both_outputs(self):
        for bluetooth in (False, True):
            with self.subTest(bluetooth=bluetooth):
                machine = self.machine(bluetooth)
                machine.load_macro(b'A!\x00')
                machine.play()
                reports = self.run_macro(machine, bluetooth=bluetooth)
                self.assertEqual(key_events(reports), [
                    (0xE1, True), (4, True), (4, False), (0xE1, False),
                    (0xE1, True), (0x1E, True), (0x1E, False), (0xE1, False),
                ])
                self.assertEqual(reports[-1], bytes(8))

    def test_delay_preserves_the_chord_until_the_deadline(self):
        machine = self.machine()
        data = (self.command('down', 0xE0) + self.command('down', 4) + self.delay(1000)
                + self.command('up', 4) + self.command('up', 0xE0) + b'\x00')
        machine.load_macro(data)
        machine.play()
        reports = []
        for _ in range(10):
            machine.macro_step()
            reports.extend(bytes(packet[1:]) for packet in machine.drain() if packet[0] == 0xA1)
            if machine.read(machine.symbol('playback_wait')) == 1000:
                break
        self.assertEqual(key_events(reports), [(0xE0, True), (4, True)])
        started = machine.read(machine.symbol('playback_started'))
        machine.ms = started + 999
        machine.macro_step()
        self.assertTrue(machine.playing())
        self.assertEqual(machine.queued(), 0)
        machine.ms = started + 1000
        reports.extend(self.run_macro(machine))
        self.assertEqual(key_events(reports), [(0xE0, True), (4, True), (4, False), (0xE0, False)])
        self.assertFalse(machine.playing())

    def test_macro_yields_at_radio_backpressure_and_then_finishes_in_order(self):
        machine = self.machine()
        text = b'abcdefghijklmnopqrstuvwxyz' * 3
        machine.load_macro(text + b'\x00')
        machine.play()
        for _ in range(10):
            machine.macro_step()
        before = machine.read(machine.symbol('playback_offset'), 2)
        self.assertTrue(machine.playing())
        self.assertLess(before, len(text))
        machine.macro_step(100)
        self.assertEqual(machine.read(machine.symbol('playback_offset'), 2), before)
        reports = self.run_macro(machine)
        expected = [event for letter in text for event in ((letter - 93, True), (letter - 93, False))]
        self.assertEqual(key_events(reports), expected)
        self.assertEqual(reports[-1], bytes(8))

    def test_physical_press_cancels_playback_and_releases_macro_keys(self):
        machine = self.machine()
        data = self.command('down', 4) + self.delay(1000) + self.command('tap', 5) + b'\x00'
        machine.load_macro(data)
        machine.play()
        machine.macro_step()
        reports = [bytes(packet[1:]) for packet in machine.drain() if packet[0] == 0xA1]
        machine.event(6, row=12, col=2)
        machine.ms += 1100
        reports.extend(self.run_macro(machine))
        self.assertEqual(key_events(reports), [(4, True), (4, False)])
        self.assertFalse(machine.playing())

    def test_slot_boundaries_and_repeat_playback_do_not_leak_keys(self):
        for slot in (0, self.abi['macro_count'] - 1):
            with self.subTest(slot=slot):
                machine = self.machine()
                machine.load_macro(self.command('tap', 4) + b'\x00', slot)
                reports = []
                for _ in range(3):
                    machine.play(slot)
                    reports.extend(self.run_macro(machine))
                self.assertEqual(key_events(reports), [(4, True), (4, False)] * 3)

    def test_every_slot_locates_its_data_after_nonempty_macros(self):
        data = b''.join(self.command('tap', 4 + slot) + b'\x00' for slot in range(self.abi['macro_count']))
        for slot in range(self.abi['macro_count']):
            with self.subTest(slot=slot):
                machine = self.machine()
                machine.macro_buffer[:len(data)] = data
                machine.play(slot)
                reports = self.run_macro(machine)
                self.assertEqual(key_events(reports), [(4 + slot, True), (4 + slot, False)])

    def test_calibration_trigger_positions_match_the_compiled_base_keymap(self):
        machine = self.machine()
        codes = {'Q': 0x14, 'W': 0x1A, 'E': 0x08, 'U': 0x18, 'I': 0x0C, 'O': 0x12}
        for half in TRIGGERS.values():
            for name, row, col in half.values():
                with self.subTest(key=name):
                    offset = (row * self.abi['matrix_cols'] + col) * 2
                    self.assertEqual(machine.read(machine.symbol('keymaps') + offset, 2), codes[name])

    def test_invalid_macro_data_releases_held_keys(self):
        for suffix in (b'\xff\x00', bytes([self.abi['string_prefix'], 0xFF, 5, 0])):
            with self.subTest(suffix=suffix.hex()):
                machine = self.machine()
                machine.load_macro(self.command('down', 4) + suffix)
                machine.play()
                reports = self.run_macro(machine)
                self.assertEqual(key_events(reports), [(4, True), (4, False)])
                self.assertEqual(reports[-1], bytes(8))

    def test_invalid_storage_marker_prevents_key_output(self):
        machine = self.machine()
        machine.load_macro(b'abc\x00')
        machine.macro_buffer[-1] = 0xFF
        machine.play()
        reports = self.run_macro(machine)
        self.assertEqual(key_events(reports), [])

    def test_usb_nkro_macro_preserves_eight_simultaneous_keys(self):
        machine = self.machine(bluetooth=False)
        machine.nkro(True)
        keys = tuple(range(4, 12))
        data = (b''.join(self.command('down', key) for key in keys)
                + self.delay(40) + b''.join(self.command('up', key) for key in reversed(keys)) + b'\x00')
        machine.load_macro(data)
        machine.play()
        reports = self.run_macro(machine, bluetooth=False)
        expected = [(key, True) for key in keys] + [(key, False) for key in reversed(keys)]
        self.assertEqual(key_events(reports), expected)
        self.assertGreater(machine.usb_nkro_count, 0)
        self.assertTrue(any(len(set(report[2:]) - {0}) == 8 for report in reports))
        self.assertEqual(reports[-1], bytes(8))

    def test_bluetooth_keeps_six_key_reports_when_nkro_is_enabled(self):
        machine = self.machine()
        machine.nkro(True)
        machine.load_macro(b'abc\x00')
        machine.play()
        reports = self.run_macro(machine)
        self.assertEqual(key_events(reports), [(4, True), (4, False), (5, True), (5, False), (6, True), (6, False)])
        self.assertEqual(machine.usb_nkro_count, 0)
        self.assertTrue(all(len(report) == 8 for report in reports))

    def test_usb_boot_protocol_uses_six_key_reports_with_nkro_enabled(self):
        machine = self.machine(bluetooth=False)
        machine.nkro(True)
        machine.write(machine.symbol('usb_device_state') + self.abi['usb_protocol'],
                      self.abi['usb_boot_protocol'], self.abi['usb_protocol_bytes'])
        machine.load_macro(b'abc\x00')
        machine.play()
        reports = self.run_macro(machine, bluetooth=False)
        self.assertEqual(key_events(reports), [(4, True), (4, False), (5, True), (5, False), (6, True), (6, False)])
        self.assertEqual(machine.usb_nkro_count, 0)

    def test_every_hardware_factor_combination_runs_in_software(self):
        self.__class__.calibration_verified = False
        self.__class__.calibration_predictions = {}
        for case in all_cases():
            with self.subTest(**case):
                bluetooth = case['transport'] == 'bluetooth'
                machine = self.machine(bluetooth)
                if case['connection'] == 'reconnected':
                    if bluetooth:
                        machine.transfer(bytes.fromhex('b6 00 00'))
                        self.assertFalse(machine.connected())
                        machine.transfer(bytes.fromhex('b6 00 02'))
                        self.assertTrue(machine.connected())
                        machine.drain()
                    else:
                        machine.usb(True, suspended=True)
                        machine.call('suspend_wakeup_init')
                        machine.usb(True)
                        machine.drain()
                held = MODIFIERS[case['modifier']]
                if held is not None:
                    machine.call('register_code', held)
                machine.load_macro(macro_data(case, self.abi))
                _, row, col = TRIGGERS[case['trigger_half']][case['macro_kind']]
                machine.play(row=row, col=col)
                reports = self.run_macro(machine, bluetooth=bluetooth)
                if held is not None:
                    machine.call('unregister_code', held)
                    if bluetooth:
                        reports.extend(bytes(packet[1:]) for packet in machine.drain() if packet[0] == 0xA1)
                events = key_events(reports)
                self.assertEqual(events, expected_events(case))
                self.assertEqual(reports[-1], bytes(8))
                self.__class__.calibration_predictions[tuple(case.values())] = {
                    'key_events': events,
                    'keyboard_reports': [report.hex(' ') for report in reports],
                }
        self.__class__.calibration_verified = True

    def test_hardware_plan_covers_all_factor_pairs(self):
        plan = hardware_plan()
        self.assertEqual(plan['software_combinations'], 72)
        self.assertEqual(plan['required_pairs'], plan['covered_pairs'])
        self.assertLess(len(plan['cases']), plan['software_combinations'])


if __name__ == '__main__':
    unittest.main()
