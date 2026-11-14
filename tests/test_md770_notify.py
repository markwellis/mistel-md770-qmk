import argparse
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location(
    "md770_notify", Path(__file__).parents[1] / "scripts/md770_notify.py"
)
notification = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notification)


class NotificationTest(unittest.TestCase):
    def test_rgb_colour(self):
        self.assertEqual(notification.parse_colour("#FF8800"), b"\xff\x88\0")
        self.assertEqual(notification.parse_colour("000000"), b"\0\0\0")
        for value in ("", "abc", "red", "ff008800", "gg0000", "ff 00 00"):
            with self.subTest(value=value), self.assertRaises(argparse.ArgumentTypeError):
                notification.parse_colour(value)

    def test_finds_qmk_raw_hid_interface(self):
        with tempfile.TemporaryDirectory() as directory:
            devices = []
            for index, (identity, descriptor) in enumerate(
                [
                    ("0003:000004D9:00000419", "06 00 ff 09 01 a1 01"),
                    ("0003:000004D9:0000041A", "06 60 ff 09 61 a1 01"),
                    ("0003:000004D9:00000419", "06 60 ff 09 61 a1 01"),
                ]
            ):
                device = Path(directory) / f"hidraw{index}"
                (device / "device").mkdir(parents=True)
                (device / "device/uevent").write_text(f"HID_ID={identity}\nHID_NAME=MD770\n")
                (device / "device/report_descriptor").write_bytes(bytes.fromhex(descriptor))
                devices.append(device)
            with patch.object(notification.Path, "glob", return_value=devices):
                self.assertEqual(notification.find_device(), Path("/dev/hidraw2"))

    def test_no_device(self):
        with patch.object(notification.Path, "glob", return_value=[]):
            with self.assertRaisesRegex(RuntimeError, "No MD770 QMK"):
                notification.find_device()

    def test_report_and_acknowledgement(self):
        packet = b"MD\x01\xff\x88\0".ljust(32, b"\0")
        with patch.object(notification.os, "write", return_value=33) as write, patch.object(
            notification.select, "select", return_value=([7], [], [])
        ), patch.object(notification.os, "read", side_effect=[b"unrelated", packet]):
            notification.notify(7, b"\xff\x88\0")
            write.assert_called_once_with(7, b"\0" + packet)

    def test_unsupported_firmware(self):
        reply = b"\xffD\x01\xff\0\0".ljust(32, b"\0")
        with patch.object(notification.os, "write", return_value=33), patch.object(
            notification.select, "select", return_value=([7], [], [])
        ), patch.object(notification.os, "read", return_value=reply):
            with self.assertRaisesRegex(RuntimeError, "does not support notifications"):
                notification.notify(7, b"\xff\0\0")

    def test_incomplete_write(self):
        with patch.object(notification.os, "write", return_value=32):
            with self.assertRaisesRegex(RuntimeError, "Incomplete HID write"):
                notification.notify(7, b"\xff\0\0")

    def test_reply_timeout(self):
        with patch.object(notification.os, "write", return_value=33), patch.object(
            notification.select, "select", return_value=([], [], [])
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                notification.notify(7, b"\xff\0\0")

    def test_unrelated_replies_do_not_extend_deadline(self):
        with patch.object(notification.os, "write", return_value=33), patch.object(
            notification.select, "select", return_value=([7], [], [])
        ), patch.object(notification.os, "read", return_value=b"unrelated"), patch.object(
            notification.time, "monotonic", side_effect=[0, 1, 3]
        ):
            with self.assertRaisesRegex(RuntimeError, "timed out"):
                notification.notify(7, b"\xff\0\0")

    def test_device_closed_after_failure(self):
        with patch.object(notification.sys, "argv", ["md770_notify.py", "ff0000"]), patch.object(
            notification, "find_device", return_value=Path("/dev/hidraw7")
        ), patch.object(notification.os, "open", return_value=7), patch.object(
            notification, "notify", side_effect=RuntimeError("failed")
        ), patch.object(notification.os, "close") as close:
            with self.assertRaisesRegex(RuntimeError, "failed"):
                notification.main()
            close.assert_called_once_with(7)


if __name__ == "__main__":
    unittest.main()
