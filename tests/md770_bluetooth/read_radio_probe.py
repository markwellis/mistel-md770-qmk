#!/usr/bin/env python3
"""Read startup traffic from the temporary MD770 Bluetooth diagnostic."""

import json
import os
from pathlib import Path
import select
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.md770_notify import find_device


def main():
    fd = os.open(find_device(), os.O_RDWR | os.O_NONBLOCK)
    try:
        payload = bytes.fromhex(sys.argv[1]) if len(sys.argv) == 2 else b""
        if len(payload) > 8:
            raise ValueError("At most eight command bytes")
        packet = (b"BT\x01" + bytes([len(payload)]) + payload).ljust(32, b"\0")
        if os.write(fd, b"\0" + packet) != 33:
            raise RuntimeError("Incomplete HID write")
        if not select.select([fd], [], [], 2)[0]:
            raise RuntimeError("Diagnostic reply timed out")
        reply = os.read(fd, 32)
        if len(reply) != 32 or reply[:3] != b"BT\x01" or reply[3] > 24:
            raise RuntimeError("Unexpected diagnostic reply")
        print(json.dumps({
            "received_bytes": reply[3],
            "spi_status": hex(int.from_bytes(reply[4:8], "little")),
            "capture_hex": reply[8:8 + reply[3]].hex(" "),
        }, indent=2))
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
