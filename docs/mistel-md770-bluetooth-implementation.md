# MD770 Bluetooth and charging implementation

The implementation is in `qmk_firmware`, branch `mistel-md770-support`.
The personal keymap remains in this repository. No candidate has been flashed;
the installed firmware remains the previously verified wired build.

## Behaviour

The right half retains the resident Bluetooth module. The MCU sends stock
A1 keyboard, A2 consumer and A3 system reports over SPI0 slave FIFO transfers.
USB retains NKRO; Bluetooth uses six-key rollover. The transport starts and
recovers asynchronously, so an absent or disabled radio does not block USB
initialisation. Its bounded queue preserves press/release order, pumps the
transport under backpressure and sends zero reports before restoring the
current state after reconnection. Incoming status messages cause the outgoing
report to be retried, as in stock; they are not acknowledgements.

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

## QMK integration and review

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

The default and personal keymaps build for both halves. QMK strict keyboard
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
nix-shell --run 'qmk compile -kb mistel/md770rgb_bt/right -km markwellis -j 4'
nix-shell --run 'qmk compile -kb mistel/md770rgb_bt/left -km markwellis -j 4'
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

Bluetooth typing, held modifiers, media, slot changes, pairing/reconnection,
USB handover and the visible indicators need testing with these QMK images.
The earlier successful stock power-bank test is a hardware baseline, not
validation of this transport. Full host sleep/wake also needs checking.

The battery is absent. Physical charging, termination, actual voltage
thresholds, battery wake/current and runtime remain untested. PA10's external
role and the charger's identity remain hardware questions; the implementation
uses the recovered stock polarity and transition rule.
