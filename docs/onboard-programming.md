# MD770 onboard programming

The `default_mistel` factory keymap provides onboard programming on the
right-hand master, using QMK's dynamic keymap and persistent macro storage.
The personal build uses that same keymap with `USER_NAME=markwellis` to add
notifications. The minimal `default` keymap omits the editor, profiles and
factory macros. VIA and OpenRGB are not required.

The personal build passed the selected representative
[hardware checks](mistel-md770-personal-hardware-tests.json), including all
profile banks, remapping, persistent macros, Fn/Pn relocation and DIP
precedence. The record identifies the checks deferred from hardware testing.
The [onboard build and review record](mistel-md770-onboard-programming-checks.json)
identifies the editor baseline before personal notifications and VIA removal.
See [personal setup](../users/markwellis/readme.md) and
[notifications](notifications.md) for the current shared-keymap build.

## Upgrade

Moving from the former copied `markwellis` keymap to `default_mistel` with
personal userspace keeps the layout, keycode values and storage layout.
That migration needs no settings reset.

Clear QMK settings when switching between minimal `default` and
`default_mistel`, or upgrading from the earlier layer/storage layout. Hold
both physical Alt keys for one second in the factory keymap. This clears
saved profiles, macros and colours; save anything you need first.

All four profiles, including the default, have independent ordinary, Fn and
Pn assignments. Explicit assignments take precedence over Mac and DIP4
overlays. Function banks retain the factory shortcuts until programmed.

## Assign a key or record a macro

1. Select the default profile with Pn+M, or profiles 1–3 with Pn+comma,
   Pn+dot or Pn+slash.
2. Press Fn+Right Ctrl. The profile indicator turns white.
3. Tap the key to programme. The indicator blinks white.
4. Tap one replacement key, or type a sequence with modifiers.
5. Press Pn to save. Release all keys to apply the change.
6. Select another destination, or press Fn+Right Ctrl to exit.

A single replacement key keeps normal press-and-hold behaviour. Longer
sequences use QMK's stored macro format and survive ordinary reboot or
power loss. To programme a function-bank assignment, hold Fn or Pn while
selecting its destination. Recording reads the original layout assignments,
so an existing remap or macro does not change the source key.

The recorder preserves key and modifier order. It uses the stock 40 ms
interval rather than measuring your typing speed. During recording,
Fn+T, Fn+G and Fn+B add 15, 100 and 500 ms respectively per complete tap
before the next recorded event. As on stock firmware, the first explicit
interval starts from zero; subsequent explicit intervals start from 40 ms.
Both edges of a delay key count; half-millisecond intervals round up to the
next millisecond. Held recorded keys receive releases when saving.

Recorded macro delays leave the split link and other keyboard tasks running.
Pressing another key interrupts playback and releases its keys. Release held
typing, media or system keys before playback; modifiers may stay held.
Imported native tap commands retain QMK's tap delays, including an 80 ms
pause for Caps Lock. Onboard recordings use separate press/release commands.

Fn and Pn remain programming controls. A solid red indicator after saving
means a recording or storage limit prevented the save. The previous
assignment remains intact, including when you cancel recording. Select a
destination again to start another recording.

## Move Fn or Pn

Select a profile. Hold Fn+Left Shift or Pn+Left Shift for three
seconds, release them, then tap the new position. The indicator is red while
waiting for that position. Left Shift, Right Shift and Right Ctrl cannot be
destinations. Fn and Pn cannot overwrite one another.

Moving Fn restores Right GUI at its factory position. Moving Pn restores
Application at its factory position. A later move restores the previous
destination's underlying layout assignment. Placements belong to the
selected profile.

An explicit Caps Lock assignment or moved Fn takes precedence over DIP4's
Caps/Fn swap. Other DIP functions remain active. The editor reserves the
profile's Fn/Pn assignments even when DIP4 temporarily changes their roles.

## Reset and storage

Hold Fn+R for one second, then release all keys to reset the selected profile.
This restores its ordinary, Fn and Pn banks, including moved controls.
The indicator flashes white five times. Hold both physical Alt keys for one
second for a full settings reset, also indicated by five white profile flashes.

The default recorder holds 200 events in 800 bytes of RAM: up to 100 complete
key press/release pairs, with modifiers also consuming events.
`MD770_MACRO_RECORD_EVENTS` changes this limit. `DYNAMIC_KEYMAP_MACRO_COUNT`
defaults to 20 shared slots. Stored recordings also share the space remaining
after 19 keymap layers and other settings in 6,400 bytes of logical EEPROM.
The wear-levelling backing allocation is 12,800 bytes within the same reserved
64 KiB external-flash erase block.

The extra layers store each profile's function-bank assignments and the
default profile's edits. The three compiled base layouts remain available as
original source mappings. Profile resets leave shared macro storage in place;
later recordings reclaim slots that have no remaining key assignments.

`DYNAMIC_KEYMAP_ENABLE=no` removes the onboard editor and persistent keymap
support from a custom build. Normal compiled keymaps and macros remain
available. Standalone left-half settings remain transient; the editor and
persistent recordings belong to the right master.

An interrupted macro-storage rewrite leaves QMK's validity marker invalid.
Playback stays disabled and further recordings are rejected. A full settings
reset restores an empty valid store. This does not recover the interrupted
recording.
