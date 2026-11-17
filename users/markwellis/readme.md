# Mark's MD770 RGB BT build

This build uses QMK's `default_mistel` keymap directly, including its profiles,
onboard programming, Fn/Pn controls, DIP switches and lighting. The only
personal addition is Raw HID notification lighting on the right half.
The factory implementation stays in QMK; there are no copied keymap files.

QMK's native `USER_NAME=markwellis` option loads `users/markwellis/rules.mk`
and `notification.c` from this External Userspace repository. The factory
keymap calls `housekeeping_task_keymap()` so notifications can run alongside
its own housekeeping. Other notification hooks use the standard QMK API.

Keep `mistel-md770-qmk` and `qmk_firmware` beside one another. `shell.nix`
supplies QMK, its compiler toolchain and the pinned `pok3rtool` with the MD770
device-ID patch. It sets `QMK_HOME` and `QMK_USERSPACE` for the session.

### Pending upstream changes

| Component | Use before merging | Switch after merging |
| --- | --- | --- |
| QMK keyboard port | `markwellis/qmk_firmware` branch `mistel-md770-support`; its PR is not open yet | Upstream QMK containing the MD770 port |
| HT32 reset address | Fix commit `410d3636` in the QMK-compatible ChibiOS-Contrib branch below; the existing local integration checkout already includes it | QMK must update its ChibiOS-Contrib dependency to include [ChibiOS-Contrib #469](https://github.com/ChibiOS/ChibiOS-Contrib/pull/469) |
| HT32 counter width | `patches/ht32f523xx-bftm-counter-width.patch` after the reset fix | QMK dependency containing [ChibiOS-Contrib #470](https://github.com/ChibiOS/ChibiOS-Contrib/pull/470) |
| `pok3rtool` | Pinned upstream source plus `patches/pok3rtool-md770.patch`, applied by `shell.nix` | Update the source pin/hash to a revision containing #19, then remove the patch entry and file |
| USB permissions | [MD770 qmk_udev branch](https://github.com/qmk/qmk_udev/compare/main...markwellis:mistel-md770-iap), or the sudo flashing command below | Install QMK udev rules containing those device IDs |

The first four supply firmware, the two controller fixes and the flasher.
The udev rules affect USB access; they are not required to compile firmware.
Merging #469 into canonical ChibiOS alone is insufficient: the fix must also
reach QMK's ChibiOS-Contrib fork and QMK's selected dependency revision.

The pushed `mistel-md770-support` branch contains the simplification.
To reproduce the pending configuration with a fresh sibling checkout, run
these commands from the userspace root. Do not clone over an existing repo:

```fish
git clone --branch mistel-md770-support https://github.com/markwellis/qmk_firmware.git ../qmk_firmware
git -C ../qmk_firmware remote add upstream https://github.com/qmk/qmk_firmware.git
git -C ../qmk_firmware submodule update --init --recursive
git -C ../qmk_firmware/lib/chibios-contrib fetch https://github.com/markwellis/ChibiOS-Contrib.git qmk-ht32f523x2-reset-register
git -C ../qmk_firmware/lib/chibios-contrib checkout --detach 410d3636a15485aefc74559a52e38c8a642b8ad9
git -C ../qmk_firmware/lib/chibios-contrib apply - < patches/ht32f523xx-bftm-counter-width.patch
```

The checkout supplies the reset-address correction from #469. The patch
supplies the 32-bit BFTM counter type from #470. These are the only required
ChibiOS-Contrib changes. Both halves run at a fixed 48 MHz while active,
using native QMK timing. No runtime-clock or USB-stop patch is required.
Shared QMK code is unchanged. The simplification is committed as
`e5b5479c53` on `mistel-md770-support`.
QMK reports that submodule as modified until its
upstream dependency catches up; keep that local dependency selection out
of the keyboard submission. Running `git submodule update` on this temporary
setup restores the older pinned dependency, so reselect the fix afterwards.

## Build

From this repository's root:

```fish
nix-shell --run 'qmk userspace-compile -j 4'
```

`qmk.json` selects the factory keymap, personal userspace and distinct output
names for both halves. Generated binaries are ignored by Git:

```text
mistel_md770rgb_bt_right_markwellis.bin
mistel_md770rgb_bt_left_markwellis.bin
```

To build one half inside `nix-shell --command fish`:

```fish
qmk compile -kb mistel/md770rgb_bt/right -km default_mistel -e USER_NAME=markwellis -e TARGET=mistel_md770rgb_bt_right_markwellis
qmk compile -kb mistel/md770rgb_bt/left -km default_mistel -e USER_NAME=markwellis -e TARGET=mistel_md770rgb_bt_left_markwellis
```

The plain upstream factory build omits `USER_NAME`; the minimal upstream
keymap is named `default`. Notification source lives only in this repository.

## Flash

Build first. Disconnect the cable between the halves and connect only the
half being flashed to the laptop. On the right, press Pn+Insert and wait for
the three blinks. On the left, connect USB while holding Escape for two
seconds, then release it. In the interactive Nix shell, run the matching
command:

```fish
qmk flash -kb mistel/md770rgb_bt/right -km default_mistel -e USER_NAME=markwellis -e TARGET=mistel_md770rgb_bt_right_markwellis
qmk flash -kb mistel/md770rgb_bt/left -km default_mistel -e USER_NAME=markwellis -e TARGET=mistel_md770rgb_bt_left_markwellis
```

After a successful update, unplug host USB for ten seconds, then reconnect
without holding keys. Rejoin the halves after both updates, with host USB
connected only to the right. Normal flashing preserves the factory bootloader.
Holding Escape or Delete during connection clears that half's settings.

If the MD770 udev rules are unavailable, flash the existing binary with
`sudo -A` inside the same shell:

```fish
sudo -A (command -v pok3rtool) flash QMK ./mistel_md770rgb_bt_right_markwellis.bin --no-boot
```

Use the left filename for the left half. Build as your own user.

## Personal changes and updates

Edit `notification.c` and `notification.h` for notification behaviour;
`rules.mk` enables Raw HID only on the right. The factory keymap's compiled
layout, custom keycode values and storage layout are retained, so this
reorganisation does not require clearing existing factory settings or macros.
Switching between minimal `default` and `default_mistel` does require a reset
because their layer/storage layouts differ.

Factory fixes arrive with the QMK checkout automatically. Update that
checkout and rebuild these targets; do not copy its keymap into this repo.
Once the keyboard and both controller fixes reach upstream, use the matching
upstream QMK revision and its normal submodules. Until then, keep the pending
dependency setup above. Update `shell.nix`'s pinned flasher source only after
its MD770 support has merged and been tested.

See [onboard programming](../../docs/onboard-programming.md) for the factory
editor and [notifications](../../docs/notifications.md) for alert behaviour.

```fish
python3 scripts/md770_notify.py ff8800
```
