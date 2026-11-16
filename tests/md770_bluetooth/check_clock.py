"""Run board clock/sleep instructions with supplied oscillator and wake events."""

import argparse
from collections import deque
import hashlib
from io import BytesIO
import json
from pathlib import Path
from random import Random
import shlex
import struct
import subprocess
from tempfile import TemporaryDirectory

from capstone import CS_ARCH_ARM, CS_MODE_THUMB, Cs
from capstone.arm_const import ARM_OP_MEM, ARM_REG_PC
from elftools.elf.elffile import ELFFile
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_R0

from emulator import Hardware, Machine, Unsupported
from stock_probe import STOCK_SHA256


class ClockHardware(Hardware):
    def __init__(self, machine):
        super().__init__()
        self.machine = machine
        self.clock = {address: 0 for address in (
            0x40088000, 0x40088004, 0x40088008, 0x4008801C,
            0x40088020, 0x40088034, 0x40088038, 0x4008803C,
            0x4008810C, 0x40080200, 0x40022000, 0x40022004,
            0x40024050, 0x40024054, 0x40024058,
            0x4006A100, 0x4006A104, 0x40068000, 0x40068004, 0x40068008,
            0xE000E010, 0xE000E014, 0xE000E018, 0xE000ED10,
            *range(0x40000000, 0x4000002C, 4),
            *range(0x40077000, 0x40077010, 4),
        )}
        self.clock.update({0x40088004: 0xA01, 0x40088008: 0xA,
                           0x40088034: 1, 0x40080200: 2,
                           0x40000010: 1 << 8, 0xE000E010: 7})
        self.delays = []

    def access(self, address, size, value=None):
        if address not in self.clock:
            return super().access(address, size, value)
        if address in (0x40024050, 0x40024054, 0x40024058) and not self.registers[0x4008802C] & (1 << 15):
            raise Unsupported('EXTI wake register access without its APB clock')
        if size != 4:
            raise Unsupported(f'Clock boundary requires a word: {address:#x}/{size}')
        self.accesses[('read' if value is None else 'write', address)] += 1
        if value is None:
            return self.clock[address]
        self.trace.append((address, value))
        if address == 0x4008810C:
            if value & ~0x30110:
                raise Unsupported(f'Unmodelled APB reset: {value:#x}')
            return 0
        if address == 0x40024058:
            self.clock[address] &= ~value
            return 0
        self.clock[address] = value
        if address == 0x40088004:
            self.clock[0x40088034] = value & 7
            self.clock[0x40088008] = 8 | (2 if value & (1 << 9) else 0)
        if address == 0x40077000 and value == 6:
            frequency = self.machine.read(self.machine.symbol('frequency'))
            duration = self.clock[0x4007700C] / frequency * 1000000
            self.delays.append(duration)
            self.machine.ms += duration / 1000
            self.clock[0x40077004] |= 1
        return 0


def thread_layout(qmk, elf):
    flags = shlex.split((elf.parent / ('obj_' + elf.stem) / 'cflags.txt').read_text())
    source = Path(__file__).with_name('clock_abi.c').resolve()
    with TemporaryDirectory(prefix='md770-clock-abi-') as temporary:
        target = Path(temporary) / 'abi.o'
        subprocess.run(['arm-none-eabi-gcc', *flags, '-fno-lto', '-c', str(source),
                        '-o', str(target)], cwd=qmk, check=True, capture_output=True)
        binary = ELFFile(BytesIO(target.read_bytes()))
        return struct.unpack('<9I', binary.get_section_by_name('.rodata.clock_abi').data())


class ClockFirmware(Machine):
    def __init__(self, qmk, elf):
        super().__init__(elf.read_bytes(), elf=True)
        self.left = 'md770_left' in self.symbols
        self.hardware = ClockHardware(self)
        self.wakes = deque()
        self.settles = deque()
        self.waits = []
        self.event_pending = False
        self.hook('timer_read32', lambda: int(self.ms))
        self.hooks[self.function('chThdSleep')] = self._sleep
        self.hooks[self.function('__port_irq_epilogue')] = lambda: None
        if not self.left:
            self.hook('md770_storage_sleep', lambda: 1)
        (current, main, self.row_bytes, self.matrix_rows,
         timer_list, timer_next, timer_prev, timer_delta, timer_time) = thread_layout(qmk, elf)
        self.write(self.symbol('ch0') + current, self.symbol('ch0') + main)
        timer_head = self.symbol('ch0') + timer_list
        self.write(timer_head + timer_next, timer_head)
        self.write(timer_head + timer_prev, timer_head)
        self.write(timer_head + timer_delta, 0xFFFFFFFF)
        self.kernel_time = self.symbol('ch0') + timer_time
        self.hardware.pin(1, 12, False)
        self.hardware.pin(1, 1, True)
        self.call(self.function('gpt_lld_init'))
        self.call(self.function('sd_lld_init'))
        self.call(self.function('board_init'))
        if not self.left:
            self.call(self.function('pwm_lld_init'))
            self.call('led_init_ports')
        self.call('matrix_init_custom')
        assert self.hardware.clock[0xE000E014] == 0x5DB0
        self.hardware.trace.clear()
        self.hardware.delays.clear()

    def _sleep(self):
        self.ms += self.cpu.reg_read(UC_ARM_REG_R0) / 2

    def _instruction(self, cpu, address, size, context):
        operation = self.read(address, 2)
        if operation == 0xBF40:
            self.event_pending = True
        elif operation in (0xBF20, 0xBF30):
            self.instructions += 1
            if operation == 0xBF20 and self.event_pending:
                self.event_pending = False
            else:
                actions = self.wakes if operation == 0xBF20 else self.settles
                if not actions:
                    raise Unsupported('Sleep reached without an explicit supplied wake event')
                self.waits.append(('wfe' if operation == 0xBF20 else 'wfi',
                                   self.hardware.registers[0x40076000],
                                   self.hardware.registers[0x4007600C]))
                actions.popleft()(self)
            cpu.reg_write(UC_ARM_REG_PC, (address + 2) | 1)
            return
        super()._instruction(cpu, address, size, context)

    def request(self, level):
        self.call('md770_power_request', level)
        self.call('md770_clock_service', budget=300000)

    def flag_address(self, getter):
        disassembler = Cs(CS_ARCH_ARM, CS_MODE_THUMB)
        disassembler.detail = True
        start = self.function(getter)
        for instruction in disassembler.disasm(bytes(self.cpu.mem_read(start, 16)), start):
            if instruction.mnemonic == 'ldr' and instruction.operands[1].type == ARM_OP_MEM:
                operand = instruction.operands[1].mem
                if operand.base == ARM_REG_PC:
                    pointer = self.read(((instruction.address + 4) & ~3) + operand.disp)
                    if 0x20000000 <= pointer < 0x20004000:
                        return pointer
        raise Unsupported(f'Cannot locate the volatile flag from compiled getter {getter}')

    def idle_address(self):
        return self.flag_address('md770_power_idle')


def check(qmk, elf):
    early = Machine(elf.read_bytes(), elf=True)
    early.hardware = ClockHardware(early)
    early.call('early_hardware_init_pre')
    assert early.hardware.trace[:4] == [(0x4008810C, 0x10), (0x40068008, 0x5FFF),
                                        (0x40068004, 0x1A7D0), (0x40068000, 0x5FA00001)]
    q = ClockFirmware(qmk, elf)
    stock_image = Path('mistel_md770rgb_bt_right_stock.bin').read_bytes()
    assert hashlib.sha256(stock_image).hexdigest() == STOCK_SHA256
    stock = Machine(stock_image)
    stock.cpu.mem_write(0x2000025F, bytes((0, 255, 255)))
    rng = Random(770)
    samples = [0] * 10 + [1, 0, 1, 0] + [1] * 12 + [0] * 12
    samples += [rng.randrange(256) for _ in range(200)]
    scratch = q.symbol('__heap_base__')
    assert scratch < q.symbol('__heap_end__')
    for sample in samples:
        for column in range(8):
            q.hardware.pin(0, column + (0 if q.left else 1), bool(sample & (1 << column)))
        q.call('md770_scan_idle_changed', scratch)
        stock.write(0x20001000, 0x2000025F)
        stock.call(0xAA70, 0x20001000, sample ^ 255)
        assert q.read(q.symbol('debounce_count'), 1) == stock.read(0x2000025F, 1)
        assert q.read(q.symbol('stable_rows'), 1) == stock.read(0x20000261, 1) ^ 255
    q = ClockFirmware(qmk, elf)
    hw = q.hardware
    q.call('SysTick_Handler')
    assert q.read(q.kernel_time) == 1
    assert [(address, value) for address, value in hw.trace if address == 0x40068000] == [(0x40068000, 0x5FA00001)]
    sleeping = q.flag_address('md770_power_sleeping')
    q.write(sleeping, 1, 1)
    hw.trace.clear()
    q.write(q.symbol('md770_tick_step'), 4)
    q.call('SysTick_Handler')
    assert q.read(q.kernel_time) == 5
    assert not any(address == 0x40068000 for address, _ in hw.trace)
    q.write(sleeping, 0, 1)
    q.write(q.symbol('md770_tick_step'), 1)
    q.call('SysTick_Handler')
    assert q.read(q.kernel_time) == 6
    assert [(address, value) for address, value in hw.trace if address == 0x40068000] == [(0x40068000, 0x5FA00001)]
    hw.clock[0x40000010] = 0
    q.request(9)
    assert q.call('md770_clock_frequency') == 48000000
    hw.clock[0x40000010] = 1 << 8
    q.call('md770_clock_service')
    assert q.call('md770_clock_frequency') == 8000000
    assert hw.clock[0x40000024] == 16
    assert hw.clock[0xE000E014] == 0xF90
    assert hw.registers[0x4007600C] == 6573
    clock_writes = [(address, value) for address, value in hw.trace
                    if address in (0x40088004, 0x40080200)]
    assert [address for address, _ in clock_writes] == [0x40088004, 0x40080200, 0x40088004]
    assert clock_writes[0][1] & 7 == 3 and clock_writes[0][1] & (1 << 9)
    assert clock_writes[1][1] & 7 == 1 and not clock_writes[2][1] & (1 << 9)
    q.call('wait_us', 1000)
    assert hw.delays[-1] == 1000
    hw.trace.clear()
    q.request(11)
    if q.left:
        q.call('md770_rgb_sleep', 0)
    assert q.call('md770_clock_frequency') == 48000000
    assert hw.clock[0x40000024] == 96
    assert hw.clock[0xE000E014] == 0x5DB0
    assert hw.registers[0x4007600C] == 39441
    clock_writes = [(address, value) for address, value in hw.trace
                    if address in (0x40088004, 0x40080200)]
    assert [address for address, _ in clock_writes] == [0x40088004, 0x40080200, 0x40088004]
    assert clock_writes[0][1] & 7 == 3 and clock_writes[0][1] & (1 << 9)
    assert clock_writes[1][1] & 7 == 2 and clock_writes[2][1] & 7 == 1
    q.call('wait_us', 1000)
    assert hw.delays[-1] == 1000
    assert 10000 in hw.delays and 100 in hw.delays
    long_delay = hw.trace.index((0x4007700C, 480000))
    release_blank = hw.trace.index((0x400B4028, 1 << 11), long_delay)
    short_delay = hw.trace.index((0x4007700C, 4800), release_blank)
    start = hw.trace.index((0x4006F010, 1), short_delay)
    clock_port, clock_pin, latch_port, latch_pin = ((0, 14, 0, 15) if q.left else (2, 15, 1, 10))
    clock_base = 0x400B0000 + 0x2000 * clock_port
    latch_base = 0x400B0000 + 0x2000 * latch_port
    latch_sequence = [(latch_base + 0x28, 1 << latch_pin),
                      (latch_base + 0x24, 1 << latch_pin),
                      (clock_base + 0x28, 1 << clock_pin),
                      (clock_base + 0x24, 1 << clock_pin),
                      (clock_base + 0x28, 1 << clock_pin),
                      (clock_base + 0x24, 1 << clock_pin),
                      (latch_base + 0x28, 1 << latch_pin),
                      (latch_base + 0x24, 1 << latch_pin)]
    assert hw.trace[start - 8:start] == latch_sequence
    if not q.left:
        assert hw.registers[0x4006E084] == 1
    q = ClockFirmware(qmk, elf)
    hw = q.hardware
    q.write(q.idle_address(), 1, 1)

    def nonmatrix_wake(machine):
        mask = 0x100 if machine.left else 0x1000
        assert machine.hardware.clock[0x40024050] & (0x1FF if machine.left else 0x1FE)
        assert machine.hardware.clock[0xE000E010] == 5
        assert machine.read(machine.symbol('md770_tick_step')) == 4
        trace = machine.hardware.trace
        reloads = [index for index, (address, _) in enumerate(trace) if address == 0x40068000]
        assert reloads
        final_feed = reloads[-1]
        controls = [value for address, value in trace[:final_feed] if address == 0xE000E010]
        assert controls[-1] == 5
        assert not any(address == 0xE000E010 and value & 2 for address, value in trace[final_feed:])
        machine.hardware.clock[0x40024058] = mask

    q.wakes.append(nonmatrix_wake)
    q.request(4)
    assert q.waits == [('wfe', 0, 39441)]
    assert q.call('md770_clock_frequency') == 48000000
    assert not q.call('md770_power_idle')
    assert q.read(q.symbol('md770_tick_step')) == 1
    assert hw.clock[0xE000E010] == 7
    assert hw.registers[0x4007600C] == 39441
    assert hw.clock[0x40000024] == 96
    assert hw.delays[:2] == [1, 1000]
    assert not hw.clock[0xE000ED10] & 4
    sense = 0xFF if q.left else 0x1FE
    assert hw.gpio[0][0] & sense == sense
    assert hw.gpio[0][4] & sense == sense
    assert hw.gpio[0][12] & sense == sense
    assert not hw.gpio[0][0x20] & sense
    q = ClockFirmware(qmk, elf)
    q.write(q.idle_address(), 1, 1)

    def matrix_wake(machine):
        machine.hardware.clock[0x40024058] = 1 if machine.left else 2

    def settle_tick(machine):
        machine.ms += 2
        machine.hardware.scan_interrupt()

    q.wakes.extend((matrix_wake, nonmatrix_wake))
    q.settles.extend([settle_tick] * 19)
    q.request(4)
    assert [wait for wait in q.waits if wait[0] == 'wfe'] == [('wfe', 0, 39441)] * 2
    assert [wait for wait in q.waits if wait[0] == 'wfi'] == [('wfi', 5, 39441)] * 19
    assert not q.wakes and not q.settles
    assert not q.call('md770_power_idle')
    q = ClockFirmware(qmk, elf)
    q.write(q.idle_address(), 1, 1)

    def counted_matrix_wake(machine):
        matrix_wake(machine)
        machine.write(machine.symbol('debounce_count'), 5, 1)

    def first_settle(machine):
        assert machine.read(machine.symbol('debounce_count'), 1) == 5
        assert machine.hardware.gpio[0][0] & sense == sense
        assert machine.hardware.gpio[0][4] & sense == sense
        assert machine.hardware.gpio[0][12] & sense == sense
        assert not machine.hardware.gpio[0][0x20] & sense
        machine.hardware.pin(1, 12, True)

    q.wakes.append(counted_matrix_wake)
    q.settles.append(first_settle)
    q.request(4)
    assert q.waits == [('wfe', 0, 39441), ('wfi', 5, 39441)]
    assert q.read(q.symbol('debounce_count'), 1) == 5
    for previous in (9, 11):
        q = ClockFirmware(qmk, elf)
        q.request(previous)
        interval = 6573 if previous == 9 else 39441
        q.write(q.idle_address(), 1, 1)
        q.wakes.append(nonmatrix_wake)
        q.request(4)
        assert q.waits == [('wfe', 0, interval)]
        assert q.call('md770_clock_frequency') == (8000000 if previous == 9 else 48000000)
        assert q.hardware.registers[0x4007600C] == interval
        assert q.hardware.clock[0x40000024] == (16 if previous == 9 else 96)
    if not q.left:
        for public in (4, 5):
            q = ClockFirmware(qmk, elf)
            q.write(q.idle_address(), 1, 1)
            q.hardware.pin(0, 1, True)
            for _ in range(9):
                q.call('md770_scan_idle_changed', q.symbol('__heap_base__'))
            assert q.read(q.symbol('stable_rows'), 1) == 1
            assert q.read(q.symbol('debounce_count'), 1) == 0
            q.write(q.symbol('radio_state'), public, 1)
            if public > 4:
                q.wakes.append(nonmatrix_wake)
            q.request(4)
            assert len(q.waits) == (1 if public > 4 else 0)
            assert not q.wakes
        for previous, first, final, age in ((1, 1, 0, 100), (0, 0, 1, 100), (0, 1, 0, 600001)):
            q = ClockFirmware(qmk, elf)
            rows = q.symbol('__heap_base__')
            assert rows + q.row_bytes * q.matrix_rows <= q.symbol('__heap_end__')
            q.cpu.mem_write(rows, bytes(q.row_bytes * q.matrix_rows))
            q.write(rows, previous, q.row_bytes)
            q.write(q.symbol('scanned'), first, q.row_bytes)
            q.write(q.symbol('held_armed'), previous, 1)
            q.write(q.symbol('held_slot'), 1 if previous else 0, 1)
            q.write(q.symbol('supply'), 1)
            q.write(q.symbol('activity'), 0)
            q.ms = age
            q.hook('host_task', lambda: None)

            def between_copies():
                assert not q.read(q.idle_address(), 1)
                q.hardware.pin(0, 1, bool(final))
                q.hardware.scan_interrupt()

            q.hook('md770_clock_service', between_copies)
            changed = q.call('matrix_scan_custom', rows)
            assert bool(changed) == (previous != final)
            assert q.read(rows, q.row_bytes) == final
            assert q.read(q.symbol('held_armed'), 1) == final
            assert q.read(q.symbol('held_slot'), 1) == (1 if previous else 0)
            assert q.read(q.symbol('activity')) == age
            assert ('enter', 17) in [(kind, irq) for kind, irq, _ in q.interrupt_trace]
    checks = ['UART drain before retiming', '48/8MHz scan, tick and UART divisors',
              f'row debounce matches actual stock 0xaa70 for {len(samples)} supplied raw samples',
              'slow/fast clock, oscillator and flash wait-state ordering',
              'runtime BFTM1 microsecond delay at both clocks',
              'RGB wake delay, row prime, latch and timer-start order',
              'nonmatrix WFE wake and retained scan compare',
              'matrix-only wake stays idle through nineteen WFI settling cycles',
              'scan restore does not add a synchronous debounce sample',
              'sense GPIO output, input-enable and pulldown state restores before scanning',
              'previous levels 9 and 11 restore their clocks, UART and scan intervals',
              'early watchdog reset, reload and sleep-halt configuration',
              'compiled idle SysTick advances four kernel ticks without reloading watchdog; active ticks reload it',
              'watchdog final reload and disabled SysTick interrupt window',
              'wake restores active level, UART, SysTick and local scan']
    if not q.left:
        checks.append('right initial changed input honours public radio state')
        checks.append('real scan IRQ between matrix copies preserves final press/release qualification and both activity boundaries')
    return {'side': 'left' if q.left else 'right',
            'elf_sha256': hashlib.sha256(elf.read_bytes()).hexdigest(),
            'stock_reference_sha256': STOCK_SHA256,
            'checks': checks,
            'limits': 'Oscillator readiness, timer completion, RTOS sleep, flash sleep and wake events are supplied. The separate matrix race case supplies host/clock service boundaries to inject a real scan IRQ. Flash protocol is checked separately; electrical/RF behaviour requires hardware.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--qmk-home', type=Path, default=Path('../qmk_firmware'))
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    result = json.dumps(check(args.qmk_home.resolve(), args.elf.resolve()), indent=2) + '\n'
    if args.json:
        args.json.write_text(result)
    print(result, end='')
