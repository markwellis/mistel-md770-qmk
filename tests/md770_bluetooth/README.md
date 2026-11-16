# MD770 Bluetooth and power checks

`run.sh` compiles the actual QMK keyboard drivers and ChibiOS resume function
against supplied registers, a FIFO model, GPIO, time and host services. It
uses address, undefined-behaviour and bounds sanitizers. C++ register proxies
provide FIFO read/write effects without changing the production C source.
The firmware itself is compiled as C in both-half QMK builds.

Run from the repository root:

```fish
nix-shell --run 'bash tests/md770_bluetooth/run.sh'
```

`QMK_HOME` defaults to the sibling `qmk_firmware` checkout. The Nix shell sets
that path. Cases cover queued reports and macro backpressure, media mappings,
transport recovery, incoming status/reconnect races, pairing, shutdown,
supply/LVD/LED states, USB suspend and both RGB drivers. The RGB checks verify
the unchanged shifted waveform for all 256 byte values and that wake priming
does not run under the global lock. Leak detection is disabled because the
execution environment uses ptrace; address and bounds checks remain enabled.

`stock_probe.py` and `stock_trace.py` execute original firmware instructions
under Unicorn. See the [stock research](../../docs/mistel-md770-stock-bluetooth-power.md)
for extraction, hashes, reproduction and the supplied-input scope.

The older `radio_probe.c` and reader remain historical diagnostics. Neither
the native tests nor Unicorn establishes electrical timing, physical charging
or Bluetooth delivery through the real module.

Run the complete software pass, including builds, macro playback and hardware
plan generation:

```fish
nix-shell --run 'bash tests/md770_bluetooth/run-software.sh'
```

This checks both right-hand keymaps, the native driver/programming tests,
stock probes and host tools. It writes the two emulator verification records
and the [hardware calibration plan](../../docs/mistel-md770-hardware-calibration.md).

`emulator*.py` and `emulator_abi.c` execute compiled QMK and stock components
against the same bounded peripheral model. The Nix shell supplies Unicorn,
pyelftools, Capstone and the firmware compiler. Apply the dependency patches
from the [keymap setup](../../keyboards/mistel/md770rgb_bt/keymaps/markwellis/readme.md#pending-upstream-changes)
and rebuild the right default keymap before running the comparisons:

```fish
nix-shell --run 'qmk compile -kb mistel/md770rgb_bt/right -km default -j 4'
nix-shell --run 'python3 -B tests/md770_bluetooth/check_emulator.py'
```

The stock input defaults to the ignored `mistel_md770rgb_bt_right_stock.bin`
in this repository's root. `--stock` accepts another location; the fixture
requires the recorded US 7.02 SHA-256. `--elf` selects another right-half
build, such as `.build/mistel_md770rgb_bt_right_markwellis.elf` in QMK.
`--qmk-home` selects the QMK checkout used to compile the ABI probe.
`--json` writes results with firmware, model and test-source hashes.
The ABI probe uses current headers and GCC with the saved build flags. The
ELF must be rebuilt after changes to those inputs. The record includes the
compiler, flags hash and preprocessed-probe hash; ELF-derived layouts are not
claimed.

The independent CPU and register tests need no firmware images:

```fish
nix-shell --run 'python3 -B tests/md770_bluetooth/check_emulator.py --model-only'
```

The earlier checkpoint had 35 model groups, 31 production-firmware groups and
17 macro/host groups per keymap, with 376 parameterised subtests. The expanded
stock conformance audit currently has 87 groups and 419 parameterised checks
and still fails; see `docs/mistel-md770-installed-stock-conformance-reviewed.json`.
The native `pair_boundary` case checks elapsed hold time, accounting for the
stock counter starting at one. Passing the earlier suite did not establish
full stock Bluetooth parity. The cases cover exception
frames and flags, MSP/PSP, stack alignment, nested and deferred interrupts,
GPIO input enables and pulls, NVIC priorities, nominal LVD thresholds and
SPI FIFO/error contracts. Firmware cases compare keyboard, media, system,
host-selection and collision/retry packets with stock. Added comparisons cover
startup reset edges, USB status notices, pairing delay, 128 seeded keyboard
reports and LED/LVD boundaries. The 18 consumer usages check QMK's mapping
against explicit bitmaps and stock framing; stock's usage-to-bitmap mapping
is not executed. Other cases cover queue backpressure, reconnects,
final-byte/error races, timer wrap, real scan-handler pre-emption and idle
timer values. The delayed-reset regression injects a busy reset bit and
configuration loss, checking that the actual SPI setup polls completion.

The completed Astra review is in
`docs/mistel-md770-astra-stock-parity-review.json`; its evidence index is
`docs/mistel-md770-astra-review-evidence.json`. The historical replay sources
are under `review/`, with exact ELF hash checks. Their successful execution
confirms reproduction of the recorded discrepancies, not stock parity.
`review/frozen_candidate.patch` is the withdrawn unsafe candidate, retained
only for reproducing that review. The production checkout no longer contains it.

Run from this repository's root:

```fish
nix-shell --run 'python3 tests/md770_bluetooth/review/radio.py'
nix-shell --run 'python3 tests/md770_bluetooth/review/power.py'
nix-shell --run 'python3 tests/md770_bluetooth/review/usb_power.py'
nix-shell --run 'python3 tests/md770_bluetooth/review/power_filter.py'
```

`emulator_macros.py` supplies stored macro bytes at the EEPROM read boundary
and captures USB driver submissions. Compiled player, key registration,
report routing and Bluetooth SPI instructions execute. The separate
`*_validation.elf` retains the public entry points through standard linker
options. `--macro-elf` adds these checks to the runner; production ELF checks
remain separate because linker retention affects LTO.

Macro cases cover all 20 slots after nonempty predecessors, ASCII, modifiers,
explicit delays, cancellation, invalid storage/data, radio backpressure,
USB NKRO, boot protocol and Bluetooth six-key reports. All 72 combinations
of the hardware plan's factors run in software against explicit event
oracles. The generated 11 hardware cases cover 57/57 factor-value pairs.
USB reconnect cases execute the radio task and assert both transition
notices; actual USB enumeration remains supplied. Trigger-half cases supply
compiled matrix coordinates, without simulating the split wire.

Host-transition cases call the real compiled power initialisation and host
task from an inactive driver state. They check USB configuration, powered
unconfigured USB, both saved host selections and a subsequent slot selection,
then compare A press/release submissions on the actual USB or Bluetooth path.
A powered unconfigured connection retains the saved host; selecting a radio
slot explicitly switches the host driver to Bluetooth. These cases supplement
the macro fixture's supplied active output rather than modelling a full boot.

The fixtures supply initialisation, time, RTOS scheduling, persistent writes
and empty UART input. GPIO floating inputs and conflicting drives fail.
Output observations require a GPIO push-pull output. Invalid exception frames,
LVD interrupt/event/brown-out enables and unsupported BFTM modes fail. Scan
interrupt injection requires the BFTM clock and repetitive interrupt mode.
Other timer/PWM registers provide configuration observations, without counter
advancement or output waveform simulation.
FIFO occupancy beyond seven bytes, free-running timer reads and USB signalling
are outside the model. USB remote wake fails explicitly. The fixture updates
both QMK and ChibiOS USB state without simulating a USB bus.

Independent review and the verification records are described in the
[resume checkpoint](../../docs/mistel-md770-emulator-checkpoint.md).
Basic Bluetooth delivery on the normal image has passed on power-bank power,
with both halves captured and no host USB connection. Three diagnostic pulse
cases match emulator key-event predictions; see the
[agreement record](../../docs/mistel-md770-diagnostic-pulse-agreement.json).
The full macro/suspend hardware calibration remains pending. Battery-specific checks are deferred
until a battery is available. Use the
[calibration guide](../../docs/mistel-md770-hardware-calibration.md) for the
small measured hardware set and automatic host-event comparison.
The recommended `--quick` command guides five scenarios and prints separate
Bluetooth-functional and emulator-agreement results. Three live traces are
compared with the actual emulator output exported after the software checks;
the two manual observation results are kept separate. The optional full
matrix still requires all 11 captures.

The saved `diagnostics-report-qmk.patch` and `diagnostics-report-keymap.patch`
add temporary report counters and known A/J pulses. Apply them from the QMK
and personal-repository roots respectively, with the production SPI reset
fix already present. The diagnostic build flags and source hashes are in
`docs/mistel-md770-radio-diagnostic-build-reports.json`.
`check_diagnostic_pulses.py` checks the compiled pulse paths before flashing;
`check_hardware_pulses.py` captures actual USB/Bluetooth input and radio
counters. These commands require the diagnostic image, not the normal image.
The diagnostic updater-entry command was used to restore the normal image;
none of its commands or injection hooks remain in the installed firmware.
