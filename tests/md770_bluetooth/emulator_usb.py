"""Execute the USB queues and callbacks with supplied physical transmit completion."""

from unicorn.arm_const import UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3

from emulator_firmware import Qmk


class UsbQmk(Qmk):
    def __init__(self, image, abi):
        super().__init__(image, abi)
        self.transmissions = []
        self.receives = []
        self.usb(True)
        self.set_host('host_usb')
        self.write(self.symbol('active_host'), abi['host_usb'], 1)
        self.write(self.symbol('driver'), self.symbol('chibios_driver'))
        self.hardware.pin(1, 12, True)
        self.write(self.symbol('supply_known'), 1, 1)
        self.write(self.symbol('external'), 1, 1)
        driver = self.symbol('USBD1')
        self.write(driver + abi['usb_driver_config'], self.function('usbcfg'))
        self.usb_registers = {0x400A8004: 0x111F, 0x400A8008: 0}
        previous_access = self.hardware.access

        def usb_access(address, size, value=None):
            if address not in self.usb_registers:
                return previous_access(address, size, value)
            if size != 4:
                raise ValueError('USB interrupt registers require word accesses')
            if value is None:
                return self.usb_registers[address]
            if address == 0x400A8008:
                self.usb_registers[address] &= ~value
            else:
                self.usb_registers[address] = value
            return 0

        self.hardware.access = usb_access
        self.hardware.enabled |= 1 << 29
        self.hook('usbStartTransmitI', self._transmit)
        for index in range(abi['in_endpoint_count']):
            endpoint = self.endpoint(index)
            self.call('usb_endpoint_in_init', endpoint)
            number = self.read(endpoint + abi['endpoint_number'], 1)
            self.write(driver + abi['usb_in_params'] + 4 * (number - 1), endpoint)
            self.write(driver + abi['usb_epc'] + 4 * number, endpoint + abi['endpoint_config'])
            self.write(endpoint + abi['endpoint_queue'] + abi['queue_suspended'], 0, 1)
        if abi['out_endpoint_count']:
            self.hook('usbStartReceiveI', self._receive)
        for index in range(abi['out_endpoint_count']):
            endpoint = self.symbol('usb_endpoints_out') + index * abi['out_endpoint_bytes']
            self.call('usb_endpoint_out_init', endpoint)
            number = self.read(endpoint + abi['out_endpoint_number'], 1)
            self.write(driver + abi['usb_out_params'] + 4 * (number - 1), endpoint)
            self.write(driver + abi['usb_epc'] + 4 * number, endpoint + abi['out_endpoint_config'])
            self.write(endpoint + abi['out_endpoint_queue'] + abi['out_queue_suspended'], 0, 1)

    def endpoint(self, index):
        return self.symbol('usb_endpoints_in') + index * self.abi['endpoint_bytes']

    def _transmit(self):
        number = self.cpu.reg_read(UC_ARM_REG_R1)
        address = self.cpu.reg_read(UC_ARM_REG_R2)
        size = self.cpu.reg_read(UC_ARM_REG_R3)
        self.transmissions.append((number, bytes(self.cpu.mem_read(address, size))))
        driver = self.symbol('USBD1')
        self.write(driver + self.abi['usb_transmitting'], self.read(driver + self.abi['usb_transmitting'], 2) | (1 << number), 2)
        endpoint = self.read(driver + self.abi['usb_in_params'] + 4 * (number - 1))
        self.write(endpoint + self.abi['endpoint_in_state'] + self.abi['usb_tx_size'], size)

    def _receive(self):
        number = self.cpu.reg_read(UC_ARM_REG_R1)
        self.receives.append((number, self.cpu.reg_read(UC_ARM_REG_R3)))
        driver = self.symbol('USBD1')
        address = driver + self.abi['usb_receiving']
        self.write(address, self.read(address, 2) | (1 << number), 2)

    def complete(self, index):
        number = self.read(self.endpoint(index) + self.abi['endpoint_number'], 1)
        driver = self.symbol('USBD1')
        self.write(driver + self.abi['usb_transmitting'], self.read(driver + self.abi['usb_transmitting'], 2) & ~(1 << number), 2)
        self.call('usb_endpoint_in_tx_complete_cb', driver, number)

    def occupied(self, index):
        queue = self.endpoint(index) + self.abi['endpoint_queue']
        return self.read(queue + self.abi['queue_count']) - self.read(queue + self.abi['queue_free'])

    def send_key(self, key):
        self.cpu.mem_write(self.scratch, bytes([0, 0, key, 0, 0, 0, 0, 0]))
        self.call('host_keyboard_send', self.scratch)

    def event(self, name):
        callback = self.read(self.function('usbcfg'))
        self.call(callback, self.symbol('USBD1'), self.abi['usb_event_' + name])

    def request_interrupt(self, flags):
        self.usb_registers[0x400A8008] |= flags
        self.hardware.pending |= 1 << 29

    def suspend(self, remote_wakeup=False):
        self.usb(True, remote_wakeup=remote_wakeup)
        self.request_interrupt(0x10)
        self.poll()

    def resume(self):
        self.request_interrupt(8)
        self.poll()

    def sof(self):
        self.request_interrupt(2)
        self.poll()
