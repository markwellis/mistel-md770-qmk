# MD770 Bluetooth and charging implementation

The current personal build uses the shared `default_mistel` keymap with
`USER_NAME=markwellis`, adding notification code from this repository. Both
halves are installed and verified; the owner confirmed joined typing.
Current setup is in [personal userspace](../users/markwellis/readme.md),
with the implementation boundary and software results in
[upstream readiness](qmk-upstream-readiness.md). No shared QMK changes are
required beyond the two separately submitted Contrib fixes.

See [hardware calibration](mistel-md770-hardware-calibration.md) for measured
macro timing, USB wake and reconnect results, each tied to its recorded image.

## Historical implementation and audits

The remaining development account describes earlier builds. Its unresolved
defects and shared-core changes are historical; the current review above
records their corrections or removal. The reproduction commands use the
current shared-keymap setup.

The implementation is in `qmk_firmware`, branch `mistel-md770-support`.
The personal notification userspace remains in this repository and builds
the shared `default_mistel` keymap. The following hardware account is
historical. Both halves were flashed on
2026-11-16. The right now runs the normal macro validation image with the
SPI reset fix and no diagnostic commands; settings were retained. Application
sum/CRC, QMK metadata and normal USB return passed. See the
[latest right flash](mistel-md770-validation-restored-flash-right.json),
[left flash](mistel-md770-bluetooth-flash-left.json) and
[normal build](mistel-md770-validation-build.json). The right binary matches
the current calibration plan. Both halves passed live Bluetooth typing on a
USB power bank, with no Mistel USB device connected, no extra keys and no keys
held afterwards; see `docs/mistel-md770-powerbank-typing.json`. There is no
internal cell. Macro, reconnection and suspend calibration remain pending.

Reliable normal Bluetooth operation is not established. In the later
[switch check](mistel-md770-switch-usb-radio-check.json), the radio connected
and answered a ping with the switch OFF under USB power, but physical keys
failed over Bluetooth with both OFF and ON. Slot selection and reopening
the recreated input endpoint did not restore delivery. Pn+2 restored a
captured USB J press/release. The owner reports intermittent behaviour;
Bluetooth remains unfinished despite the earlier individual successes.

The first hardware check exposed an SPI reset ordering defect: programming
CR1 before reset completed left CR1=0 and caused slave-abort errors. Polling
reset completion restores CR1=0x108 and stable startup on hardware. A
delayed-reset fault-injection regression fails against the old ARM image and
passes against the correction in `patches/md770-spi-reset-wait.patch`.
The owner confirmed the steady blue indicator also appears on an identical
stock keyboard. Missing pairing flashes were traced to using Pn+1 (Bluetooth
output) instead of Pn+F1 (slot1); the corrected shortcut starts pairing.

Three automatic diagnostic pulse paths passed on hardware: the Bluetooth
sender, real QMK report routing and a queue comparison without the connection
guard. Each produced the expected Bluetooth key press/release events and raw
HID reports, with no USB key events. A physical right J also passed, followed
by a traced physical Pn+1 selection that changed USB output to Bluetooth and
delivered J. The earlier no-input result was not reproduced with route and
key processing visible. No further report-path correction was made. Evidence
is linked from `docs/mistel-md770-bluetooth-hardware-bringup.json`.

The three pulse recordings match the emulator's predicted key-event order;
see `docs/mistel-md770-diagnostic-pulse-agreement.json`. This comparison is for
those paths on the identified diagnostic image. Macro recording/playback,
full boot, timing, USB signalling and analogue power remain outside that
measured agreement. The normal validation image is now restored.

Host capture discovery needed explicit device closing because the installed
evdev API lacks a context manager. All 44 host checks pass after correction.
Diagnostic reply matching also now tolerates unrelated Raw HID messages.
The earlier empty captures are retained with their scope and timing; they do
not supersede the later successful traced checks.

## Stock conformance audit

The requirement is all stock Bluetooth functionality. The earlier passing
component checks did not establish that. Two independent `gpt-6-astra`
reviews at maximum reasoning effort concluded that neither the installed
firmware nor the unflashed candidate has stock parity. The
[full review](mistel-md770-astra-stock-parity-review.json) records findings,
stock addresses, correction boundaries and unproved scope.

| Area | Verified differences |
| --- | --- |
| Reports and status | Rejected reports outside public state 4, lost queued releases and synthetic release/press sequences when status changes |
| Recovery and controls | Full resets for recoverable frames/errors, lost pairing intent after timeout and a pairing request emitted during shutdown |
| Playback and backpressure | Macros consumed while reports are discarded; a full queue blocks USB handover for 2000 supplied milliseconds |
| Input state | Held modifiers lost across output changes and USB wake; overlapping consumer/system keys lose held bits |
| Shortcuts | Pairing ignores the current chord; short selection does not wait for all keys to be released |
| USB and power handover | Starved USB notices, missing persistence/cancellation, and retained configuration used as active USB state |
| Idle and voltage | Missing radio-activity refresh, different pairing-expiry/PA10 policy, and a foreground filter that misses interrupted low voltage |
| Indicators | Feedback depends on SPI progress; priority, phase retention and charging-burst start differ |

The candidate introduced two additional regressions: clearing pairing's retry
budget and clearing the displayed Caps cache. After a short selection, its
retry limit combined with the existing SPI-error reset produced permanent
failure from one recoverable error. It was never flashed and has been
withdrawn. Its [frozen patch](../tests/md770_bluetooth/review/frozen_candidate.patch)
and [image manifest](mistel-md770-stock-parity-candidate-build.json) are
retained only for reproducing that review.

The working QMK source was restored to the installed baseline, verified by
its source hash. The existing SPI reset-completion wait and ChibiOS fixes
remain. This withdrawal is not a parity fix. The installed images and their
calibration plan are unchanged; Bluetooth remains unfinished.

The [reviewed installed-image audit](mistel-md770-installed-stock-conformance-reviewed.json)
ran 87 groups and 419 parameterised checks and reported 28 failing cases
after correcting the false LED oracle. Those are repeated cases, not 28
distinct defects. The initial 34-failure record included the six invalid
LED-field comparisons and is historical. Some older tests still assert
QMK behaviour without a stock oracle; the independent review identifies
those gaps rather than treating the remaining passing cases as full coverage.

Two diagnoses were withdrawn. Stock seeds its hold counter at one, making
the existing 3000 ms elapsed pairing threshold correct. Stock also retains
its displayed Caps cache when selection clears a different public LED byte;
retaining that visible state in the original implementation was correct.

The [evidence index](mistel-md770-astra-review-evidence.json) identifies the
retained radio, power and USB replay sources and observations. The replays
reproduce the reviewed discrepancies; their successful execution does not
mean conformance. The reviews do not establish the cause of the last missing
physical J, full boot or deep-sleep restoration, RF behaviour, electrical
USB/SPI timing or battery performance. No further firmware was flashed and
no additional manual key tests were requested during the review.

## Historical design

The right half retains the resident Bluetooth module. The MCU sends stock
A1 keyboard, A2 consumer and A3 system reports over SPI0 slave FIFO transfers.
USB retains NKRO; Bluetooth uses six-key rollover. The transport starts and
recovers asynchronously, so an absent or disabled radio does not block USB
initialisation. It uses a bounded report queue and pumps the transport under
backpressure. The status-change paths currently discard queued reports and
send zero reports before replaying the current state; Astra has reproduced
lost releases and synthetic key transitions from those decisions. Incoming
messages are currently treated as collisions based on any nonzero prefix;
stock treats some invalid fields as non-collisions. These paths need correction.

| Control | Action |
| --- | --- |
| Pn+1 | Select Bluetooth output |
| Pn+2 | Select USB output |
| Pn+F1/F2/F3, released before three seconds | Select Bluetooth slot 1/2/3 |
| Pn+F1/F2/F3, held for three seconds | Select the slot, then request pairing after 150 ms |

Slot changes release the previous host. Output selection uses QMK's existing
connection settings. Bond storage remains inside the radio module. This
implementation does not invent a bond-erasure command.

Charging eligibility follows the traced supply/USB transition history,
including the PA10 transition gate. PC13 selects steady blue or the stock
three-flash charging burst. The MCU's seven LVD thresholds and continuous
25 ms low-voltage filter control the battery warning. Low battery suppresses
Caps red and RGB; charging blue can coexist with Caps red. Repeated Bluetooth
LED messages restart its two-second Caps indication. Slot changes and pairing
use the recovered blue timings.

The charger appears autonomous in the stock application. Firmware reproduces
the GPIO configuration, monitoring and indications; it does not add a current
or charge-termination algorithm. The [stock trace](mistel-md770-stock-bluetooth-power.md)
and its English/Japanese manual comparison remain the behavioural reference.

Battery idle is ten minutes on the right, with local right-hand wake, and
300 ms on the left. Held keys prevent idle; DIP switch positions do not.
RGB is gated and idle scanning uses a 2 ms interval. The foreground yields
to ChibiOS's WFI idle thread. The implementation retains the 48 MHz clock,
SysTick/watchdog and SPI/UART configuration. It does not reproduce stock's
8 MHz clock changes or deep WFE power sequence, so stock battery runtime and
sleep current are not established.

## Historical QMK integration and review

| Responsibility | Existing interface or source in `qmk_firmware` |
| --- | --- |
| Bluetooth reports and task hooks | `drivers/bluetooth/bluetooth.h`, `BLUETOOTH_DRIVER=custom` |
| Output routing and persistence | `quantum/connection/connection.c` |
| Output/profile keys | `QK_OUTPUT_USB`, `QK_OUTPUT_BLUETOOTH`, `QK_BLUETOOTH_PROFILE1`–`3` |
| Stock radio transport | `keyboards/mistel/md770rgb_bt/bluetooth.c` |
| Supply, voltage detection and USB wake states | `keyboards/mistel/md770rgb_bt/power.c` |
| Dedicated LED PWM | `keyboards/mistel/md770rgb_bt/indicators.c`, ChibiOS PWM |
| Split, scan and RGB | Existing keyboard drivers, ChibiOS serial/GPT/GPIO |
| USB resume report preservation | `platforms/chibios/suspend.c` |

The BIOI G60 BLE custom driver and QMK's Bluefruit driver were inspected.
They share the Bluetooth interface and queue pattern; their UART/AT and
SPI-master SDEP protocols cannot drive Mistel's SPI-slave module. QMK's SPI
master API likewise does not supply this slave transaction protocol.
QMK's battery API reports a percentage; the traced LVD states do not provide
a calibrated cell percentage, so no percentage is fabricated.

The core change preserves held Bluetooth reports on an unrelated USB resume.
It needs separate attention during upstream review alongside the existing
ChibiOS USB receive fix. The Bluetooth driver uses QMK's normal startup-check
bypass; board USB suspend/wake is handled by explicit running, sleeping and
wake-requested states. Output and pairing controls remain available while
USB is suspended.

The asynchronous macro player yields when the radio queue is busy; the driver
also provides bounded backpressure for synchronous QMK senders. RGB PWM values
now occupy bytes and expand to the same 16-bit wire values when shifted,
recovering 512 bytes on the right. Wake priming runs in the scan interrupt,
where SPI/serial interrupts can pre-empt it, rather than under a global lock.

GPT-6 Astra reviewed the source at maximum effort in multiple passes.
Its reproduced queue, acknowledgement, reconnect, IRQ, power, pairing and
suspend findings were corrected and given regression coverage. The final
review result and image fingerprints are in the
[verification record](mistel-md770-bluetooth-implementation-checks.json).

## Verification

The minimal `default`, factory `default_mistel` and personal builds compile
for both halves. QMK strict keyboard
lint passes for both halves. The linked record includes image sizes, hashes,
static RAM and remaining heap after reserving the existing 1 KiB interrupt
and 2 KiB thread stacks. The new transport allocates no heap memory.

The actual-source native harness checks radio FIFO refill, all media mappings,
macros exceeding queue capacity, timeouts, pending IRQ errors, padded frames,
status collisions, reconnect/retry ordering, replacement pairing requests,
shutdown releases, charging eligibility, low-voltage filtering, LEDs, idle
and USB wake. It also runs the actual ChibiOS resume function and both RGB
drivers, checking all 256 PWM levels, gated sleep and interruptible priming.
The left RGB test exercises its battery idle and nonzero-payload wake.
Hardware services are supplied by the harness; electrical timing is not
simulated.

Run from this repository with the sibling QMK support checkout:

```fish
nix-shell --run 'bash tests/md770_bluetooth/run.sh'
nix-shell --run 'bash tests/md770_keymap/run-programming.sh'
nix-shell --run 'qmk userspace-compile -j 4'
```

Existing protocol, split, DIP, notification, USB receive and host-tool
regressions also pass. The independent stock-instruction harness now has
39 check groups, including status collisions and padded transfers.

Saved dynamic keymaps retain their existing bindings. Older Pn maps may still
contain `KC_NO` at the five new controls: restore or assign those bindings
before testing Bluetooth. A full QMK reset installs the compiled defaults but
also clears saved assignments, macros and lighting; it is not performed
automatically.

## Remaining hardware checks

Use the [short hardware pass](mistel-md770-hardware-calibration.md) for five
scenarios focused on the new transport and wake path. It reuses the earlier
wired/personal hardware baseline. The optional full 11-case macro matrix
covers all 57 factor pairs after all 72 combinations pass in software.

Bluetooth typing, held modifiers, media, slot changes, pairing/reconnection,
USB handover and the visible indicators need testing with these QMK images.
The earlier successful stock power-bank test is a hardware baseline, not
validation of this transport. Full host sleep/wake also needs checking.

The battery is absent. Physical charging, termination, actual voltage
thresholds, battery wake/current and runtime remain untested. PA10's external
role and the charger's identity remain hardware questions; the implementation
uses the recovered stock polarity and transition rule.

Battery-dependent checks are deferred until a battery is available. They do
not block software review or externally powered Bluetooth testing.
