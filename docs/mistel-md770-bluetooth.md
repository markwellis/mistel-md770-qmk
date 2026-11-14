# MD770 Bluetooth investigation

Bluetooth support is technically feasible while retaining the original radio
module firmware. The host MCU already communicates with that module through
a small SPI report/control protocol. A custom QMK transport can reproduce
this boundary. No replacement Bluetooth stack on the Holtek MCU is needed.
The module's exact IC remains unidentified beneath its shield.

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

## Recovered interface

The stock right US 7.02 image has SHA-256
`8fafdca096756f23626802d5b586b270b0bd512fe5d1c0327db4eafcd4f689b2`.
The following addresses refer to that image, loaded at `0x3200`.

| Function | Stock evidence |
| --- | --- |
| Radio SPI, idle | Descriptor `0xdfe0`; SPI0 slave, CR1 `0x0108`, CR0 `1`, CPR `0x17`, FCR `0x410` |
| Active transfer setup | `0x3da4(...,1)` sets FCR `0` and CR0 `0x0f`; inspect this transition when reproducing framing |
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

## Remaining implementation

QMK needs a custom SPI0 slave transport reproducing stock transaction
framing, startup, control/status exchange and report delivery. Its standard
Bluetooth hooks provide the integration point. Consumer/system reports need
the stock bitmap translation; pairing, slot selection, host LEDs, output
selection, reconnection and power transitions need implementation and tests.
The finished driver also needs a build and RAM check with the personal
keymap. The compiled empty-hook experiment is not that check.

No production Bluetooth driver has been added. The published
`qmk_firmware:mistel-md770-support` branch remains the existing wired port.
Image checks and hardware results are recorded in
[`mistel-md770-bluetooth-checks.json`](mistel-md770-bluetooth-checks.json).

The known-good personal right QMK image was restored after investigation
(SHA-256 `04469837738827efc765826d5bc7abcd3217ce210987099b6c91c292113ee888`).
Application sum/CRC and generated version metadata passed readback checks.
The owner rejoined the halves and confirmed normal USB typing. Delete-on-connect
recovery during the diagnostics cleared saved QMK settings.

## Resuming

Start with the stock transfer state machine at `0xa424` and setup routine
`0x3da4`. Obtain a valid radio status packet from QMK before adding report
routing. The power-bank test already established the radio's power and
hardware baseline. Slot 3 is paired with the development computer.

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
