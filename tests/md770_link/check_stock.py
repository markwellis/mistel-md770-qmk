"""Compare native QMK link observations with actual stock instructions."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys

from unicorn.arm_const import UC_ARM_REG_R0

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'md770_bluetooth'))
from emulator import Machine
from emulator_firmware import Stock

STOCK_SHA256 = 'febc84d9dc1fd23152218232839279ecb59f255615a6d6c5b4d951a848c85064'


def stock_trace(image, observations):
    machine = Machine(image)
    machine.hardware.gpio[1][4] = 1 << 8
    machine.hardware.gpio[1][12] = 1 << 8
    attempts = []
    usb = []

    def enqueue():
        if machine.cpu.reg_read(UC_ARM_REG_R0) != 0xAAB4:
            raise AssertionError('Unexpected stock split descriptor')
        attempts.append(True)
        return 1

    machine.hooks[0x3D84] = enqueue
    machine.hooks[0x7A0C] = lambda: usb.append(machine.cpu.reg_read(UC_ARM_REG_R0)) or 0
    machine.hooks[0x6B34] = lambda: 0
    result = []
    for high, elapsed in observations:
        machine.hardware.pin(1, 8, bool(high))
        if elapsed:
            machine.call(0x5468, elapsed)
        machine.call(0x53BC)
        result.append((machine.read(0x20000014, 1), machine.read(0x20000015, 1),
                       machine.read(0x20000016, 1), len(attempts), len(usb),
                       usb[-1] if usb else 1))
    return result


def cases():
    yield 'initial_low_wrap', [(0, 0)] * 256 + [(1, 1)] * 80
    yield 'initial_low_then_high', [(0, 0)] + [(1, 1)] * 81
    yield 'threshold_and_glitch', [(1, 0)] * 16 + [(1, 1)] * 63 + [(0, 1)] + [(1, 1)] * 16 + [(0, 0)] * 16 + [(1, 3)] * 80
    for seed in range(4):
        rng = random.Random(seed)
        observations = []
        for _ in range(30):
            high = rng.randrange(2)
            for _ in range(rng.randrange(1, 80)):
                observations.append((high, rng.choice((0, 1, 2, 8, 127, 256, 511))))
        yield f'seed_{seed}', observations


def right_cases():
    yield 'coalesced_boundaries', [(0, elapsed) for elapsed in
                                  (0, 63, 1, 128, 0, 255, 1, 256, 511, 1, 65536, 63, 1)]
    for seed in range(4):
        rng = random.Random(seed)
        yield f'seed_{seed}', [(0, rng.choice((0, 1, 2, 63, 64, 65, 127, 128, 255, 256, 257, 511, 512)))
                              for _ in range(512)]


def right_stock_trace(image, observations):
    machine = Stock(image)
    result = []
    for _, elapsed in observations:
        if elapsed:
            machine.call(0x66AC, elapsed, budget=100000 + 64 * elapsed)
        result.append((machine.read(0x20000028, 1), machine.split_attempts))
    return result


def compare(native_path, image, scenarios, reference, half):
    records = []
    for name, observations in scenarios:
        supplied = ''.join(f'{pin} {elapsed}\n' for pin, elapsed in observations)
        native = subprocess.run([str(native_path), 'trace'], input=supplied, check=True,
                                text=True, capture_output=True)
        actual = [tuple(map(int, line.split())) for line in native.stdout.splitlines()]
        expected = reference(image, observations)
        if actual != expected:
            for index, (observed, stock) in enumerate(zip(actual, expected, strict=True)):
                if observed != stock:
                    raise AssertionError(f'{half}/{name} observation {index}: QMK {observed}, stock {stock}')
            raise AssertionError(f'{half}/{name}: trace lengths differ')
        records.append({'case': name, 'observations': len(observations),
                        'trace_sha256': hashlib.sha256(native.stdout.encode()).hexdigest()})
        print(f'{half}/{name}: {len(observations)} observations match stock')
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--native', type=Path, required=True)
    parser.add_argument('--native-right', type=Path, required=True)
    parser.add_argument('--stock', type=Path, default=Path('mistel_md770rgb_bt_left_stock.bin'))
    parser.add_argument('--stock-right', type=Path, default=Path('mistel_md770rgb_bt_right_stock.bin'))
    parser.add_argument('--qmk-home', type=Path, default=Path('../qmk_firmware'))
    parser.add_argument('--json', type=Path)
    args = parser.parse_args()
    image = args.stock.read_bytes()
    if hashlib.sha256(image).hexdigest() != STOCK_SHA256:
        raise ValueError('The left address profile requires its recorded US 4.01 image')
    records = compare(args.native, image, cases(), stock_trace, 'left')
    right_image = args.stock_right.read_bytes()
    right_records = compare(args.native_right, right_image, right_cases(), right_stock_trace, 'right')
    if args.json:
        record = {
            'date': datetime.now(timezone.utc).isoformat(),
            'passed': True,
            'scope': 'Native QMK link source versus stock left PB8 and both halves periodic-send instructions; USB transport and UART enqueue boundaries supplied',
            'stock_sha256': STOCK_SHA256,
            'right_stock_sha256': hashlib.sha256(right_image).hexdigest(),
            'qmk_link_sha256': hashlib.sha256((args.qmk_home / 'keyboards/mistel/md770rgb_bt/link.c').read_bytes()).hexdigest(),
            'test_sources_sha256': {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                   for name in ('check_stock.py', 'test.cpp', 'quantum.h', 'usb_main.h')},
            'cases': records,
            'right_cases': right_records,
        }
        args.json.write_text(json.dumps(record, indent=2) + '\n')


if __name__ == '__main__':
    main()
