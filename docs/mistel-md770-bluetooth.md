# MD770 Bluetooth, charging and power investigation

Bluetooth support is technically feasible while retaining the original radio
module firmware. The host MCU already communicates with that module through
a small SPI report/control protocol. A custom QMK transport can reproduce
this boundary. No replacement Bluetooth stack on the Holtek MCU is needed.
The module's exact IC remains unidentified beneath its shield.

The [stock Bluetooth, charging, power and indicator trace](mistel-md770-stock-bluetooth-power.md)
now records the completed Holtek-side research. Its
[39 instruction-execution check groups](mistel-md770-stock-trace-checks.json)
include a complete FIFO keyboard transaction, pairing sequencing, charging
and low-battery waveforms. The subsequent
[QMK implementation and verification](mistel-md770-bluetooth-implementation.md)
are now recorded separately; hardware validation remains outstanding.

The module is installed and the battery is removed. On 2026-11-15, the
unmodified stock right application advertised as `Mistel 3`, paired with
Linux and delivered keyboard input. The owner then moved USB power to a
power bank and typed `aj`. Linux showed the Bluetooth input device with
bus type `0x0005` and no Mistel USB device. The radio therefore works without
a battery or host USB data connection. Its HID service is classic Bluetooth
UUID `0x1124`.

The underside switch is unmarked. The position used for that successful
stock test permits radio operation; earlier assumptions about its position
were unreliable. The stock right application also accepted matrix reports
from the unchanged QMK left half.

## Implementation plan

The target is stock-compatible Bluetooth, charging, battery indications and
power management, including the dedicated LEDs. The research stages below
are now recorded in the linked trace. The linked implementation follows
that specification. The previous probe builds remain historical experiments.
They are not the starting point for further development.

### 1. Establish the behaviour and its sources

Use the right US 7.02 image identified below as the primary executable
reference. Include the left US 4.01 application wherever split operation,
lighting or sleep depends on it. Keep a function/address index, state
transition tables and unresolved questions in this document. Generated vendor
decompilation and firmware remain outside Git under the existing
[artefact policy](firmware-artefacts.md).

The manual references checked on 2026-11-15 are:

| Reference | Applicable detail |
| --- | --- |
| [Supplied English manual](mistel-md770-user-manual.pdf), PDF pages 2, 5 and 6; printed pages 33, 36 and 37 | Indicator names, Bluetooth/USB selection, pairing and host selection |
| [Archisite Japanese manual V1.2](https://archisite.co.jp/wp-content/uploads/2020/10/Mistel-MD770RGB-BT-Manual-web.pdf), PDF sheet 1; printed pages 4–8 | Bluetooth 3.0 model; charging, shared LED2 behaviour, idle sleep and right-half wake |
| [Princeton Japanese manual, August 2024](https://www.princeton.co.jp/sites/default/files/support/manual/Mistel-MD770RGB-RGB_BT-A3-manual.pdf), PDF sheet 1, LED table; sheet 2, charging instructions | Later Bluetooth 5.0 model; additional timing details require confirmation against this unit's firmware |

The downloaded Japanese PDFs have SHA-256
`8621cffe34c0e16895964a5714aa59e7379e41e8539f28c8726967470a799659`
(Archisite) and
`1a666ecf0262d8bdbd3caf82c9c8bfee0e540b0c5e7c3dbcc8b0d7b65a52d8da`
(Princeton). Page references identify the printed panels within each large
PDF sheet. The English PDF contains outlined text and needs visual inspection.

These are manual requirements to reconcile with the executable, not
completed firmware findings:

| Behaviour | Manual evidence | Stock trace required |
| --- | --- | --- |
| Output selection | Pn+1 selects Bluetooth; Pn+2 selects USB | Routing, saved selection, USB insertion/removal and behaviour without host USB data |
| Three hosts | Pn+F1/F2/F3 selects a host; holding the combination enters pairing | Hold threshold, command ordering, pairing completion/cancellation, reconnect and saved bonds |
| Pairing indicator | LED2 flashes blue slowly and turns off after pairing | Status inputs, waveform and competing indications |
| Host-change indicator | Archisite specifies one blue flash; English specifies two | Resolve the disagreement from the right US 7.02 instructions |
| Charging | Archisite specifies slow blue flashing on LED2 | Source of charging state, exact timing and applicability in USB/Bluetooth modes |
| Full charge | Archisite specifies steady blue on LED2 | Source of completion state, clearing on unplug and indicator priority |
| Low battery | Archisite specifies red flashing on LED2 | Status source or voltage threshold, filtering, hysteresis, cadence and recovery |
| Caps Lock | Archisite specifies two slow red flashes on OFF→ON, then off; English identifies LED2 as Caps Lock | USB/Bluetooth differences, host feedback and interaction with charging/pairing |
| Idle sleep and wake | Archisite specifies about two minutes idle and wake from a right-half key | Exact timeout, clocks, radio, split link, lighting and first-key handling |
| Charging supply | Archisite permits a computer or generic 5 V USB charger through the right outer port | Power detection independent of USB enumeration and the underside switch |

Princeton specifies approximately three-second intervals for charging and
low-battery flashes, and steady red Caps Lock in USB mode. It also describes
USB taking priority over Bluetooth when connected to a PC. These details
belong to its later revision until the current stock trace confirms them.
Do not silently resolve manual differences by mixing revisions.

### 2. Trace the complete Bluetooth path

Start at reset/main-loop initialisation, the SPI setup at `0x3da4`, transfer
state machine at `0xa424`, callback at `0x40a4`, report builder at `0x9dec`
and parser at `0x9d6c`. Follow every relevant caller, interrupt handler,
function-pointer target and shared-state writer, rather than stopping at
the known packet examples.

Record each state's entry conditions, register operations, packets, timers,
completion conditions and recovery path. Cover startup/reset, PC14 request
and PB2 select sequencing, FIFO priming/draining, transfer lengths and
padding, unsolicited input, back-to-back reports, timeouts and retries.
Establish SPI mode and active/idle transitions from the instructions and
the peripheral documentation. Convert tick counts only after tracing their
clock source and any changes during sleep.

Trace all command builders and incoming status fields through to their
consumers. Include keyboard/modifier releases, consumer/system bitmap
translation, host lock LEDs, slot selection, pairing, disconnect/reconnect,
USB/Bluetooth routing and persistent state. Identify which behaviour belongs
to the resident radio and which the Holtek application must reproduce.

Completion means every relevant state, command, status field and hardware
signal has an evidenced meaning or an explicit unresolved question. A
successful keyboard packet alone does not complete this stage.

### 3. Trace charging, battery state, power and indicators

Find every related GPIO, alternate-function assignment, ADC access if
present, radio status field, timer and power-control operation. Trace their
initialisation, readers and writers in active, USB suspend, idle sleep,
wake and reset paths. Include both halves where their power states interact.

Determine whether the charger operates independently, needs MCU control,
or exposes its status through the radio. Establish signal polarity and
default states from evidence. Preserve all stock charge-enable and
power-control behaviour that exists. Record any autonomous charger functions
as hardware responsibilities; do not infer charge completion from USB power
or implement a replacement charging algorithm from the manual's charge time.

Trace the LED2 red and blue outputs, including the additional timer output
omitted from the wired indicator implementation. Recover PWM configuration,
brightness, blink phase/duration/count, indication priority and restoration
after a temporary indication. Include LED1/profile behaviour where it shares
timers, reset handling or sleep state. Reuse the existing
[indicator reconstruction](mistel-md770-firmware.md#dedicated-status-indicators)
and verify any additional channel in the stock image.

Cover USB insertion/removal, charging while typing, full charge, low battery,
power-switch changes, no battery and charging without host enumeration.
Record any hardware-dependent state that the executable cannot explain.
The battery is absent, so physical charging and battery-powered runtime
cannot be validated on this unit.

### 4. Use emulation only where it resolves a question

Static analysis is the default. The existing Unicorn harness in
`tests/md770_bluetooth/stock_probe.py` already executes the stock packet
builder and parser. Use it for targeted branch checks where helpful.

Extend that harness only if a specific state or timing dependency remains
unclear, or if executing stock transitions supplies a useful comparison for
the QMK implementation. Model only the required peripheral behaviour, such
as SPI FIFO/status/select transitions, elapsed ticks or a charge-status
input. Capture ordered MMIO writes, transmitted bytes and state/LED changes.
Keep scenarios reproducible against the hashed stock image.

A model must identify supplied inputs and assumptions. It must not invent
a radio response or charging input and then treat that result as proof of
the physical protocol. A complete board/radio emulator is not a prerequisite.

### 5. Implement from the recovered specification

Reuse QMK's custom Bluetooth hooks and the existing board, split, storage
and indicator drivers. Keep the resident radio firmware. Implement only the
transport and board behaviour that the trace establishes. Put hardware
support in the QMK keyboard port; keep personal notification behaviour in
this repository's keymap.

Match stock routing, pairing, reconnect, power management, charging control
and indicator arbitration. Preserve key releases across output/host changes
and prevent stale reports after reconnect. Check the finished personal and
default builds for flash/RAM use and interrupt conflicts; the empty-hook
build's memory result is not sufficient.

### 6. Verify before a hardware candidate

Use the recovered stock transitions as the test oracle. Check packet bytes,
register sequencing, queue/completion behaviour and timer boundaries, plus
the charging and indicator states in the requirements table. Exercise shared
indications, USB suspend/resume, sleep/wake and output changes with held keys.
Compare against stock instruction execution where the existing or a targeted
emulator can provide independent evidence.

Prepare a hardware candidate only after the relevant trace is complete and
the offline checks and memory checks pass. Hardware validation then checks
Bluetooth typing, modifiers/media, three hosts, pairing/reconnect, routing
and observable LEDs. Diagnostic builds are reserved for a specific remaining
hardware question that the stock trace cannot answer.

Record source-derived compatibility, offline test results and physical
results separately. Charging support remains part of the implementation
even without a battery; mark physical charging, charge termination,
battery thresholds and battery-powered sleep/runtime as untested wherever
they cannot be checked. Do not label emulation as hardware validation.

## Recovered interface

The stock right US 7.02 image has SHA-256
`8fafdca096756f23626802d5b586b270b0bd512fe5d1c0327db4eafcd4f689b2`.
The following addresses refer to that image, loaded at `0x3200`.

| Function | Stock evidence |
| --- | --- |
| Radio SPI, idle | Descriptor `0xdfe0`; SPI0 slave, CR1 `0x0108`, CR0 `1`, CPR `3`/`0x17` according to clock state, FCR `0x410` |
| Generic DMA setup | `0x3da4(...,1)` sets FCR `0` and CR0 `0x0f`; the completed trace establishes that the normal radio path retains FIFO mode instead |
| SPI pins | Table `0xdf94`: PB2 select, PB3 clock, PB4 MOSI, PB5 MISO, AF5 |
| Pin configuration | Executed `0xcb98(0,2)`: GPIOB DIRCR `0`, INER `0x3c`, GPBCFGR0 `0x00555500` |
| Request output | PC14 set by report builder `0x9dec`; cleared by `0x40a4` after a transaction |
| Reset-like output | `0x9f58` sets PD1 high; `0x40a4` clears it after 2000 nominal half-millisecond ticks |
| Auxiliary input | Table `0xdffb`: PA10, GPIO input with pulldown |
| Keyboard report | `a1` followed by eight ordinary HID keyboard bytes |
| Consumer report | `a2` followed by the stock four-byte bitmap; QMK consumer usages still need translation |
| System report | `a3` followed by the stock one-byte bitmap |
| Host selection | Internal commands `0x41`–`0x43` produce `aa 03 01`–`aa 03 03` |
| Pairing | Long Pn+F1/F2/F3 selects the slot, then queues `aa 00 01` after 300 nominal half-millisecond ticks |
| USB state notification | Internal `0x80` produces `a7 02 00 01` when USB state is 5/6, otherwise `a7 02 00 02` |
| Incoming status | Parser `0x9d6c` handles `b6` status fields; field 3 appears to identify the active host |

The pin functions also match the manufacturer's
[HT32 datasheet, Table 3](https://www.holtek.com.tw/webapi/11842/HT32F52342_52_Datasheetv160.pdf).
SPI1 remains the external settings flash; USART0 remains the split link.
The transport context is `0x200001ec`. Its transmit and receive buffers start
at `0x20000200` and `0x2000020c` respectively. Callback `0x40a4` manages
startup and commands. The transfer state machine at `0xa424` calls that
callback with operation `0x11` after completion/SEL release.

## Offline checks

`tests/md770_bluetooth/stock_probe.py` runs the actual stock Thumb report
builder and parser under Unicorn. All eight packet checks pass. The input
transport state and received bytes are supplied by the harness. This proves
packet construction and parser assignments, rather than physical SPI or
radio operation.

Run it against the extracted right US image:

```fish
nix-shell -p python3Packages.unicorn --run 'python3 tests/md770_bluetooth/stock_probe.py /path/to/right-us.firmware.bin'
```

The later [`stock_trace.py`](../tests/md770_bluetooth/stock_trace.py) adds
37 named research check groups. Its small FIFO model supplies byte clocks,
occupancy and select edges to the actual stock backend and IRQ routines.
It also checks the power/indicator branches with supplied RAM/MMIO inputs.
See the [results and reproduction instructions](mistel-md770-stock-bluetooth-power.md#reproduce-the-research).

QMK provides custom Bluetooth report hooks and calls their task from its
main loop. The custom driver option removes the USB-only startup gate.
The existing personal keymap compiles with custom Bluetooth and SPI0 enabled,
while retaining SPI1 and USART0. That compilation uses empty driver hooks;
it leaves 96 bytes after the reserved interrupt/process stacks. The finished
transport needs a separate memory check.

## Hardware capture

The diagnostic copies the current default keymap into a temporary userspace.
It adds the radio probe's init/task calls to the existing post-init and
housekeeping hooks, enables Raw HID, and retains USB output. It leaves the
Bluetooth/connection subsystem disabled, avoiding its new EEPROM settings.
The production support branch is unchanged.

The first diagnostic used the generic HAL's slave transfer API. It enumerated
on USB but stopped responding to typing and Raw HID. An interrupt-handling
problem is suspected; its exact cause remains unproven. The owner entered
the updater with Delete at power-on. That also erased the saved QMK settings.
No case opening was required.

The receive-only revision remained responsive but captured no bytes after
cold reconnect. The final `radio_probe.c` also accepts up to eight stock
command bytes. It preloads the FIFO before asserting PC14, records at most
24 received bytes, then disables the receive interrupt. PC14 clears after
received data and SEL release, or a two-second timeout. Its custom handler
replaces the disabled SPI0 HAL handler. This build is 42,576 bytes, SHA-256
`f6f719026f3262b8547ba696c40665bf56bf4e8431bdfc8794aac036eab1d7dc`,
with 160 aligned spare RAM bytes after reserved stacks. Astra high and max
cleared the high-risk interrupt/GPIO code; the final binary has the sole
expected SPI0 handler and retains SPI1.

`read_radio_probe.py` reads the bounded capture over USB. Sending recovered
control packets yielded either no bytes or a single `00`; no valid radio
status packet was captured. This diagnostic did not establish a working
QMK transport. The subsequent stock test established radio operation and
removed the battery/power uncertainty.

## Implementation and remaining hardware checks

The local `qmk_firmware:mistel-md770-support` checkout now includes the
[Bluetooth, charging and power implementation](mistel-md770-bluetooth-implementation.md),
with default/personal builds, RAM checks and offline regressions. It has not
been flashed or published. The earlier diagnostic and stock hardware
results remain recorded in
[`mistel-md770-bluetooth-checks.json`](mistel-md770-bluetooth-checks.json).

The known-good personal right QMK image was restored after investigation
(SHA-256 `04469837738827efc765826d5bc7abcd3217ce210987099b6c91c292113ee888`).
Application sum/CRC and generated version metadata passed readback checks.
The owner rejoined the halves and confirmed normal USB typing. Delete-on-connect
recovery during the diagnostics cleared saved QMK settings.

## Resuming

The requested research is complete at the Holtek application boundary; use
the [state trace](mistel-md770-stock-bluetooth-power.md) and recorded checks.
Implementation is now available locally. The trace distinguishes
remaining physical/module questions from recovered application behaviour.
The power-bank test already established the radio's power and hardware
baseline. Slot 3 is paired with the development computer.

### Historical diagnostic reproduction

The diagnostic sources are retained in `tests/md770_bluetooth/`. To rebuild,
copy the default keymap into a separate QMK userspace and add `radio_probe.c`
and `radio_probe.h`. Include the header and call `md770_radio_probe_init()`
from the existing post-init hook and `md770_radio_probe_task()` from the
existing housekeeping hook. Add `RAW_ENABLE = yes` and
`SRC += $(KEYMAP_PATH)/radio_probe.c` to its keymap rules. Set `QMK_USERSPACE`
to that userspace and build the right half with
`EXTRAFLAGS="-DHT32_SPI_USE_SPI0=0"`. This disables the HAL's competing SPI0
handler while retaining SPI1. Keep the Bluetooth subsystem disabled for
this diagnostic.

With that diagnostic installed, `read_radio_probe.py` accepts an optional
hexadecimal command of up to eight bytes. Call it again without a command
to read the resulting capture. The personal firmware uses a different Raw
HID protocol. The probe is not a production Bluetooth driver.

The production QMK revision is
`bf866604c116844c1e6ae10969be6774de0a54f6`. Builds also used the existing local
`chibios-contrib` reset fix at `410d3636a15485aefc74559a52e38c8a642b8ad9`,
as documented in the existing upstream-readiness notes. The QMK branch has
no new Bluetooth changes.
