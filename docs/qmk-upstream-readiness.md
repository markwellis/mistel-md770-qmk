# MD770 QMK development

## Simplification and independent review, 2026-11-17

QMK commit `e5b5479c53` on `mistel-md770-support` keeps existing shared files identical to
upstream base `552db5253fed26665a90d85de6a28adfed0c7d54`. The support diff
contains the keyboard and its tests; QMK's dependency pin is unchanged.
ChibiOS itself is unchanged. The Contrib source contains only the two
one-line corrections in the owner's PRs #469 and #470.

The implementation uses fixed 48 MHz active clocks, native QMK waits and
the periodic kernel tick. The runtime-clock and USB-stop patches are removed.
The optional Raw HID receive-wake change is also removed from QMK.

The source review's eight reductions are implemented:

1. Native report clearing replaces preservation, mirrors and forced USB
   resends. Output changes and USB interruptions cancel running playback.
2. A bounded 16-report FIFO lives inside the Bluetooth driver. It preserves
   ordinary quick taps without changing matrix history. Overflow releases
   all report families and drops the waiting backlog; it does not block.
3. Native consumer/system usages are encoded for the resident module without
   additional simultaneous-usage state or core APIs.
4. USB keeps its normal driver lifetime. Linked-left mode uses the existing
   output-selection API and USB pull-up disconnect/reconnect.
5. Serial sleep uses `sdStop()`/`sdStart()`. Partial frames are discarded;
   periodic complete snapshots restore input.
6. Flash wakes through the existing `spi_init()` hook before EEPROM startup,
   sleeps only for deep idle, and wakes before foreground work resumes.
   Exhausted identification/status retries fail closed.
7. Actual sleep, supply and RGB conditions replace the stock numeric power
   levels and intermediate transition timer.
8. One filtered, latched low-battery flag replaces the unused threshold ladder.

The resident radio stays running when USB is configured, so an ordinary
return to Bluetooth needs no extra stop/restart state machine. Native USB
notifications suspend lighting when USB is selected; matrix activity can
request host wake on either half. Automatic supply changes do not write
connection preferences to EEPROM. Startup reapplies the policy after QMK
loads those preferences.

A further independent Astra Max review found no remaining ordinary-use
blocker or reason to restore shared-core changes. It checked boot selection,
FIFO/control ordering, explicit releases on cancellation, ordinary output
changes and USB suspend lighting/wake. Exact stock parity and continuation
of held reports, alerts or running macros are not requirements.

The four production builds and both keymaps' 100-group, 408-subtest compiled
suites pass. Native Bluetooth/RGB, USB queue, split, flash and programming
checks, both compiled clock/wake checks, 16 QMK unit tests and strict
keyboard lint pass.
See `mistel-md770-simplification-checks.json` and the referenced records.
The personal builds were subsequently installed on both halves. Application
sum/CRC and generated metadata matched after programming; both halves
returned to normal QMK USB identities. The owner confirmed joined typing,
both space bars and cross-half Shift. See
[right](mistel-md770-simplified-flash-right.json) and
[left](mistel-md770-simplified-flash-left.json) installation records.
A subsequent short differential pass matched all 24 physical key events on
Bluetooth/power-bank power and all 24 on USB against the installed production
ELF. See [the comparison](hardware-calibration/simplified-input-summary.json).
Automatic reconnect, macro playback calibration, KVM switching, USB
suspend/wake, deep-sleep wake and battery runtime remain unverified.

## Separate USB-stop investigation

The additional stop guard was a separate local change, not part of the
owner's two PRs. The original HT32 driver does not shut down its hardware
when `usbStop()` is called from SELECTED (addressed), ACTIVE (configured) or
SUSPENDED. The retained actual-source test reproduces this and compares a
one-line correction in its temporary build.

The simplified keyboard does not use those stop paths. The patch is removed
from its dependency and setup instructions; no third Contrib fix is needed
for the port. The investigation establishes a source-level shutdown defect,
not an observed keyboard failure. No upstream PR was opened for it.
See `tests/chibios_usb/README.md` in the research repository.

## Historical bring-up record

The current local candidate adds [onboard assignments, persistent macro
recording and Fn/Pn relocation](onboard-programming.md). The personal build
passed the selected representative [hardware checks](mistel-md770-personal-hardware-tests.json).
Upgrading from the preceding layer order requires a settings reset.
The bring-up records below describe the preceding firmware.

The tested support tree is committed on `mistel-md770-support` as
`bf866604c1`, including onboard programming and the USB receive wake correction.
The one-line ChibiOS USB transport correction re-arms OUT reception. Without
it, a reset input queue can deliver a previous report from the retained
receive buffer. The actual-source regression in `tests/chibios_usb/` and
the first fresh-colour report after physical USB wake both passed.

This is the historical bring-up record. The current
[combined QMK candidate](https://github.com/markwellis/qmk_firmware/tree/mistel-md770-support)
uses the chip's measured 512 KiB geometry and native 64 KiB allocation;
no shared SPI or wear-levelling patch is required. The older sector-erase
workarounds below are superseded. See the
[native storage hardware result](mistel-md770-native-storage-test.json).

The port lives in the separate `qmk_firmware` repository on branch
`mistel-md770-bt`. Both halves passed USB installation, basic typing, cold
reconnect and software updater entry/return with RGB animations disabled.
Both also have tested stock recovery, independent ROM entry and two matching
stock-IAP backups.

Split typing and cold reconnect passed after restoring right PB11's stock
active state in QMK commit `ea746927f6`. See the [right](mistel-md770-right-qmk-first-test.json),
[left](mistel-md770-left-qmk-first-test.json) and
[split](mistel-md770-qmk-split-test.json) records. These describe the baseline
before the RGB feature build and persistence correction recorded below.

The preceding paired baseline used clean QMK images with RGB Matrix and
the console disabled. The feature images described below now replace them.
The right image has SHA-256
`ca6756e58bf8c59cabdd2a18070a8e3cb7e960fa4d63f2a5ea8a414a31395d89`.
The left image has SHA-256
`6586bedbe6c3dba8577dc377c7aefe48d4d407990533df49ebee8e5a6473fa9d`.
The right USB update passed application and version-page checks and returned
to QMK. Its HID descriptors contain no diagnostic console interface.
After reassembly, the owner confirmed both halves, both space bars and
cross-half Shift work, including after a cold USB reconnect. No PCB bridge
was needed. The owner also confirmed Fn calculator, screenshot and volume
up/down shortcuts. Caps Lock changes letter case after the host's disable
option is temporarily removed, but the keyboard shows no Caps Lock indicator.
The preceding baseline lacked indicator support. The feature build below
adds it. Diagnostic code is absent from the QMK tree.

## Complete wired feature build

The reviewed implementation is QMK commit `c80470f32e`. See the
[build and verification record](mistel-md770-qmk-complete-build.json).

The feature build adds dedicated Caps Lock and profile indicators using the
stock timer routing, polarity, frequency and duty. These work independently
of RGB Matrix. It also adds the three native QMK profile overlays, persistent
layout/profile selection, profile reset after key release, the physical
both-Alt factory-reset chord and a real MCU reboot implementation.

Pn+F9/F10 now edit, save and display per-key colours. The RGB Matrix effects
include a WASD/arrow-key mode. USB suspend clears the RGB payload sent left;
a stale-frame timeout also clears retained left-side lighting. Momentary
Fn/Pn releases remain active while colour editing suppresses ordinary typing.
The source uses native QMK dynamic-keymap APIs; it has no VIA-specific
handlers or enabled-by-default host configuration protocol.

The right EEPROM allocation is now 4,096 logical bytes with 8,192 backing
bytes, covering external flash `0x0000`–`0x1fff`. This replaces stock global
settings and the first stock profile sector. Clear QMK settings when moving
from the previous seven-layer/4 KiB allocation to this ten-layer layout.
The owner uses stock defaults. Standalone left-half settings remain transient;
paired settings belong to the right master.

The optional [VIA definition and instructions](../via/README.md) remain in
this repository. They are separate from the upstream QMK submission. Vial
uses a separate firmware fork and remains a downstream integration choice.
Native QMK/VIA remapping and macros replace the vendor's programming editor;
the stock macro bytecode engine and Bluetooth remain outside the wired port.

Both feature images passed normal USB programming, application/version
checks and QMK enumeration. The owner confirmed joined typing, the red Caps
Lock indicator on LED2, profile colours on LED1 and RGB on/off across both
halves. Per-key painting also works before reconnect. Cold reconnect loses
both the saved colours and profile selection in the original feature build.

The SPI backend's default block count erased only one 4 KiB sector despite
the configured 8 KiB backing store. The checksum at `0x1000` and journal from
`0x1008` therefore remained dirty. QMK commit `43cb16c512` derives two erase
blocks from the configured allocation. The real wear-levelling/backend
[regression](../tests/md770_storage/README.md) passes dirty-flash erasure,
cold reload, journal consolidation and allocation bounds; the old configuration
fails the two-sector assertion. The right default and optional VIA builds
pass. The left image is unaffected.

The corrected right image, including the updater-entry indicator cue, is
built from QMK commit `aa420b6e36`. USB installation and the full both-Alt
reset passed. The selected red profile survives cold reconnect. Saved A/J
colours and the active custom-lighting mode also survive reconnect without
Pn+F10. This validates the storage correction on the recorded hardware.

Pn+Insert now requests three 100 ms on/off flashes on both indicators before
updater entry. The stock IAP owns the LEDs after reset. The owner confirmed
visible entry flashes. The updater's identity, version page and both installed
application checksums matched, and its normal-return command restored QMK.
No flash write or erase occurred during that check. The subsequent
[final hardware checks](mistel-md770-final-hardware-tests.json) passed every
standard key and modifier, Fn navigation and media controls, DIP2–4,
DIP1+DIP3 and DIP2+DIP4 precedence, and held-key/modifier split-link loss
and reconnect. The owner also reported about one hour of ordinary typing
without problems.

The kernel confirmed USB selective suspend while the laptop stayed running.
The owner confirmed all lighting went out, key presses woke the keyboard
and lighting returned. The original USB power settings were restored.
KVM power-loss/reconnect also restored lighting and typing. Full laptop
system suspend/wake remains untested. Seven of sixteen DIP switch sets
were exercised physically; the other nine remain untested on hardware.

The refinement is recorded in QMK commit `789e14987a`. Both halves pass
strict lint and formatting checks. Twenty-one QMK unit tests pass, covering UART
framing, SPI erase geometry and DIP behaviour. Five firmware configurations
build: both defaults, right VIA and both halves without RGB Matrix.
The first right-half hardware build disables RGB animations. The port
contains no custom notification protocol; this work is limited to the wired
QMK port.

## Build prerequisites

The branch contains the SPI-flash erase-geometry correction as a separate
commit, `2ae8c20db1`. Submit that independently of keyboard support.

The pinned ChibiOS-Contrib revision has an incorrect HT32 reset-controller
address. The correction is preserved in
`patches/ht32f523xx-reset-register.patch` in this repository. With the QMK
checkout beside this repository, apply it from here before building:

```fish
git -C ../qmk_firmware/lib/chibios-contrib apply - < patches/ht32f523xx-reset-register.patch
```

That correction must land in ChibiOS-Contrib and QMK's dependency pin
before the keyboard can build from an upstream checkout without a patch.
The board's priority encoding also accounts for the pinned platform's
eight-bit priority declaration on a controller with two implemented bits.

## Implementation boundaries

Hardware configuration, layouts, RGB coordinates, supported settings and
the default keymap data use QMK JSON. Clock setup, the shared matrix/RGB
multiplexer and the existing UART framing need board-specific C.
Ordinary GPIO uses QMK helpers. Grouped GPIOA direction/input operations
remain in the scan interrupt because those pins alternate between matrix
inputs and LED row outputs. Peripheral alternate functions use ChibiOS PAL.

The RGB driver retains electrical slot mappings and the inter-half payload
order. Its vendor brightness table has been removed; RGB Matrix supplies
its own CIE1931 conversion and the driver expands PWM bytes linearly.
Brightness is therefore not visually equivalent to the old implementation,
and a stock left half can apply a different brightness curve.

The default keeps the manual's Fn shortcuts, DIP functions, layout cycle
and main Pn lighting controls. DIP2 takes precedence over DIP4. Mac mode
already swaps Alt/GUI, so DIP3 does not apply that swap twice. DIP changes
clear held reports before changing modifier mappings. The default retains
QMK's other magic flags and restores the DIP-owned flags after magic-key
EEPROM reloads.

The right matrix has eight rows, including the DIP row. The left occupies
global rows 8–15. QMK generates the DIP row's key-event mask from the
layout; the DIP driver can still read that row. An initial physical scan
prevents the active-low DIP contacts being mistaken for four active switches.

## Manual

The supplied [Mistel manual](mistel-md770-user-manual.pdf) is copied unchanged.
Its SHA-256 is
`8b3da7a4256e76d48dfe1a52ecf1a3415847e8c9e8f62b56c2a9ee0f2bda9865`.
English PDF pages 2, 6, 7 and 8 cover DIP, Fn/Pn, lighting and Mac functions.
The firmware reconstruction records the conditional DIP precedence omitted
from the short manual descriptions.

Vendor macro programming and Bluetooth are outside the wired QMK port.
Pn lighting uses native QMK effects and a named palette, not the vendor
effect engine. Pn+F9/F10 edit and display saved per-key QMK colours.
Vial-specific code belongs downstream; it is not accepted in upstream QMK.

## Before submission

Complete the dependency updates before submission. The
[final hardware record](mistel-md770-final-hardware-tests.json) distinguishes
verified keyboard behaviour from the untested full-host sleep/wake path and
remaining DIP switch combinations. No upstream pull requests are authorised
yet. The supported flashing workflow is documented in
[USB installation](usb-flashing.md). The tested wired features and
persistence results are recorded above.
Keep research images, dumps, decompiler output and host recovery tools in
this repository rather than the QMK keyboard directory.

## First hardware test

The first prepared test uses only the recorded red-switch right half, with
the inter-half cable and battery power disconnected. The DIP positions are
unconfirmed; check them when interpreting key mappings. The left half remains
on stock firmware.

Build the default keymap after applying the reset-register correction above:

```fish
make -j4 mistel/md770rgb_bt/right:default RGB_MATRIX_ENABLE=no TARGET=mistel_md770rgb_bt_right_first_test
```

This disables QMK RGB animations. The shared matrix/LED scan driver still
runs and sends zero PWM data; it is not an electrically isolated LED test.
The build retains the normal external-flash settings backend.

The prepared application is 26,824 bytes, SHA-256
`ef455622c99999992ceb39ed965434fcd5ea6a0c566e15f12adfbbbbef67e3b5`.
It was built from QMK commit `aba11aa9f9` with the dependency correction.
Its initial stack is `0x20000400`, reset vector `0x00003ce1`, and right-hand
compatibility record at `0x3bf8` is `040450c0 34000001 00020004`.

A fallback ROM image preserves bytes `0x0000`–`0x31ff` from the verified
right stock recovery image, places QMK at `0x3200`, and fills the remainder
through `0x1fdff` with `ff`. It excludes the option page. The resulting
130,560-byte image has SHA-256
`d82f62cbe46f23f71ef652d0852008bf12c59a434ed7f01e98e9d6d6ac9f76a3`.
The private test package includes that image, the original stock recovery
image, the reviewed writer, matching source, runtime and checksums.

Normal installation uses the [stock USB updater](usb-flashing.md), preserving
its bootloader and option page. The full reconstructed image and ROM writer
above are fallback recovery artefacts, not the normal flashing route.
SEL2 on the right and SEL4 on the left are only needed if software entry
and the resident updater are unavailable.

After programming succeeds, check that QMK enumerates and then cold-reconnect
USB with all pads open. Check USB identification, every right-half key, held
keys, modifiers and cold reconnect before adding the split link or RGB.
USB programming, basic typing, Backspace/Enter/arrows and cold reconnect
have passed. Every individual key, DIP combination, RGB and settings
persistence still need verification. Pn+Insert entered the retained updater,
and its software reset returned to QMK. A visible updater-entry indication
is deferred until baseline testing is complete. The left half was still on
stock firmware during this first right-half test; its later QMK results are
linked above.

## DIP input polarity correction

The first image inverted the right DIP row even though its GPIO scanner
already supplies active-high contact bits. All four physical switches off
therefore reported all four switches as on, enabling Mac-mode media keys.
Removing that complement is a one-line correction in the matrix adapter.
The rebuilt application changes only four binary bytes. Its SHA-256 is
`fdbe9864ab58b5c92294c75c9da6290962430fe081fb2a98b05bf1a936811480`.
The [correction test record](mistel-md770-right-dip-polarity-test.json)
records programming and physical retest results separately.

The actual adapter passes all 256 raw DIP-byte values, including upper-bit
masking, unchanged local key rows and unchanged repeated scans. The original
code fails the all-off case. Seven existing DIP behaviour tests also pass.
The small native harness is under `tests/md770_matrix/`; it stubs hardware
services while compiling the real QMK matrix adapter. With the QMK checkout
beside this repository, run it using:

```fish
nix-shell -p gcc --run 'gcc -std=c11 -Wall -Wextra -Werror -ffunction-sections -fdata-sections -Itests/md770_matrix ../qmk_firmware/keyboards/mistel/md770rgb_bt/md770rgb_bt.c tests/md770_matrix/test.c -Wl,--gc-sections -o /tmp/md770-matrix-test && /tmp/md770-matrix-test'
```

The corrected application passed USB programming and QMK enumeration.
DIP1 OFF → ON → OFF and cold reconnect passed: F12 switches between
normal F12 and Volume Up as expected, and Fn+F12 remains F12. All switches
were left off. Later paired-keyboard tests passed the other individual DIP
functions and the precedence cases recorded in the final hardware checks.

## Split GPIO correction

The first paired test produced no left-hand keys. Restoring stock PB8 pulls
alone did not repair it. A temporary standard QMK console build showed the
right UART transmitting and draining its queue, but only one stray received
byte and no valid left matrix frames, including during a held left key.

Stock right record `0xe65b` configures PB11 as GPIO AF1, push-pull high, with
input sensing enabled and no pulls. Its setup preloads high before enabling
the output. The port had left that pin as an input. Restoring this state
produced valid matrix packets, paired typing and successful cold reconnect.
The observed `DIR=6c81`, `INE=0942` and high input bit `0800` match the intended
configuration. The physical net has not been traced; this does not establish
that PB11 is a power-enable signal.

The production change only restores left PB8 input pull-down, right PB8 input
pull-up and the right PB11 state. UART speed, framing and gate polarity are
unchanged. QMK GPIO helpers cover the ordinary operations; ChibiOS PAL combines
PB11 output drive with input sensing, which the generic GPIO helper cannot
express. PB11 is not changed on the left, where it selects a matrix row.

Temporary counters and console output remain outside the upstream source.
The [diagnostic record](mistel-md770-qmk-split-diagnostics.json) retains the
small before/after observations without publishing a key-logging transcript.
