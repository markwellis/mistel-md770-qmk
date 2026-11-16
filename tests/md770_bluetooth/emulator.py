"""Execute MD770 ARM code with a deliberately bounded HT32 peripheral model."""

from collections import Counter, deque
from io import BytesIO
import struct

from elftools.elf.elffile import ELFFile
from unicorn import (
    Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB, UC_HOOK_CODE,
    UC_HOOK_INTR, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE, UC_PROT_READ,
    UC_PROT_WRITE, UC_PROT_EXEC,
)
from unicorn.arm_const import (
    UC_CPU_ARM_CORTEX_M0, UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2,
    UC_ARM_REG_R3, UC_ARM_REG_R12, UC_ARM_REG_LR, UC_ARM_REG_PC,
    UC_ARM_REG_XPSR, UC_ARM_REG_IPSR, UC_ARM_REG_MSP, UC_ARM_REG_PSP,
    UC_ARM_REG_CONTROL, UC_ARM_REG_PRIMASK,
)

SPI_BASE = 0x40004000
SPI_IRQ = 21
STOP = 0x1FFF0
FRAME_REGS = [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3,
              UC_ARM_REG_R12, UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_XPSR]


class Unsupported(RuntimeError):
    pass


class Spi:
    """FIFO mode, slave byte boundaries and documented sticky error flags."""

    def __init__(self):
        self.selected = False
        self.reset()

    def reset(self):
        self.registers = {offset: 0 for offset in (0, 4, 8, 12, 24, 32)}
        self.rx = deque()
        self.tx = deque()
        self.errors = 0
        self.maximum_tx = 0

    def read(self, offset):
        if offset == 16:
            if not self.rx:
                raise Unsupported("SPI read from an empty RX FIFO")
            return self.rx.popleft()
        if offset == 20:
            fcr = self.registers[24]
            rx_ready = len(self.rx) >= ((fcr >> 4) & 15) if fcr & 0x400 else bool(self.rx)
            tx_ready = len(self.tx) <= (fcr & 15) if fcr & 0x400 else not self.tx
            return (self.errors | (self.selected << 8) | (rx_ready << 2)
                    | ((not self.tx) << 1) | tx_ready)
        if offset == 28:
            return len(self.rx) << 4 | len(self.tx)
        if offset in self.registers:
            return self.registers[offset]
        raise Unsupported(f"SPI register read +0x{offset:x}")

    def write(self, offset, value):
        if offset == 16:
            if len(self.tx) >= 7:
                raise Unsupported("Full TX FIFO/shift-register interaction is outside the model")
            self.tx.append(value & 255)
            self.maximum_tx = max(self.maximum_tx, len(self.tx))
        elif offset == 20:
            self.errors &= ~(value & 0xF8)
        elif offset in self.registers:
            if offset == 0 and value & ~1:
                raise Unsupported("SPI DMA/master controls are outside the FIFO model")
            if offset == 8 and value & ~0xFC:
                raise Unsupported("TX-empty SPI interrupts are outside the model")
            if offset == 4 and value != 0x108:
                raise Unsupported("Only SPI slave, mode 0, eight-bit MSB-first is modelled")
            if offset == 24 and value not in (0, 0x410):
                raise Unsupported("Only FIFO enabled with RX threshold one is modelled")
            if offset == 32 and value:
                raise Unsupported("SPI FIFO timeout counter is outside the model")
            self.registers[offset] = value
        else:
            raise Unsupported(f"SPI register write +0x{offset:x}")

    def clock(self, incoming):
        if not self.selected or not self.registers[0] & 1:
            raise Unsupported("SPI byte clocked while disabled or deselected")
        if self.registers[4] != 0x108 or self.registers[24] != 0x410:
            raise Unsupported("SPI byte clocked before supported configuration")
        outgoing = self.tx.popleft() if self.tx else None
        if len(self.rx) >= 7:
            raise Unsupported("Full RX FIFO/shift-register interaction is outside the model")
        self.rx.append(incoming)
        return outgoing

    @property
    def interrupt(self):
        return bool(self.registers[0] & 1 and self.read(20) & self.registers[8] & 0xFC)


class Hardware:
    def __init__(self):
        self.spi = Spi()
        self.enabled = 0
        self.pending = 0
        self.priorities = [0] * 32
        self.gpio = [{offset: 0 for offset in range(0, 0x2C, 4)} for _ in range(4)]
        self.gpio[0][4] = self.gpio[0][8] = 0x3300
        self.inputs = [0] * 4
        self.input_driven = [0] * 4
        self.registers = {address: 0 for address in
                          [0x40088024, 0x40088028, 0x4008802C, 0x40088030,
                           0x40088040, 0x40088108, *range(0x40022020, 0x40022040, 4)]}
        for base in (0x4002C000, 0x4006E000, 0x4006F000):
            for offset in (0, 4, 8, 0x10, *range(0x40, 0x58, 4),
                           0x6C, 0x70, 0x74, 0x78, 0x7C, 0x80, 0x84, 0x88,
                           *range(0x90, 0xA0, 4)):
                self.registers[base + offset] = 0
        for offset in range(0, 16, 4):
            self.registers[0x40076000 + offset] = 0
        self.voltage_mv = 3300
        self.usb_power = 0x400
        self.lvd = 0
        self.accesses = Counter()
        self.trace = []
        self.on_read = None

    def pin(self, port, pad, high):
        mask = 1 << pad
        if high is None:
            self.input_driven[port] &= ~mask
            return
        self.input_driven[port] |= mask
        self.inputs[port] = (self.inputs[port] & ~mask) | (mask if high else 0)

    def _gpio_input(self, port):
        registers = self.gpio[port]
        enabled, pull_up, pull_down = registers[4], registers[8], registers[12]
        output = registers[0x20]
        driven = registers[0] & ~(registers[0x10] & output)
        external = self.input_driven[port]
        if enabled & driven & external & (output ^ self.inputs[port]):
            raise Unsupported('Conflicting GPIO output and external drive')
        if enabled & ~(driven | external | pull_up | pull_down) & 0xFFFF:
            raise Unsupported('Cannot read a floating GPIO input')
        return ((output & driven) | (self.inputs[port] & external & ~driven)
                | (pull_up & ~driven & ~external)) & enabled & 0xFFFF

    def output(self, port, pad):
        registers = self.gpio[port]
        mask = 1 << pad
        if not registers[0] & mask or registers[0x10] & mask:
            raise Unsupported('GPIO output observation requires a push-pull output')
        if self.input_driven[port] & mask & (self.inputs[port] ^ registers[0x20]):
            raise Unsupported('Conflicting GPIO output and external drive')
        mux = self.registers[0x40022020 + port * 8 + (pad // 8) * 4]
        function = (mux >> ((pad % 8) * 4)) & 15
        if function != 1 and not (function == 0 and (port, pad) in ((2, 14), (3, 1))):
            raise Unsupported('GPIO output observation requires a GPIO alternate function')
        return bool(registers[0x20] & mask)

    def clock(self, byte):
        if not self.registers[0x4008802C] & 16:
            raise Unsupported("SPI0 peripheral clock is disabled")
        return self.spi.clock(byte)

    def scan_interrupt(self):
        if not self.registers[0x40088030] & (1 << 16):
            raise Unsupported('Scan interrupt requested with the BFTM0 clock disabled')
        if self.registers[0x40076000] != 5:
            raise Unsupported("Scan interrupt requested while its timer is disabled")
        self.registers[0x40076004] |= 1
        self.pending |= 1 << 17

    def access(self, address, size, value=None):
        writing = value is not None
        self.accesses[("write" if writing else "read", address)] += 1
        if not writing and self.on_read:
            self.on_read(address)
        if address == 0x40068000:
            if size != 4 or value != 0x5FA00001:
                raise Unsupported('Only the watchdog reload write is supplied')
        elif SPI_BASE <= address <= SPI_BASE + 32:
            if not self.registers[0x4008802C] & 16:
                raise Unsupported("SPI0 register access with its peripheral clock disabled")
            if size != 4:
                raise Unsupported("SPI register access must be a 32-bit word")
            if writing:
                self.spi.write(address - SPI_BASE, value)
            else:
                return self.spi.read(address - SPI_BASE)
        elif 0x400B0000 <= address < 0x400B8000:
            port, offset = divmod(address - 0x400B0000, 0x2000)
            registers = self.gpio[port]
            if size != 4 or offset not in registers:
                raise Unsupported(f"GPIO register 0x{address:08x}")
            if writing:
                if offset == 0x1C:
                    raise Unsupported("GPIO input register is read-only")
                if offset == 0x18 and value:
                    raise Unsupported('GPIO locking is outside the model')
                if offset == 0x24:
                    registers[0x20] &= ~(value >> 16)
                    registers[0x20] |= value & 0xFFFF
                elif offset == 0x28:
                    registers[0x20] &= ~value
                else:
                    registers[offset] = value
            elif offset == 0x1C:
                return self._gpio_input(port)
            else:
                return registers[offset]
        elif address == 0x4006A110:
            if size != 4:
                raise Unsupported("LVD register access must be a 32-bit word")
            if writing:
                if value & 0x300003:
                    raise Unsupported('LVD interrupts/events and brown-out detection are outside the model')
                self.lvd = value & 0x470000
            else:
                select = ((self.lvd >> 17) & 3) | ((self.lvd >> 20) & 4)
                threshold = [2250, 2400, 2550, 2700, 2850, 3000, 3150, 3300][select]
                low = bool(self.lvd & 0x10000) and self.voltage_mv <= threshold
                return self.lvd | (0x80000 if low else 0)
        elif address == 0x400A8000:
            if size != 4 or (writing and value & ~0x40C):
                raise Unsupported('USB signalling, including remote wake, is outside the model')
            if writing:
                self.usb_power = value
            else:
                return self.usb_power
        elif 0x400A8000 <= address < 0x400A9000:
            raise Unsupported('USB signalling, including remote wake, is outside the model')
        elif 0xE000E400 <= address < 0xE000E420:
            index = address - 0xE000E400
            if size != 4 or index % 4 or index + size > 32:
                raise Unsupported("NVIC priority register access")
            if writing:
                self.priorities[index:index + size] = [byte & 0xC0 for byte in value.to_bytes(size, "little")]
            else:
                return int.from_bytes(bytes(self.priorities[index:index + size]), "little")
        elif address in (0xE000E100, 0xE000E180, 0xE000E200, 0xE000E280):
            if size != 4:
                raise Unsupported("NVIC bitmask register access")
            if writing:
                if address == 0xE000E100:
                    self.enabled |= value
                elif address == 0xE000E180:
                    self.enabled &= ~value
                elif address == 0xE000E200:
                    self.pending |= value
                else:
                    self.pending &= ~value
            else:
                return self.enabled if address < 0xE000E200 else self.pending
        elif address in self.registers:
            if size != 4:
                raise Unsupported("Peripheral register access must be a 32-bit word")
            if writing:
                if address == 0x40076000 and value not in (0, 5):
                    raise Unsupported('Only stopped or repetitive BFTM0 scan mode is modelled')
                if address == 0x40076008 and value:
                    raise Unsupported('Only a cleared BFTM0 counter is modelled')
                if address in (0x4002C000, 0x4006E000, 0x4006F000) and value not in (0, 1):
                    raise Unsupported('Unsupported PWM timer control mode')
                if address == 0x40088108:
                    if value & ~(1 << 4):
                        raise Unsupported("Only the SPI0 peripheral reset is modelled")
                    if value & (1 << 4):
                        self.spi.reset()
                else:
                    self.registers[address] = value
            else:
                if address in (0x40076008, 0x4002C080, 0x4006E080, 0x4006F080):
                    raise Unsupported("Free-running timer counters are not modelled")
                return self.registers[address]
        else:
            raise Unsupported(f"Unmodelled {'write' if writing else 'read'} 0x{address:08x}/{size}")
        if writing:
            self.trace.append((address, value))
        return 0


class Machine:
    def __init__(self, image, *, elf=False):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.cpu.ctl_set_cpu_model(UC_CPU_ARM_CORTEX_M0)
        self.cpu.mem_map(0, 0x20000)
        self.cpu.mem_map(0x20000000, 0x4000, UC_PROT_READ | UC_PROT_WRITE)
        self.cpu.mem_map(0x40000000, 0x100000)
        self.cpu.mem_map(0xE000E000, 0x2000)
        self.symbols = {}
        if elf:
            binary = ELFFile(BytesIO(image))
            for segment in binary.iter_segments():
                if segment['p_type'] == 'PT_LOAD' and segment['p_filesz']:
                    self.cpu.mem_write(segment['p_vaddr'], segment.data())
            for symbol in binary.get_section_by_name('.symtab').iter_symbols():
                if symbol['st_shndx'] != 'SHN_UNDEF':
                    value = symbol['st_value']
                    if symbol['st_info']['type'] == 'STT_FUNC':
                        value &= ~1
                    self.symbols.setdefault(symbol.name, []).append(value)
        else:
            self.cpu.mem_write(0x3200, image)
        self.cpu.mem_protect(0, 0x20000, UC_PROT_READ | UC_PROT_EXEC)
        self.hardware = Hardware()
        self.ms = 0
        self.instructions = 0
        self.hooks = {}
        self.events = {}
        self.active = []
        self.running = False
        self.interrupt_trace = []
        self.cpu.mem_write(STOP - 2, bytes.fromhex('7047'))
        self.cpu.reg_write(UC_ARM_REG_MSP, self.symbol('__main_stack_end__') if elf else self.read(0x3200))
        if elf:
            self.cpu.reg_write(UC_ARM_REG_PSP, self.symbol('__process_stack_end__'))
        self.cpu.reg_write(UC_ARM_REG_CONTROL, 2 if elf else 0)
        self.cpu.hook_add(UC_HOOK_MEM_READ, self._read, begin=0x40000000, end=0x400FFFFF)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self._write, begin=0x40000000, end=0x400FFFFF)
        self.cpu.hook_add(UC_HOOK_MEM_READ, self._read, begin=0xE000E000, end=0xE000FFFF)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self._write, begin=0xE000E000, end=0xE000FFFF)
        self.cpu.hook_add(UC_HOOK_CODE, self._instruction)
        self.cpu.hook_add(UC_HOOK_INTR, self._exception)
        self.cpu.hook_add(UC_HOOK_MEM_READ | UC_HOOK_MEM_WRITE, self._alignment)

    def symbol(self, name):
        matches = self.symbols.get(name, [])
        if not matches:
            matches = [address for key, addresses in self.symbols.items()
                       if key.startswith(name + '.lto_priv.') for address in addresses]
        if len(matches) != 1:
            raise Unsupported(f"Expected one ELF symbol {name!r}, found {len(matches)}")
        return matches[0]

    def function(self, name):
        candidates = [key for key in self.symbols if key == name or key.startswith(name + '.')]
        if len(candidates) != 1:
            raise Unsupported(f"Expected one compiled function {name!r}: {candidates}")
        return self.symbol(candidates[0])

    def read(self, address, size=4):
        return int.from_bytes(self.cpu.mem_read(address, size), "little")

    def write(self, address, value, size=4):
        self.cpu.mem_write(address, value.to_bytes(size, "little"))

    def _read(self, cpu, access, address, size, value, context):
        result = self.hardware.access(address, size)
        self.write(address, result, size)

    def _write(self, cpu, access, address, size, value, context):
        self.hardware.access(address, size, value)

    def _alignment(self, cpu, access, address, size, value, context):
        if size > 1 and address % size:
            raise Unsupported(f"Unaligned ARMv6-M access 0x{address:08x}/{size}")

    def _next_irq(self):
        hw = self.hardware
        if hw.registers[0x4008802C] & (1 << 4) and hw.spi.interrupt and SPI_IRQ not in [irq for irq, _ in self.active]:
            hw.pending |= 1 << SPI_IRQ
        available = hw.pending & hw.enabled
        if not available or self.cpu.reg_read(UC_ARM_REG_PRIMASK):
            return None
        ceiling = hw.priorities[self.active[-1][0]] if self.active else 256
        candidates = [irq for irq in range(32) if available & (1 << irq)
                      and hw.priorities[irq] < ceiling]
        return min(candidates, key=lambda irq: (hw.priorities[irq], irq)) if candidates else None

    def _enter(self, irq, address):
        cpu = self.cpu
        handler = bool(self.active)
        process = not handler and bool(cpu.reg_read(UC_ARM_REG_CONTROL) & 2)
        stack = UC_ARM_REG_PSP if process else UC_ARM_REG_MSP
        original_sp = cpu.reg_read(stack)
        frame_address = (original_sp - 32) & ~7
        frame = [cpu.reg_read(register) for register in FRAME_REGS]
        frame[6] = address
        frame[7] = (frame[7] & ~(1 << 9)) | ((original_sp & 4) << 7)
        cpu.mem_write(frame_address, struct.pack('<8I', *frame))
        cpu.reg_write(stack, frame_address)
        exc_return = 0xFFFFFFF1 if handler else 0xFFFFFFFD if process else 0xFFFFFFF9
        self.active.append((irq, exc_return))
        self.hardware.pending &= ~(1 << irq)
        cpu.reg_write(UC_ARM_REG_XPSR, (frame[7] & 0xF0000000) | 0x1000000 | (16 + irq))
        cpu.reg_write(UC_ARM_REG_CONTROL, cpu.reg_read(UC_ARM_REG_CONTROL) & ~2)
        cpu.reg_write(UC_ARM_REG_LR, exc_return)
        vector = self.read(0x3200 + (16 + irq) * 4)
        if not vector & 1 or not 0x3200 <= vector < 0x20000:
            raise Unsupported(f"Invalid IRQ {irq} vector 0x{vector:08x}")
        cpu.reg_write(UC_ARM_REG_PC, vector)
        self.interrupt_trace.append(("enter", irq, address))

    def _exception(self, cpu, number, context):
        if number != 8 or not self.active:
            raise Unsupported(f"Unexpected CPU exception {number} at 0x{cpu.reg_read(UC_ARM_REG_PC):x}")
        irq, exc_return = self.active.pop()
        if cpu.reg_read(UC_ARM_REG_PC) | 1 != exc_return:
            raise Unsupported("Unexpected EXC_RETURN value")
        stack = UC_ARM_REG_PSP if exc_return & 4 else UC_ARM_REG_MSP
        address = cpu.reg_read(stack)
        frame = struct.unpack('<8I', cpu.mem_read(address, 32))
        expected_exception = 16 + self.active[-1][0] if self.active else 0
        if not frame[7] & 0x1000000 or frame[7] & 0x1FF != expected_exception:
            raise Unsupported('Invalid stacked Thumb or exception mode state')
        for register, value in zip(FRAME_REGS, frame):
            if register not in (UC_ARM_REG_PC, UC_ARM_REG_XPSR):
                cpu.reg_write(register, value)
        cpu.reg_write(stack, address + 32 + (4 if frame[7] & (1 << 9) else 0))
        control = cpu.reg_read(UC_ARM_REG_CONTROL) & ~2
        cpu.reg_write(UC_ARM_REG_CONTROL, control | (2 if exc_return & 4 else 0))
        cpu.reg_write(UC_ARM_REG_XPSR, frame[7] & ~(1 << 9))
        cpu.reg_write(UC_ARM_REG_PC, frame[6] | 1)
        self.interrupt_trace.append(("return", irq, frame[6]))

    def _instruction(self, cpu, address, size, context):
        if self.read(address, 2) in (0xBF20, 0xBF30):
            raise Unsupported("WFE/WFI sleep execution is outside component emulation")
        self.instructions += 1
        event = self.events.pop(self.instructions, None)
        if event:
            event()
        irq = self._next_irq()
        if irq is not None:
            self._enter(irq, address)
            return
        hook = self.hooks.get(address)
        if hook:
            result = hook()
            if result is not None:
                cpu.reg_write(UC_ARM_REG_R0, result & 0xFFFFFFFF)
            cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))

    def call(self, address, *arguments, budget=100000):
        if isinstance(address, str):
            address = self.symbol(address)
        if self.active or self.running:
            raise Unsupported("Cannot recursively call firmware from a running callback")
        for register, value in zip(FRAME_REGS[:4], arguments):
            self.cpu.reg_write(register, value)
        self.cpu.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.running = True
        try:
            self.cpu.emu_start(address | 1, STOP, count=budget)
        finally:
            self.running = False
        if self.cpu.reg_read(UC_ARM_REG_PC) != STOP or self.active:
            raise Unsupported(f"Firmware call did not return within {budget} instructions")
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def hook(self, name, callback):
        self.hooks[self.symbol(name)] = callback
