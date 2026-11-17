# Personal keyboard notifications

The personal right-half build uses `default_mistel` with
`USER_NAME=markwellis`. It accepts a Raw HID colour message and
breathes that colour across both halves until the next physical key press.
Dismissal does not consume the press; QMK's normal USB wake behaviour still
applies when suspended. Releases and synthetic events
do not dismiss the alert. A new message replaces the colour and restarts
the breathing cycle.
Keys already held when a message arrives do not dismiss it; a new press is
needed. Wake-up key presses also dismiss it.

The alert works when normal lighting is off. Dismissal restores the normal
effect, colour, brightness, speed and LED selection, including custom colours
or lighting off. USB suspend keeps the LEDs dark. Losing power clears the
alert; the next boot loads the normal saved lighting settings.
Alerts respect the firmware's brightness limit and lightness curve.

Notification state lives only in RAM. Rendering leaves QMK's lighting
configuration unchanged, so pending or forced settings saves cannot store
the alert colour. No notification command writes EEPROM.

The implementation lives in `users/markwellis/notification.c`, enabled by
its userspace `rules.mk`. It uses standard QMK hooks and the factory
keymap's `housekeeping_task_keymap()` callback. Both upstream keymaps omit
notifications; the personal build adds them without copying the factory
layout or programming code. VIA is disabled; factory onboard remapping and
persistent macro recording remain available.

See [personal setup](../users/markwellis/readme.md) for the two build targets
and flashing commands.

## Send an alert

After installing the personal firmware, run from this repository on Linux:

```fish
python3 scripts/md770_notify.py ff8800
```

The argument is a six-digit RGB colour. The sender finds the right half's
QMK Raw HID interface and waits for acknowledgement. It uses only Python's
standard library. It requires access to the device's `/dev/hidraw*` node.

When changing from the earlier VIA build, clear settings after flashing by
holding both physical Alt keys for one second. This clears saved keymaps,
macros and colours because removing VIA changes the storage offsets.

## HID message

Use VID `0x04d9`, PID `0x0419`, usage page `0xff60`, usage `0x61`.
The output report contains 32 bytes and has no numbered report ID:

| Offset | Value |
| --- | --- |
| 0–1 | ASCII `MD` (`4d 44`) |
| 2 | Protocol version `01` |
| 3–5 | Red, green and blue, each `00`–`ff` |
| 6–31 | Zero padding |

The keyboard echoes an accepted report. Unsupported signatures or versions
return the same report with byte 0 replaced by `ff`. Reports with the wrong
length are ignored. Linux hidraw writes require a leading zero report-ID
byte, making the write 33 bytes; reads return the 32-byte report.

The feature requires RGB Matrix and its sleep support, both enabled by the
personal build. The left half receives its colours through the existing
split protocol.

## Verification

Run the native keymap/notification tests, actual QMK RGB-core tests and
Python sender tests without accessing hardware:

```fish
nix-shell --run 'bash tests/md770_notification/run.sh'
nix-shell --run 'bash tests/chibios_usb/run.sh'
```

These cover incremental-effect restoration, excluded LEDs, normal settings
during pending and forced EEPROM saves, lighting off, suspend/wake keys,
held keys, brightness limits and HID framing. The suspend regressions check
the immediate output from QMK's real suspend path, including lighting off
and re-suspension before a resumed frame flush.
The USB regression compiles QMK's actual ChibiOS transport and buffer queues,
with simulated hardware delivery. It checks that the first report after
wake contains the new colour. The preceding driver replayed an old report
because wake did not re-arm reception after resetting the queue.
Hardware results are recorded in the [personal hardware checks](mistel-md770-personal-hardware-tests.json).
Darkness during suspend, key wake, dismissal and active-alert power loss
passed. The USB receive correction is flashed and verified: the first red
report after wake was acknowledged, displayed red and dismissed back to off.
The [build and review record](mistel-md770-notification-checks.json) identifies
the current personal source and firmware images.
