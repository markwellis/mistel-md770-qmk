"""Execute native USB queues and keyboard suspend policy with supplied bus events."""

from pathlib import Path
import unittest

from emulator_abi import layout
from emulator_usb import UsbQmk


class UsbTests(unittest.TestCase):
    qmk_home = Path('../qmk_firmware')
    elf_path = None

    @classmethod
    def setUpClass(cls):
        cls.elf_path = cls.elf_path or cls.qmk_home / '.build/mistel_md770rgb_bt_right_default_mistel_conformance_validation.elf'
        cls.abi = layout(cls.qmk_home.resolve(), cls.elf_path.resolve())
        cls.image = cls.elf_path.read_bytes()

    def qmk(self):
        return UsbQmk(self.image, self.abi)

    def test_suspend_discards_old_reports_and_fresh_input_works_after_resume(self):
        qmk = self.qmk()
        index = self.abi['keyboard_endpoint']
        qmk.send_key(4)
        qmk.send_key(5)
        self.assertEqual(qmk.occupied(index), 2)
        qmk.suspend()
        self.assertEqual(qmk.occupied(index), 0)
        qmk.resume()
        qmk.call('usb_event_queue_task')
        qmk.sof()
        qmk.send_key(6)
        self.assertEqual(qmk.transmissions[-1][1][2], 6)
        self.assertIn(('enter', 29), [(kind, irq) for kind, irq, _ in qmk.interrupt_trace])

    def test_selected_usb_suspend_disables_lighting_and_resume_restores_it(self):
        qmk = self.qmk()
        qmk.suspend()
        qmk.call('usb_event_queue_task')
        self.assertTrue(qmk.call('md770_power_usb_suspended'))
        self.assertFalse(qmk.call('md770_power_rgb_allowed'))
        qmk.resume()
        qmk.call('usb_event_queue_task')
        self.assertFalse(qmk.call('md770_power_usb_suspended'))
        self.assertTrue(qmk.call('md770_power_rgb_allowed'))

    def test_bluetooth_remains_awake_while_usb_host_suspends(self):
        qmk = self.qmk()
        qmk.call('connection_set_host_noeeprom', self.abi['host_bluetooth'])
        qmk.suspend()
        qmk.call('usb_event_queue_task')
        self.assertFalse(qmk.call('md770_power_usb_suspended'))
        self.assertTrue(qmk.call('md770_power_rgb_allowed'))

    def test_remote_wake_requires_permission_and_selected_usb_output(self):
        qmk = self.qmk()
        qmk.suspend()
        requests = []
        qmk.hook('usbWakeupHost', lambda: requests.append(qmk.ms))
        qmk.call('md770_power_usb_wake')
        self.assertEqual(requests, [])
        qmk.usb(True, suspended=True, remote_wakeup=True)
        qmk.call('md770_power_usb_wake')
        self.assertEqual(len(requests), 1)
        qmk.call('connection_set_host_noeeprom', self.abi['host_bluetooth'])
        qmk.call('md770_power_usb_wake')
        self.assertEqual(len(requests), 1)
