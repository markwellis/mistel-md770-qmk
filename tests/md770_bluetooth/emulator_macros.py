"""Run the compiled macro player with supplied stored bytes and host submissions."""

from unicorn.arm_const import UC_ARM_REG_R0

from emulator import Unsupported
from emulator_firmware import Qmk


class MacroQmk(Qmk):
    def __init__(self, image, abi):
        super().__init__(image, abi)
        self.macro_buffer = bytearray(self.call('nvm_dynamic_keymap_macro_size'))
        observed = []
        self.hook('eeprom_read_byte', lambda: observed.append(self.cpu.reg_read(UC_ARM_REG_R0)) or 0)
        self.call('nvm_dynamic_keymap_macro_read_buffer', 0, 1, self.scratch)
        if len(observed) != 1:
            raise Unsupported('Expected one macro-storage read when locating the EEPROM region')
        self.macro_base = observed[0]
        self.hook('eeprom_read_byte', self._read_macro_byte)
        self.record = (self.scratch + 8 + 3) & ~3
        if self.record + abi['record_bytes'] > self.symbol('__heap_end__'):
            raise Unsupported('No space for a supplied macro key event')
        self.usb_reports = []
        self.usb_extra_reports = []
        self.usb_nkro_count = 0
        driver = self.symbol('chibios_driver')
        self.write(self.symbol('driver'), driver)
        keyboard_send = self.read(driver + abi['driver_keyboard']) & ~1
        self.hooks[keyboard_send] = self._usb_keyboard
        nkro_send = self.read(driver + abi['driver_nkro']) & ~1
        self.hooks[nkro_send] = self._usb_nkro
        extra_send = self.read(driver + abi['driver_extra']) & ~1
        self.hooks[extra_send] = self._usb_extra

    def _read_macro_byte(self):
        offset = self.cpu.reg_read(UC_ARM_REG_R0) - self.macro_base
        if not 0 <= offset < len(self.macro_buffer):
            raise Unsupported('EEPROM read outside the supplied macro storage')
        return self.macro_buffer[offset]

    def _usb_keyboard(self):
        if self.read(self.symbol('USBD1') + self.abi['usb_driver_state'], self.abi['usb_driver_state_bytes']) != self.abi['usb_active']:
            return
        report = self.cpu.reg_read(UC_ARM_REG_R0)
        mods = self.read(report + self.abi['report_mods'], 1)
        keys = self.cpu.mem_read(report + self.abi['report_keys'], 6)
        self.usb_reports.append(bytes([mods, 0, *keys]))
        self._usb_accepted(1)

    def _usb_nkro(self):
        report = self.cpu.reg_read(UC_ARM_REG_R0)
        mods = self.read(report + self.abi['nkro_mods'], 1)
        bitmap = self.cpu.mem_read(report + self.abi['nkro_bits'], self.abi['nkro_bit_bytes'])
        keys = [index * 8 + bit for index, value in enumerate(bitmap)
                for bit in range(8) if value & (1 << bit)]
        self.usb_reports.append(bytes([mods, 0, *keys, *([0] * max(0, 6 - len(keys)))]))
        self.usb_nkro_count += 1
        self._usb_accepted(1)

    def _usb_extra(self):
        report = self.cpu.reg_read(UC_ARM_REG_R0)
        self.usb_extra_reports.append((self.read(report + self.abi['extra_report_id'], 1),
                                       self.read(report + self.abi['extra_usage'], 2)))
        self._usb_accepted(4 if self.usb_extra_reports[-1][0] == self.abi['report_system'] else 2)

    def _usb_accepted(self, family):
        if 'usb_pending' in self.symbols:
            address = self.symbol('usb_pending')
            self.write(address, self.read(address, 1) & ~family, 1)

    def nkro(self, enabled):
        address = self.symbol('keymap_config')
        value = self.read(address, 2) & ~self.abi['nkro_mask']
        self.write(address, value | (self.abi['nkro_mask'] if enabled else 0), 2)

    def load_macro(self, data, slot=0):
        if not data or data[-1] or slot < 0 or slot >= self.abi['macro_count']:
            raise ValueError('A macro requires a valid slot and a terminating zero')
        if slot + len(data) >= len(self.macro_buffer):
            raise ValueError('Macro data exceeds the supplied storage')
        self.macro_buffer[:] = bytes(len(self.macro_buffer))
        self.macro_buffer[slot:slot + len(data)] = data

    def event(self, keycode, *, row=3, col=2, pressed=True):
        self.cpu.mem_write(self.record, bytes(self.abi['record_bytes']))
        for name, value, size in (
            ('record_row', row, 1), ('record_col', col, 1),
            ('record_type', self.abi['key_event'], self.abi['record_type_bytes']),
            ('record_pressed', int(pressed), 1),
        ):
            self.write(self.record + self.abi[name], value, size)
        return self.call('md770_programming_process', keycode, self.record)

    def play(self, slot=0, *, row=3, col=2):
        self.event(self.abi['macro_keycode'] + slot, row=row, col=col)
        self.event(self.abi['macro_keycode'] + slot, row=row, col=col, pressed=False)

    def macro_step(self, elapsed=0):
        self.ms = (self.ms + elapsed) & 0xFFFFFFFF
        self.call('md770_programming_task')

    def playing(self):
        return bool(self.call('md770_playback_active'))

    def output_mode(self, bluetooth):
        host = 'host_bluetooth' if bluetooth else 'host_usb'
        self.set_host(host)
        self.write(self.symbol('active_host'), self.abi[host], 1)
        self.usb(not bluetooth)
        self.hardware.pin(1, 12, not bluetooth)
