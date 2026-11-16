"""Stock-derived transitions and QMK input-ownership regressions."""

from pathlib import Path
import struct
import unittest

from unicorn.arm_const import UC_ARM_REG_PRIMASK, UC_ARM_REG_R0, UC_ARM_REG_R1

from emulator import STOP
from emulator_abi import layout
from emulator_firmware import Stock
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

    def stock(self):
        stock = Stock(self.stock_image)
        stock.ready()
        stock.transfer(bytes.fromhex('b6 00 02'))
        stock.task()
        stock.task(20)
        stock.write(0x2000068C, 2, 1)
        return stock

    def stock_key(self, stock, code, down):
        stock.cpu.mem_write(0x20003E00, bytes([code & 255, code >> 8, 0, int(down)]))
        stock.call(0x56A8, 0x20003E00)

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
        accepted = bool(qmk.call('pre_process_keyevent_kb', *words))
        if accepted:
            qmk.call('action_exec', *words)
        return accepted

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

    def test_pairing_hold_uses_the_actual_pn_layer_and_three_second_boundary(self):
        qmk = self.qmk()
        self.shortcut_fixture(qmk)
        qmk.task(2999)
        self.assertFalse(qmk.hardware.output(2, 14))
        qmk.task(1)
        self.assertEqual(qmk.transfer(bytes(3)), [0xAA, 3, 1])
        self.assertEqual(qmk.drain(), [[0xAA, 0, 1]])

    def test_pn_release_and_extra_key_release_disarm_the_long_hold(self):
        for release_pn in (True, False):
            qmk = self.qmk()
            self.shortcut_fixture(qmk)
            if release_pn:
                self.physical(qmk, 0, 0, False)
            else:
                self.physical(qmk, 0, 2, True)
                self.physical(qmk, 0, 2, False)
            qmk.task(4000)
            self.assertFalse(qmk.hardware.output(2, 14))
            self.assertEqual(qmk.read(qmk.symbol('pending_command'), 1), 0x20)

    def test_shortcut_waits_for_all_keys_up(self):
        qmk = self.qmk()
        self.shortcut_fixture(qmk)
        self.physical(qmk, 0, 1, False)
        qmk.task(10)
        self.assertFalse(qmk.hardware.output(2, 14))
        self.physical(qmk, 0, 0, False)
        self.assertEqual(qmk.drain()[0], [0xAA, 3, 1])

    def test_shortcut_during_initialisation_is_not_replayed_after_startup(self):
        qmk = self.qmk(connected=False)
        qmk.call('reset_radio')
        self.shortcut_fixture(qmk)
        self.physical(qmk, 0, 1, False)
        self.physical(qmk, 0, 0, False)
        qmk.task()
        self.assertEqual(qmk.read(qmk.symbol('deferred_slot'), 1), 0)
        self.assertEqual(qmk.read(qmk.symbol('pending_command'), 1), 0x80)
        qmk.task(1000)
        qmk.task(1500)
        self.assertFalse(any(p[0] == 0xAA for p in qmk.drain()))

    def test_usb_configuration_preserves_held_and_deferred_shortcuts(self):
        for long_hold in (False, True):
            qmk = self.qmk()
            self.shortcut_fixture(qmk)
            qmk.ms += 1000
            qmk.hardware.pin(1, 12, True)
            qmk.write(qmk.symbol('supply'), 2, 1)
            qmk.usb(True)
            qmk.call('md770_power_task')
            qmk.task()
            if long_hold:
                qmk.task(2000)
            else:
                self.physical(qmk, 0, 1, False)
                self.physical(qmk, 0, 0, False)
                qmk.task()
            self.assertEqual(qmk.call('connection_get_host'), self.abi['host_bluetooth'])
            self.assertEqual(qmk.read(qmk.symbol('pending_command'), 1), 0x51 if long_hold else 0x41)

    def test_forced_clear_updates_keyboard_duplicate_suppression(self):
        for nkro in (False, True):
            qmk = self.qmk()
            qmk.output_mode(False)
            qmk.nkro(nkro)
            qmk.call('register_code', 4)
            qmk.call('clear_keyboard')
            qmk.call('register_code', 4)
            self.assertEqual(key_events(qmk.usb_reports), [(4, True), (4, False), (4, True)])

    def test_release_waits_for_build_then_retry_uses_latest_image(self):
        qmk, stock = self.qmk(), self.stock()
        qmk.call('register_code', 4)
        self.stock_key(stock, 4, True)
        self.assertFalse(qmk.call('md770_radio_key_ready', 4))
        self.stock_key(stock, 4, False)
        self.assertEqual(stock.read(0x200005DA, 1), 4)
        qmk.task(10)
        stock.command(0x20)
        self.assertTrue(qmk.call('md770_radio_key_ready', 4))
        qmk.call('unregister_code', 4)
        self.stock_key(stock, 4, False)
        collision = bytes.fromhex('b6 00 02') + bytes(6)
        self.assertEqual(qmk.transfer(collision), stock.transfer(collision))
        qmk.task(10)
        stock.task()
        stock.task(20)
        self.assertEqual(qmk.transfer(bytes(9)), [0xA1, *bytes(8)])
        self.assertEqual(stock.transfer(bytes(9)), [0xA1, *bytes(8)])
        self.assertEqual(qmk.drain(), [])

    def test_recovery_causes_preserve_accepted_input_and_public_state(self):
        for cause in ('short', 'spi', 'timeout'):
            with self.subTest(cause=cause):
                qmk, stock = self.qmk(), self.stock()
                qmk.call('register_code', 4)
                self.stock_key(stock, 4, True)
                qmk.task(10)
                stock.command(0x20)
                if cause == 'short':
                    self.assertEqual(qmk.transfer(bytes(3)), stock.transfer(bytes(3)))
                elif cause == 'spi':
                    qmk.hardware.spi.errors = stock.hardware.spi.errors = 8
                    qmk.poll()
                    stock.call(STOP - 2)
                    qmk.task()
                    stock.task()
                else:
                    qmk.task(2000)
                    stock.task(4000)
                self.assertEqual(qmk.connected(), stock.read(0x200001E4, 1) == 4)
                self.assertEqual(qmk.hardware.output(2, 14), stock.hardware.output(2, 14))
                self.assertEqual(qmk.hardware.output(3, 1), stock.hardware.output(3, 1))
                qmk.call('unregister_code', 4)
                self.stock_key(stock, 4, False)
                if cause == 'timeout':
                    qmk.task(1000)
                    qmk.task(1500)
                    stock.task(2000)
                    stock.task(3000)
                qmk.task(10)
                stock.task()
                stock.task(20)
                self.assertEqual(qmk.transfer(bytes(9)), [0xA1, *bytes(8)])
                self.assertEqual(stock.transfer(bytes(9)), [0xA1, *bytes(8)])

    def test_status_is_parsed_before_cs_release_and_survives_error(self):
        qmk, stock = self.qmk(), self.stock()
        qmk.call('register_code', 4)
        self.stock_key(stock, 4, True)
        qmk.task(10)
        stock.command(0x20)
        for machine in (qmk, stock):
            machine.hardware.spi.selected = True
            for byte in bytes.fromhex('b6 00 03'):
                machine.hardware.clock(byte)
                machine.call(STOP - 2)
        self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), 5)
        self.assertEqual(stock.read(0x200001E4, 1), 5)
        qmk.task(2000)
        stock.task(4000)
        self.assertFalse(qmk.hardware.output(3, 1))
        self.assertFalse(stock.hardware.output(3, 1))
        for machine in (qmk, stock):
            machine.hardware.spi.errors = 8
            machine.call(STOP - 2)
        qmk.task()
        stock.task()
        self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), stock.read(0x200001E4, 1))

    def test_rx_only_cs_activity_has_no_command_timeout(self):
        qmk, stock = self.qmk(), self.stock()
        for machine in (qmk, stock):
            machine.hardware.spi.selected = True
            machine.call(STOP - 2)
        qmk.task(3000)
        stock.task(6000)
        self.assertFalse(qmk.hardware.output(3, 1))
        self.assertFalse(stock.hardware.output(3, 1))

    def test_valid_and_invalid_status_dispositions_match_stock(self):
        for incoming in (b'\xb6\x04', b'\xb6\xff', b'\xb7\x01', b'\xb7\x03', b'\x99', b'\xb1\x02', b'\xb6\x00\x02', b'\xb7\x02'):
            with self.subTest(incoming=incoming.hex()):
                qmk, stock = self.qmk(), self.stock()
                qmk.keyboard(bytes([0, 0, 4, 0, 0, 0, 0, 0]))
                stock.cpu.mem_write(0x200005D8, bytes([0, 0, 4, 0, 0, 0, 0, 0]))
                qmk.task(10)
                stock.command(0xF0)
                frame = incoming + bytes(9 - len(incoming))
                self.assertEqual(qmk.transfer(frame), stock.transfer(frame))
                qmk.task(10)
                stock.task()
                stock.task(20)
                self.assertEqual(qmk.hardware.output(2, 14), stock.hardware.output(2, 14))

    def test_b7_does_not_invent_a_wire_reply(self):
        for configured in (False, True):
            qmk, stock = self.qmk(), self.stock()
            qmk.usb(configured)
            qmk.drain()
            stock.usb(configured)
            self.assertEqual(qmk.transfer(bytes.fromhex('b7 02 00 00 00')),
                             stock.transfer(bytes.fromhex('b7 02 00 00 00')))

    def test_media_overlap_retains_each_held_usage(self):
        for system, usages, codes, address, command in (
            (False, (0x183, 0x18A), (0xEC, 0xED), 0x200005B1, 0xA2),
            (True, (0x81, 0x82), (0xE9, 0xEA), 0x200005AD, 0xA3),
        ):
            qmk, stock = self.qmk(), self.stock()
            name = 'host_system_key_event' if system else 'host_consumer_key_event'
            size = 1 if system else 4
            for key, down in ((0, True), (1, True), (0, False), (1, False)):
                qmk.call(name, usages[key], int(down))
                self.stock_key(stock, codes[key], down)
                qmk.task(10)
                stock.command(0x20)
                self.assertEqual(qmk.transfer(bytes(size + 1)), stock.transfer(bytes(size + 1)))
                expected = stock.read(address, size)
                self.assertEqual(int.from_bytes(qmk.cpu.mem_read(qmk.symbol('latest_system' if system else 'latest_consumer'), size), 'little'), expected)
                stock.task()
                stock.task(20)
            self.assertEqual(qmk.read(qmk.symbol('last_system_usage' if system else 'last_consumer_usage'), 2), 0)

    def test_usb_escape_is_accepted_while_radio_release_is_deferred(self):
        qmk = self.qmk()
        qmk.usb(True)
        codes = {(0, 0): 4, (0, 1): self.abi['select_usb']}
        self.physical_fixture(qmk, codes)
        self.assertTrue(self.physical(qmk, 0, 0, True))
        self.assertFalse(self.physical(qmk, 0, 0, False))
        self.assertTrue(self.physical(qmk, 0, 1, True))
        self.assertEqual(qmk.call('connection_get_host'), self.abi['host_usb'])
        self.assertFalse(self.physical(qmk, 0, 0, False))
        qmk.task(10)
        self.assertTrue(self.physical(qmk, 0, 0, False))

    def test_dirty_radio_release_rule_survives_manual_output_change(self):
        qmk, stock = self.qmk(), self.stock()
        qmk.usb(True)
        self.physical_fixture(qmk, {(0, 0): 4, (0, 1): self.abi['select_usb'], (0, 2): 5})
        self.physical(qmk, 0, 0, True)
        self.stock_key(stock, 4, True)
        self.physical(qmk, 0, 1, True)
        stock.write(0x2000068C, 1, 1)
        self.assertFalse(self.physical(qmk, 0, 0, False))
        self.stock_key(stock, 4, False)
        self.assertEqual(stock.read(0x200005DA, 1), 4)
        self.physical(qmk, 0, 2, True)
        self.stock_key(stock, 5, True)
        self.assertTrue(self.physical(qmk, 0, 0, False))
        self.stock_key(stock, 4, False)
        self.assertEqual(bytes(qmk.cpu.mem_read(qmk.symbol('latest_keyboard'), 8)), bytes(stock.cpu.mem_read(0x200005D8, 8)))

    def test_error_rejects_status_not_parsed_before_the_error_irq(self):
        qmk, stock = self.qmk(), self.stock()
        for machine in (qmk, stock):
            machine.hardware.spi.selected = True
            for byte in bytes.fromhex('b6 00 01'):
                machine.hardware.clock(byte)
            machine.hardware.spi.errors = 0x20
            machine.call(STOP - 2)
        qmk.task()
        stock.task()
        self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), 4)
        self.assertEqual(stock.read(0x200001E4, 1), 4)

    def test_physical_macro_interruption_preserves_the_new_owner(self):
        for stage in ('unbuilt', 'inflight', 'delivered'):
            for key in (4, 5):
                with self.subTest(stage=stage, key=key):
                    qmk = self.qmk()
                    qmk.load_macro(self.command('down', 4) + bytes([self.abi['string_prefix'], self.abi['string_delay']]) + b'1000|' + self.command('up', 4) + b'\0')
                    qmk.play()
                    qmk.macro_step()
                    if stage != 'unbuilt':
                        qmk.task(10)
                    if stage == 'delivered':
                        qmk.transfer(bytes(9))
                    old_wire = bytes(qmk.cpu.mem_read(qmk.symbol('tx'), 9))
                    self.physical_fixture(qmk, {(0, 0): key})
                    self.assertTrue(self.physical(qmk, 0, 0, True))
                    if stage == 'inflight':
                        self.assertEqual(bytes(qmk.cpu.mem_read(qmk.symbol('tx'), 9)), old_wire)
                    qmk.drain()
                    self.assertIn(key, qmk.cpu.mem_read(qmk.symbol('latest_keyboard') + 2, 6))
                    self.assertTrue(self.physical(qmk, 0, 0, False))
                    qmk.drain()
                    qmk.macro_step(2000)
                    self.assertEqual(qmk.drain(), [])
                    self.assertEqual(bytes(qmk.cpu.mem_read(qmk.symbol('latest_keyboard'), 8)), bytes(8))
                    self.assertFalse(qmk.playing())

    def test_macro_replacement_survives_the_replacement_trigger_release(self):
        qmk = self.qmk()
        first = self.command('down', 4) + bytes([self.abi['string_prefix'], self.abi['string_delay']]) + b'1000|' + self.command('up', 4) + b'\0'
        qmk.load_macro(first + b'b\0')
        self.physical_fixture(qmk, {(0, 0): self.abi['macro_keycode'], (0, 1): self.abi['macro_keycode'] + 1})
        self.physical(qmk, 0, 0, True)
        self.physical(qmk, 0, 0, False)
        qmk.macro_step()
        self.physical(qmk, 0, 1, True)
        self.physical(qmk, 0, 1, False)
        packets = self.pump_macro(qmk)
        self.assertEqual(key_events([bytes(p[1:]) for p in packets if p[0] == 0xA1]),
                         [(4, True), (4, False), (5, True), (5, False)])

    def test_manual_output_selection_routes_the_next_event_in_the_same_scan(self):
        for bluetooth in (False, True):
            for code in (4, 0xA8, 0xA5):
                with self.subTest(bluetooth=bluetooth, code=code):
                    qmk = self.qmk()
                    qmk.output_mode(not bluetooth)
                    qmk.usb(True)
                    qmk.drain()
                    selector = self.abi['select_bluetooth' if bluetooth else 'select_usb']
                    self.physical_fixture(qmk, {(0, 0): selector, (0, 1): code})
                    self.physical(qmk, 0, 0, True)
                    self.physical(qmk, 0, 0, False)
                    self.physical(qmk, 0, 1, True)
                    packets = qmk.drain()
                    self.assertEqual(qmk.read(qmk.symbol('active_host'), 1), self.abi['host_bluetooth' if bluetooth else 'host_usb'])
                    if code == 4:
                        self.assertEqual(any(p[0] == 0xA1 for p in packets), bluetooth)
                        self.assertEqual(bool(qmk.usb_reports), not bluetooth)
                    else:
                        self.assertEqual(any(p[0] == (0xA2 if code == 0xA8 else 0xA3) for p in packets), bluetooth)
                        self.assertEqual(qmk.usb_extra_reports, [] if bluetooth else
                                         [(self.abi['report_consumer' if code == 0xA8 else 'report_system'], 0xE2 if code == 0xA8 else 0x81)])

    def test_usb_clear_all_does_not_resurrect_radio_media(self):
        for system, first, second, name in ((False, 0x183, 0x18A, 'latest_consumer'),
                                           (True, 0x81, 0x82, 'latest_system')):
            qmk = self.qmk()
            qmk.output_mode(False)
            event = 'host_system_key_event' if system else 'host_consumer_key_event'
            qmk.call(event, first, True)
            qmk.call('clear_keyboard')
            self.assertEqual(qmk.read(qmk.symbol(name), 1), 0)
            qmk.call('connection_set_host_noeeprom', self.abi['host_bluetooth'])
            qmk.call(event, second, True)
            packets = qmk.drain()
            self.assertEqual([p[1] for p in packets if p[0] == (0xA3 if system else 0xA2)], [2])

    def test_usb_driver_enable_is_idempotent_and_stop_disables_the_actual_irq(self):
        for state in ('usb_ready', 'usb_selected', 'usb_active', 'usb_driver_suspended'):
            with self.subTest(state=state):
                qmk = self.qmk(connected=False)
                helper = qmk.function('usb_driver_set_enabled')
                qmk.hooks.pop(helper)
                qmk.usb(True)
                qmk.write(qmk.symbol('USBD1') + self.abi['usb_driver_state'], self.abi[state], self.abi['usb_driver_state_bytes'])
                qmk.call(helper, qmk.symbol('USBD1'), 1)
                self.assertEqual(qmk.read(qmk.symbol('USBD1') + self.abi['usb_driver_state'], self.abi['usb_driver_state_bytes']), self.abi[state])
                qmk.write(qmk.symbol('USBD1') + self.abi['usb_driver_state'], self.abi[state], self.abi['usb_driver_state_bytes'])
                registers = {0x400A8000: 0, 0x40088104: 0}
                access = qmk.hardware.access

                def stop_registers(address, size, value=None):
                    if address not in registers:
                        return access(address, size, value)
                    self.assertEqual(size, 4)
                    if value is None:
                        return registers[address]
                    registers[address] = value
                    return 0

                qmk.hardware.access = stop_registers
                qmk.hardware.enabled |= 1 << 29
                qmk.call(helper, qmk.symbol('USBD1'), 0)
                self.assertEqual(qmk.read(qmk.symbol('USBD1') + self.abi['usb_driver_state'], self.abi['usb_driver_state_bytes']), self.abi['usb_stop'])
                self.assertFalse(qmk.hardware.enabled & (1 << 29))
                self.assertEqual(registers[0x40088104], 0x20)

    def test_macro_pauses_without_consuming_a_release_during_recovery(self):
        qmk = self.qmk()
        qmk.load_macro(b'abc\0')
        qmk.play()
        qmk.macro_step()
        self.assertTrue(qmk.playing())
        for _ in range(100):
            qmk.macro_step(1)
        self.assertEqual(qmk.read(qmk.symbol('latest_keyboard') + 2, 1), 4)
        qmk.call('reset_radio')
        packets = self.pump_macro_after_startup(qmk)
        self.assertEqual(key_events([bytes(p[1:]) for p in packets if p[0] == 0xA1]),
                         [(4, True), (4, False), (5, True), (5, False), (6, True), (6, False)])

    def test_qmk_macro_policy_waits_for_usb_submission_before_releasing(self):
        for code, family in ((4, 1), (0xA8, 2), (0xA5, 4)):
            with self.subTest(code=code):
                qmk = self.qmk()
                qmk.output_mode(False)
                qmk.hardware.pin(1, 12, True)
                qmk.write(qmk.symbol('supply'), 3, 1)
                qmk.write(qmk.symbol('external'), 1, 1)
                qmk.usb(True, suspended=True)
                qmk.load_macro(self.command('tap', code) + b'\0')
                qmk.play()
                for _ in range(3):
                    qmk.macro_step()
                self.assertTrue(qmk.playing())
                self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), family)
                self.assertEqual(qmk.usb_reports, [])
                self.assertEqual(qmk.usb_extra_reports, [])
                qmk.usb(True)
                qmk.write(qmk.symbol('usb_resume_pending'), 1, 1)
                qmk.call('md770_power_task')
                qmk.macro_step()
                self.assertTrue(qmk.playing())
                self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), family)
                qmk.write(qmk.symbol('usb_resume_pending'), 0, 1)
                qmk.call('md770_power_task')
                for _ in range(3):
                    qmk.macro_step()
                self.assertFalse(qmk.playing())
                self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), 0)
                if code == 4:
                    self.assertEqual(key_events(qmk.usb_reports), [(4, True), (4, False)])
                else:
                    report = self.abi['report_consumer' if code == 0xA8 else 'report_system']
                    self.assertEqual(qmk.usb_extra_reports, [(report, 0xE2 if code == 0xA8 else 0x81), (report, 0)])

    def test_pending_status_irq_during_radio_reset_retains_public_state(self):
        qmk, stock = self.qmk(), self.stock()
        for machine in (qmk, stock):
            machine.hardware.spi.selected = True
            for byte in (0xB6, 0):
                machine.hardware.clock(byte)
                machine.call(STOP - 2)
        access = qmk.hardware.access
        injected = False

        def final_byte(address, size, value=None):
            nonlocal injected
            if address == 0x40004008 and value == 0 and not injected:
                self.assertEqual(qmk.cpu.reg_read(UC_ARM_REG_PRIMASK), 1)
                injected = True
                qmk.hardware.clock(1)
                qmk.hardware.pending |= 1 << 21
            return access(address, size, value)

        qmk.hardware.access = final_byte
        qmk.write(qmk.symbol('pending_command'), 0, 1)
        qmk.call('pulse_radio')
        stock.cpu.reg_write(UC_ARM_REG_PRIMASK, 1)
        stock.hardware.clock(1)
        stock.hardware.pending |= 1 << 21
        stock.call(0x36B8, 0)
        stock.cpu.reg_write(UC_ARM_REG_PRIMASK, 0)
        stock.call(STOP - 2)
        self.assertTrue(injected)
        self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), 4)
        self.assertEqual(stock.read(0x200001E4, 1), 4)

    def pump_macro_after_startup(self, qmk):
        qmk.task(1000)
        qmk.task(1500)
        return self.pump_macro(qmk)

    def test_macro_terminator_releases_an_unclosed_chord(self):
        qmk = self.qmk()
        qmk.load_macro(self.command('down', 0xE1) + self.command('down', 4) + b'\0')
        qmk.play()
        packets = self.pump_macro(qmk)
        self.assertEqual(key_events([bytes(p[1:]) for p in packets if p[0] == 0xA1]),
                         [(0xE1, True), (4, True), (4, False), (0xE1, False)])

    def test_tapping_owned_modifier_keeps_it_held(self):
        qmk = self.qmk()
        qmk.load_macro(self.command('down', 0xE1) + self.command('tap', 0xE1) + self.command('tap', 4) + self.command('up', 0xE1) + b'\0')
        qmk.play()
        packets = self.pump_macro(qmk)
        self.assertEqual(key_events([bytes(p[1:]) for p in packets if p[0] == 0xA1]),
                         [(0xE1, True), (4, True), (4, False), (0xE1, False)])

    def test_control_press_cancellation_sends_the_removed_weak_modifier(self):
        qmk = self.qmk()
        qmk.load_macro(self.command('down', 0xE1) + bytes([self.abi['string_prefix'], self.abi['string_delay']]) + b'1000|a\0')
        qmk.play()
        qmk.macro_step()
        packets = qmk.drain()
        self.physical_fixture(qmk, {(0, 0): self.abi['momentary_pn']})
        self.assertTrue(self.physical(qmk, 0, 0, True))
        packets.extend(self.pump_macro(qmk))
        self.assertEqual(key_events([bytes(p[1:]) for p in packets if p[0] == 0xA1]),
                         [(0xE1, True), (0xE1, False)])

    def test_lvd_filter_samples_half_ms_and_latches_until_foreground(self):
        qmk, stock = self.qmk(), Stock(self.stock_image)
        qmk.call('md770_power_task')
        stock.power()
        for voltage, ticks in ((3100, 20), (3300, 1), (3100, 49)):
            qmk.hardware.voltage_mv = stock.hardware.voltage_mv = voltage
            for _ in range(ticks):
                qmk.call('md770_power_tick')
            stock.voltage_tick(ticks)
        self.assertEqual(qmk.read(qmk.symbol('lvd_remaining'), 2), 1)
        self.assertEqual(stock.read(0x2000001C, 2), 1)
        qmk.call('md770_power_tick')
        stock.voltage_tick()
        qmk.hardware.voltage_mv = stock.hardware.voltage_mv = 3300
        qmk.call('md770_power_tick')
        stock.voltage_tick()
        self.assertEqual(qmk.read(qmk.symbol('lvd_remaining'), 2), 0)
        self.assertEqual(stock.read(0x2000001C, 2), 0)
        qmk.call('md770_power_task')
        stock.power()
        self.assertEqual(qmk.read(qmk.symbol('battery_level'), 1), stock.read(0x2000001E, 1))


if __name__ == '__main__':
    unittest.main()
