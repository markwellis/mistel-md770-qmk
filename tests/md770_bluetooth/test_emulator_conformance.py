"""Compiled integration checks for native QMK lifecycle and local radio buffering."""

from pathlib import Path
import struct
import unittest

from unicorn.arm_const import UC_ARM_REG_R0, UC_ARM_REG_R1

from emulator_abi import layout
from emulator_macros import MacroQmk
from test_emulator_macros import key_events


class ConformanceTests(unittest.TestCase):
    qmk_home = Path('../qmk_firmware')
    elf_path = None
    stock_path = Path('mistel_md770rgb_bt_right_stock.bin')

    @classmethod
    def setUpClass(cls):
        cls.elf_path = cls.elf_path or cls.qmk_home / '.build/mistel_md770rgb_bt_right_default_conformance_validation.elf'
        cls.abi = layout(cls.qmk_home.resolve(), cls.elf_path.resolve())
        cls.image = cls.elf_path.read_bytes()
        cls.stock_image = cls.stock_path.read_bytes()


    def qmk(self, connected=True):
        qmk = MacroQmk(self.image, self.abi)
        if connected:
            qmk.start()
        return qmk


    def physical_fixture(self, qmk, codes):
        qmk.physical_rows = [0] * self.abi['matrix_rows']
        qmk.write(qmk.symbol('default_layer_state'), 1)
        qmk.hook('matrix_get_row', lambda: qmk.physical_rows[qmk.cpu.reg_read(UC_ARM_REG_R0)])
        qmk.hook('keymap_key_to_keycode', lambda: codes.get(
            (qmk.cpu.reg_read(UC_ARM_REG_R0) & 255, qmk.cpu.reg_read(UC_ARM_REG_R1) & 65535),
            1 if qmk.cpu.reg_read(UC_ARM_REG_R0) & 255 else 0))


    def physical(self, qmk, row, col, down):
        event = bytearray(self.abi['event_bytes'])
        for field, value in [('record_row', row), ('record_col', col),
                             ('record_pressed', int(down)), ('record_type', self.abi['key_event'])]:
            event[self.abi[field] - self.abi['record_event']] = value
        struct.pack_into('<H', event, self.abi['event_time'], qmk.ms & 65535)
        words = struct.unpack('<' + 'I' * ((len(event) + 3) // 4), event + bytes(-len(event) % 4))
        if down:
            qmk.physical_rows[row] |= 1 << col
        else:
            qmk.physical_rows[row] &= ~(1 << col)
        qmk.call('md770_radio_matrix_changed', int(down))
        qmk.call('action_exec', *words)
        return True


    def pump_macro(self, qmk, limit=3000):
        packets = []
        for _ in range(limit):
            qmk.macro_step(1)
            packets.extend(qmk.drain())
            if not qmk.playing() and not qmk.queued():
                return packets
        self.fail('Macro did not finish within the supplied execution bound')


    def command(self, name, code):
        return bytes([self.abi['string_prefix'], self.abi['string_' + name], code])


    def shortcut_fixture(self, qmk):
        codes = {}
        for layer in range(19):
            codes[(layer, 0)] = self.abi['momentary_pn']
            codes[(layer, 1)] = self.abi['bluetooth_profile1']
            codes[(layer, 2)] = self.abi['momentary_fn']
        self.physical_fixture(qmk, codes)
        self.physical(qmk, 0, 0, True)
        self.physical(qmk, 0, 1, True)


    def test_fast_physical_taps_queue_without_waiting_for_the_radio(self):
        qmk = self.qmk()
        self.physical_fixture(qmk, {(0, 0): 4, (0, 1): 5})
        for col in (0, 1):
            self.physical(qmk, 0, col, True)
            self.physical(qmk, 0, col, False)
        reports = [bytes(p[1:]) for p in qmk.drain() if p[0] == 0xA1]
        self.assertEqual(key_events(reports), [(4, True), (4, False), (5, True), (5, False)])

    def test_physical_press_discards_the_unsent_macro_tail(self):
        qmk = self.qmk()
        self.physical_fixture(qmk, {(0, 0): 6})
        qmk.load_macro(b'abcdefghi\x00')
        qmk.play()
        for _ in range(10):
            qmk.macro_step()
        self.assertGreater(qmk.queued(), 1)
        self.physical(qmk, 0, 0, True)
        reports = [bytes(p[1:]) for p in qmk.drain() if p[0] == 0xA1]
        self.assertEqual(key_events(reports), [(6, True)])
        self.assertFalse(qmk.playing())
        self.physical(qmk, 0, 0, False)
        self.assertEqual(qmk.drain()[-1], [0xA1, *bytes(8)])

    def test_output_change_cancels_the_waiting_macro(self):
        qmk = self.qmk()
        qmk.load_macro(b'abcdefghi\x00')
        qmk.play()
        for _ in range(10):
            qmk.macro_step()
        qmk.usb(True)
        qmk.call('connection_set_host_noeeprom', self.abi['host_usb'])
        self.assertFalse(qmk.playing())
        packets = qmk.drain()
        self.assertTrue(all(not any(p[1:]) for p in packets if p[0] in (0xA1, 0xA2, 0xA3)))
        qmk.call('register_code', 6)
        self.assertEqual(qmk.usb_reports[-1][2], 6)

    def test_battery_boot_reselects_bluetooth_after_connection_initialisation(self):
        qmk = self.qmk()
        qmk.matrix()
        qmk.set_host('host_usb')
        qmk.call('keyboard_post_init_kb')
        qmk.matrix()
        self.assertEqual(qmk.call('connection_get_host'), self.abi['host_bluetooth'])

    def test_usb_resume_keeps_a_manual_bluetooth_selection(self):
        qmk = self.qmk()
        qmk.hardware.pin(0, 10, False)
        qmk.usb(True)
        qmk.matrix()
        qmk.call('connection_set_host_noeeprom', self.abi['host_bluetooth'])
        qmk.usb(True, suspended=True)
        qmk.matrix()
        qmk.usb(True)
        qmk.matrix()
        self.assertEqual(qmk.call('connection_get_host'), self.abi['host_bluetooth'])

    def test_bluetooth_typing_returns_after_usb_is_unplugged(self):
        qmk = self.qmk()
        qmk.hardware.pin(0, 10, False)
        qmk.usb(True)
        qmk.matrix()
        qmk.usb(False)
        qmk.hardware.pin(1, 12, False)
        qmk.matrix()
        qmk.drain()
        qmk.call('register_code', 4)
        qmk.call('unregister_code', 4)
        reports = [bytes(p[1:]) for p in qmk.drain() if p[0] == 0xA1]
        self.assertEqual(key_events(reports), [(4, True), (4, False)])

    def test_native_single_consumer_and_system_usage_callbacks(self):
        qmk = self.qmk()
        for system, first, second in ((False, 0x183, 0x18A), (True, 0x81, 0x82)):
            name = 'host_system_send' if system else 'host_consumer_send'
            for value in (first, second, 0):
                qmk.call(name, value)
            packets = qmk.drain()
            self.assertEqual([p[1] for p in packets], [1, 2, 0])

    def test_pairing_waits_for_the_real_three_second_hold(self):
        qmk = self.qmk()
        self.shortcut_fixture(qmk)
        qmk.task(2999)
        self.assertFalse(qmk.hardware.output(2, 14))
        qmk.task(1)
        self.assertEqual(qmk.transfer(bytes(3)), [0xAA, 3, 1])
        self.assertEqual([p for p in qmk.drain() if p[0] == 0xAA], [[0xAA, 0, 1]])
