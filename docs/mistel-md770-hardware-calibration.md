# MD770 emulator calibration on hardware

The recommended pass is five short scenarios, with three macro recordings
for setup. The earlier 20-case count repeated checks already recorded on
hardware. The [wired results](mistel-md770-final-hardware-tests.json) and
[personal results](mistel-md770-personal-hardware-tests.json) cover ordinary
keys, cross-half modifiers, DIP switches, profiles, editor/storage, macro
modifiers/delays/cancellation and split recovery. Those results belong to
the earlier wired build; the short pass below checks the new transport and
changed wake path on the candidate.

## Recommended five scenarios

| Scenario | Action | Pass condition |
| --- | --- | --- |
| 1. USB sleep/wake baseline | Select USB, suspend the host and wake it with a keyboard key; capture HC01 by tapping the left Q text macro | Keyboard wake works and automatic key-event comparison passes |
| 2. Bluetooth connection | Pair/select one slot, type a few keys, try one media key and toggle Caps Lock on/off | Bluetooth delivers the keys; media press/release and blue connection/red Caps indications work |
| 3. Bluetooth macro/modifiers | Capture HC08: hold Left Shift, tap the right I chord macro, release Shift after playback | Automatic key-event comparison passes, including all modifier releases |
| 4. Bluetooth reconnection | Disconnect/reconnect Bluetooth, then capture HC11: hold Left Ctrl, tap the left E delay macro, release Ctrl after playback | Automatic key-event comparison passes after reconnection |
| 5. Host sleep and output handover | With USB connected and Bluetooth selected, suspend/resume the host, type over Bluetooth, switch to USB and type, then switch back | Both outputs recover and no keys remain held |

HC01, HC08 and HC11 are existing software-verified cases in the generated
[plan](mistel-md770-hardware-calibration.json). The reduced set samples each
declared factor value but does not cover every factor pair. Passing it is a
practical smoke check using the earlier hardware baseline, not completion of
the optional full calibration matrix. No live macro-calibration cases have
been recorded yet. Basic power-bank typing and three diagnostic pulse paths
have passed separately; see the
[pulse agreement record](mistel-md770-diagnostic-pulse-agreement.json).
These scenarios do not need a battery.

The owner authorised both-half flashing and a full settings reset on
2026-11-16. Both the original right validation image and
[left personal image](mistel-md770-bluetooth-flash-left.json) were flashed,
checksummed and returned to QMK. The owner reports performing the full settings
reset on the joined keyboard; a blue right-hand indicator was observed
afterwards, without explicit confirmation of the five white reset flashes.
The Bluetooth test supply is a USB power bank, not an internal cell.
This establishes installation, not either hardware test outcome.

Hardware bring-up then found an SPI reset race. The corrected normal
[right validation image](mistel-md770-validation-restored-flash-right.json) is now
flashed and checksum-verified, with settings retained. Both halves passed
[live Bluetooth typing on a power bank](mistel-md770-powerbank-typing.json).
The binary matches
the current plan generated after 83 emulator groups and 376 parameterised
subtests per keymap. The temporary diagnostic image has been removed.
Connection in this run followed a long Pn+F1 pairing request; automatic cold
reconnection remains unverified.

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
| `keyboards/mistel/md770rgb_bt/power.c` | USB running/sleeping/wake-requested transitions, supply history, low-voltage filtering and idle | Scenarios 1 and 5 check the two wake/output paths; battery behaviour is deferred |
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
`qmk_firmware/.build/mistel_md770rgb_bt_right_markwellis_validation.bin`.
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
python3 scripts/md770_calibrate.py --quick --out docs/hardware-calibration/quick.json
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
python3 scripts/md770_calibrate.py --show-plan
python3 scripts/md770_calibrate.py --list
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
python3 scripts/md770_calibrate.py --case HC01 --device /dev/input/eventX --out docs/hardware-calibration/HC01.json
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
python3 scripts/md770_calibrate.py --results docs/hardware-calibration
```

This summary measures the full 11-case matrix. After the recommended short
pass, it will still list the eight optional cases as remaining. Keep that
distinction when recording the result.

Charging, cell voltage thresholds, battery wake, current and runtime remain
deferred because no battery is available.
