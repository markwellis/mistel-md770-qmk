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
        cls.elf_path = cls.elf_path or cls.qmk_home / '.build/mistel_md770rgb_bt_right_default.elf'
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

    def assert_reset(self, machine):
        self.assertFalse(machine.connected())
        self.assertTrue(machine.hardware.output(3, 1))
        self.assertFalse(machine.hardware.output(2, 14))

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
                self.assertEqual(packets[-1], expected)
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
                            size = qmk.read(qmk.symbol('current_length'), 1)
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
        self.assertEqual(qmk.queued(), 0)
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
                stock.command(0x80)
                qmk.usb(True)
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
                stock.call(0x36B8, 0x80)
                stock.task()
                qmk.usb(False)
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

    def test_usb_status_notices_match_stock(self):
        qmk, stock = self.qmk(), self.stock()
        for configured in (True, False, True, False):
            with self.subTest(configured=configured):
                qmk.usb(configured)
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
                        length = qmk.read(qmk.symbol('current_length'), 1)
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
                qmk.write(qmk.symbol('battery_level'), 4 if low_battery else 7, 1)
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

    def test_all_lvd_selections_and_debounce_match_stock(self):
        thresholds = (0, 2250, 2400, 2550, 2700, 2850, 3000, 3150)
        for level in range(7, 0, -1):
            with self.subTest(level=level):
                qmk, stock = self.qmk(connected=False), Stock(self.stock_image)
                qmk.write(qmk.symbol('battery_level'), level, 1)
                stock.write(0x2000001E, level, 1)
                qmk.matrix()
                stock.power()
                self.assertEqual(qmk.hardware.lvd, stock.hardware.lvd)
                qmk.hardware.voltage_mv = stock.hardware.voltage_mv = thresholds[level] - 1
                qmk.matrix()
                stock.voltage_tick(49)
                stock.power()
                qmk.ms += 24
                qmk.matrix()
                self.assertEqual(stock.read(0x2000001E, 1), level)
                self.assertEqual(qmk.read(qmk.symbol('battery_level'), 1), level)
                stock.voltage_tick()
                stock.power()
                qmk.ms += 1
                qmk.matrix()
                self.assertEqual(stock.read(0x2000001E, 1), level - 1)
                self.assertEqual(qmk.read(qmk.symbol('battery_level'), 1), level - 1)

    def test_pairing_waits_150_ms_after_selection(self):
        qmk = self.qmk()
        qmk.select(2, pair=True)
        for _ in range(20):
            qmk.task(10)
            if qmk.hardware.output(2, 14):
                length = qmk.read(qmk.symbol('current_length'), 1)
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

    def test_queue_backpressure_yields_to_module_byte_clocks(self):
        qmk = self.qmk()
        reports = [bytes([0, 0, key, 0, 0, 0, 0, 0]) for key in range(4, 21)]
        for report in reports[:16]:
            qmk.keyboard(report)
        self.assertEqual(qmk.queued(), 16)
        current, completed = [], []

        def clock_byte():
            if not qmk.hardware.output(2, 14):
                return
            qmk.hardware.spi.selected = True
            current.append(qmk.hardware.clock(0))
            if len(current) == 9:
                qmk.hardware.spi.selected = False
                completed.append(current.copy())
                current.clear()

        qmk.sleep_action = clock_byte
        qmk.keyboard(reports[16])
        qmk.sleep_action = None
        self.assertTrue(qmk.connected())
        self.assertEqual(qmk.queued(), 16)
        self.assertEqual(completed + qmk.drain(), [[0xA1, *report] for report in reports])

    def test_radio_startup_survives_timer_wrap(self):
        qmk = self.qmk(connected=False)
        qmk.ms = 0xFFFFFF00
        qmk.start()
        self.assertTrue(qmk.connected())
        qmk.keyboard(bytes(8))
        self.assertEqual(qmk.drain(), [[0xA1, *bytes(8)]])

    def test_reconnect_discards_stale_queue_and_resynchronises(self):
        qmk = self.qmk()
        qmk.keyboard(bytes.fromhex('00 00 04 00 00 00 00 00'))
        qmk.keyboard(bytes(8))
        qmk.transfer(bytes.fromhex('b6 00 00'))
        self.assertFalse(qmk.connected())
        self.assertEqual(qmk.queued(), 0)
        qmk.transfer(bytes.fromhex('b6 00 02'))
        packets = qmk.drain()
        self.assertEqual(packets, [[0xA1, *bytes(8)], [0xA2, *bytes(4)], [0xA3, 0]] * 2)

    def test_short_keyboard_frame_resets_radio(self):
        qmk = self.qmk()
        qmk.keyboard(bytes(8))
        qmk.task(10)
        qmk.transfer(bytes(8))
        self.assert_reset(qmk)

    def test_transfer_timeout_resets_radio(self):
        qmk = self.qmk()
        qmk.keyboard(bytes(8))
        qmk.task(10)
        qmk.task(1999)
        self.assertTrue(qmk.connected())
        qmk.task(1)
        self.assert_reset(qmk)

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
                    self.assert_reset(qmk)
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

    def test_actual_idle_timer_uses_96000_ticks(self):
        qmk = self.qmk()
        qmk.matrix()
        qmk.ms += 600000
        qmk.matrix()
        self.assertEqual(self.abi['gpt_counter_bytes'], 4)
        self.assertEqual(qmk.hardware.registers[0x4007600C], 96000)
        qmk.keyboard(bytes(8))
        qmk.matrix()
        self.assertEqual(qmk.hardware.registers[0x4007600C], 39441)

    def test_lvd_requires_25_ms_before_changing_level(self):
        qmk = self.qmk()
        qmk.hardware.voltage_mv = 3100
        qmk.matrix()
        self.assertEqual(qmk.read(qmk.symbol('battery_level'), 1), 7)
        qmk.ms += 24
        qmk.matrix()
        self.assertEqual(qmk.read(qmk.symbol('battery_level'), 1), 7)
        qmk.ms += 1
        qmk.matrix()
        self.assertEqual(qmk.read(qmk.symbol('battery_level'), 1), 6)
        qmk.ms += 100
        qmk.matrix()
        self.assertEqual(qmk.read(qmk.symbol('battery_level'), 1), 6)

    def test_charging_indicator_burst_boundaries(self):
        qmk = self.qmk()
        qmk.hardware.pin(1, 12, True)
        qmk.hardware.pin(2, 13, False)
        qmk.matrix()
        started = qmk.read(qmk.symbol('burst_started'))
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

    def test_remote_wake_is_explicitly_outside_the_model(self):
        qmk = self.qmk()
        qmk.hardware.pin(1, 12, True)
        qmk.usb(True, suspended=True, remote_wakeup=True)
        qmk.matrix()
        qmk.write(qmk.symbol('scanned'), 1, 1)
        with self.assertRaisesRegex(Unsupported, 'USB signalling, including remote wake'):
            qmk.matrix()

    def test_wrong_stock_image_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'recorded US 7.02'):
            Stock(self.stock_image[:-1] + bytes([self.stock_image[-1] ^ 1]))


if __name__ == '__main__':
    unittest.main()
