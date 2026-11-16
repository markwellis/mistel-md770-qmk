"""Independent ARM exception fixtures and documented peripheral contracts."""

from pathlib import Path
import struct
import subprocess
from tempfile import TemporaryDirectory
import unittest

from unicorn.arm_const import (
    UC_ARM_REG_CONTROL, UC_ARM_REG_LR, UC_ARM_REG_MSP,
    UC_ARM_REG_PRIMASK, UC_ARM_REG_PSP, UC_ARM_REG_R0, UC_ARM_REG_R1,
    UC_ARM_REG_R2, UC_ARM_REG_R3, UC_ARM_REG_R4, UC_ARM_REG_R12,
    UC_ARM_REG_XPSR,
)

from emulator import Hardware, Machine, Spi, STOP, Unsupported
from emulator_abi import firmware_binary, layout


class CpuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = Path(__file__).with_name('cpu_fixture.S')
        with TemporaryDirectory(prefix='md770-cpu-') as temporary:
            elf = Path(temporary) / 'fixture.elf'
            subprocess.run([
                'arm-none-eabi-gcc', '-mcpu=cortex-m0', '-mthumb', '-nostdlib',
                '-Wl,-Ttext=0x3200,-e,thread', str(source), '-o', str(elf),
            ], check=True, capture_output=True, text=True)
            cls.image = elf.read_bytes()

    def test_candidate_binary_must_match_the_executed_elf(self):
        with TemporaryDirectory(prefix='md770-candidate-') as temporary:
            elf = Path(temporary) / 'fixture.elf'
            binary = elf.with_suffix('.bin')
            elf.write_bytes(self.image)
            subprocess.run(['arm-none-eabi-objcopy', '-O', 'binary', str(elf), str(binary)],
                           check=True, capture_output=True, text=True)
            self.assertEqual(firmware_binary(elf, self.image), binary.read_bytes())
            binary.write_bytes(b'This is not the tested ARM application.')
            with self.assertRaisesRegex(ValueError, 'differs from the tested ELF'):
                firmware_binary(elf, self.image)

    def setUp(self):
        self.machine = Machine(self.image, elf=True)
        self.machine.hardware.enabled = (1 << 17) | (1 << 21)

    def test_exception_frames_preserve_registers_flags_and_stack(self):
        for process in (False, True):
            for padding in (0, 4):
                with self.subTest(process=process, padding=padding):
                    machine = Machine(self.image, elf=True)
                    machine.hardware.enabled = 1 << 17
                    cpu = machine.cpu
                    cpu.reg_write(UC_ARM_REG_CONTROL, 2 if process else 0)
                    stack = UC_ARM_REG_PSP if process else UC_ARM_REG_MSP
                    original = cpu.reg_read(stack) - padding
                    cpu.reg_write(stack, original)
                    for index, register in enumerate((UC_ARM_REG_R0, UC_ARM_REG_R1,
                                                      UC_ARM_REG_R2, UC_ARM_REG_R3,
                                                      UC_ARM_REG_R4, UC_ARM_REG_R12)):
                        cpu.reg_write(register, 0x12340000 + index)
                    cpu.reg_write(UC_ARM_REG_XPSR, 0xB1000000)
                    machine.hardware.pending = 1 << 17
                    machine.call('thread')
                    for index, register in enumerate((UC_ARM_REG_R0, UC_ARM_REG_R1,
                                                      UC_ARM_REG_R2, UC_ARM_REG_R3,
                                                      UC_ARM_REG_R4, UC_ARM_REG_R12)):
                        self.assertEqual(cpu.reg_read(register), 0x12340000 + index)
                    self.assertEqual(machine.read(0x20000100), 0xB0000000)
                    self.assertEqual(machine.read(0x20000104), 33)
                    self.assertEqual(cpu.reg_read(UC_ARM_REG_XPSR), 0xB1000000)
                    self.assertEqual(cpu.reg_read(stack), original)
                    self.assertEqual(cpu.reg_read(UC_ARM_REG_CONTROL) & 2, 2 if process else 0)
                    frame_address = (original - 32) & ~7
                    frame = struct.unpack('<8I', cpu.mem_read(frame_address, 32))
                    self.assertEqual(frame[5], STOP | 1)
                    self.assertEqual(frame[6], machine.symbol('thread'))
                    self.assertEqual(bool(frame[7] & 0x200), bool(padding))
                    self.assertEqual(machine.read(0x20000108),
                                     0x20004000 if process else frame_address)

    def test_higher_priority_irq_preempts_and_restores_handler(self):
        machine = self.machine
        machine.hardware.priorities[17] = 0x80
        machine.hardware.priorities[21] = 0x40
        machine.hardware.pending = 1 << 17
        machine.events[3] = lambda: setattr(machine.hardware, 'pending', 1 << 21)
        machine.call('thread')
        self.assertEqual([(kind, irq) for kind, irq, _ in machine.interrupt_trace],
                         [('enter', 17), ('enter', 21), ('return', 21), ('return', 17)])
        self.assertEqual(machine.read(0x20000104), 33)
        self.assertEqual(machine.read(0x20000110), 37)

    def test_equal_priority_irq_waits_for_exception_return(self):
        machine = self.machine
        machine.hardware.pending = 1 << 17
        machine.events[3] = lambda: setattr(machine.hardware, 'pending', 1 << 21)
        machine.call('thread')
        self.assertEqual([(kind, irq) for kind, irq, _ in machine.interrupt_trace],
                         [('enter', 17), ('return', 17), ('enter', 21), ('return', 21)])

    def test_exception_number_breaks_equal_priority_ties(self):
        self.machine.hardware.pending = (1 << 17) | (1 << 21)
        self.machine.call('thread')
        self.assertEqual([irq for kind, irq, _ in self.machine.interrupt_trace if kind == 'enter'],
                         [17, 21])

    def test_primask_defers_pending_irq_until_cpsie(self):
        machine = self.machine
        machine.events[2] = lambda: setattr(machine.hardware, 'pending', 1 << 17)
        machine.call('masked_thread')
        self.assertEqual(machine.interrupt_trace[0],
                         ('enter', 17, machine.symbol('masked_thread') + 6))
        self.assertEqual(machine.cpu.reg_read(UC_ARM_REG_PRIMASK), 0)

    def test_disabled_irq_remains_pending(self):
        machine = self.machine
        machine.hardware.enabled = 0
        machine.hardware.pending = 1 << 17
        machine.call('thread')
        self.assertEqual(machine.interrupt_trace, [])
        self.assertEqual(machine.hardware.pending, 1 << 17)
        machine.hardware.enabled = 1 << 17
        machine.call('thread')
        self.assertEqual(machine.hardware.pending, 0)
        self.assertEqual(machine.read(0x20000104), 33)

    def test_unaligned_access_is_rejected(self):
        with self.assertRaisesRegex(Unsupported, 'Unaligned ARMv6-M'):
            self.machine.call('unaligned_thread')

    def test_sleep_is_rejected(self):
        with self.assertRaisesRegex(Unsupported, 'WFE/WFI'):
            self.machine.call('sleep_thread')

    def test_invalid_vector_is_rejected(self):
        self.machine.write(0x3200 + 33 * 4, 0)
        self.machine.hardware.pending = 1 << 17
        with self.assertRaisesRegex(Unsupported, 'Invalid IRQ 17 vector'):
            self.machine.call('thread')

    def test_recursive_call_is_rejected(self):
        self.machine.events[1] = lambda: self.machine.call('thread')
        with self.assertRaisesRegex(Unsupported, 'recursively'):
            self.machine.call('thread')

    def test_lto_private_symbol_resolution_requires_one_address(self):
        self.machine.symbols['private_state.lto_priv.0'] = [0x20000100]
        self.assertEqual(self.machine.symbol('private_state'), 0x20000100)
        self.machine.symbols['private_state.lto_priv.1'] = [0x20000200]
        with self.assertRaisesRegex(Unsupported, 'found 2'):
            self.machine.symbol('private_state')

    def test_wrong_exception_return_is_rejected(self):
        machine = self.machine
        machine.hardware.pending = 1 << 17
        machine.events[3] = lambda: machine.cpu.reg_write(UC_ARM_REG_LR, 0xFFFFFFF9)
        with self.assertRaisesRegex(Unsupported, 'Unexpected EXC_RETURN'):
            machine.call('thread')

    def test_instruction_budget_is_enforced(self):
        with self.assertRaisesRegex(Unsupported, 'within 1 instructions'):
            self.machine.call('thread', budget=1)

    def test_invalid_stacked_thumb_or_mode_state_is_rejected(self):
        for status in (0, 0x1000021):
            with self.subTest(status=hex(status)):
                machine = Machine(self.image, elf=True)
                machine.hardware.enabled = machine.hardware.pending = 1 << 17

                def corrupt_frame():
                    machine.write(machine.cpu.reg_read(UC_ARM_REG_PSP) + 28, status)

                machine.events[3] = corrupt_frame
                with self.assertRaisesRegex(Unsupported, 'Invalid stacked Thumb or exception mode'):
                    machine.call('thread')


class RegisterTests(unittest.TestCase):
    def setUp(self):
        self.hardware = Hardware()

    def test_gpio_input_enable_gates_external_level(self):
        hw = self.hardware
        hw.pin(1, 12, True)
        self.assertEqual(hw.access(0x400B201C, 4), 0)
        hw.access(0x400B2004, 4, 1 << 12)
        self.assertEqual(hw.access(0x400B201C, 4), 1 << 12)
        hw.pin(1, 12, False)
        self.assertEqual(hw.access(0x400B201C, 4), 0)

    def test_gpio_pulls_and_external_drive(self):
        hw = self.hardware
        hw.access(0x400B4004, 4, 1 << 13)
        hw.access(0x400B4008, 4, 1 << 13)
        hw.access(0x400B400C, 4, 1 << 13)
        self.assertEqual(hw.access(0x400B401C, 4), 1 << 13)
        hw.pin(2, 13, False)
        self.assertEqual(hw.access(0x400B401C, 4), 0)
        hw.pin(2, 13, None)
        self.assertEqual(hw.access(0x400B401C, 4), 1 << 13)
        hw.access(0x400B4008, 4, 0)
        self.assertEqual(hw.access(0x400B401C, 4), 0)

    def test_gpio_set_wins_over_simultaneous_reset(self):
        hw = self.hardware
        hw.access(0x400B4000, 4, 1 << 14)
        hw.access(0x400B4024, 4, (1 << 30) | (1 << 14))
        self.assertTrue(hw.output(2, 14))
        hw.access(0x400B4028, 4, 1 << 14)
        self.assertFalse(hw.output(2, 14))
        self.assertEqual(hw.access(0x400B4024, 4), 0)

    def test_gpio_output_observation_rejects_input_open_drain_and_alternate_function(self):
        hw = self.hardware
        hw.access(0x400B4024, 4, 1 << 14)
        with self.assertRaisesRegex(Unsupported, 'push-pull output'):
            hw.output(2, 14)
        hw.access(0x400B4000, 4, 1 << 14)
        hw.access(0x400B4010, 4, 1 << 14)
        with self.assertRaisesRegex(Unsupported, 'push-pull output'):
            hw.output(2, 14)
        hw.access(0x400B4010, 4, 0)
        hw.access(0x40022034, 4, 4 << 24)
        with self.assertRaisesRegex(Unsupported, 'GPIO alternate function'):
            hw.output(2, 14)
        hw.access(0x40022034, 4, 1 << 24)
        self.assertTrue(hw.output(2, 14))

    def test_gpio_open_drain_release_uses_pull(self):
        hw = self.hardware
        for offset in (0, 4, 8, 0x10, 0x20):
            hw.access(0x400B4000 + offset, 4, 1 << 14)
        self.assertEqual(hw.access(0x400B401C, 4), 1 << 14)
        hw.pin(2, 14, False)
        self.assertEqual(hw.access(0x400B401C, 4), 0)
        hw.access(0x400B4028, 4, 1 << 14)
        hw.pin(2, 14, None)
        self.assertEqual(hw.access(0x400B401C, 4), 0)

    def test_output_conflict_is_rejected_without_input_enable(self):
        hw = self.hardware
        hw.access(0x400B4000, 4, 1 << 14)
        hw.access(0x400B4024, 4, 1 << 14)
        hw.pin(2, 14, False)
        with self.assertRaisesRegex(Unsupported, 'Conflicting GPIO'):
            hw.output(2, 14)

    def test_gpio_floating_input_is_rejected(self):
        self.hardware.access(0x400B4004, 4, 1)
        with self.assertRaisesRegex(Unsupported, 'floating GPIO'):
            self.hardware.access(0x400B401C, 4)

    def test_opposing_external_and_push_pull_drives_are_rejected(self):
        hw = self.hardware
        for offset in (0, 4, 0x20):
            hw.access(0x400B4000 + offset, 4, 1)
        hw.pin(2, 0, False)
        with self.assertRaisesRegex(Unsupported, 'Conflicting GPIO'):
            hw.access(0x400B401C, 4)

    def test_gpio_read_only_and_locking_are_rejected(self):
        with self.assertRaisesRegex(Unsupported, 'read-only'):
            self.hardware.access(0x400B401C, 4, 1)
        with self.assertRaisesRegex(Unsupported, 'GPIO locking'):
            self.hardware.access(0x400B4018, 4, 0x5FA00001)

    def test_nvic_has_two_priority_bits_and_word_access(self):
        hw = self.hardware
        hw.access(0xE000E400, 4, 0xFFAA5511)
        self.assertEqual(hw.access(0xE000E400, 4), 0xC0804000)
        with self.assertRaisesRegex(Unsupported, 'priority register'):
            hw.access(0xE000E400, 1, 0x80)

    def test_nvic_set_clear_masks(self):
        hw = self.hardware
        for set_address, clear_address in ((0xE000E100, 0xE000E180),
                                            (0xE000E200, 0xE000E280)):
            hw.access(set_address, 4, 5)
            hw.access(set_address, 4, 2)
            self.assertEqual(hw.access(clear_address, 4), 7)
            hw.access(clear_address, 4, 2)
            self.assertEqual(hw.access(set_address, 4), 5)

    def test_lvd_all_nominal_thresholds_and_read_only_flag(self):
        hw = self.hardware
        for selection, threshold in enumerate((2250, 2400, 2550, 2700, 2850, 3000, 3150, 3300)):
            with self.subTest(selection=selection):
                value = 0x10000 | ((selection & 3) << 17) | ((selection & 4) << 20)
                hw.access(0x4006A110, 4, value | 0x80000)
                hw.voltage_mv = threshold + 1
                self.assertEqual(hw.access(0x4006A110, 4) & 0x80000, 0)
                hw.voltage_mv = threshold - 1
                self.assertEqual(hw.access(0x4006A110, 4) & 0x80000, 0x80000)
                hw.access(0x4006A110, 4, value & ~0x10000)
                self.assertEqual(hw.access(0x4006A110, 4) & 0x80000, 0)

    def test_lvd_interrupt_event_and_brown_out_modes_are_rejected(self):
        for enable in (1, 2, 0x100000, 0x200000):
            with self.subTest(enable=hex(enable)), self.assertRaisesRegex(Unsupported, 'outside the model'):
                self.hardware.access(0x4006A110, 4, 0x10000 | enable)

    def test_scan_injection_requires_supported_mode_and_clock(self):
        hw = self.hardware
        hw.access(0x40076000, 4, 5)
        with self.assertRaisesRegex(Unsupported, 'clock disabled'):
            hw.scan_interrupt()
        hw.access(0x40088030, 4, 1 << 16)
        hw.scan_interrupt()
        self.assertEqual(hw.pending, 1 << 17)
        with self.assertRaisesRegex(Unsupported, 'repetitive BFTM0'):
            hw.access(0x40076000, 4, 7)
        with self.assertRaisesRegex(Unsupported, 'cleared BFTM0'):
            hw.access(0x40076008, 4, 12)
        for address in (0x4002C000, 0x4006E000, 0x4006F000):
            with self.subTest(address=hex(address)), self.assertRaisesRegex(Unsupported, 'PWM timer control'):
                hw.access(address, 4, 2)

    def test_unknown_mmio_and_free_running_timer_fail(self):
        for address, message in ((0x400FFFF0, 'Unmodelled'),
                                  (0x40076008, 'Free-running')):
            with self.subTest(address=address), self.assertRaisesRegex(Unsupported, message):
                self.hardware.access(address, 4)

    def test_spi_clock_gating_and_reset(self):
        hw = self.hardware
        with self.assertRaisesRegex(Unsupported, 'clock disabled'):
            hw.access(0x40004000, 4)
        hw.access(0x4008802C, 4, 16)
        hw.spi.errors = 0x80
        hw.spi.tx.append(12)
        hw.access(0x40088108, 4, 16)
        self.assertEqual(hw.spi.errors, 0)
        self.assertEqual(list(hw.spi.tx), [])

    def test_watchdog_boundary_accepts_only_the_reload_command(self):
        self.hardware.access(0x40068000, 4, 0x5FA00001)
        self.assertIn((0x40068000, 0x5FA00001), self.hardware.trace)
        with self.assertRaisesRegex(Unsupported, 'watchdog reload'):
            self.hardware.access(0x40068000, 4)
        with self.assertRaisesRegex(Unsupported, 'watchdog reload'):
            self.hardware.access(0x40068000, 4, 0)


class SpiTests(unittest.TestCase):
    def setUp(self):
        self.spi = Spi()
        for offset, value in ((0, 1), (4, 0x108), (24, 0x410), (8, 0xFC)):
            self.spi.write(offset, value)
        self.spi.selected = True

    def test_fifo_order_and_receive_interrupt(self):
        spi = self.spi
        for byte in (0xA1, 2, 0, 4):
            spi.write(16, byte)
        self.assertFalse(spi.interrupt)
        self.assertEqual([spi.clock(byte) for byte in (0xB6, 0, 2)], [0xA1, 2, 0])
        self.assertEqual(spi.read(28), 0x31)
        self.assertTrue(spi.interrupt)
        self.assertEqual([spi.read(16) for _ in range(3)], [0xB6, 0, 2])
        self.assertFalse(spi.interrupt)

    def test_error_flags_are_write_one_to_clear(self):
        self.spi.errors = 0xF8
        self.spi.write(20, 0x88)
        self.assertEqual(self.spi.read(20) & 0xF8, 0x70)
        self.assertTrue(self.spi.interrupt)
        self.spi.write(20, 0xFF)
        self.assertFalse(self.spi.interrupt)

    def test_disabled_spi_does_not_reassert_its_interrupt(self):
        self.spi.clock(0xB6)
        self.assertTrue(self.spi.interrupt)
        self.spi.write(0, 0)
        self.assertFalse(self.spi.interrupt)
        self.assertEqual(list(self.spi.rx), [0xB6])

    def test_empty_rx_and_fifo_boundary_are_rejected(self):
        with self.assertRaisesRegex(Unsupported, 'empty RX FIFO'):
            self.spi.read(16)
        for _ in range(7):
            self.spi.write(16, 0)
        with self.assertRaisesRegex(Unsupported, 'shift-register'):
            self.spi.write(16, 0)
        for _ in range(7):
            self.spi.clock(0)
        with self.assertRaisesRegex(Unsupported, 'shift-register'):
            self.spi.clock(0)

    def test_unsupported_spi_modes_are_rejected(self):
        for offset, value in ((0, 2), (4, 0), (8, 1), (24, 0x420), (32, 1)):
            with self.subTest(offset=offset), self.assertRaises(Unsupported):
                self.spi.write(offset, value)


class AbiTests(unittest.TestCase):
    def test_flags_without_an_elf_do_not_establish_an_abi(self):
        with TemporaryDirectory(prefix='md770-missing-elf-') as temporary:
            directory = Path(temporary)
            flags = directory / 'obj_missing/cflags.txt'
            flags.parent.mkdir()
            flags.write_text('')
            with self.assertRaises(FileNotFoundError):
                layout(directory, directory / 'missing.elf')


if __name__ == '__main__':
    unittest.main()
