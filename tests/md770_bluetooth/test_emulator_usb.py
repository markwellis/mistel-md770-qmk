"""Execute USB event IRQs and retained queue ownership with supplied bus transfers."""

from pathlib import Path
import unittest

from unicorn import UC_HOOK_CODE

from emulator_abi import layout
from emulator_usb import UsbQmk


class UsbTests(unittest.TestCase):
    qmk_home = Path('../qmk_firmware')
    elf_path = None

    @classmethod
    def setUpClass(cls):
        cls.elf_path = cls.elf_path or cls.qmk_home / '.build/mistel_md770rgb_bt_right_default_conformance_validation.elf'
        cls.abi = layout(cls.qmk_home.resolve(), cls.elf_path.resolve())
        cls.image = cls.elf_path.read_bytes()

    def qmk(self):
        return UsbQmk(self.image, self.abi)

    def test_actual_suspend_resume_and_sof_irq_keep_queued_keyboard_reports(self):
        qmk = self.qmk()
        index = self.abi['keyboard_endpoint']
        for key in (4, 5, 6, 7):
            qmk.send_key(key)
            qmk.complete(index)
        qmk.send_key(8)
        qmk.send_key(9)
        self.assertEqual(qmk.occupied(index), 2)
        qmk.suspend()
        self.assertEqual(qmk.read(qmk.symbol('USBD1') + self.abi['usb_driver_state'], self.abi['usb_driver_state_bytes']), self.abi['usb_driver_suspended'])
        self.assertEqual(qmk.occupied(index), 2)
        self.assertTrue(qmk.call('usb_keyboard_report_pending'))
        qmk.resume()
        self.assertFalse(qmk.call('md770_power_usb_ready'))
        qmk.sof()
        self.assertTrue(qmk.call('md770_power_usb_ready'))
        qmk.complete(index)
        qmk.complete(index)
        self.assertFalse(qmk.call('usb_keyboard_report_pending'))
        self.assertEqual([packet[2] for _, packet in qmk.transmissions[-2:]], [8, 9])
        self.assertIn(('enter', 29), [(kind, irq) for kind, irq, _ in qmk.interrupt_trace])

    def test_suspended_new_input_waits_for_sof_before_submission(self):
        qmk = self.qmk()
        index = self.abi['keyboard_endpoint']
        qmk.suspend()
        qmk.call('register_code', 4)
        self.assertEqual(qmk.occupied(index), 0)
        self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), 1)
        qmk.resume()
        qmk.call('md770_power_task')
        self.assertEqual(qmk.occupied(index), 0)
        qmk.sof()
        qmk.call('md770_power_task')
        self.assertEqual(qmk.occupied(index), 1)
        self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), 0)
        self.assertEqual(qmk.transmissions[-1][1][2], 4)

    def test_irq_between_host_observer_and_driver_submission_retains_input(self):
        qmk = self.qmk()
        entry = qmk.function('send_keyboard')
        injected = False

        def suspend_at_entry(cpu, address, size, context):
            nonlocal injected
            if address == entry and not injected:
                injected = True
                qmk.request_interrupt(0x10)

        hook = qmk.cpu.hook_add(UC_HOOK_CODE, suspend_at_entry)
        qmk.call('register_code', 4)
        qmk.cpu.hook_del(hook)
        self.assertTrue(injected)
        self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), 1)
        self.assertEqual(qmk.occupied(self.abi['keyboard_endpoint']), 0)
        qmk.resume()
        qmk.sof()
        qmk.call('md770_power_task')
        self.assertEqual(qmk.transmissions[-1][1][2], 4)
        self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), 0)

    def test_shared_extra_queue_does_not_create_a_keyboard_wake_reason(self):
        qmk = self.qmk()
        qmk.call('host_consumer_key_event', 0xE9, True)
        self.assertEqual(qmk.occupied(self.abi['shared_endpoint']), 1)
        self.assertFalse(qmk.call('usb_keyboard_report_pending'))
        qmk.complete(self.abi['shared_endpoint'])
        qmk.cpu.mem_write(qmk.scratch, bytes([self.abi['report_nkro'], 0]) + bytes(self.abi['nkro_bit_bytes']))
        qmk.call(qmk.read(qmk.symbol('chibios_driver') + self.abi['driver_nkro']), qmk.scratch)
        self.assertTrue(qmk.call('usb_keyboard_report_pending'))

    def test_reset_callback_clears_resume_gate_and_discards_pending_queue(self):
        qmk = self.qmk()
        qmk.send_key(4)
        qmk.suspend()
        qmk.resume()
        self.assertFalse(qmk.call('md770_power_usb_ready'))
        qmk.usb(False)
        qmk.event('reset')
        self.assertFalse(qmk.read(qmk.symbol('usb_resume_pending'), 1))
        self.assertEqual(qmk.occupied(self.abi['keyboard_endpoint']), 0)

    def test_phy_power_and_trim_policy_preserves_fine_calibration(self):
        qmk = self.qmk()
        qmk.hardware.registers[0x40088040] = 0x12340023
        qmk.suspend()
        self.assertEqual(qmk.hardware.usb_power, 0x40C)
        self.assertEqual(qmk.hardware.registers[0x40088040], 0x12340011)
        qmk.resume()
        self.assertEqual(qmk.hardware.usb_power, 0x400)
        self.assertEqual(qmk.hardware.registers[0x40088040], 0x12340011)
        qmk.usb(False)
        qmk.event('reset')
        self.assertEqual(qmk.hardware.registers[0x40088040], 0x12340023)

    def test_remote_wake_is_requested_on_each_service_with_pending_keyboard(self):
        qmk = self.qmk()
        requests = []
        qmk.suspend(remote_wakeup=True)
        csr = 0x400A8000
        registers = {csr: qmk.hardware.usb_power}
        access = qmk.hardware.access

        def supplied_csr(address, size, value=None):
            if address != csr:
                return access(address, size, value)
            self.assertEqual(size, 4)
            if value is None:
                return registers[csr]
            self.assertFalse(value & ~0x42C)
            registers[csr] = value
            if value & 0x20:
                requests.append(qmk.ms)
            return 0

        qmk.hardware.access = supplied_csr
        qmk.call('register_code', 4)
        for index, now in enumerate((0, 1, 99, 100), 1):
            qmk.ms = now
            qmk.call('md770_power_task')
            self.assertEqual(len(requests), index)
            self.assertEqual(qmk.read(qmk.symbol('usb_pending'), 1), 1)
            self.assertEqual(registers[csr], 0x420)


if __name__ == '__main__':
    unittest.main()
