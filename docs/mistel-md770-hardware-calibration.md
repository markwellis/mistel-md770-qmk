# MD770 emulator calibration on hardware

## Current short differential pass

The QMK scope simplification is complete. On 2026-11-17, two short physical
sequences passed on the installed `markwellis` production image: Bluetooth
on a power bank with no host USB connection, followed by USB to the laptop.
Each capture matched all 24 independently expected and emulated press/release
events. See the [summary](hardware-calibration/simplified-input-summary.json),
[Bluetooth capture](hardware-calibration/simplified-input-bt.json) and
[USB capture](hardware-calibration/simplified-input-usb.json).

The sequence uses A/J, both cross-half Shift combinations, each space bar
and four quick J taps. It needs no macro recordings or diagnostic firmware.
An initial capture with operator-reported accidental input was excluded;
the clean Bluetooth repeat and USB capture passed strict ordered comparison.
Manual Bluetooth reconnection was needed after flashing; this is recorded
separately from the connected-input test.

Predictions execute `action_exec()` and report/radio code from the exact
installed production ELF. The fixture supplies decoded scan events, the
compiled base keymap, RTOS boundaries and radio transactions. The live
comparison measures ordered Linux key press/release events, not raw-report
bytes or timing. It provides hardware evidence for these input/report paths;
it does not establish every emulator contract. The additional macro timing
and USB wake checks are described below. KVMs, interrupts and battery
behaviour remain outside these hardware comparisons.

Generate the fixed predictions before capturing:

```fish
nix-shell --run 'python3 -B tests/md770_bluetooth/predict_physical_input.py --elf ../qmk_firmware/.build/mistel_md770rgb_bt_right_markwellis_conformance.elf --out docs/hardware-calibration/simplified-input-plan.json'
```

Use `scripts/md770_calibrate.py` with that plan, the matching production
binary, case `DP-BT` or `DP-USB`, and the appropriate event devices. Grab all
relevant keyboard interfaces for the chosen transport. The installed image
hash is checked, and the plan hash binds each capture to its predictions.

## Macro timing and USB device wake

The current installation uses one temporary F3 recording: Left Shift+A,
release Shift, then B/C/D with the Fn+T, Fn+G and Fn+B delays. The fixed
[prediction plan](hardware-calibration/macro-wake-plan.json) was generated
before capture. Its ten key/modifier events span 935 ms. Timing limits were
also fixed before capture: USB permits 2% duration error and 10 ms per-event
error; Bluetooth permits 5% and 45 ms.

The macro player is inlined in the installed production ELF. These
predictions therefore execute the paired verification ELF, which retains
the macro entry points and uses the same verified keyboard sources.
The plan records both image hashes. The keyboard keeps its production
firmware; no calibration firmware is flashed.

The first [USB macro capture](hardware-calibration/macro-usb.json) matched
all ten events. Its duration was 933.987 ms, and its largest relative
event-time error was 1.013 ms.

The [post-wake observation](hardware-calibration/macro-usb-after-wake.json)
also matched all ten macro events: 934.971 ms total, with at most 1.030 ms
relative event-time error. Its full capture failed strict comparison
because capture started before the chat prompt and included earlier
typing. The record explicitly identifies the final macro burst, separated
from that input by 26.101 seconds. This supports normal post-wake playback;
it is not counted as a strict full-window calibration pass.

The [Bluetooth macro capture](hardware-calibration/macro-bt.json) matched
all ten events and the declared timing limits. Its duration was 940.042 ms,
with at most 6.000 ms relative event-time error. USB powered the keyboard
from a power bank, with no host USB connection.

Bluetooth reconnection remains unresolved. Host connection attempts failed
after startup and a short Pn+F1 slot selection. Holding Pn+F1 for three
seconds opened the pairing window and allowed the existing paired host to
connect. No bond was removed. The owner suspects stock reconnected
successfully; this has not been verified. The connected playback pass does
not establish correct cold reconnection.

The [USB device wake check](hardware-calibration/usb-wake-visual.json)
passed without suspending the laptop. The owner saw the controlled red
notification, confirmed both halves went dark during USB runtime suspend,
and tapped A to wake the keyboard. Linux recorded suspend, resume and A's
press/release, with the same USB enumeration. The notification Raw HID
interface was temporarily unbound to prevent host alerts from waking USB
before the key press. The script restored that interface and all original
USB power settings.

The earlier wake attempts remain excluded: the
[first attempt](hardware-calibration/usb-wake-inconclusive.json) lacked a
captured wake key and visual sleep confirmation; an
[incomplete attempt](hardware-calibration/usb-wake-isolated-incomplete.json)
missed the input window; a subsequent
[host-only result](hardware-calibration/usb-wake-isolated.json) lacked visual
confirmation. None counts as a complete wake pass.

The owner restored ordinary F3 through the onboard editor after capture.
The [combined record](hardware-calibration/macro-wake-summary.json) binds
these results to the fixed prediction plan and installed production image.
All 21 host-scorer checks pass, including rejection of the wrong clock scale
and of wrong intermediate gaps with the correct total duration.

## Historical broader macro calibration

The procedure below describes the earlier candidate and its separate
validation image. Its shared-QMK changes were subsequently removed. It is
retained as historical context, not as the current installation procedure.

The older pass uses five short scenarios, with three macro recordings
for setup. The earlier 20-case count repeated checks already recorded on
hardware. The [wired results](mistel-md770-final-hardware-tests.json) and
[personal results](mistel-md770-personal-hardware-tests.json) cover ordinary
keys, cross-half modifiers, DIP switches, profiles, editor/storage, macro
modifiers/delays/cancellation and split recovery. Those results belong to
the earlier wired build; the short pass below checks the new transport and
changed wake path on the candidate.

## Five macro scenarios

| Scenario | Action | Pass condition |
| --- | --- | --- |
| 1. USB sleep/wake baseline | Select USB, suspend the host and wake it with a keyboard key; capture HC01 by tapping the left Q text macro | Keyboard wake works and automatic key-event comparison passes |
| 2. Bluetooth connection | Pair/select one slot, type a few keys, try one media key and toggle Caps Lock on/off | Bluetooth delivers the keys; media press/release and blue connection/red Caps indications work |
| 3. Bluetooth macro/modifiers | Capture HC08: hold Left Shift, tap the right I chord macro, release Shift after playback | Automatic key-event comparison passes, including all modifier releases |
| 4. Bluetooth reconnection | Disconnect/reconnect Bluetooth, then capture HC11: hold Left Ctrl, tap the left E delay macro, release Ctrl after playback | Automatic key-event comparison passes after reconnection |
| 5. Host sleep and output handover | With USB connected and Bluetooth selected, suspend/resume the host, type over Bluetooth, switch to USB and type, then switch back | Both outputs recover and no keys remain held |

HC01, HC08 and HC11 are existing software-verified cases in the generated
[plan](mistel-md770-conformance-hardware-calibration.json). The reduced set samples each
declared factor value but does not cover every factor pair. Passing it is a
practical smoke check using the earlier hardware baseline, not completion of
the optional full calibration matrix. No live macro-calibration cases have
been recorded yet. Basic power-bank typing and three diagnostic pulse paths
have passed separately; see the
[pulse agreement record](mistel-md770-diagnostic-pulse-agreement.json).
These scenarios do not need a battery.

Both reviewed images were flashed and checksum-verified on 2026-11-16:
the [right validation image](mistel-md770-conformance-flash-right.json) and
[left personal image](mistel-md770-conformance-flash-left.json).
Right-side settings were retained. The right binary matches the current
plan generated after 125 emulator groups and 449 parameterised subtests
per keymap.

Physical left A then right J each produced exactly one press/release over
[USB](hardware-calibration/conformance-usb-split.json) and
[Bluetooth](hardware-calibration/conformance-bluetooth-split.json), with no
extra events. Bluetooth used the existing slot-1 pairing while laptop USB
supplied power. These are functional baselines, without an emulator
prediction comparison. Testing stopped at the owner's request; the three
macro recordings have not been confirmed. Reconnection, media/indicators,
power-bank delivery and host sleep/wake remain for this candidate.

The five scenarios include two host sleep/wake cycles: one with USB selected,
then one with Bluetooth selected while USB remains connected. They exercise
different paths in the revised firmware.

## Two separate results

The guided run records two outcomes in one report:

- `bluetooth_functional`: the Bluetooth captures match independent expected
  key events, and the operator confirms USB key wake, pairing/media/LEDs and
  sleep/output handover. These observations concern the candidate's function.
- `emulator_agreement`: all three live captures match the actual emulator
  predictions exported for the tested validation image, including key order,
  modifiers and final releases. Predictions are also checked against
  independent expected events. Operator observations do not establish this
  result, and a mismatching emulator prediction can fail separately.

The plan retains the emulator's normalised keyboard reports and key events,
plus the tested firmware hash. The host result retains the live input events
and matching plan/reference hashes. This supplies a reproducible comparison
between a prediction and hardware observation, rather than only a judgement
that Bluetooth typed something.

Agreement covers the named host-event paths. It does not directly calibrate
CPU exception rules, IRQ timing, peripheral registers, internal radio states,
USB signalling or analogue power behaviour. Timestamps are retained, but
timing and auto-repeat are not scored. Those boundaries stay explicitly
uncalibrated; future software tests can reuse the demonstrated paths without
claiming that the whole board model is correct.

## Changed stateful behaviour

| Area in `qmk_firmware` | Change since the wired baseline | Hardware check |
| --- | --- | --- |
| `keyboards/mistel/md770rgb_bt/bluetooth.c` | Reset/startup, transfer/retry/recovery, reconnect resynchronisation and pairing delay | Scenarios 2–4 check successful connection, reports and reconnection; deliberate FIFO faults/timeouts remain software checks |
| `keyboards/mistel/md770rgb_bt/power.c` | USB stop/resume, supply history, low-voltage filtering and idle | Scenarios 1 and 5 check the two wake/output paths; battery behaviour is deferred |
| `platforms/chibios/suspend.c` | Preserve Bluetooth-held reports during an unrelated USB resume | Scenario 5 checks post-resume Bluetooth delivery and output handover; held-during-resume details retain software coverage |
| `keyboards/mistel/md770rgb_bt/scan.c`, `rgb.c` | Idle scan cadence and RGB sleep/wake gating/priming | Wake paths are sampled; battery idle and electrical waveforms remain unmeasured |
| `keyboards/mistel/md770rgb_bt/indicators.c` | Bluetooth, Caps, charging and warning indications | Scenario 2 samples Bluetooth/Caps; charging/low-battery observations are deferred |
| `keyboards/mistel/md770rgb_bt/keymaps/default/programming.c` | Playback yields when the Bluetooth queue lacks space | Scenarios 3–4 check Bluetooth playback; queue saturation is tested in software |

The personal keymap has the matching playback change. Recording/editing
states otherwise retain their earlier hardware baseline. Passing the short
run does not mean every internal state transition has been observed.

## Prepare the software

Run from this repository with the sibling QMK checkout and dependency fixes
described in the [keymap setup](../keyboards/mistel/md770rgb_bt/keymaps/markwellis/readme.md#pending-upstream-changes):

```fish
nix-shell --run 'bash tests/md770_bluetooth/run-software.sh'
```

This builds both right-hand production images and separate validation images,
runs the component and macro suites, and writes their verification records.
The validation build retains the public macro entry points through linker
options; it uses the existing macro implementation. Retention changes LTO,
so the production and validation images are recorded separately. The plan
is exported only after the tests pass. Its binary must match `objcopy`
output from the exact tested ELF bytes.

For hardware calibration, install the plan's right-hand validation image:
`qmk_firmware/.build/mistel_md770rgb_bt_right_markwellis_conformance_validation.bin`.
Use the existing [USB installation procedure](usb-flashing.md). Keep the
matching left-hand personal build. The capture command verifies the local
reference binary's hash; confirming which image is actually flashed remains
an operator step.

## Record three patterns

Use QWERTY, DIP switches off, and a profile whose three destination assignments
you can replace. Select the desired profile and layout before recording.
Record these bindings using the [onboard editor](onboard-programming.md):

| Macro | Destination | Recording |
| --- | --- | --- |
| Text | Left Q | Tap A, B, C |
| Chord | Right I | Hold Left Ctrl, tap A, release Left Ctrl |
| Delay | Left E | Tap A, tap Fn+G once, tap B |

Enter the editor with Fn+Right Ctrl, tap the destination, record the pattern,
then press Pn to save and release all keys. Repeat for the other destinations;
Fn+Right Ctrl exits. The recorder supplies 40 ms intervals; Fn+G inserts
100 ms before B. These three recordings also check the real editor and
storage path, which the playback fixture supplies as stored bytes.

## Run the guided super test

After preparing the image and three recordings, start one command from the
Nix environment:

```fish
nix-shell --command fish
set md770_plan docs/mistel-md770-conformance-hardware-calibration.json
set md770_firmware ../qmk_firmware/.build/mistel_md770rgb_bt_right_markwellis_conformance_validation.bin
python3 scripts/md770_calibrate.py --plan $md770_plan --firmware $md770_firmware --quick --timeout 300 --out docs/hardware-calibration/quick.json
```

If input access requires root, use
`sudo -A env PYTHONPATH="$PYTHONPATH" (command -s python3)` in place of
`python3` inside that shell. The run finds the Mistel keyboard interfaces
for each transport, prompts for the five scenarios, and captures HC01,
HC08 and HC11. It waits one second after each preparation prompt before
checking that all keys are released. Caps and the media action happen outside
the grab so the host receives them; the controlled macro captures are grabbed.
For guidance through chat, add `--timeout 300` to allow for message delay.
Results record when capture started and finished. An empty window without
an overlapping physical action does not establish a firmware failure.

Answer the two observation prompts from what happened. A failed observation
or hardware key sequence stops the run and saves the partial result. The
report gives separate Bluetooth-functional and emulator-agreement outcomes,
with the raw captures saved alongside it. A mismatch with an emulator
prediction does not turn a correct independently expected Bluetooth sequence
into a functional failure; the emulator result fails separately.

## Capture individual cases instead

Run only HC01, HC08 and HC11 for the recommended pass. The listing command
also shows the other eight optional cases.

Enter the Nix environment and print the cases and available input devices:

```fish
nix-shell --command fish
set md770_plan docs/mistel-md770-conformance-hardware-calibration.json
set md770_firmware ../qmk_firmware/.build/mistel_md770rgb_bt_right_markwellis_conformance_validation.bin
python3 scripts/md770_calibrate.py --plan $md770_plan --firmware $md770_firmware --show-plan
python3 scripts/md770_calibrate.py --plan $md770_plan --firmware $md770_firmware --list
```

The plan is grouped by transport and connection state. Select output with
Pn+2 for USB or Pn+1 for Bluetooth. Bluetooth can use external USB power;
these checks do not need a battery. Pair the selected Bluetooth slot once
if necessary.

For a `reconnected` case, disconnect and reconnect that transport before
capture, then wait for the host input device to return. For `steady`, keep
the established connection. Recheck the event path after reconnection.

Run each case with its Mistel input device, replacing the example path:

```fish
python3 scripts/md770_calibrate.py --plan $md770_plan --firmware $md770_firmware --case HC01 --device /dev/input/eventX --out docs/hardware-calibration/HC01.json
```

If input access requires root, run the same command with
`sudo -A env PYTHONPATH="$PYTHONPATH" (command -s python3)` in place of
`python3` inside this Nix shell.
The tool requires a Mistel/MD770 name and the case's USB or Bluetooth bus.
Repeat `--device` only if that keyboard uses multiple relevant interfaces.

Start with all keys released. After `Capture ready`, hold the case's Left
Shift or Left Ctrl if requested, tap its trigger key, wait for playback to
finish, then release the modifier. A `none` case needs only the trigger.
The tool grabs the selected input device while capturing, so these events
are withheld from desktop shortcuts. It stops after a matching released
sequence and 250 ms of quiet, or after 20 seconds. A failed case can be
repeated with the same output path.

Already-held keys, input loss (`SYN_DROPPED`) and device removal invalidate
the live capture. Wrong, missing, additional or reordered key events fail
comparison. Each capture prints `passed: true` and exits successfully only
when its sequence matches. Retain all three result files and record the
observations for scenarios 2 and 5 against the same candidate.

Transport selection, reconnection and use of the named physical trigger are
operator preconditions. In software, the half factor supplies the matching
matrix coordinate; a live left-trigger case additionally exercises the
physical split link. USB enumeration, the radio module and host delivery
are hardware boundaries.

## Optional full pairwise calibration

The software suite runs all 72 combinations of transport, trigger half, macro
kind, held modifier and connection state. The full generated plan selects
11 cases covering all 57 factor-value pairs. This is pairwise coverage of
these five factors, not proof of every interaction or of complete hardware
equivalence. [NIST SP 800-142](https://nvlpubs.nist.gov/nistpubs/legacy/sp/nistspecialpublication800-142.pdf)
describes this use of combinatorial testing.

To perform the full matrix later, also record text on right U, chord on left
W and delay on right O, then capture the remaining eight cases. The summary
rechecks saved events and accepts only live results for the same plan and
reference binary; replayed files cannot complete it:

```fish
python3 scripts/md770_calibrate.py --plan $md770_plan --firmware $md770_firmware --results docs/hardware-calibration
```

This summary measures the full 11-case matrix. After the recommended short
pass, it will still list the eight optional cases as remaining. Keep that
distinction when recording the result.

Charging, cell voltage thresholds, battery wake, current and runtime remain
deferred because no battery is available.
