"""Explicit post-initialisation fixtures for the stock and QMK components."""

import hashlib
import struct

from unicorn.arm_const import UC_ARM_REG_R0

from emulator import Machine, SPI_IRQ, STOP, Unsupported
from stock_probe import STOCK_SHA256


class Qmk(Machine):
    def __init__(self, image, abi):
        super().__init__(image, elf=True)
        self.abi = abi
        self.scratch = self.symbol('__heap_base__')
        if self.scratch + 8 > self.symbol('__heap_end__'):
            raise ValueError('The firmware has no space for a supplied report')
        self.persistent_writes = 0
        self.sleep_action = None
        self.hook('timer_read32', lambda: self.ms)
        self.hooks[self.function('__port_irq_epilogue')] = lambda: None
        self.hooks[self.function('chThdSleep')] = self._sleep
        self.hooks[self.function('nvm_eeconfig_update_connection')] = self._persist
        self.hook('iqGetTimeout', lambda: -1)
        self.hardware.registers[0x4008802C] = (1 << 14) | (1 << 4)
        self.hardware.registers[0x40088030] = (1 << 16) | (1 << 9)
        self.hardware.enabled = (1 << SPI_IRQ) | (1 << 17)
        self.hardware.priorities[SPI_IRQ] = 0x40
        self.hardware.priorities[17] = 0x80
        self.hardware.gpio[2][0] = 1 << 14
        self.hardware.gpio[3][0] = 1 << 1
        self.hardware.gpio[0][4] = (self.hardware.gpio[0][4] & ~0x1FE) | (1 << 10)
        self.hardware.gpio[0][8] &= ~(0x1FE | (1 << 10))
        self.hardware.gpio[0][12] |= 0x1FE | (1 << 10)
        self.hardware.gpio[1][4] = self.hardware.gpio[1][8] = 1 << 12
        self.hardware.gpio[2][4] = self.hardware.gpio[2][8] = 1 << 13
        self.hardware.pin(1, 12, False)
        self.set_host('host_bluetooth')
        self.write(self.symbol('active_host'), abi['host_bluetooth'], 1)
        self._hal()
        self.usb(False)

    def _sleep(self):
        self.ms += self.cpu.reg_read(UC_ARM_REG_R0)
        if self.sleep_action:
            self.sleep_action()

    def _persist(self):
        self.persistent_writes += 1

    def _hal(self):
        abi = self.abi
        for driver, config in [('PWMD_GPTM0', 'gptm_config'), ('PWMD_MCTM0', 'mctm_config')]:
            address = self.symbol(driver)
            self.write(address + abi['pwm_state'], abi['pwm_stop'])
            self.write(address + abi['pwm_config'], self.function(config))
            self.call('pwm_lld_start', address)
            self.write(address + abi['pwm_state'], abi['pwm_ready'])
            self.write(address + abi['pwm_period'], 65535)
            self.write(address + abi['pwm_channels'], 4)
        address = self.symbol('GPTD_BFTM0')
        self.write(address + abi['gpt_state'], abi['gpt_continuous'])
        self.write(address + abi['gpt_config'], self.function('scan_config'))
        self.write(address + abi['gpt_timer'], 0x40076000)
        self.hardware.registers[0x40076000] = 5
        self.hardware.registers[0x4007600C] = 39441

    def set_host(self, name):
        self.write(self.symbol('config'), self.abi[name], 1)

    def usb(self, configured, suspended=False, remote_wakeup=False):
        if suspended and not configured:
            raise ValueError('Only a configured USB connection can be suspended')
        self.write(self.symbol('USBD1') + self.abi['usb_configuration'], int(configured), 1)
        self.write(self.symbol('USBD1') + self.abi['usb_status'], 2 if remote_wakeup else 0, 2)
        state = (self.abi['usb_driver_suspended'] if suspended else
                 self.abi['usb_active'] if configured else self.abi['usb_ready'])
        self.write(self.symbol('USBD1') + self.abi['usb_driver_state'], state,
                   self.abi['usb_driver_state_bytes'])
        state = (self.abi['usb_suspended'] if suspended else
                 self.abi['usb_configured'] if configured else self.abi['usb_init'])
        self.write(self.symbol('usb_device_state') + self.abi['usb_configure_state'], state,
                   self.abi['usb_configure_state_bytes'])

    def task(self, elapsed=0):
        self.ms = (self.ms + elapsed) & 0xFFFFFFFF
        self.call('radio_task')

    def poll(self):
        self.call(STOP - 2)

    def transfer(self, incoming, irq_batch=1):
        hw = self.hardware
        outgoing = []
        hw.spi.selected = True
        for index, byte in enumerate(incoming):
            outgoing.append(hw.clock(byte))
            if (index + 1) % irq_batch == 0:
                self.poll()
        hw.spi.selected = False
        self.poll()
        self.task()
        return outgoing

    def keyboard(self, report):
        if len(report) != 8:
            raise ValueError('A keyboard report must contain eight bytes')
        address = self.scratch
        self.cpu.mem_write(address, report)
        self.call('bluetooth_send_keyboard', address)

    def extra(self, system, usage):
        address = self.scratch
        report_id = self.abi['report_system' if system else 'report_consumer']
        self.cpu.mem_write(address, struct.pack('<BH', report_id, usage))
        self.call('bluetooth_send_extra', address)

    def select(self, slot, pair=False):
        self.call(self.function('md770_radio_select'), slot, int(pair))

    def matrix(self):
        self.call(self.function('matrix_scan'))

    def indicators(self):
        self.call(self.function('md770_indicators_task'))

    def connected(self):
        return self.read(self.symbol('radio_state'), 1) == 4

    def queued(self):
        return self.read(self.symbol('count'), 1)

    def start(self):
        self.call('reset_radio')
        self.task(1000)
        self.task(1500)
        self.task(10)
        expected = [0xA7, 2, 0, 1 if self.read(self.symbol('USBD1') + self.abi['usb_configuration'], 1) else 2]
        assert self.transfer(bytes(4)) == expected
        self.transfer(bytes.fromhex('b6 00 02'))
        self.drain()

    def drain(self):
        outgoing = []
        for _ in range(100):
            self.task(10)
            if self.hardware.output(2, 14):
                size = self.read(self.symbol('current_length'), 1)
                outgoing.append(self.transfer(bytes(size)))
            elif (not self.queued() and not self.read(self.symbol('resynchronise'), 1)
                  and self.read(self.symbol('phase'), 1) == 2
                  and not self.read(self.symbol('pending_slot'), 1)
                  and not self.read(self.symbol('pair_requested'), 1)):
                return outgoing
        raise AssertionError('Radio did not become idle')


class Stock(Machine):
    def __init__(self, image):
        if hashlib.sha256(image).hexdigest() != STOCK_SHA256:
            raise ValueError('The stock address profile requires the recorded US 7.02 image')
        super().__init__(image)
        self.cpu.mem_write(0x20000000, image[0xF150 - 0x3200:0xF170 - 0x3200])
        self.hardware.registers[0x4008802C] = (1 << 14) | (1 << 4)
        self.hardware.gpio[0][4] |= 1 << 10
        self.hardware.gpio[0][12] |= 1 << 10
        self.hardware.gpio[1][4] = self.hardware.gpio[1][8] = 1 << 12
        self.hardware.gpio[2][4] = self.hardware.gpio[2][8] = 1 << 13
        self.hardware.pin(1, 12, False)
        self.persistent_writes = 0
        self.hooks[0x4B68] = self._persist
        self.split_attempts = 0
        self.hooks[0x42DC] = self._split_unavailable
        self.write(0x20000628, 1)
        self.call(0x8600)

    def _persist(self):
        self.persistent_writes += 1

    def _split_unavailable(self):
        if self.cpu.reg_read(UC_ARM_REG_R0) != 0xDF10:
            raise Unsupported('Only the periodic stock split submission has a supplied transport boundary')
        self.split_attempts += 1
        return 0

    def usb(self, configured):
        self.write(0x20000601, 5 if configured else 0, 1)

    def task(self, ticks=0):
        for _ in range(ticks):
            self.call(0x40A4, 1, 1)
        for _ in range(2):
            self.call(0x40A4, 0, 0)
            self.call(0x43A0, 0, 0)

    def start_radio(self):
        self.call(0x43A0, 2, 0)
        self.write(0x20000218, 0x20, 1)
        self.task()

    def indicators(self, ticks=0):
        self.call(0x66AC, ticks, budget=100000 + 64 * ticks)
        self.call(0xD7E4)
        self.call(0x6D04)

    def power(self):
        self.call(0x84FC)

    def voltage_tick(self, ticks=1):
        for _ in range(ticks):
            self.call(0x8650)

    def ready(self):
        self.call(0x43A0, 2, 0)
        self.write(0x20000218, 0x20, 1)
        self.call(0x40A4, 0, 0)
        for _ in range(2):
            self.write(0x20000216, 0, 2)
            self.call(0x40A4, 0, 0)
        self.call(0x40A4, 0, 0)
        self.call(0x43A0, 0, 0)
        self.write(0x20000216, 0, 2)

    def command(self, command):
        self.write(0x20000218, command, 1)
        for _ in range(100):
            self.call(0x40A4, 0, 0)
            self.call(0x43A0, 0, 0)
            if self.hardware.output(2, 14):
                return
            self.call(0x40A4, 1, 1)
        raise Unsupported('Stock command did not start within 100 scheduler callbacks')

    def transfer(self, incoming, irq_batch=1):
        hw = self.hardware
        outgoing = []
        hw.spi.selected = True
        for index, byte in enumerate(incoming):
            outgoing.append(hw.clock(byte))
            if (index + 1) % irq_batch == 0:
                self.call(STOP - 2)
        hw.spi.selected = False
        self.call(STOP - 2)
        self.call(0x43A0, 0, 0)
        return outgoing
