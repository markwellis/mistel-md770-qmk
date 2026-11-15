# Stock Bluetooth, charging, power and indicator trace

Research completed on 2026-11-15 for the right US 7.02 application and the
left US 4.01 application. This records the Holtek applications' behaviour.
The separate radio module's internal firmware is not in the supplied
updaters. No QMK driver or firmware implementation was changed.

The main findings are:

- The normal radio path uses SPI0 slave FIFO polling and interrupts. The
  generic SPI backend's DMA mode is not part of that normal path.
- Charging indication uses PC13 and the application's power state. Low
  battery indication uses the MCU supply-voltage detector, not an ADC
  percentage or a battery-status packet from the radio.
- LED2 has independently controlled red and blue channels. Stock can enable
  both together. Low battery suppresses the Caps Lock writer.
- The 7.02 instructions specify two host-change flashes, a repeating burst
  of three charging/low-battery flashes, and a ten-minute battery idle timer.
  Some older manual descriptions differ.

## References and verification

All right addresses below refer to the image linked at `0x3200`, SHA-256
`8fafdca096756f23626802d5b586b270b0bd512fe5d1c0327db4eafcd4f689b2`.
The left image has SHA-256
`febc84d9dc1fd23152218232839279ecb59f255615a6d6c5b4d951a848c85064`.
The [firmware reconstruction](mistel-md770-firmware.md) identifies the
updaters, extraction, matrix, clocks, split link and storage.

The [manual comparison](mistel-md770-bluetooth.md#1-establish-the-behaviour-and-its-sources)
identifies the supplied English manual, Archisite's Japanese V1.2 manual
and Princeton's later Bluetooth 5.0 manual, with page references and hashes.
Register meanings were checked against the manufacturer's
[HT32F52342/52 user manual](https://www.holtek.com/webapi/187531/HT32F52342_52_UserManual_v160.pdf),
chapters 5, 8, 12, 14, 15 and 21, and
[datasheet](https://www.holtek.com.tw/webapi/11842/HT32F52342_52_Datasheetv160.pdf),
Tables 3 and 10. The LVD electrical characteristics are on printed page 31.

The trace follows reset, main-loop scheduling, callback tables, interrupt
vectors, GPIO/timer descriptors and every caller of the radio command and
indicator writers. The compiler's inline switch tables were decoded from
Thumb instructions. Their decompiled indirect-call expressions are not a
usable substitute for their case bodies.

[`stock_trace.py`](../tests/md770_bluetooth/stock_trace.py) executes the
actual stock routines under Unicorn. Its 39 named check groups cover
packets, startup, complete FIFO transactions, status parsing, pairing,
timeout/error handling, voltage detection, indicators and timing boundaries.
The [recorded output](mistel-md770-stock-trace-checks.json) identifies the
stock hash and supplied-input scope. The original eight packet checks also
pass. These checks do not establish electrical timing or physical charging.

## Reset and scheduling

Reset `0x32c0` starts the watchdog, then `0x3394` processes the scatter table
at `0xf130`. It copies 32 bytes from `0xf150` to `0x20000000` and clears the
following 9,172 bytes. This includes the radio context and indicator state.
The initial battery-level index at `0x2000001e` is 7. Main `0xd998` establishes
clocks and runs the power-state callbacks before entering its service loop.

The ordinary SysTick `0x8adc` represents a nominal 0.5 ms. Main service
`0xda78` consumes accumulated ticks. `0x66ac` decrements indicator timers
once for each elapsed tick. Radio callback `0x40a4(1, elapsed)` instead
decrements its timer once per invocation, ignoring `elapsed`. Radio delays
can therefore stretch when ticks coalesce. The nominal times below assume
each tick is serviced separately and the clock dependencies in the existing
reconstruction hold.

`0x478c` calls the three transport callbacks and then the two backend
callbacks. Tables `0xdfb0` and `0xdf8c` identify radio `0x40a4`, split
`0x4258`, storage `0x47c8`, SPI `0x43a0` and UART `0x4550`. The radio's
SPI descriptor is `0xdfe0`. The per-SPI0 backend slot is `0x200000e8`.

## Hardware boundary

| Signal | Stock use and evidence |
| --- | --- |
| PB2 / PB3 / PB4 / PB5 | SPI0 select / clock / MOSI / MISO; table `0xdf94`, configuration `0xcb98`; slave, mode 0, eight bits, most significant bit first, select active low |
| PC14 | MCU request output; set when `0x9dec` builds a command, cleared by completion `0x40a4(0x11, ...)` and startup `0x9f58` |
| PD1 | Startup/recovery pulse output; high for 2000 radio callbacks, then low for 3000 callbacks before reception is armed |
| PA10 | GPIO input with pull-down; `0x84c8` returns true when the public radio state is below 2 or this input is low; otherwise it returns false |
| PB12 | GPIO input read by `0x38e0`; high enters the external-power/USB branch, low enters the battery branch; the left application uses the same input |
| PC13 | GPIO input with pull-up, table `0xe655`; high selects steady LED2 blue, low selects the blue flash burst when charging indication is eligible |
| PC8 | LED2 red, GPTM0 channel 2, alternate function 4 |
| PD3 | LED2 blue, MCTM0 channel 3, alternate function 4; table `0xe64f` |
| PC4 / PC5 / PA14 | LED1 red / green / blue; existing profile/programming indicator paths |
| PA0 / ADC channel 0 | ADC setup `0x33ec`, input record `0xf124`, ADC list zero at `0xf128`; raw result is available independently of the LVD warning path |

PB12's supply interpretation follows the application branches; PA10's
external electrical role is not identified by the application. Preserve its
actual polarity and consumers rather than assigning it a speculative radio
ready or charging name. The underside switch's physical wiring is also not
established by the firmware. Its effect must not be inferred from PA10 alone.

## Radio context and states

| Address | Meaning |
| --- | --- |
| `0x200001e4` | Public radio state; incoming `b6 00 value` stores `value + 2` |
| `0x200001e5` | Radio host LED bitmap; `b1 value` and status field 1 update it |
| `0x200001e6` | Startup attempt counter, initialised to 4; incoming status field 2 can also write this byte |
| `0x200001e7` | Selected host value from status field 3 |
| `0x200001ec` / `0x200001f0` | Current transmit / receive pointers |
| `0x200001f4` / `0x200001f6` | Transmit budget / remaining payload bytes |
| `0x200001f8` / `0x200001fa` | Remaining receive bytes / signed dummy-byte alignment count |
| `0x200001fc` | Generic SPI context state; normal radio uses 0, 2 and 4 |
| `0x20000200` / `0x2000020c` | Transmit / receive buffer starts |
| `0x20000216` | Radio callback countdown |
| `0x20000218` | Pending internal command; `0x20` means no control command queued |
| `0x20000219` | Radio callback state, separate from the public radio and SPI states |

Callback `0x40a4` implements these states:

| State | Behaviour |
| --- | --- |
| 0 | Wait for a pending command. Initialise PC14/PD1/PA10, clear public state/LED/host bytes, set attempt counter 4 and start the PD1 pulse. |
| 1 | Wait 2000 callbacks with PD1 high. If a command remains, drive PD1 low, set countdown 3000 and enter state 2. |
| 2 | At countdown expiry, stop with public state 7 if the attempt counter is zero. Otherwise decrement it and call `0x9d24`. |
| 3 | Reception armed. `0x9dec` advances to state 4, normally imposing a 20-callback guard. A pending `0x50` retains its pairing delay. |
| 4 | Build the pending command or a dirty keyboard/system/consumer report once the countdown permits it. |
| 5 | Command outstanding, with a 4000-callback timeout. Timeout restarts the PD1 sequence. |
| 6 | An incoming message was processed. Completion rearms reception through `0x9d24`. |

`0x9d24` resets both pointers, sets a ten-byte receive budget, clears
transmit counts/alignment, sets generic context state 2 and radio state 3,
and ensures at least 20 callbacks of delay. Registration through
`0x4364(0x23, 0)` and `0x43a0` moves the generic context to FIFO state 4.
Callback operations 0, 1, 2, `0x11`, `0x12`, `0x13` and errors above
`0x13` cover service, elapsed time, power transitions, completion, incoming
data, cleanup and rearming respectively.

Public state 4 is the connection-completion condition used by `0x5ce4` to
end the pairing/host-change indication. Host selection sets public state 2;
pairing commands set it to 3. Other module status values retain their exact
numeric transformations; the application does not name their RF meanings.
In particular, status field 2 is not evidence of a battery-level packet.

## SPI transaction sequence

1. `0x3da4(descriptor, 0)` selects `CR1=0x0108`, interrupt mask `0xfc`,
   `FCR=0x410` and `CR0=1`. FIFO mode is enabled with receive trigger 1.
   CPR is 3 or `0x17` according to clock state; SPI0's clock comes from
   the radio master rather than that master-mode divider.
2. The report builder writes the transmit payload/counts and raises PC14.
   The backend fills at most seven FIFO entries initially. A keyboard report
   is nine bytes, so it requires further FIFO service.
3. The radio clocks the transaction as SPI master. IRQ21 at `0x8abc` calls
   `0x3c04`, which services bytes through `0xcb60` and `0x3c78`, then invokes
   radio callback operation `0x12` to parse received data. Each received byte
   can permit the remaining transmit bytes to enter the FIFO.
4. Backend `0xa424` remembers that select was active using `SPISR.BUSY`.
   It completes the frame when select becomes inactive, including a frame
   shorter than the initial ten-byte receive budget.
5. Completion calls `0x40a4(0x11, ...)`, lowers PC14, applies command-specific
   received-length tests and rearms the next reception. Byte alignment uses
   zero dummy bytes, not the diagnostic probe's `0xff` filler.

The normal radio context never requests generic state 3, which starts DMA.
The `0x3da4(..., 1)` branch (`FCR=0`, `CR0=0x0f`, RX/TX DMA enabled)
belongs to the shared SPI backend. It must not be copied into the radio
path merely because it exists nearby. The nine-byte instruction-execution
check exercises FIFO refill and completes without entering that branch.

The SPI IRQ treats status error bits 3–7 as failure, calls operation
`0x14`, marks the backend for cleanup, clears the hardware error flags and
disables the transport as needed. The main service's `0x13` cleanup rearms
the radio context. The command timeout independently pulses PD1 again.
The error callback itself does not explicitly lower PC14.

There is no application-level checksum, sequence number or explicit
acknowledgement packet in this boundary. Incoming B1/B6/B7 or unknown nonzero
messages move the parser into its receive state and leave the outgoing
command pending for retry. Otherwise completion checks the number of
received bytes against the outgoing command's minimum length. Padded 11- and
16-clock keyboard transfers pass; ten bytes is the receive storage budget.
The complete
FIFO checks pass with supplied zero reply bytes; that establishes the
application's completion rule, not acceptance by a physical radio.

## Packets, reports and control

| Internal command / input | Encoded bytes or action |
| --- | --- |
| `0xf0` | `a1` + eight keyboard bytes from `0x200005d8`; modifiers, reserved byte and six ordinary key usages |
| `0xf1` | `a2` + four consumer bitmap bytes from `0x200005b1` |
| `0xf2` | `a3` + one system bitmap byte from `0x200005ad`; bits 0–2 represent System Power Down, Sleep and Wake Up |
| `0x41`–`0x44` | `aa 03 slot`; normal user controls select slots 1–3 |
| `0x51`–`0x54` | First send `aa 03 slot`; completion changes the queued command to `0x50` and delays 300 callbacks |
| `0x50` | `aa 00 01`, pairing control after selection |
| `0x60`, `0x61`, `0x63` | `a6 field 00`, status queries for fields 0, 1 and 3 |
| `0x80` | `a7 02 00 01` for USB states 5/6; otherwise `a7 02 00 02` |
| `0xa0`, `0xa1`, `0xa2`, `0xa4`, `0xa8`, `0xaf` | `a4 mask`; `0xa0` derives the mask from the selected host. No user-facing disconnect/erase meaning is established. |
| `b1 bitmap` | Update radio host LEDs, copy to `0x2000068b` and restart the Caps indication timer |
| `b6 field value` | For fields 0–3, update the public-state/LED/attempt/host bytes above; require at least three received bytes |
| `b7 02` | Prepare a one-byte value 1 when USB is configured, otherwise 2, and set alignment to `3 - received_length`; its separate over-air meaning is not established |

The full consumer mapping is retained in
[`consumer_codes`](mistel-md770-driver-data.json). Bitmap bit `n` corresponds
to internal code `0xec + n`, with 18 defined usages. A2 is this bitmap,
not a little-endian QMK consumer usage. System A3 is also a bitmap. The
radio keyboard report remains six-key rollover even when USB uses NKRO.
When no control command is pending, dirty-report priority is keyboard,
then system, then consumer. USB and radio use separate host LED bytes.

`0x36b8` validates queued controls. Most commands are ignored while public
state is below 2; reset and USB-state notification are exceptions. Selection
clears public LED/attempt/host bytes and enters state 2. Pairing enters
state 3. The builder and callback use a single pending control byte rather
than a command queue. Received B1/B6 messages with insufficient bytes do
not change the corresponding public state. Unknown nonzero packet types
finish the receive phase without updating those fields.

## Keys, selection and persistence

The short Pn+F1/F2/F3 path in `0x5ef8` sets a deferred slot value.
`0x634c` waits for `0x567c(1)`, selects Bluetooth output, saves that output
selection, queues `0x41`/`0x42`/`0x43` and installs four 500-tick LED phases:
blue on, off, on, off. This is two flashes at nominal 250 ms per phase.

Long-combination table `0xde00` uses a hold counter greater than 6000 for
the three pairing combinations. The counter starts at 1, giving a nominal
three-second hold. `0x5d40` then queues `0x51`/`0x52`/`0x53`,
sets indicator mode 4, installs 680 phases of 1000 ticks and keeps the
application awake. The wire sequence is selection, nominal 150 ms delay,
then `aa 00 01`. A connected-state update clears the remaining phase count.
Without that update, the indicator can run nominally 340 seconds. The
radio module controls actual pairing, bond storage and reconnection.

Pn+1/Pn+2 in `0x5ef8` set output mode 2/1 respectively. That mode lives at
`0x2000068c`; the saved value is `0x2000158e`, offset `0x92` in the
168-byte global settings record. `0x4b68` persists it in external flash.
`0x6544` restores 1 or 2 at initialisation, defaulting invalid values to 1.
The report paths attach routing flags to changed reports; the radio tests
bit 1 and the USB path uses its USB routing bit.

The selected Bluetooth host byte and module bonds are not copied into the
MCU's global settings record by these paths. Reset/profile reset does not
issue a demonstrated bond-erasure command. There is no identified explicit
all-keys-release sequence in the host-selection code; report construction
and the resident module determine that behaviour.

## Supply and low-voltage management

`0x84fc` is the right supply-state controller. Its state byte at
`0x2000001f` distinguishes uninitialised (0), battery monitoring (1),
special startup mode (2), powered but USB not configured (3) and configured
USB (4). `0x38e0` reads PB12 independently of USB enumeration.

When PB12 is low, the controller selects Bluetooth output, enters battery
monitoring, enables LVD and requests active power level 11, or level 9 when
the battery-level index is already below 5. When PB12 is high, PA10/public
radio state can defer the transition. An accepted transition disables LVD
and raises the requested active power level to at least 13. It then uses
`0x987c` to distinguish configured USB states 5/6 from other USB states.

Power event handler `0x8420` maintains the charging-indication eligibility
byte at `0x20000020`. Events 0, 3 and 4 set it; every entry first clears it,
so events 1 and 2 leave it clear. Event 0 selects and saves USB output;
event 2 selects and saves Bluetooth output and starts a 500-tick transition
timer; events 1/3 update the USB enable path through `0x9874`/`0xcf68`.
Thus the LED eligibility byte must not be replaced by a simple test of USB
enumeration or PB12 alone. A powered, never-enumerated initial connection
can retain eligibility from event 3; dropping from configured USB to
unconfigured USB executes event 1 and clears it.

The LVD logic is separate from the ADC:

| Level index | `PWRCU.LVDCSR` selection | Nominal falling VDD threshold |
| --- | --- | ---: |
| 7, initial | `0x00450000` | 3.15 V |
| 6 | `0x00430000` | 3.00 V |
| 5 | `0x00410000` | 2.85 V |
| 4 | `0x00070000` | 2.70 V |
| 3 | `0x00050000` | 2.55 V |
| 2 | `0x00030000` | 2.40 V |
| 1 | `0x00010000` | 2.25 V |

`0xc7b4` selects the threshold and loads a 50-tick filter. SysTick helper
`0x8650` decrements that filter only while both LVDEN and LVDF are set.
Any sample that does not meet that condition reloads 50. On expiry,
`0x84fc` decrements the index and selects the next threshold. Crossing
index 5→4 enables the low-battery indication and requests power level 9.
This follows nominal VDD falling below 2.85 V for 25 ms; these are MCU
supply thresholds with the manufacturer's tolerance, not battery-cell
voltages. The datasheet specifies typical 100 mV detector hysteresis.

The index decreases during battery monitoring. These paths do not increase
it during charging or disable/re-enable cycles; reset restores its initial
value. `0xd75c` reports low battery only when supply state is 1 and the
index is below 5. Entering external-power states suppresses that warning
without inventing a new charge percentage.

ADC IRQ `0x33b8` copies channel 0 into `0x200023f2`. `0x634c` updates the
accumulator at `0x20000034` with `acc - (acc >> 11) + sample` and rearms
the conversion. The vendor command handler can return the raw sample.
Neither this accumulator nor a calibrated ADC voltage drives the traced
charging/low-battery indicator decisions.

## Charging and indicator waveforms

`0x6630(index, on)` writes compare 6000 or zero. Index/register mapping is
0→`0x4006e098` (LED2 red), 1→`0x4002c09c` (LED2 blue),
2→`0x4006e090`, 3→`0x4006e094`, 4→`0x4002c090` (LED1 RGB).
The timer descriptors use reload `0xffff` and prescaler 1. With the
nominal 48 MHz timer source this is approximately 366 Hz and the stock
active-low pulse width is 6000 counts, about 9.16% duty. It is not a
continuous GPIO drive. Slow-clock operation changes the carrier frequency
while preserving compare/reload counts.

Indicator service `0xd7e4` gives explicit indication modes priority over
the ordinary profile/charge path. Mode 1 blanks the RGB framebuffer and
LED1; mode 2 alternates LED1 white, mode 3 alternates LED1 red, and mode 4
drives the finite LED2 blue sequence. Modes 2/3 use
1000-tick phases. Mode 4 uses the installed phase count/delay and explicitly
clears LED2 red while driving blue. A pending reset flag at `0x20000022`
forces mode 3. Once a finite mode-4 sequence ends, both LED2 channels are
cleared and normal service resumes. Installing a mode-4 sequence does not
reset its phase bit; its starting phase can therefore inherit an interrupted
earlier indication.

In ordinary mode 0, when no special lighting function suppresses the path:

| Condition | Output |
| --- | --- |
| Eligibility byte set, PC13 high | LED2 blue on continuously |
| Eligibility byte set, PC13 low | LED2 blue burst described below |
| Eligibility byte clear, low-battery predicate true | LED2 red burst described below |
| Eligibility byte clear, low-battery predicate false | LED2 blue off; the separate Caps writer controls red |

Both bursts use state at `0x200000d0`: phase bit at `+1`, modulo-six
phase count at `+2`, and countdown at `+6`. Six toggles produce three
flashes. The first five intervals are 50 ticks (25 ms each); the sixth
loads 6000 ticks (3 s). The repeating period is nominally 3125 ms:
on at 0, off at 25, on at 50, off at 75, on at 100, off at 125, next
on at 3125 ms. The shared burst phase is retained across indication changes.

Caps service `0x6d04` runs after the indicator service. USB mode uses bit 1
of host byte `0x2000068a` for steady red. Bluetooth mode uses bit 1 of
`0x2000068b` and bit 10 of a nonzero 4000-tick timer at `0x2000002a`.
`0x9d54`/`0x5e68` restart that timer on radio LED updates. This gives two
red on windows over nominally two seconds, then off. A repeated host LED
update can restart it. Low battery bypasses the Caps writer, preserving the
warning. This writer also runs after mode 4, so that mode's red clear can
be overwritten by the Caps decision. Charging blue and Caps red can coexist;
instruction execution confirms both compare registers can hold 6000
simultaneously.

The application configures PC13 as an input and reacts to its state. No
charger-current control, timed charge cutoff, cell-voltage regulation or
charger configuration transaction was identified in these paths. Charging
therefore appears to be an autonomous hardware responsibility. The charger
IC and circuit have not been identified sufficiently to prove their current
and termination characteristics. PC13 high is the firmware's full-charge
indication condition, not proof of a physically full or present battery.
There is no separate absent-battery decision in this indicator path.

## Idle, sleep, wake and both halves

Activity helper `0x8600` loads 1,200,000 nominal 0.5 ms ticks into
`0x200023ec`: ten minutes. Right matrix activity and non-idle radio activity
refresh it. Pairing keep-awake handling in `0x634c` uses a separate
240,000-tick minimum and a 6000-tick cap after completion; that two-minute
pairing interval must not be mistaken for the ordinary idle timeout.

On battery idle expiry, `0x84fc` requests power level 4. The state sequencer
`0xc7f0`/`0xc9a4` calls nine callbacks from `0xe694` across GPIO, matrix,
ADC, USB, split/SPI, storage and indicator configuration. `0xc87c` selects
48 MHz for levels 11 and above or 8 MHz for levels 6–10. Crossing those
boundaries also updates SysTick, serial divisors and active peripheral
configuration. Level 9 suppresses the normal RGB effect service; the RGB
callback `0x88e8` disables the driver when crossing below level 11.

For deeper idle, `0xc928` uses a nominal 2 ms SysTick interval, services
the local right matrix through `0x54d8`/`0x5548`/`0x55f8`, and enters
the WFE power sequence at `0x3518`. Wake restores the nominal 0.5 ms
interval and requests the recorded active level, capped at 13. This path
does not service incoming left key reports as a wake source. The ordinary
matrix initialisation/normalisation path runs during restoration; it must
be preserved rather than assuming wake simply resumes an unchanged scan.
The source establishes the local-wake route, but first-key RF delivery
still depends on the resident module and physical timing.

The left US image has no radio command or charger controller. Its
`0x67d4` checks PB12 and uses a 600-tick battery-side interval before
requesting level 4. Its deep-idle loop `0x9d2c` and local scan service
`0x4cf8` mirror the right structure. Incoming RGB callback `0x532c`
selects active level 13 for nonzero RGB or level 11 when the right sends
all zeros. The UART's ordinary payload remains eight matrix bytes one way
and 126 RGB bytes the other, with no extra battery/charge command.

The short left interval is not a battery-discharge or charging timeout.
It is part of the left power-state machinery. The Japanese manual's
right-half-only wake requirement is consistent with the right application's
deep-idle polling boundary.

## Manual differences resolved by the current application

| Manual statement | Right US 7.02 result |
| --- | --- |
| Archisite: one blue flash for a host change; English: two | Four 500-tick phases give two flashes. |
| Archisite: blue charging blink; Princeton: about three-second intervals | Three short flashes followed by a 3 s gap; use the recovered phase counts. |
| Blue steady when full; red blink when low | Matches the GPIO/LVD decisions, subject to indication eligibility and priority. |
| Archisite: two red Caps flashes; Princeton distinguishes USB/BT | USB uses steady red; Bluetooth uses the timed two-window indication. |
| Archisite: approximately two-minute idle sleep | Application idle timer is ten minutes; the separate pairing minimum is two minutes. |
| Princeton Bluetooth 5.0: USB forces USB output | This application accepts Pn+1 while USB remains connected; do not import that later revision's restriction. |

## Remaining physical boundaries

The research supplies the Holtek-side state, packets, GPIO polarity,
threshold selection, timing and indicator composition needed for a port.
It does not supply the shielded module's internal Bluetooth implementation,
bond-storage format or definitive meanings for unconsumed status values and
the unused A4 control family. Those cannot be recovered from an application
that only exchanges this boundary protocol.

PA10's external role, the underside switch wiring, the charger IC, actual
charge current/termination, the cell-to-VDD relationship and electrical
sleep/current measurements remain hardware questions. The battery is absent.
The existing stock pairing/power-bank typing result establishes a working
radio baseline only. The supplied-input checks do not replace those
measurements. Work stops here before firmware implementation.

## Reproduce the research

Extract both updaters and reproduce the Ghidra projects using the existing
[instructions](mistel-md770-firmware.md#reproducing-the-extraction-and-decompilation).
For the right image, also seed callback functions `0x33ec`, `0x3efc`,
`0x40a4`, `0x43a0`, `0x4550`, `0x47c8`, `0x52cc`, `0x5584`, `0x5a68`,
`0x6544`, `0x88e8` and `0x9a08`. Add
`-postScript ExportTraceIndex.java "$ANALYSIS/c"` to export function,
assembly and reference indexes. Complete vendor exports remain local.

Run the checks against a locally extracted image, in fish:

```fish
nix-shell -p python3Packages.unicorn --run 'python3 tests/md770_bluetooth/stock_probe.py md770-analysis/images/MD770R_FW_0419_7.02_20230421.g4e8.firmware.bin'
nix-shell -p python3Packages.unicorn --run 'python3 tests/md770_bluetooth/stock_trace.py md770-analysis/images/MD770R_FW_0419_7.02_20230421.g4e8.firmware.bin'
```

The FIFO model supplies byte clocks, select edges, occupancy and an explicit
error condition. It invokes the real SPI0 IRQ after each received byte.
It does not run the MCU from reset as a complete board or invent radio
responses. The complete keyboard transfer, release, consumer/system
transfers, unsolicited status and pairing sequence execute their real stock
callback/backend paths. Other checks supply the specific RAM/MMIO state
listed in their source, including elapsed countdown expiry where needed.
The pairing-key boundary check stubs the external-settings write routine;
it executes the key matching, hold comparison, command and indicator setup.
