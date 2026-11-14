#!/usr/bin/env python3
"""Latch a breathing notification on the personal MD770 QMK firmware."""

import argparse
import os
from pathlib import Path
import select
import sys
import time


def parse_colour(value: str) -> bytes:
    value = value.removeprefix("#")
    try:
        colour = bytes.fromhex(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("Use a six-digit RGB colour, such as ff8800") from error
    if len(value) != 6 or len(colour) != 3:
        raise argparse.ArgumentTypeError("Use a six-digit RGB colour, such as ff8800")
    return colour


def find_device() -> Path:
    for device in Path("/sys/class/hidraw").glob("hidraw*"):
        properties = dict(
            line.split("=", 1)
            for line in (device / "device/uevent").read_text().splitlines()
            if "=" in line
        )
        if properties.get("HID_ID") == "0003:000004D9:00000419" and (
            device / "device/report_descriptor"
        ).read_bytes().startswith(bytes.fromhex("06 60 ff 09 61 a1 01")):
            return Path("/dev") / device.name
    raise RuntimeError("No MD770 QMK Raw HID interface found")


def notify(fd: int, colour: bytes) -> None:
    packet = (b"MD\x01" + colour).ljust(32, b"\0")
    if os.write(fd, b"\0" + packet) != 33:
        raise RuntimeError("Incomplete HID write")
    deadline = time.monotonic() + 2
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0 or not select.select([fd], [], [], remaining)[0]:
            raise RuntimeError("Keyboard reply timed out")
        reply = os.read(fd, 32)
        if reply == packet:
            return
        if reply == b"\xff" + packet[1:]:
            raise RuntimeError("This firmware does not support notifications")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("colour", type=parse_colour, help="RGB hex colour, such as ff8800")
    args = parser.parse_args()
    fd = os.open(find_device(), os.O_RDWR | os.O_NONBLOCK)
    try:
        notify(fd, args.colour)
    finally:
        os.close(fd)
    print("Notification latched; press any key to dismiss.")


if __name__ == "__main__":
    try:
        main()
    except (OSError, RuntimeError) as error:
        sys.exit(str(error))
