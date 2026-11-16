#!/usr/bin/env python3
"""Read MD770 diagnostic snapshots, optionally requesting pairing first."""

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
    ('time_ms', 'phase', 'radio_state', 'pending_slot', 'pair_requested', 'held_slot', 'queue_count'),
    ('spi_cr0', 'spi_cr1', 'spi_fcr', 'spi_sr', 'spi_fsr', 'spi_ier', 'rx_selected_failed'),
    ('gpioa_input', 'gpiob_input', 'gpioc_input', 'gpioc_output', 'gpiod_output', 'gpioc_input_enable', 'apb_clock_enable'),
    ('resets', 'spi_interrupts', 'tasks', 'profile_events', 'profile_code', 'phase_started', 'last_frame'),
    ('active_output', 'desired_output', 'charge_eligible', 'idle', 'usb_sleeping', 'usb_configured', 'gpiob_input_enable'),
    ('afio_a0', 'afio_a1', 'afio_b0', 'afio_b1', 'afio_c1', 'afio_d0', 'gpiob_direction'),
    ('last_irq_status', 'last_irq_control', 'last_task_status', 'last_error_phase', 'spi_clock_prescaler', 'apb_reset', 'spi_fifo_timeout'),
    ('layers', 'default_layers', 'pn_f1', 'default_pn_f1', 'compiled_f1', 'profile_seen', 'profile_consumed'),
    ('f1_down', 'pn_down', 'fn_down', 'default_pn_f2', 'default_pn_f3', 'default_profile_pn', 'base_pn'),
    ('profile1_pn_f1', 'profile2_pn_f1', 'profile3_pn_f1', 'selected_profile', 'selected_pn_f1', 'f1_source_layer', 'f1_resolved_code'),
    ('keyboard_calls', 'keyboard_drops', 'keyboard_call_radio_state', 'last_physical_code', 'last_physical_position', 'last_nonzero_report_0', 'last_nonzero_report_1'),
    ('keyboard_frames_started', 'keyboard_frames_completed', 'last_rx_prefix', 'b7_messages', 'current_command', 'current_length', 'fifo_positions'),
    ('test_mode', 'test_completed', 'test_started', 'test_released', 'test_queue', 'last_wire_report_0', 'last_wire_report_1'),
)


def read_page(fd, page, slot=0):
    request = bytes([ord('M'), ord('D'), 2, page, slot]).ljust(32, b'\0')
    if os.write(fd, b'\0' + request) != 33:
        raise RuntimeError('Incomplete diagnostic request')
    deadline = time.monotonic() + 2
    last_header = None
    while time.monotonic() < deadline:
        if not select.select([fd], [], [], max(0, deadline - time.monotonic()))[0]:
            break
        response = os.read(fd, 32)
        last_header = response[:4].hex(' ')
        if len(response) == 32 and response[:4] == request[:4]:
            result_page = 0 if page == 16 else 12 if page == 17 else 4 if page == 19 else page
            return dict(zip(FIELDS[result_page], struct.unpack('<7I', response[4:]), strict=True))
        if len(response) == 32 and response[0] == 0xff and response[1:4] == request[1:4]:
            raise RuntimeError(f'Diagnostic page {page} was rejected by the installed image')
    raise RuntimeError(f'Diagnostic page {page} timed out; last header: {last_header}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=6)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--pair-slot', type=int, choices=(1, 2, 3), help='Request pairing through the existing driver instead of a physical shortcut')
    parser.add_argument('--pulse', choices=('driver', 'qmk', 'unguarded'), help='Inject the known A/J diagnostic pulse through the selected path')
    args = parser.parse_args()
    if args.samples < 1:
        parser.error('Provide at least one sample')
    samples = []
    failure, sample = None, None
    fd = os.open(find_device(), os.O_RDWR | os.O_NONBLOCK)
    try:
        if args.pair_slot:
            read_page(fd, 16, args.pair_slot)
        if args.pulse:
            read_page(fd, 17, ('driver', 'qmk', 'unguarded').index(args.pulse) + 1)
        for index in range(args.samples):
            sample = {}
            for page in range(len(FIELDS)):
                sample.update(read_page(fd, page))
            samples.append(sample)
            print(json.dumps({name: sample[name] for name in
                              ('time_ms', 'phase', 'radio_state', 'resets', 'spi_interrupts', 'tasks',
                               'profile_events', 'charge_eligible', 'gpioc_input', 'spi_sr', 'spi_fsr', 'last_irq_status',
                               'active_output', 'desired_output', 'queue_count', 'last_frame', 'keyboard_calls',
                               'keyboard_drops', 'keyboard_frames_started', 'keyboard_frames_completed', 'test_mode', 'test_completed')}), flush=True)
            sample = None
            if index + 1 < args.samples:
                time.sleep(0.5)
    except BaseException as error:
        failure = error
        if sample:
            sample['partial'] = True
            samples.append(sample)
    finally:
        os.close(fd)
    result = {'date': datetime.now(timezone.utc).isoformat(), 'capture_mode': 'live_usb_driver_diagnostic',
              'scope': 'Non-atomic driver snapshots', 'requested_pair_slot': args.pair_slot, 'samples': samples,
              'requested_pulse': args.pulse,
              'output_field_scope': 'active_output reads connection_get_host(), the resolved requested host; it does not read host.c active_host'}
    if failure:
        result['error'] = str(failure) or type(failure).__name__
    args.out.write_text(json.dumps(result, indent=2) + '\n')
    if os.environ.get('SUDO_UID'):
        os.chown(args.out, int(os.environ['SUDO_UID']), int(os.environ['SUDO_GID']))
    if failure:
        raise failure


if __name__ == '__main__':
    main()
