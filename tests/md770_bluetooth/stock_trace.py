#!/usr/bin/env python3
"""Check stock Bluetooth, power and indicator transitions with supplied inputs."""

import hashlib
import json
from pathlib import Path
import sys

from unicorn import UC_HOOK_CODE, UC_HOOK_MEM_READ, UC_HOOK_MEM_WRITE
from unicorn.arm_const import (
    UC_ARM_REG_LR,
    UC_ARM_REG_PC,
    UC_ARM_REG_R0,
    UC_ARM_REG_R1,
    UC_ARM_REG_R2,
    UC_ARM_REG_R3,
)

from stock_probe import CONTEXT, RX_BUFFER, STOCK_SHA256, Stock


class Trace(Stock):
    def __init__(self, firmware):
        super().__init__(firmware)
        self.write(0x20000000, firmware[0xF150 - 0x3200 : 0xF170 - 0x3200])
        self.leds = []
        self.mmio = []
        self.cpu.hook_add(UC_HOOK_CODE, self.instruction, begin=0x6630, end=0x6630)
        self.cpu.hook_add(UC_HOOK_MEM_WRITE, self.store, begin=0x40000000, end=0x400FFFFF)

    def instruction(self, cpu, address, size, context):
        self.leds.append([cpu.reg_read(UC_ARM_REG_R0), cpu.reg_read(UC_ARM_REG_R1)])

    def store(self, cpu, access, address, size, value, context):
        self.mmio.append([f"0x{address:08x}", size, value])

    def put(self, address, value, size=1):
        self.write(address, value.to_bytes(size, "little"))

    def get(self, address, size=1):
        return int.from_bytes(self.read(address, size), "little")

    def call(self, address, *arguments):
        for register, value in zip(
            [UC_ARM_REG_R0, UC_ARM_REG_R1, UC_ARM_REG_R2, UC_ARM_REG_R3], arguments
        ):
            self.cpu.reg_write(register, value)
        super().call(address)
        return self.cpu.reg_read(UC_ARM_REG_R0)

    def packet(self, command):
        self.put(CONTEXT + 0x10, 4)
        self.write(CONTEXT + 0x2C, bytes([command, 4]))
        self.call(0x9DEC)
        return self.read(CONTEXT + 0x14, self.get(CONTEXT + 10, 2)).hex(" ")


class Fifo:
    """Supply FIFO occupancy, byte clocks and select edges without modelling a radio."""

    def __init__(self, stock):
        self.stock = stock
        self.rx = []
        self.tx = []
        self.selected = False
        self.errors = 0
        self.maximum_tx = 0
        stock.cpu.hook_add(UC_HOOK_MEM_READ, self.read, begin=0x40004000, end=0x40004020)
        stock.cpu.hook_add(UC_HOOK_MEM_WRITE, self.write, begin=0x40004000, end=0x40004020)

    def read(self, cpu, access, address, size, value, context):
        if address == 0x4000401C:
            self.stock.put(address, len(self.rx) << 4 | len(self.tx), 4)
        elif address == 0x40004014:
            self.stock.put(address, self.errors | (0x100 if self.selected else 0) | (0 if self.tx else 3), 4)
        elif address == 0x40004010:
            assert self.rx, "Read from an empty supplied FIFO"
            self.stock.put(address, self.rx.pop(0), 4)

    def write(self, cpu, access, address, size, value, context):
        if address == 0x40004010:
            self.tx.append(value & 0xFF)
            self.maximum_tx = max(self.maximum_tx, len(self.tx))
            assert len(self.tx) <= 8, "Stock overfilled the supplied FIFO"

    def clocks(self, incoming, batch=1):
        outgoing = []
        self.selected = True
        for index, byte in enumerate(incoming):
            outgoing.append(self.tx.pop(0) if self.tx else None)
            self.rx.append(byte)
            if (index + 1) % batch == 0:
                self.stock.call(0x8ABC)
        if self.rx:
            self.stock.call(0x8ABC)
        self.selected = False
        self.stock.call(0x43A0, 0, 0)
        return outgoing


def ready(firmware):
    stock = Trace(firmware)
    fifo = Fifo(stock)
    stock.call(0x43A0, 2, 0)
    stock.put(0x20000218, 0x20)
    stock.call(0x40A4, 0, 0)
    for unused in range(2):
        stock.put(0x20000216, 0, 2)
        stock.call(0x40A4, 0, 0)
    stock.call(0x40A4, 0, 0)
    stock.call(0x43A0, 0, 0)
    stock.put(0x20000216, 0, 2)
    return stock, fifo


def check(firmware):
    results = {}
    for command, expected in {
        0x41: "aa 03 01", 0x42: "aa 03 02", 0x43: "aa 03 03",
        0x50: "aa 00 01", 0x60: "a6 00 00", 0x61: "a6 01 00",
        0x63: "a6 03 00", 0xA1: "a4 01", 0xA2: "a4 02", 0xAF: "a4 0f",
    }.items():
        actual = Trace(firmware).packet(command)
        assert actual == expected, (hex(command), actual, expected)
        results[f"command_{command:02x}"] = actual

    for usb_state in range(7):
        stock = Trace(firmware)
        stock.put(0x20000601, usb_state)
        expected = "a7 02 00 01" if usb_state in (5, 6) else "a7 02 00 02"
        assert stock.packet(0x80) == expected
    results["usb_notification"] = "USB states 5/6 send 01; all other states 0..6 send 02"

    for field, value in [(0, 0), (0, 1), (0, 2), (0, 3), (1, 2), (2, 7), (3, 3)]:
        stock = Trace(firmware)
        stock.receive(bytes([0xB6, field, value]))
        assert stock.get(0x200001E4 + field) == value + (2 if field == 0 else 0)
    results["incoming_status"] = "b6 fields 0..3; field 0 stores value + 2"

    for length in (0, 1, 2):
        stock = Trace(firmware)
        stock.put(0x200001E4, 9)
        stock.receive(bytes.fromhex("b6 00 02")[:length])
        assert stock.get(0x200001E4) == 9
    results["short_status"] = "Incomplete b6 packets leave the public state unchanged"

    stock = Trace(firmware)
    stock.put(0x20000218, 0x20)
    stock.call(0x40A4, 0, 0)
    assert stock.get(0x20000219) == 1
    assert stock.get(0x20000216, 2) == 2000
    assert stock.get(0x200001E6) == 4
    assert ["0x400b6024", 4, 2] in stock.mmio
    stock.put(0x20000216, 0, 2)
    stock.call(0x40A4, 0, 0)
    assert stock.get(0x20000219) == 2
    assert stock.get(0x20000216, 2) == 3000
    assert ["0x400b6028", 4, 2] in stock.mmio
    stock.put(0x20000216, 0, 2)
    stock.call(0x40A4, 0, 0)
    assert stock.get(0x20000219) == 3
    assert stock.get(0x200001E6) == 3
    assert stock.get(CONTEXT, 4) == CONTEXT + 0x14
    assert stock.get(CONTEXT + 4, 4) == RX_BUFFER
    assert stock.get(CONTEXT + 0x0C, 2) == 10
    results["startup"] = "PD1 high 2000 ticks, low 3000 ticks, then receive setup with 3 retries remaining"
    stock.put(0x20000219, 2)
    stock.put(0x20000216, 0, 2)
    stock.put(0x200001E6, 0)
    stock.call(0x40A4, 0, 0)
    assert stock.get(0x200001E4) == 7
    assert stock.get(0x20000219) == 0
    assert stock.get(0x20000218) == 0
    assert stock.get(CONTEXT + 0x10) == 0

    for active in (0, 1):
        stock = Trace(firmware)
        stock.call(0x3DA4, 0xDFE0, active)
        assert stock.get(0x40004004, 4) == 0x108
        assert stock.get(0x40004018, 4) == (0 if active else 0x410)
        assert stock.get(0x40004000, 4) == (0xF if active else 1)
    results["spi_configuration"] = "Slave mode 0; idle FIFO enabled; active FIFO disabled and both DMA requests enabled"

    for index, register in enumerate([0x4006E098, 0x4002C09C, 0x4006E090, 0x4006E094, 0x4002C090]):
        stock = Trace(firmware)
        stock.call(0x6630, index, 1)
        assert stock.get(register, 4) == 6000
        stock.call(0x6630, index, 0)
        assert stock.get(register, 4) == 0
    results["indicator_channels"] = "Indices 0..4 use the five recovered compare registers at 6000/0"

    stock = Trace(firmware)
    stock.put(0x20000020, 1)
    stock.put(0x400B401C, 1 << 13, 4)
    stock.call(0xD7E4)
    assert [1, 1] in stock.leds
    results["charge_complete"] = "PC13 high with external-power state sets LED2 blue continuously"

    stock = Trace(firmware)
    stock.put(0x20000020, 1)
    pulses = []
    for unused in range(7):
        stock.put(0x200000D6, 0, 2)
        stock.leds.clear()
        stock.call(0xD7E4)
        pulses.append([stock.leds[-1], stock.get(0x200000D6, 2)])
    assert pulses == [[[1, 1], 50], [[1, 0], 50], [[1, 1], 50], [[1, 0], 50], [[1, 1], 50], [[1, 0], 6000], [[1, 1], 50]], pulses
    results["charging_phases"] = pulses

    stock = Trace(firmware)
    stock.put(0x2000001F, 1)
    stock.put(0x2000001E, 4)
    stock.call(0xD7E4)
    assert [0, 1] in stock.leds
    assert stock.get(0x200000D6, 2) == 50
    results["low_battery"] = "Battery-monitor state 1 with level < 5 drives the same burst on LED2 red"

    levels = []
    for level in range(1, 8):
        stock = Trace(firmware)
        stock.put(0x2000001E, level)
        stock.call(0xC7B4)
        register = stock.get(0x4006A110, 4)
        assert register == (0x10000 | ((level - 1) % 4) << 17 | (0x400000 if level >= 5 else 0))
        assert stock.get(0x2000001C, 2) == 50
        levels.append(f"0x{register:08x}")
    results["voltage_detector_levels_1_to_7"] = levels

    for flags, expected in [(0x90000, 49), (0x10000, 50), (0x80000, 50), (0, 50)]:
        stock = Trace(firmware)
        stock.put(0x2000001C, 50, 2)
        stock.put(0x4006A110, flags, 4)
        stock.call(0x8650)
        assert stock.get(0x2000001C, 2) == expected
    results["voltage_filter"] = "50 consecutive LVD-enabled low samples; any high sample resets the counter"

    stock = Trace(firmware)
    stock.put(0x200000C0, 4)
    stock.put(0x200000C2, 4, 2)
    stock.put(0x200000C8, 500, 2)
    phases = []
    for unused in range(5):
        stock.put(0x200000C6, 0, 2)
        stock.leds.clear()
        stock.call(0xD7E4)
        phases.append([stock.leds.copy(), stock.get(0x200000C2, 2), stock.get(0x200000C6, 2)])
    assert [phase[0][-1] for phase in phases] == [[1, 1], [1, 0], [1, 1], [1, 0], [1, 0]]
    assert stock.get(0x200000C0) == 0
    results["slot_change_phases"] = phases

    stock, fifo = ready(firmware)
    stock.write(0x200005D8, bytes.fromhex("02 00 04 00 00 00 00 00"))
    stock.put(0x20000218, 0xF0)
    stock.call(0x40A4, 0, 0)
    stock.call(0x43A0, 0, 0)
    assert len(fifo.tx) == 7
    outgoing = fifo.clocks(bytes(9))
    assert outgoing == list(bytes.fromhex("a1 02 00 04 00 00 00 00 00")), outgoing
    assert stock.get(0x40004018, 4) == 0x410
    assert stock.get(0x40004000, 4) == 1
    assert not any(address == "0x40004000" and value == 0xF for address, size, value in stock.mmio)
    results["keyboard_fifo_transaction"] = {"outgoing": outgoing, "maximum_fifo_bytes": fifo.maximum_tx, "dma_enabled": False}

    for command, expected in [(0xF0, bytes.fromhex("a1 02 00 04 00 00 00 00 00")), (0x80, bytes.fromhex("a7 02 00 02"))]:
        for message in [bytes.fromhex("b1 02"), bytes.fromhex("b6 00 02"), bytes.fromhex("b7 02"), b"\x99"]:
            for batch in (1, 2):
                stock, fifo = ready(firmware)
                stock.write(0x200005D8, bytes.fromhex("02 00 04 00 00 00 00 00"))
                stock.put(0x20000218, command)
                stock.call(0x40A4, 0, 0)
                stock.call(0x43A0, 0, 0)
                incoming = message.ljust(len(expected), b"\x00")
                assert fifo.clocks(incoming, batch) == list(expected)
                assert stock.get(0x20000218) == command
    results["incoming_message_does_not_acknowledge"] = "B1/B6/B7/unknown messages preserve pending A1/A7 commands; bytewise and two-byte IRQ batches leave wire packets unchanged"

    for length in (11, 16):
        stock, fifo = ready(firmware)
        stock.put(0x20000218, 0xF0)
        stock.call(0x40A4, 0, 0)
        stock.call(0x43A0, 0, 0)
        outgoing = fifo.clocks(bytes(length))
        assert outgoing[:9] == list(bytes.fromhex("a1 00 00 00 00 00 00 00 00"))
        assert stock.get(0x20000218) == 0x20
    results["padded_frames"] = "11- and 16-clock A1 frames acknowledge normally; ten bytes is an RX storage budget"

    stock, fifo = ready(firmware)
    fifo.clocks(bytes.fromhex("b6 00 02"))
    assert stock.get(0x200001E4) == 4
    results["unsolicited_status_transaction"] = "FIFO IRQ parses b6 00 02 and select release rearms reception"

    for command, source, data, expected in [
        (0xF0, 0x200005D8, bytes(8), bytes.fromhex("a1 00 00 00 00 00 00 00 00")),
        (0xF1, 0x200005B1, bytes.fromhex("00 04 00 00"), bytes.fromhex("a2 00 04 00 00")),
        (0xF2, 0x200005AD, b"\x04", bytes.fromhex("a3 04")),
    ]:
        stock, fifo = ready(firmware)
        stock.write(source, data)
        stock.put(0x20000218, command)
        stock.call(0x40A4, 0, 0)
        stock.call(0x43A0, 0, 0)
        assert fifo.clocks(bytes(len(expected))) == list(expected)
    results["release_consumer_system_fifo_transactions"] = "All three complete stock transfers match their source buffers"

    stock, fifo = ready(firmware)
    stock.put(0x20000218, 0x51)
    stock.call(0x40A4, 0, 0)
    stock.call(0x43A0, 0, 0)
    assert fifo.clocks(bytes(3)) == list(bytes.fromhex("aa 03 01"))
    assert stock.get(0x20000218) == 0x50
    assert stock.get(0x20000216, 2) == 300
    stock.put(0x20000216, 0, 2)
    stock.call(0x40A4, 0, 0)
    stock.call(0x40A4, 0, 0)
    stock.call(0x43A0, 0, 0)
    assert fifo.clocks(bytes(3)) == list(bytes.fromhex("aa 00 01"))
    results["pairing_command_sequence"] = "Select slot, wait 300 scheduler callbacks, then aa 00 01"

    stock, fifo = ready(firmware)
    stock.put(0x20000218, 0x80)
    stock.call(0x40A4, 0, 0)
    stock.call(0x43A0, 0, 0)
    assert stock.get(0x20000216, 2) == 4000
    stock.put(0x20000216, 0, 2)
    stock.call(0x40A4, 0, 0)
    assert stock.get(0x20000219) == 1
    assert stock.get(0x20000216, 2) == 2000
    results["command_timeout"] = "4000 callbacks without completion restart the PD1 reset sequence"

    stock, fifo = ready(firmware)
    fifo.errors = 0x10
    stock.call(0x8ABC)
    assert stock.get(0x200000ED) == 6
    assert stock.get(0x20000219) == 3
    results["spi_error"] = "Read overrun rearms the radio context and marks the generic port for cleanup"

    stock = Trace(firmware)
    stock.put(0x2000001F, 1)
    stock.put(0x2000001E, 5)
    stock.put(0x200023EC, 100, 4)
    stock.put(0x20000628, 1, 4)
    stock.put(0x4006A110, 0x90000, 4)
    for unused in range(50):
        stock.call(0x8650)
    stock.call(0x84FC)
    assert stock.get(0x2000001E) == 4
    assert stock.get(0x20000623) == 9
    assert stock.get(0x4006A110, 4) == 0x70000
    results["low_voltage_transition"] = "Level 5 falls to 4, requests power state 9 and selects the 2.70 V nominal detector threshold"

    stock = Trace(firmware)
    stock.put(0x2000068C, 1)
    stock.put(0x2000068A, 2)
    stock.call(0x6D04)
    assert stock.leds == [[0, 1]]
    stock.put(0x2000068C, 2)
    stock.put(0x2000068B, 2)
    phases = []
    for timer in (4000, 3072, 3071, 2048, 2047, 1024, 1023, 0):
        stock.put(0x2000002A, timer, 2)
        stock.leds.clear()
        stock.call(0x6D04)
        phases.append(stock.leds[-1][1])
    assert phases == [1, 1, 0, 0, 1, 1, 0, 0]
    results["caps_lock"] = "USB: steady red; Bluetooth: timer bit 10 while the 4000-tick indication remains active"

    stock.put(0x2000001F, 1)
    stock.put(0x2000001E, 4)
    stock.leds.clear()
    stock.call(0x6D04)
    assert stock.leds == []
    results["low_battery_caps_priority"] = "Low voltage suppresses the Caps Lock writer, preserving the red warning"

    stock = Trace(firmware)
    stock.put(0x20000020, 1)
    stock.put(0x400B401C, 1 << 13, 4)
    stock.put(0x2000068C, 1)
    stock.put(0x2000068A, 2)
    stock.call(0xD7E4)
    stock.call(0x6D04)
    assert stock.get(0x4002C09C, 4) == 6000
    assert stock.get(0x4006E098, 4) == 6000
    results["charging_caps_overlap"] = "The stock paths can enable LED2 red and blue simultaneously"

    stock = Trace(firmware)
    stock.call(0x8600)
    assert stock.get(0x200023EC, 4) == 1200000
    stock.call(0x8650)
    assert stock.get(0x200023EC, 4) == 1199999
    results["idle_timer"] = "1200000 nominal half-millisecond ticks: ten minutes, differing from the older Japanese manual"

    for elapsed, remaining in [(49, 1), (50, 0), (51, 0)]:
        stock = Trace(firmware)
        stock.put(0x200000D6, 50, 2)
        stock.call(0x66AC, elapsed)
        assert stock.get(0x200000D6, 2) == remaining
    results["indicator_elapsed_ticks"] = "The actual elapsed-tick routine decrements the 50-tick phase without underflow"

    stock = Trace(firmware)
    stock.put(0x20000216, 20, 2)
    stock.put(0x20000219, 3)
    stock.call(0x40A4, 1, 5)
    assert stock.get(0x20000216, 2) == 19
    results["radio_elapsed_callbacks"] = "The radio callback decrements once per invocation, even when five elapsed ticks are supplied"

    stock = Trace(firmware)
    stock.put(0x200000C0, 4)
    stock.put(0x200000C2, 680, 2)
    stock.put(0x200000C8, 1000, 2)
    stock.put(0x200001E4, 4)
    stock.call(0x5CE4)
    assert stock.get(0x200000C2, 2) == 0
    results["connection_ends_pairing_indicator"] = "Public radio state 4 clears the pending blink count"

    for key, held, pending in [
        (0x68, 6000, 0), (0x68, 6001, 0x51),
        (0x60, 6000, 0), (0x60, 6001, 0x52),
        (0x58, 6000, 0), (0x58, 6001, 0x53),
    ]:
        stock = Trace(firmware)
        stock.write(0x20000231, bytes([0xFF] * 15))
        for index in (0x35, key):
            address = 0x20000231 + index // 8
            stock.put(address, stock.get(address) & ~(1 << (index % 8)))
        stock.put(0x20000682, held, 2)
        stock.put(0x200001E4, 2)

        def skip_settings(cpu, address, size, context):
            cpu.reg_write(UC_ARM_REG_PC, cpu.reg_read(UC_ARM_REG_LR))

        stock.cpu.hook_add(UC_HOOK_CODE, skip_settings, begin=0x4B68, end=0x4B68)
        stock.call(0x5D40)
        assert stock.get(0x20000218) == pending
        if pending:
            assert stock.get(0x200000C2, 2) == 680
            assert stock.get(0x200000C8, 2) == 1000
    results["pairing_hold_boundary"] = "Pn+F1/F2/F3 fire when the hold counter exceeds 6000; settings-write routine stubbed, all key/command logic executed"
    return results


def main():
    firmware = Path(sys.argv[1]).read_bytes()
    assert hashlib.sha256(firmware).hexdigest() == STOCK_SHA256, "Wrong stock image"
    results = check(firmware)
    print(json.dumps({
        "stock_sha256": STOCK_SHA256,
        "scope": "Actual stock instructions; supplied RAM, GPIO and peripheral state; no physical radio or battery model",
        "checks": results,
    }, indent=2))


if __name__ == "__main__":
    main()
