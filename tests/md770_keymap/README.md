# MD770 keymap and indicator regression harnesses

These compile the actual QMK source with mocked host/hardware services.
They check colour-editor press/release pairing, held Fn, saved colours,
synthetic and out-of-range events, physical Alt reset timing, deferred profile
rewrites, early indicator calls,
PWM limits, Caps/profile independence, suspend/resume and the three-pulse
updater-entry cue. The programming harness checks the actual editor and
keymap with generated layout data, cached release layers and bounded storage.
It covers assignments, saved macro encoding, modifiers, allocation failures,
interrupted writes, shared and resized macro slots, all four profiles and
their function banks, Fn/Pn relocation, Mac/DIP4 precedence, stock delay
controls and interruptible playback with held keys and modifiers. It also
checks overlapping space bars, repeated native taps, moved Fn/Pn on delay
positions and recording releases when Fn changes while a key is held.
The hardware services and persistence APIs are mocked;
these tests do not prove flash writes survive a physical power cycle.
They do not prove
physical wiring, LED current or firmware timing on the keyboard.

Run from this repository with the QMK checkout beside it:

```fish
nix-shell -p gcc --run 'gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined,bounds -fno-sanitize-recover=all -Itests/md770_keymap -I../qmk_firmware -I../qmk_firmware/quantum -DQMK_KEYBOARD_H=\"keyboards/mistel/md770rgb_bt/md770rgb_bt.h\" -DRGB_MATRIX_ENABLE -DDYNAMIC_KEYMAP_ENABLE ../qmk_firmware/keyboards/mistel/md770rgb_bt/keymaps/default/keymap.c tests/md770_keymap/test.c -o /tmp/md770-keymap-test && /tmp/md770-keymap-test'
nix-shell -p gcc --run 'gcc -std=c11 -Wall -Wextra -Werror -Itests/md770_keymap -I../qmk_firmware ../qmk_firmware/keyboards/mistel/md770rgb_bt/indicators.c tests/md770_keymap/indicators.c -o /tmp/md770-indicators-test && /tmp/md770-indicators-test'
nix-shell -p gcc --run 'bash tests/md770_keymap/run-programming.sh'
```

The personal notification checks also run the actual QMK RGB engine and
sender tests. See [notifications](../../docs/notifications.md#verification).
