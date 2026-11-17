#!/usr/bin/env python3
"""Read the temporary reconnect diagnostic image without exposing key payloads."""

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import select
import struct
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from scripts.md770_notify import find_device

FIELDS = (
    ('time_ms', 'phase', 'radio_state', 'pending_command', 'startup_attempts', 'queue_count', 'trace_count'),
    ('spi_sr', 'spi_fsr', 'spi_ier', 'spi_cr0', 'spi_cr1', 'spi_cpr', 'apb_clock_enable'),
    ('desired_host', 'resolved_host', 'usb_ready', 'usb_state', 'usb_configuration', 'radio_input_A10', 'supply_B12'),
)


def exchange(fd, page, item=0):
    packet = bytes([ord('M'), ord('D'), 2, page, item]).ljust(32, b'\0')
    for _ in range(2):
        if os.write(fd, b'\0' + packet) != 33:
            raise RuntimeError('Incomplete diagnostic write')
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
                break
            reply = os.read(fd, 32)
            if len(reply) == 32 and reply[:4] == packet[:4]:
                return reply[4:]
            if len(reply) == 32 and reply[:4] == b'\xff' + packet[1:4]:
                raise RuntimeError('The installed image rejected this diagnostic command')
    raise RuntimeError(f'Diagnostic page {page} timed out')


def snapshot(fd):
    result = {}
    for page, names in enumerate(FIELDS):
        result.update(zip(names, struct.unpack('<7I', exchange(fd, page)), strict=True))
    result['trace'] = []
    for sequence in range(max(0, result['trace_count'] - 4), result['trace_count']):
        raw = exchange(fd, 3 + sequence % 4)
        stamp, event, phase, state, command, tx_length, rx_length, attempts, queued, status, sent, received = struct.unpack('<I8BH7s7s', raw)
        result['trace'].append({
            'sequence': sequence, 'time_ms': stamp, 'event': event, 'phase': phase,
            'radio_state': state, 'command': command, 'tx_length': tx_length,
            'rx_length': rx_length, 'attempts': attempts, 'queued': queued, 'spi_sr': status,
            'sent': (f'{sent[0]:02x} (input payload omitted)' if sent[0] in (0xA1, 0xA2, 0xA3)
                     else sent[:min(tx_length, 7)].hex(' ')),
            'received': received[:min(rx_length, 7)].hex(' '),
        })
    result['trace_count_after_read'] = struct.unpack('<7I', exchange(fd, 0))[-1]
    result['trace_changed_during_read'] = result['trace_count_after_read'] != result['trace_count']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--action', choices=('snapshot', 'select', 'pair', 'reset', 'release', 'bootloader'), default='snapshot')
    parser.add_argument('--samples', type=int, default=1)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('Provide at least one sample')
    fd = os.open(find_device(), os.O_RDWR | os.O_NONBLOCK)
    result = {'date': datetime.now(timezone.utc).isoformat(), 'action': args.action,
              'scope': 'Non-atomic USB observations from temporary keyboard-only instrumentation', 'samples': []}
    try:
        if args.action == 'bootloader':
            packet = b'MD\x02\x23\x01'.ljust(32, b'\0')
            if os.write(fd, b'\0' + packet) != 33:
                raise RuntimeError('Incomplete updater-entry write')
        else:
            if args.action != 'snapshot':
                page = {'select': 32, 'pair': 33, 'reset': 34, 'release': 36}[args.action]
                exchange(fd, page, 0 if args.action in ('reset', 'release') else 1)
            for index in range(args.samples):
                result['samples'].append(snapshot(fd))
                if index + 1 < args.samples:
                    time.sleep(0.5)
    finally:
        os.close(fd)
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
