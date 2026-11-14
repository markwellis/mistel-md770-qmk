#!/usr/bin/env python3
"""Execute the stock US radio protocol routines in an isolated ARM emulator."""

import hashlib
import json
from pathlib import Path
import struct
import sys

from unicorn import Uc, UC_ARCH_ARM, UC_MODE_MCLASS, UC_MODE_THUMB
from unicorn.arm_const import UC_ARM_REG_LR, UC_ARM_REG_PC, UC_ARM_REG_SP

STOCK_SHA256 = "8fafdca096756f23626802d5b586b270b0bd512fe5d1c0327db4eafcd4f689b2"
CONTEXT = 0x200001EC
TX_BUFFER = CONTEXT + 0x14
RX_BUFFER = CONTEXT + 0x20
STOP = 0x10000


class Stock:
    def __init__(self, firmware):
        self.cpu = Uc(UC_ARCH_ARM, UC_MODE_THUMB | UC_MODE_MCLASS)
        self.cpu.mem_map(0, 0x20000)
        self.cpu.mem_write(0x3200, firmware)
        self.cpu.mem_map(0x20000000, 0x4000)
        self.cpu.mem_map(0x40000000, 0x100000)
        self.cpu.mem_map(0xE000E000, 0x2000)
        self.cpu.reg_write(UC_ARM_REG_SP, 0x20003F00)
        self.cpu.reg_write(UC_ARM_REG_LR, STOP | 1)

    def write(self, address, value):
        self.cpu.mem_write(address, value)

    def read(self, address, length):
        return bytes(self.cpu.mem_read(address, length))

    def call(self, address):
        self.cpu.reg_write(UC_ARM_REG_LR, STOP | 1)
        self.cpu.emu_start(address | 1, STOP, count=10000)
        assert self.cpu.reg_read(UC_ARM_REG_PC) == STOP, "Stock routine did not return"

    def report(self, command):
        self.write(CONTEXT + 0x10, b"\x04")
        self.write(CONTEXT + 0x2C, bytes([command, 4]))
        self.call(0x9DEC)
        length = struct.unpack("<H", self.read(CONTEXT + 0x0A, 2))[0]
        assert self.read(0x400B4024, 4) == struct.pack("<I", 1 << 14)
        return self.read(TX_BUFFER, length)

    def receive(self, packet):
        self.write(RX_BUFFER, packet)
        self.write(CONTEXT + 4, struct.pack("<I", RX_BUFFER + len(packet)))
        self.call(0x9D6C)


def main():
    firmware = Path(sys.argv[1]).read_bytes()
    assert hashlib.sha256(firmware).hexdigest() == STOCK_SHA256, "Wrong stock image"
    results = {}
    for name, command, address, payload, expected in [
        ("keyboard", 0xF0, 0x200005D8, bytes.fromhex("02 00 04 00 00 00 00 00"), "a1 02 00 04 00 00 00 00 00"),
        ("consumer", 0xF1, 0x200005B1, bytes.fromhex("00 04 00 00"), "a2 00 04 00 00"),
        ("system", 0xF2, 0x200005AD, b"\x01", "a3 01"),
    ]:
        stock = Stock(firmware)
        stock.write(address, payload)
        packet = stock.report(command)
        assert packet == bytes.fromhex(expected), (name, packet.hex())
        results[name] = packet.hex(" ")

    for slot in range(1, 4):
        stock = Stock(firmware)
        packet = stock.report(0x40 + slot)
        assert packet == bytes([0xAA, 3, slot]), packet.hex()
        results[f"select_slot_{slot}"] = packet.hex(" ")

    stock = Stock(firmware)
    stock.receive(bytes.fromhex("b6 00 02"))
    assert stock.read(0x200001E4, 1) == b"\x04"
    results["incoming_state"] = "b6 00 02 -> state 4"

    stock = Stock(firmware)
    stock.receive(bytes.fromhex("b6 03 03"))
    assert stock.read(0x200001E7, 1) == b"\x03"
    results["incoming_slot"] = "b6 03 03 -> slot 3"
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
