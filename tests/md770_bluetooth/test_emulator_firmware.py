"""Run real QMK and stock instructions against the same peripheral contracts."""

import os
from pathlib import Path
import random
import unittest

from unicorn.arm_const import UC_ARM_REG_PRIMASK

from emulator import SPI_IRQ, Unsupported
from emulator_abi import layout
from emulator_firmware import Qmk, Stock

ROOT = Path(__file__).resolve().parents[2]


class FirmwareTests(unittest.TestCase):
    qmk_home = Path(os.environ.get('QMK_HOME', ROOT.parent / 'qmk_firmware'))
    elf_path = None
    stock_path = ROOT / 'mistel_md770rgb_bt_right_stock.bin'

    @classmethod
    def setUpClass(cls):
        cls.qmk_home = cls.qmk_home.resolve()
        cls.elf_path = cls.elf_path or cls.qmk_home / '.build/mistel_md770rgb_bt_right_default_mistel.elf'
        cls.abi_provenance = {}
        cls.abi = layout(cls.qmk_home, cls.elf_path, provenance=cls.abi_provenance)
        cls.image = cls.elf_path.read_bytes()
        cls.stock_image = cls.stock_path.read_bytes()

    def qmk(self, connected=True):
        machine = Qmk(self.image, self.abi)
        if connected:
            machine.start()
        return machine

    def stock(self):
        machine = Stock(self.stock_image)
        machine.ready()
        machine.transfer(bytes.fromhex('b6 00 02'))
        return machine

    def test_keyboard_packets_match_stock_with_batched_irqs(self):
        for batch in (1, 3, 6):
            with self.subTest(batch=batch):
                qmk, stock = self.qmk(), self.stock()
                for report in (bytes.fromhex('02 00 04 00 00 00 00 00'), bytes(8)):
                    qmk.keyboard(report)
                    qmk.task(10)
                    stock.cpu.mem_write(0x200005D8, report)
                    stock.command(0xF0)
                    expected = [0xA1, *report]
                    self.assertEqual(qmk.transfer(bytes(9), batch), expected)
                    self.assertEqual(stock.transfer(bytes(9), batch), expected)

    def test_consumer_and_system_packets_match_stock(self):
        for system, usage, command, address, payload in (
            (False, 0xE9, 0xF1, 0x200005B1, bytes.fromhex('00 04 00 00')),
            (False, 0, 0xF1, 0x200005B1, bytes(4)),
            (True, 0x81, 0xF2, 0x200005AD, bytes([1])),
            (True, 0x82, 0xF2, 0x200005AD, bytes([2])),
            (True, 0x83, 0xF2, 0x200005AD, bytes([4])),
            (True, 0, 0xF2, 0x200005AD, bytes([0])),
        ):
            with self.subTest(system=system, usage=usage):
                qmk, stock = self.qmk(), self.stock()
                qmk.extra(system, usage)
                qmk.task(10)
                stock.cpu.mem_write(address, payload)
                stock.command(command)
                expected = [0xA3 if system else 0xA2, *payload]
                self.assertEqual(qmk.transfer(bytes(len(expected))), expected)
                self.assertEqual(stock.transfer(bytes(len(expected))), expected)

    def test_host_selection_matches_stock(self):
        for slot in (1, 2, 3):
            with self.subTest(slot=slot):
                qmk, stock = self.qmk(), self.stock()
                qmk.select(slot)
                packets = qmk.drain()
                stock.command(0x40 + slot)
                expected = [0xAA, 3, slot]
                self.assertEqual(packets[0], expected)
                self.assertEqual(stock.transfer(bytes(3)), expected)
                self.assertEqual(qmk.persistent_writes, 1)

    def test_radio_startup_reset_edges_match_stock(self):
        qmk, stock = self.qmk(connected=False), Stock(self.stock_image)
        qmk.call('reset_radio')
        stock.start_radio()
        self.assertTrue(qmk.hardware.output(3, 1))
        self.assertTrue(stock.hardware.output(3, 1))
        for elapsed, high in ((999, True), (1, False), (1499, False), (1, False)):
            with self.subTest(elapsed=elapsed):
                qmk.task(elapsed)
                stock.task(elapsed * 2)
                self.assertEqual(qmk.hardware.output(3, 1), high)
                self.assertEqual(stock.hardware.output(3, 1), high)
        for machine in (qmk, stock):
            self.assertEqual(machine.hardware.spi.registers[0], 1)
            self.assertEqual(machine.hardware.spi.registers[4], 0x108)
            self.assertEqual(machine.hardware.spi.registers[24], 0x410)

    def test_saved_slot_is_selected_after_startup_only_for_bluetooth(self):
        if 'bluetooth_init' not in self.qmk(connected=False).symbols:
            self.skipTest('Use the verification ELF retaining bluetooth_init')
        for slot, expected in ((0, 1), (1, 1), (2, 2), (3, 3), (0xffffffff, 1)):
            for transport in ('host_usb', 'host_bluetooth'):
                with self.subTest(slot=slot, transport=transport):
                    qmk = self.qmk(connected=False)
                    address = qmk.symbol('wear_leveling') + self.abi['eeconfig_keyboard']
                    qmk.write(address, slot)
                    qmk.set_host(transport)
                    qmk.call('bluetooth_init')
                    qmk.task(1000)
                    qmk.task(1500)
                    qmk.task(10)
                    self.assertEqual(qmk.transfer(bytes(4)), [0xa7, 2, 0, 2])
                    packets = qmk.drain()
                    self.assertEqual(packets, [[0xaa, 3, expected]] if transport == 'host_bluetooth' else [])
                    self.assertEqual(qmk.read(address), slot)
                    self.assertEqual(qmk.eeprom_writes, [])
                    qmk.usb(True)
                    qmk.matrix()
                    self.assertEqual(qmk.read(qmk.symbol('config'), 1), self.abi[transport])

    def test_selected_slot_is_saved_for_the_next_startup(self):
        if 'bluetooth_init' not in self.qmk(connected=False).symbols:
            self.skipTest('Use the verification ELF retaining bluetooth_init')
        for slot in (1, 2, 3):
            with self.subTest(slot=slot):
                qmk = self.qmk()
                qmk.select(slot)
                qmk.drain()
                address = qmk.symbol('wear_leveling') + self.abi['eeconfig_keyboard']
                self.assertEqual(qmk.read(address), slot)
                persisted = bytes(qmk.cpu.mem_read(qmk.symbol('wear_leveling'), self.abi['eeprom_logical_size']))
                reboot = self.qmk(connected=False)
                reboot.cpu.mem_write(reboot.symbol('wear_leveling'), persisted)
                reboot.call('bluetooth_init')
                reboot.task(1000)
                reboot.task(1500)
                reboot.task(10)
                self.assertEqual(reboot.transfer(bytes(4)), [0xa7, 2, 0, 2])
                self.assertEqual(reboot.drain(), [[0xaa, 3, slot]])

    def test_host_selection_preserves_display_cache_like_stock(self):
        for slot in (1, 2, 3):
            for pair in (False, True):
                with self.subTest(slot=slot, pair=pair):
                    qmk, stock = self.qmk(), self.stock()
                    stock.task()
                    stock.task(20)
                    for machine in (qmk, stock):
                        machine.transfer(bytes([0xB1, 2]))
                    stock.task()
                    stock.task(20)
                    control = (0x50 if pair else 0x40) + slot
                    stock.call(0x36B8, control)
                    qmk.select(slot, pair)
                    self.assertEqual(stock.read(0x200001E5, 1), 0)
                    self.assertEqual(stock.read(0x2000068B, 1), 2)
                    self.assertEqual(qmk.call('bluetooth_keyboard_leds'), stock.read(0x2000068B, 1))
                    stock.command(control)
                    expected = stock.transfer(bytes(3))
                    for _ in range(20):
                        qmk.task(10)
                        if qmk.hardware.output(2, 14):
                            size = qmk.read(qmk.symbol('tx_length'), 1)
                            packet = qmk.transfer(bytes(size))
                            if packet[0] == 0xAA:
                                break
                    else:
                        self.fail('Slot selection did not start')
                    self.assertEqual(packet, expected)
                    self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), stock.read(0x200001E4, 1))

    def test_startup_retry_exhaustion_and_manual_restart_match_stock(self):
        qmk, stock = self.qmk(connected=False), Stock(self.stock_image)
        qmk.call('reset_radio')
        stock.start_radio()
        stock.write(0x20000218, 0x80, 1)
        for attempt in range(1, 6):
            with self.subTest(attempt=attempt):
                stock.task(2000)
                stock.task(3000)
                stock.task(20)
                qmk.task(1000)
                qmk.task(1500)
                qmk.task(10)
                self.assertEqual(qmk.hardware.output(2, 14), stock.hardware.output(2, 14))
                self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), stock.read(0x200001E4, 1))
                stock.task(4000)
                qmk.task(2000)
        self.assertEqual(stock.read(0x200001E4, 1), 7)
        qmk.keyboard(bytes.fromhex('00 00 04 00 00 00 00 00'))
        self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), 7)
        stock.call(0x36B8, 0x41)
        stock.task()
        qmk.select(1)
        self.assertTrue(qmk.hardware.output(3, 1))
        self.assertTrue(stock.hardware.output(3, 1))
        self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), stock.read(0x200001E4, 1))

    def test_module_retry_budget_updates_match_stock(self):
        for remaining in (0, 1):
            with self.subTest(remaining=remaining):
                qmk, stock = self.qmk(), self.stock()
                stock.task()
                stock.task(20)
                status = bytes([0xB6, 2, remaining])
                qmk.transfer(status)
                stock.transfer(status)
                self.assertEqual(stock.read(0x200001E6, 1), remaining)
                stock.command(0xF0)
                qmk.usb(True)
                qmk.keyboard(bytes(8))
                qmk.task(10)
                stock.task(4000)
                qmk.task(2000)
                for _ in range(remaining + 1):
                    stock.task(2000)
                    stock.task(3000)
                    stock.task(20)
                    qmk.task(1000)
                    qmk.task(1500)
                    qmk.task(10)
                    self.assertEqual(qmk.hardware.output(2, 14), stock.hardware.output(2, 14))
                    self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), stock.read(0x200001E4, 1))
                    stock.task(4000)
                    qmk.task(2000)
                self.assertEqual(stock.read(0x200001E4, 1), 7)
                stock.call(0x36B8, 0x41)
                stock.task()
                qmk.usb(False)
                qmk.select(1)
                qmk.task()
                self.assertTrue(stock.hardware.output(3, 1))
                self.assertTrue(qmk.hardware.output(3, 1))
                self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), stock.read(0x200001E4, 1))

    def test_spi_configuration_survives_a_delayed_peripheral_reset(self):
        qmk = self.qmk(connected=False)
        hardware = qmk.hardware
        original = hardware.access
        pending, polls = False, 0

        def delayed_reset(address, size, value=None):
            nonlocal pending, polls
            if pending and address == 0x40088108 and value is None:
                polls += 1
                if polls == 2:
                    pending = False
                    hardware.spi.reset()
                    return 0
                return 1 << 4
            result = original(address, size, value)
            if pending and 0x40004000 <= address <= 0x40004020 and value is not None:
                hardware.spi.reset()
                pending = False
            if address == 0x40088108 and value is not None and value & (1 << 4):
                pending, polls = True, 0
            return result

        hardware.access = delayed_reset
        qmk.call('reset_radio')
        qmk.task(1000)
        qmk.task(1500)
        self.assertEqual(hardware.spi.registers[4], 0x108)
        self.assertEqual(hardware.spi.registers[24], 0x410)
        self.assertEqual(hardware.spi.registers[0], 1)

    def test_startup_usb_status_notices_match_stock(self):
        for configured in (True, False):
            with self.subTest(configured=configured):
                qmk, stock = self.qmk(connected=False), self.stock()
                qmk.usb(configured)
                qmk.call('reset_radio')
                qmk.task(1000)
                qmk.task(1500)
                qmk.task(10)
                stock.usb(configured)
                stock.command(0x80)
                expected = [0xA7, 2, 0, 1 if configured else 2]
                self.assertEqual(qmk.transfer(bytes(4)), expected)
                self.assertEqual(stock.transfer(bytes(4)), expected)

    def test_pairing_sequence_and_delay_match_stock(self):
        for slot in (1, 2, 3):
            with self.subTest(slot=slot):
                qmk, stock = self.qmk(), self.stock()
                qmk.select(slot, pair=True)
                for _ in range(20):
                    qmk.task(10)
                    if qmk.hardware.output(2, 14):
                        length = qmk.read(qmk.symbol('tx_length'), 1)
                        if qmk.transfer(bytes(length)) == [0xAA, 3, slot]:
                            break
                else:
                    self.fail('QMK did not send the pairing selection')
                stock.command(0x50 + slot)
                self.assertEqual(stock.transfer(bytes(3)), [0xAA, 3, slot])
                self.assertEqual(stock.read(0x20000216, 2), 300)
                qmk.task(149)
                stock.task(298)
                self.assertFalse(qmk.hardware.output(2, 14))
                self.assertFalse(stock.hardware.output(2, 14))
                qmk.task(1)
                stock.task(2)
                self.assertEqual(qmk.transfer(bytes(3)), [0xAA, 0, 1])
                self.assertEqual(stock.transfer(bytes(3)), [0xAA, 0, 1])

    def test_all_consumer_usages_match_stock_packet_format(self):
        usages = (0x183, 0x18A, 0x192, 0x194, 0xCD, 0xB7, 0xB6, 0xB5, 0xE2,
                  0xEA, 0xE9, 0x221, 0x223, 0x224, 0x225, 0x226, 0x227, 0x22A)
        qmk, stock = self.qmk(), self.stock()
        for index, usage in enumerate(usages):
            with self.subTest(usage=hex(usage)):
                payload = (1 << index).to_bytes(4, 'little')
                qmk.extra(False, usage)
                qmk.task(10)
                stock.cpu.mem_write(0x200005B1, payload)
                stock.command(0xF1)
                expected = [0xA2, *payload]
                self.assertEqual(qmk.transfer(bytes(5)), expected)
                self.assertEqual(stock.transfer(bytes(5)), expected)
                qmk.extra(False, 0)
                qmk.task(10)
                stock.cpu.mem_write(0x200005B1, bytes(4))
                stock.command(0xF1)
                self.assertEqual(qmk.transfer(bytes(5)), [0xA2, 0, 0, 0, 0])
                self.assertEqual(stock.transfer(bytes(5)), [0xA2, 0, 0, 0, 0])

    def test_seeded_keyboard_sequences_match_stock(self):
        generator = random.Random(20261116)
        qmk, stock = self.qmk(), self.stock()
        for index in range(128):
            mods = generator.randrange(256)
            keys = generator.sample(range(4, 0x74), generator.randrange(7))
            report = bytes([mods, 0, *keys, *([0] * (6 - len(keys)))])
            batch = (1, 2, 3, 6)[index % 4]
            with self.subTest(index=index, modifiers=mods, batch=batch):
                qmk.keyboard(report)
                qmk.task(10)
                stock.cpu.mem_write(0x200005D8, report)
                stock.command(0xF0)
                expected = [0xA1, *report]
                self.assertEqual(qmk.transfer(bytes(9), batch), expected)
                self.assertEqual(stock.transfer(bytes(9), batch), expected)

    def test_charging_and_low_voltage_indicator_edges_match_stock(self):
        for low_battery in (False, True):
            with self.subTest(low_battery=low_battery):
                qmk, stock = self.qmk(connected=False), Stock(self.stock_image)
                qmk.hardware.pin(1, 12, not low_battery)
                qmk.hardware.pin(2, 13, False)
                qmk.write(qmk.symbol('supply_known'), 1, 1)
                qmk.write(qmk.symbol('external'), int(not low_battery), 1)
                qmk.write(qmk.symbol('battery_low'), int(low_battery), 1)
                qmk.matrix()
                stock.hardware.pin(2, 13, False)
                stock.write(0x2000001F, 1 if low_battery else 3, 1)
                stock.write(0x20000020, int(not low_battery), 1)
                stock.write(0x2000001E, 4 if low_battery else 7, 1)
                previous = 0
                for elapsed in (0, 24, 25, 49, 50, 74, 75, 99, 100, 124, 125, 3124, 3125):
                    with self.subTest(elapsed=elapsed):
                        qmk.ms = elapsed
                        qmk.indicators()
                        stock.indicators((elapsed - previous) * 2)
                        previous = elapsed
                        for address in (0x4006E098, 0x4002C09C):
                            self.assertEqual(qmk.hardware.registers[address], stock.hardware.registers[address])

    def test_caps_indicator_edges_match_stock(self):
        qmk, stock = self.qmk(connected=False), Stock(self.stock_image)
        qmk.write(qmk.symbol('radio_leds'), 2, 1)
        stock.write(0x2000068C, 2, 1)
        stock.write(0x2000068B, 2, 1)
        for elapsed in (0, 463, 464, 975, 976, 1487, 1488, 1999, 2000):
            with self.subTest(elapsed=elapsed):
                qmk.ms = elapsed
                qmk.indicators()
                stock.write(0x2000002A, max(0, 4000 - elapsed * 2), 2)
                stock.indicators()
                self.assertEqual(qmk.hardware.registers[0x4006E098], stock.hardware.registers[0x4006E098])

    def test_one_lvd_threshold_filters_and_latches_the_warning(self):
        qmk = self.qmk()
        qmk.matrix()
        self.assertEqual(qmk.hardware.lvd, 0x410000)
        qmk.hardware.voltage_mv = 2849
        qmk.voltage_tick(49)
        qmk.matrix()
        self.assertFalse(qmk.call('md770_battery_low'))
        qmk.voltage_tick()
        qmk.matrix()
        self.assertTrue(qmk.call('md770_battery_low'))
        qmk.hardware.voltage_mv = 3300
        qmk.voltage_tick(100)
        qmk.matrix()
        self.assertTrue(qmk.call('md770_battery_low'))

    def test_pairing_waits_150_ms_after_selection(self):
        qmk = self.qmk()
        qmk.select(2, pair=True)
        for _ in range(20):
            qmk.task(10)
            if qmk.hardware.output(2, 14):
                length = qmk.read(qmk.symbol('tx_length'), 1)
                packet = qmk.transfer(bytes(length))
                if packet == [0xAA, 3, 2]:
                    break
        else:
            self.fail('The selection packet was not sent')
        qmk.task(149)
        self.assertFalse(qmk.hardware.output(2, 14))
        qmk.task(1)
        self.assertEqual(qmk.transfer(bytes(3)), [0xAA, 0, 1])

    def test_status_collision_retries_the_keyboard_packet(self):
        qmk = self.qmk()
        report = bytes.fromhex('00 00 04 00 00 00 00 00')
        qmk.keyboard(report)
        qmk.task(10)
        qmk.transfer(bytes.fromhex('b6 00 02'))
        self.assertEqual(qmk.queued(), 1)
        self.assertEqual(qmk.drain(), [[0xA1, *report]])
        self.assertTrue(qmk.connected())

    def test_status_collisions_preserve_reports_in_both_firmwares(self):
        report = bytes.fromhex('02 00 04 00 00 00 00 00')
        for status in (bytes.fromhex('b1 02'), bytes.fromhex('b6 00 02'),
                       bytes.fromhex('b7 02'), bytes([0x99])):
            with self.subTest(status=status.hex()):
                qmk, stock = self.qmk(), self.stock()
                qmk.keyboard(report)
                qmk.task(10)
                stock.cpu.mem_write(0x200005D8, report)
                stock.command(0xF0)
                incoming = status.ljust(9, b'\x00')
                expected = [0xA1, *report]
                self.assertEqual(qmk.transfer(incoming, 3), expected)
                self.assertEqual(stock.transfer(incoming, 3), expected)
                self.assertEqual(qmk.queued(), 1)
                self.assertEqual(stock.read(0x20000218, 1), 0xF0)
                self.assertEqual(qmk.drain(), [expected])
                stock.command(0xF0)
                self.assertEqual(stock.transfer(bytes(9)), expected)
                self.assertEqual(stock.read(0x20000218, 1), 0x20)

    def test_report_fifo_acceptance_yields_without_sleeping(self):
        qmk = self.qmk()
        started = qmk.ms
        for _ in range(8):
            qmk.keyboard(bytes([0, 0, 4, 0, 0, 0, 0, 0]))
            qmk.keyboard(bytes(8))
        self.assertEqual(qmk.queued(), 16)
        self.assertEqual(qmk.ms, started)
        reports = qmk.drain()
        self.assertEqual(len(reports), 16)
        self.assertEqual([p[3] for p in reports], [4, 0] * 8)

    def test_radio_startup_survives_timer_wrap(self):
        qmk = self.qmk(connected=False)
        qmk.ms = 0xFFFFFF00
        qmk.start()
        self.assertTrue(qmk.connected())
        qmk.keyboard(bytes(8))
        self.assertEqual(qmk.drain(), [[0xA1, *bytes(8)]])

    def test_status_changes_retain_accepted_input_without_synthetic_reports(self):
        qmk = self.qmk()
        report = bytes.fromhex('00 00 04 00 00 00 00 00')
        qmk.keyboard(report)
        qmk.transfer(bytes.fromhex('b6 00 00'))
        self.assertFalse(qmk.connected())
        self.assertEqual(qmk.queued(), 1)
        qmk.transfer(bytes.fromhex('b6 00 02'))
        self.assertEqual(qmk.drain(), [[0xA1, *report]])

    def test_short_keyboard_frame_rearms_without_a_reset_pulse(self):
        qmk = self.qmk()
        qmk.keyboard(bytes(8))
        qmk.task(10)
        qmk.transfer(bytes(8))
        self.assertTrue(qmk.connected())
        self.assertFalse(qmk.hardware.output(3, 1))
        self.assertFalse(qmk.hardware.output(2, 14))
        self.assertEqual(qmk.drain(), [[0xA1, *bytes(8)]])

    def test_transfer_timeout_resets_radio(self):
        qmk = self.qmk()
        qmk.keyboard(bytes(8))
        qmk.task(10)
        qmk.task(1999)
        self.assertTrue(qmk.connected())
        qmk.task(1)
        self.assertTrue(qmk.connected())
        self.assertTrue(qmk.hardware.output(3, 1))
        self.assertFalse(qmk.hardware.output(2, 14))

    def test_request_pin_must_remain_a_gpio_output(self):
        qmk = self.qmk()
        qmk.hardware.access(0x400B4000, 4, 0)
        qmk.keyboard(bytes(8))
        with self.assertRaisesRegex(Unsupported, 'push-pull output'):
            qmk.drain()

    def test_request_pin_cannot_ignore_an_opposing_external_drive(self):
        qmk = self.qmk()
        qmk.hardware.pin(2, 14, False)
        qmk.keyboard(bytes(8))
        with self.assertRaisesRegex(Unsupported, 'Conflicting GPIO'):
            qmk.drain()

    def test_final_byte_and_error_between_fifo_drain_and_busy_read(self):
        for error in (False, True):
            with self.subTest(error=error):
                qmk = self.qmk()
                qmk.keyboard(bytes(8))
                qmk.task(10)
                hw = qmk.hardware
                hw.spi.selected = True
                for _ in range(8):
                    hw.clock(0)
                    qmk.poll()
                status_reads = 0

                def tail(address):
                    nonlocal status_reads
                    if address == 0x40004014:
                        status_reads += 1
                    if address == 0x40004014 and status_reads == 2:
                        hw.on_read = None
                        hw.clock(0)
                        hw.spi.selected = False
                        if error:
                            hw.spi.errors |= 0x80

                hw.on_read = tail
                qmk.task()
                self.assertIsNone(hw.on_read)
                self.assertEqual(status_reads, 2)
                if error:
                    self.assertTrue(qmk.connected())
                    self.assertFalse(qmk.hardware.output(3, 1))
                else:
                    self.assertTrue(qmk.connected())
                    self.assertEqual(qmk.queued(), 0)

    def test_rx_irq_is_deferred_by_primask(self):
        qmk = self.qmk()
        qmk.interrupt_trace.clear()
        qmk.cpu.reg_write(UC_ARM_REG_PRIMASK, 1)
        qmk.hardware.spi.selected = True
        qmk.hardware.clock(0xB6)
        qmk.poll()
        self.assertEqual(qmk.interrupt_trace, [])
        self.assertTrue(qmk.hardware.pending & (1 << SPI_IRQ))
        qmk.cpu.reg_write(UC_ARM_REG_PRIMASK, 0)
        qmk.poll()
        self.assertEqual([irq for kind, irq, _ in qmk.interrupt_trace if kind == 'enter'], [SPI_IRQ])

    def test_spi_irq_preempts_the_actual_scan_handler(self):
        qmk = self.qmk()
        qmk.interrupt_trace.clear()
        qmk.hardware.scan_interrupt()

        def incoming():
            qmk.hardware.spi.selected = True
            qmk.hardware.clock(0xB6)

        qmk.events[qmk.instructions + 5] = incoming
        qmk.poll()
        self.assertEqual([(kind, irq) for kind, irq, _ in qmk.interrupt_trace],
                         [('enter', 17), ('enter', 21), ('return', 21), ('return', 17)])
        self.assertEqual(qmk.hardware.registers[0x40076004], 0)

    def test_pending_spi_irq_skips_a_gated_or_disabled_peripheral(self):
        for clocked in (False, True):
            with self.subTest(clocked=clocked):
                qmk = self.qmk()
                qmk.hardware.spi.registers[0] = 0
                if not clocked:
                    qmk.hardware.registers[0x4008802C] &= ~(1 << 4)
                qmk.hardware.spi.rx.extend((0xB6, 0, 1))
                qmk.hardware.pending |= 1 << SPI_IRQ
                qmk.poll()
                self.assertEqual(list(qmk.hardware.spi.rx), [0xB6, 0, 1])
                self.assertEqual(qmk.read(qmk.symbol('radio_state'), 1), 4)
                self.assertIn(('enter', SPI_IRQ), [(kind, irq) for kind, irq, _ in qmk.interrupt_trace])

    def test_charging_indicator_burst_boundaries(self):
        qmk = self.qmk()
        qmk.hardware.pin(1, 12, True)
        qmk.hardware.pin(2, 13, False)
        qmk.matrix()
        started = qmk.ms
        for elapsed, expected in ((0, 6000), (24, 6000), (25, 0), (50, 6000),
                                   (75, 0), (100, 6000), (125, 0), (3125, 6000)):
            with self.subTest(elapsed=elapsed):
                qmk.ms = started + elapsed
                qmk.indicators()
                self.assertEqual(qmk.hardware.registers[0x4002C09C], expected)
        qmk.hardware.pin(2, 13, None)
        qmk.ms = started + 126
        qmk.indicators()
        self.assertEqual(qmk.hardware.registers[0x4002C09C], 6000)

    def test_usb_fixture_updates_both_state_machines(self):
        qmk = self.qmk()
        for configured, suspended, driver, core in (
            (False, False, 'usb_ready', 'usb_init'),
            (True, False, 'usb_active', 'usb_configured'),
            (True, True, 'usb_driver_suspended', 'usb_suspended'),
        ):
            with self.subTest(configured=configured, suspended=suspended):
                qmk.usb(configured, suspended)
                self.assertEqual(qmk.read(qmk.symbol('USBD1') + self.abi['usb_driver_state'],
                                          self.abi['usb_driver_state_bytes']), self.abi[driver])
                self.assertEqual(qmk.read(qmk.symbol('usb_device_state') + self.abi['usb_configure_state'],
                                          self.abi['usb_configure_state_bytes']), self.abi[core])

    def test_wrong_stock_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'recorded US 7.02'):
            Stock(self.stock_image[:-1] + bytes([self.stock_image[-1] ^ 1]))


if __name__ == '__main__':
    unittest.main()
