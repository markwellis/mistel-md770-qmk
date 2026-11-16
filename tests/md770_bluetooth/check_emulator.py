#!/usr/bin/env python3
"""Validate the bounded model and compare the supplied firmware components."""

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import unittest

import unicorn

import test_emulator
from test_emulator_firmware import FirmwareTests
from test_emulator_macros import MacroTests
from emulator_scenarios import hardware_plan
from emulator_abi import firmware_binary


class ScenarioResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.subtests_run = 0

    def addSubTest(self, test, subtest, error):
        self.subtests_run += 1
        super().addSubTest(test, subtest, error)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--model-only', action='store_true', help='Run without QMK or stock firmware')
    parser.add_argument('--qmk-home', type=Path, default=FirmwareTests.qmk_home)
    parser.add_argument('--elf', type=Path, help='Right-half QMK ELF; defaults to the default keymap build')
    parser.add_argument('--macro-elf', type=Path, help='Validation ELF retaining the compiled macro entry points')
    parser.add_argument('--stock', type=Path, default=FirmwareTests.stock_path)
    parser.add_argument('--json', type=Path, help='Write a machine-readable verification record')
    parser.add_argument('--plan', type=Path, help='Export hardware calibration cases after the full software suite passes')
    args = parser.parse_args()
    if args.plan and (args.model_only or not args.macro_elf):
        parser.error('--plan requires the firmware suites and --macro-elf')
    suite = unittest.defaultTestLoader.loadTestsFromModule(test_emulator)
    if not args.model_only:
        FirmwareTests.qmk_home = args.qmk_home
        FirmwareTests.elf_path = args.elf
        FirmwareTests.stock_path = args.stock
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(FirmwareTests))
        if args.macro_elf:
            MacroTests.qmk_home = args.qmk_home
            MacroTests.elf_path = args.macro_elf
            suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(MacroTests))
    result = unittest.TextTestRunner(verbosity=2, resultclass=ScenarioResult).run(suite)
    if args.json:
        record = {
            'date': datetime.now(timezone.utc).isoformat(),
            'unicorn': unicorn.__version__,
            'tests': result.testsRun,
            'parameterised_subtests': result.subtests_run,
            'passed': result.wasSuccessful(),
            'failures': [test.id() for test, _ in result.failures],
            'errors': [test.id() for test, _ in result.errors],
            'model_only': args.model_only,
            'scope': 'Component instruction execution with supplied time and RTOS boundaries; no physical validation',
            'model_sources_sha256': {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in sorted(Path(__file__).parent.glob('emulator*.*'))
                if path.suffix in ('.py', '.c')
            },
            'test_sources_sha256': {
                path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                for path in [Path(__file__), Path(__file__).with_name('cpu_fixture.S'),
                             *sorted(Path(__file__).parent.glob('test_emulator*.py'))]
            },
        }
        if not args.model_only and hasattr(FirmwareTests, 'image'):
            record['qmk_elf_sha256'] = hashlib.sha256(FirmwareTests.image).hexdigest()
            record['stock_sha256'] = hashlib.sha256(FirmwareTests.stock_image).hexdigest()
            record['abi'] = FirmwareTests.abi
            record['abi_provenance'] = FirmwareTests.abi_provenance
        if args.macro_elf and hasattr(MacroTests, 'image'):
            record['macro_elf_sha256'] = hashlib.sha256(MacroTests.image).hexdigest()
            record['macro_abi_provenance'] = MacroTests.abi_provenance
        args.json.write_text(json.dumps(record, indent=2) + '\n')
    if args.plan and result.wasSuccessful() and getattr(MacroTests, 'calibration_verified', False):
        plan = hardware_plan()
        for case in plan['cases']:
            key = tuple(case[name] for name in plan['factors'])
            case['emulator_prediction'] = MacroTests.calibration_predictions[key]
        plan['prediction_build'] = {
            'validation_elf': MacroTests.elf_path.name,
            'validation_elf_sha256': hashlib.sha256(MacroTests.image).hexdigest(),
            'validation_binary_sha256': hashlib.sha256(firmware_binary(MacroTests.elf_path, MacroTests.image)).hexdigest(),
            'abi_provenance': MacroTests.abi_provenance,
            'software_tests_passed': result.testsRun,
            'software_subtests': result.subtests_run,
        }
        args.plan.write_text(json.dumps(plan, indent=2) + '\n')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
