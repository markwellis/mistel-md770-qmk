# Resume checkpoint: Bluetooth and ARM emulator

The requested checkpoint is saved as `779831a` here and `7f95caf037` in
`qmk_firmware`. The reviewed corrections are now in QMK `5919f04d30`.
This repository retains the matching personal macro player, regression tests,
stock probes, dependency patches and verification records.

The final software run passed both keymaps: 125 groups and 449 parameterised
subtests each. All four ordinary production targets built. Separate retained
links cover macro/input producers and both halves' clock/sleep paths. Native
radio, USB queues, flash, split-link, programming and host-tool checks passed.
The split comparison covers 7,546 stock observations; clock checks include
238 stock debounce samples per half and real kernel/IRQ execution.
Two Astra reviews at maximum effort found no remaining verified blocker in
the new source and tests. See
[the final record](mistel-md770-stock-conformance-fixes.json) for hashes,
reproduction, covered boundaries and explicit QMK macro policies.

No new firmware was flashed. Installed-image hashes are unchanged; measured
hardware calibration remains pending. RF delivery, reconnection, first-key
wake, electrical power behaviour, battery runtime and switch wiring remain
unverified. Passing these bounded comparisons does not establish full stock
or board equivalence.

Reproduce with `nix-shell --run 'bash tests/md770_bluetooth/run-software.sh'`.
New builds and records use `_conformance` names. The upstream dependency pin
is retained; the keymap setup lists all four portable ChibiOS patches.
The following sections record earlier checkpoints and installed images.

Stopped at the owner's request on 2026-11-15. No firmware was flashed and
no PRs were opened during that session. Continue from this checkpoint
rather than restarting the stock research or firmware implementation.

Resumed on 2026-11-16 with the repositories cloned as sibling checkouts.
The emulator now has a repeatable runner and CPU/register/firmware checks.
Independent review completed for the bounded component scope. Hardware
validation remains pending; battery-specific checks are deferred.

The later stock conformance audit found that the passing component checks
were insufficient to establish the required Bluetooth parity. Two Astra
reviews at maximum effort confirmed substantial radio, input, USB and power
gaps and two additional candidate regressions. That unflashed candidate has
been withdrawn; QMK source again matches the installed baseline plus the
SPI reset fix. The corrected installed-image audit still has 28 failing
cases in 87 groups and 419 subtests. Bluetooth remains unfinished. See the
[completed review](mistel-md770-bluetooth-implementation.md#stock-conformance-audit).
Do not treat the historical verification counts below as full stock parity.

The earlier left/right images were flashed on 2026-11-16. Their application sum/CRC,
QMK metadata and normal USB return passed; the initial right binary matched
the calibration plan. The owner reports performing a full settings reset after
joining the halves; the five white flashes were not explicitly confirmed.
Subsequent Bluetooth tests use a USB power bank, without an internal battery.
Installation evidence is in
`docs/mistel-md770-bluetooth-flash-right.json` and
`docs/mistel-md770-bluetooth-flash-left.json`. The guided hardware run remains
pending.

Hardware bring-up subsequently exposed a real SPI reset ordering defect.
Polling SPI0 reset completion before writing its configuration fixes the
observed CR1=0/slave-abort startup loop. Twelve fixed-image snapshots retain
CR1=0x108, reset_count=1 and a ready radio. Temporary diagnostic images are
separately identified by `docs/mistel-md770-radio-controls-flash-right.json`.
The right now runs the normal macro validation image with the reset fix and
no diagnostic code. Its flash sum/CRC, metadata and USB return passed; see
`docs/mistel-md770-validation-restored-flash-right.json` and
`docs/mistel-md770-validation-build.json`. It matches the current exported
calibration plan. Settings were retained.

The owner confirmed the steady blue light also appears on an identical stock
keyboard. Missing slot events came from pressing Pn+1 instead of Pn+F1.
The corrected physical shortcut produces pairing flashes; the compiled
handler, stored bindings and live control-key trace agree. The laptop has
paired and connected to Mistel1, including on power-bank power after slot
selection. The owner later typed `aj` with USB connected and reported no
connection changes; connected-radio diagnostics show Bluetooth selected and
advancing SPI traffic. Earlier empty input windows do not prove lost keys:
overlap with the physical actions was not established. Measured event
calibration remains pending. See
`docs/mistel-md770-bluetooth-hardware-bringup.json` for the linked evidence.

Later automatic diagnostic pulses passed through the Bluetooth sender,
real QMK routing and an unguarded queue comparison. Each produced exactly the
expected Bluetooth key events and raw reports, without USB key events. A
physical right J passed, as did physical Pn+1 selection from USB followed by
J. The earlier empty captures were not reproduced with the route and key
callback visible. The other stock keyboard was already off and unplugged.

The three pulse cases match the emulator's key-event predictions for the
matching diagnostic build; see
`docs/mistel-md770-diagnostic-pulse-agreement.json`. This is a measured
comparison of those report paths, not a completed macro/board calibration.
The normal validation image was subsequently restored, settings retained,
and all diagnostic source hooks removed. Power-bank typing from both halves now passes on the normal image, with no
Mistel USB device connected and no extra or held keys; see
`docs/mistel-md770-powerbank-typing.json`. Macro, media/Caps, automatic cold
reconnection and host-suspend scenarios remain pending.

The underside switch follow-up found no dedicated switch handler or
switch-triggered radio-off command in the stock Holtek application. Its
physical wiring remains unverified; no speculative switch behaviour was
added to the emulator. See the [stock trace](mistel-md770-stock-bluetooth-power.md#underside-switch-follow-up-2026-11-16).
A subsequent live QMK check connected to the radio and received a Bluetooth
ping reply with USB connected and the owner reporting switch OFF after Pn+1;
see `docs/mistel-md770-switch-usb-radio-check.json`. This proves the radio
remains powered in that condition; key delivery is a separate check.
During that run Bluetooth remained connected but physical keypresses failed
with both switch positions, including after slot 1 selection and reopening
the recreated Bluetooth input endpoint. Pn+2 restored a captured USB J
press/release. Treat Bluetooth as unfinished: the earlier diagnostic pulse
successes and single normal power-bank typing capture do not establish
reliable normal operation. The owner reports intermittent behaviour and
does not want more manual key tests while the software is investigated.

## Saved code

- `qmk_firmware`, branch `mistel-md770-support`: `3f9fb0f449061752370c3359d6a981d387fe5e7d` adds Bluetooth/charging; preceding `f066691b14` preserves Bluetooth reports on USB resume.
- `ChibiOS-Contrib`, branch `qmk-ht32-bftm-counter-width`: `a175f0d820dc125367073c30a1fb6029b419621d` widens HT32 BFTM's `gptcnt_t` to 32 bits. The owner opened [ChibiOS-Contrib #470](https://github.com/ChibiOS/ChibiOS-Contrib/pull/470) on 2026-11-16.
- This repository contains the personal keymap, native tests, stock traces,
  implementation evidence and bounded component emulator.

The existing QMK submodule pin is intentionally retained. Its working tree
has two local dependency fixes, both saved here as patches:
`patches/ht32f523xx-reset-register.patch` and
`patches/ht32f523xx-bftm-counter-width.patch`. They must be reapplied to a
fresh pinned dependency. The personal keymap README gives the setup.

## Verified state

The Bluetooth/power implementation received Astra maximum-effort software
review with no remaining P1/P2 findings. Both default and personal keymaps
build for both halves. The existing 29 driver/resume/RGB checks and 40
programming checks passed again at this checkpoint. Previous QMK protocol,
split, DIP, notification, USB and host-tool results are in
`docs/mistel-md770-bluetooth-implementation-checks.json`.

On 2026-11-16, all four firmware targets rebuilt after restoring the dependency
patches. The 29 native Bluetooth/resume/RGB checks, 40 programming checks,
eight stock packet checks and 39 stock trace groups passed again. Both right
keymaps passed all 83 emulator groups, with 376 parameterised subtests per
keymap, after the expanded independent review. The latest guided-calibration
extension exports actual emulator key/report predictions and reports hardware
function and emulator agreement separately. The 44 host-tool tests include
18 capture/scoring/guided-run checks. The model-only CLI also passed its earlier
34-check suite with nonexistent firmware paths; it now includes a binary
provenance regression as a 35th group.

The new emulator found a real dependency defect: the compiled idle path
wrote BFTM0 CMP=30464 instead of 96000 because the HAL interval type was
16-bit. The counter-width fix matches the chip's 32-bit counter/compare
registers. Rebuilt right default and personal images now write CMP=96000;
ABI extraction reports four-byte `gptcnt_t`. Both halves were rebuilt.

Hardware subsequently found the SPI reset race omitted by the immediate-reset
peripheral fixture. The new delayed-reset fault-injection regression fails
against the old compiled image and passes after the reset-completion poll.
This checks the fix without claiming a cycle-accurate reset model.
The production correction is saved as `patches/md770-spi-reset-wait.patch`.

Two additional validation groups execute the compiled power initialisation
and host task from an inactive driver state. They cover both saved host
selections, powered unconfigured USB, configured USB and explicit slot
selection, checking actual USB submissions or Bluetooth packets. Macro
fixtures still supply their initial active route; these new cases cover
the transition separately and do not model a complete hardware boot.

The first host capture also caught a test-double/API mismatch: evdev's
InputDevice lacks the context-manager methods supplied by the test double.
Discovery and listing now use contextlib.closing; the discovery test uses
the actual close-only contract. All 44 host checks pass after this correction.

Basic Bluetooth delivery now passes on power-bank power. Macro playback,
media/Caps, automatic cold reconnection, revised sleep/wake and battery
behaviour still require hardware validation. There is no internal cell;
stock deep sleep and battery runtime are not reproduced or established.

## Emulator progress

The component emulator has 35 model groups, 31 production-firmware groups and
17 macro/host groups. Both right keymaps pass. All 72 combinations of the declared
macro factors execute in software; 11 generated hardware cases cover all
57 factor-value pairs. Do not present this as a validated board emulator.

- `tests/md770_bluetooth/emulator.py`: Unicorn Cortex-M0 instruction
  execution, ELF loading, bounded SPI/GPIO/LVD/NVIC register model,
  instruction-boundary IRQ delivery, MSP/PSP exception frames, PRIMASK,
  priorities and EXC_RETURN. Unknown MMIO and unsupported operations fail.
- `emulator_abi.c` / `emulator_abi.py`: probe current headers and GCC with saved
  build flags, including USB states and HID report IDs. Matching ELF build
  inputs are an explicit assumption. Records include compiler, flags and
  preprocessed-probe hashes; the probe does not derive layouts from the ELF.
- `emulator_firmware.py`: explicit post-initialisation QMK and stock fixtures.
  The actual QMK radio task and vector handler run, as does stock US7.02
  under the same model. Report buffers use the ELF's unused heap region.
- `cpu_fixture.S` / `test_emulator.py`: independent exception frames, flags,
  aligned/misaligned stacks, MSP/PSP, priorities, deferred IRQs, register
  contracts and rejection cases. The tests caught pre-fix APSR, GPIO and
  NVIC defects.
- `test_emulator_firmware.py`: differential keyboard/consumer/system/host
  packets, startup reset edges, USB notices, pairing sequence/delay, 128
  seeded keyboard reports, collision retries and LVD/LED boundaries; QMK
  reconnect, backpressure, final-byte/error races, timer wrap, actual scan-IRQ
  pre-emption and idle-timer register checks. All 18 consumer usages compare
  QMK's mapping with explicit bitmaps and stock framing, without executing
  stock's usage-to-bitmap mapper.
- `emulator_macros.py` / `test_emulator_macros.py`: execute the compiled macro
  player, key registration, report routing and Bluetooth SPI path. Stored
  macro bytes and USB driver submissions are supplied boundaries. Cases cover
  all 20 slots after nonempty predecessors, ASCII, held modifiers, delay
  deadlines, cancellation, malformed data, backpressure, USB NKRO and boot
  protocol, Bluetooth six-key reports and all 72 calibration combinations.
  Separate validation images retain the public entry points through linker
  options; LTO differs from the separately tested production images.
- `emulator_scenarios.py`: explicit key-event oracles and measured pairwise
  coverage. The half factor supplies a compiled matrix coordinate. USB
  reconnect cases run the radio task and check both transition notices;
  electrical reconnection and enumeration are not simulated.
- `check_emulator.py`: repeatable runner with optional JSON evidence.
  `docs/mistel-md770-emulator-checks-default.json` and
  `docs/mistel-md770-emulator-checks-markwellis.json` record the runs.
- `run-software.sh`: builds both right-hand production/validation images,
  runs the complete software pass and generates
  `docs/mistel-md770-hardware-calibration.json` after success. The exported
  binary must match standard `objcopy` output from the tested ELF bytes.
- `scripts/md770_calibrate.py`: Linux host capture and strict ordered
  press/release comparison. Initial held keys and lost input events reject
  capture. Summaries re-score events and count only live results matching
  the plan, device transport and reference binary. Timing and auto-repeat
  are not scored; flashed-image identity and case preconditions are operator
  responsibilities. `--quick` guides five scenarios, captures three selected
  cases and records separate `bluetooth_functional` and `emulator_agreement`
  outcomes. Functional key checks use independent oracles; model agreement
  compares actual exported emulator predictions. Manual observations do not
  calibrate the model. There are no live results yet.

GPIO input reads now honour INER, pull-up priority and open-drain outputs.
Unresolved floating inputs and conflicting external drives fail. NVIC
priority registers implement the Cortex-M0+'s two priority bits and word
accesses. Exception entry preserves APSR flags. `Qmk.usb()` updates both
USB state machines; actual remote-wake signalling fails explicitly.

Time, RTOS sleep/scheduling, persistent writes and empty UART input are
supplied boundaries. This is component execution, not MCU boot, a Bluetooth
stack, an analogue charger model or cycle-accurate hardware timing. FIFO
occupancies approaching the separate shift-register boundary are rejected;
error flags are injected inputs, not validated overflow timing.
Timer register configuration and manually supplied scan interrupts are
covered; timer/PWM waveforms are not simulated. Free-running counter reads
fail. LVD voltage thresholds are nominal
digital inputs without analogue tolerance, hysteresis or settling time.
The stock elapsed-time/LED fixture also supplies its periodic split-send
boundary: the guarded descriptor call returns the actual busy/unavailable
result. Its timer and LED instructions still execute.

## Independent review

A separate agent reviewed the implementation and tests on 2026-11-16 using
inherited model settings. It independently ran both 80-group suites and the
10 capture-tool tests, including the negative reproductions. No material
findings remain within the recorded component scope.

The guided-calibration extension received a further independent review. Its
18 host groups and all 72 macro combinations per keymap passed. The reviewer
reconstructed the key events from the retained reports and checked all 11
exports against the actual emulator output, independent oracles and source
hashes. An unexpected predicted usage now produces an agreement failure
without discarding a correct functional result. No live devices were opened
and no firmware was flashed during these software checks.

The initial review closed four P2 findings and one P3 finding:

- The final-byte/error test now injects at the BUSY read after the first
  clean error check. Removing the second error read makes the corrected
  test fail; the original test missed that mutation.
- GPIO output observations now require push-pull direction and a supported
  GPIO mux. Opposing external drives fail even when INER is disabled.
- LVD interrupt/event/brown-out enables and unsupported BFTM controls fail.
  Scan interrupt injection requires an enabled clock and repetitive mode.
- Exception return rejects stacked Thumb or exception-mode corruption.
- ABI probing requires an actual ARM ELF and records the compiler, saved
  flags hash and preprocessed-probe hash. Matching ELF build inputs remain
  an explicit assumption.

The expansion review closed four further P2 findings:

- USB reconnection originally changed supplied state twice without executing
  firmware between. The test now executes the task at each transition and
  checks its state and outgoing notice before macro playback.
- The capture scorer originally ignored `SYN_DROPPED`. Live capture now
  rejects input loss, and saved traces containing it cannot pass scoring or
  complete the hardware summary.
- Capture now rejects keys already held when the device is grabbed, so
  unobserved modifiers cannot produce a false match.
- Plan export originally trusted the adjacent binary's hash. It now compares
  that binary with `objcopy` output from the actual tested ELF bytes. The
  reviewer's unrelated-binary reproduction now rejects export.

The review covers the recorded packet/recovery scenarios and tested CPU,
SPI/GPIO/LVD contracts. Timer/PWM results are configuration observations.
It does not establish physical Bluetooth delivery, USB signalling, timer
waveforms, FIFO/shift-register timing or analogue power behaviour.

## Next work

1. Follow the recommended five scenarios in
   `docs/mistel-md770-hardware-calibration.md`: three recordings, captured
   cases HC01/HC08/HC11, one connection/media/LED sequence and one host
   sleep/output-handover sequence. Reuse the recorded wired/personal
   baseline rather than repeating keys, DIP, profiles, editor and split
   recovery. Prior results are not candidate hardware passes.
   The guided `--quick` run includes USB-selected key wake first and
   Bluetooth-selected host sleep/output handover last. Its two results have
   separate acceptance criteria; a matching key trace does not calibrate
   CPU/IRQ, internal radio, register, timing or analogue contracts.
2. The full 11-case pairwise matrix is optional. It covers all 57 factor
   pairs; the recommended smoke pass does not. Both routes use external
   power and do not require a battery.
3. Defer physical charging, battery wake/current and runtime checks until a
   battery is available. The owner has no battery; this does not block the
   software review or externally powered Bluetooth checks.

The latest corrections already present include CONTROL.SPSEL handling on
exception entry/return, rejection of unaligned ARMv6-M accesses, stock stack
placement from its vector, GPIO SRR reset bits, the 3.30 V LVD selection and
rejection of recursive firmware calls from callbacks.

The relevant primary references are the
[Holtek manual](https://www.holtek.com/webapi/187531/HT32F52342_52_UserManual_v160.pdf)
(BFTM pp296–301, SPI pp459–470, GPIO pp124–137, LVD pp78–79) and
[Arm DUI0662B](https://documentation-service.arm.com/static/5f04abc8dbdee951c1cdc9f7)
(exception entry/return pp2-20–2-21). Unicorn's
[FAQ](https://github.com/unicorn-engine/unicorn/blob/master/docs/FAQ.md)
describes its exception-return interrupt8 convention.

## Reproduce the existing timer observation

Dependencies: Python with `unicorn`, `pyelftools`, `capstone`, plus
`gcc-arm-embedded`; `shell.nix` supplies them. Rebuild the ELF files in the
sibling QMK checkout's `.build/` after applying both dependency patches.
Binaries remain outside Git under the artefact policy.

The complete repeatable runner includes the timer observation and macro
calibration predictions:

```fish
nix-shell --run 'bash tests/md770_bluetooth/run-software.sh'
```

To rerun only the production component checks against existing builds:

```fish
nix-shell --run 'python3 -B tests/md770_bluetooth/check_emulator.py'
```

Run this Python from this repository's root with those dependencies:

```python
from pathlib import Path
import sys
sys.path.insert(0, "tests/md770_bluetooth")
from emulator_abi import layout
from emulator_firmware import Qmk
qmk = Path("../qmk_firmware").resolve()
elf = qmk / ".build/mistel_md770rgb_bt_right_markwellis.elf"
abi = layout(qmk, elf)
machine = Qmk(elf.read_bytes(), abi)
machine.start()
machine.matrix()
machine.ms += 600001
machine.matrix()
assert abi["gpt_counter_bytes"] == 4
assert machine.hardware.registers[0x4007600C] == 96000
```

The stock fixture requires the already-extracted US7.02 image identified in
`docs/mistel-md770-stock-bluetooth-power.md`; its hash is enforced. The
existing `stock_probe.py` / `stock_trace.py` checks remain separate from
the bounded component emulator.
