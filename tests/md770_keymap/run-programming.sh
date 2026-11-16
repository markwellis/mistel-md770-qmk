#!/usr/bin/env bash
set -euo pipefail

md770_test_dir=$(mktemp -d)
trap 'rm -rf "$md770_test_dir"' EXIT

python3 - "$md770_test_dir/keymap_data.h" <<'PY'
import json
import pathlib
import re
import sys

root = pathlib.Path("../qmk_firmware/keyboards/mistel/md770rgb_bt")
layout = json.loads((root / "info.json").read_text())["layouts"]["LAYOUT"]["layout"]
keymap = json.loads(pathlib.Path("keyboards/mistel/md770rgb_bt/keymaps/markwellis/keymap.json").read_text())
lines = [f"static const uint16_t compiled_keymaps[{len(keymap['layers'])}][MATRIX_ROWS][MATRIX_COLS] = {{"]
for layer, codes in enumerate(keymap["layers"]):
    for key, code in zip(layout, codes, strict=True):
        row, col = key["matrix"]
        lines.append(f"[{layer}][{row}][{col}] = {code},")
lines.append("};")
source = pathlib.Path("../qmk_firmware/quantum/send_string/send_string.c").read_text()
for table in re.findall(r"__attribute__\(\(weak\)\) const uint8_t ascii_to_\w+\[\d+\] PROGMEM = \{.*?\n\};", source, re.S):
    lines.append(table.replace("__attribute__((weak)) ", "").replace(" PROGMEM", ""))
pathlib.Path(sys.argv[1]).write_text("\n".join(lines) + "\n")
PY

gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined,bounds -fno-sanitize-recover=all \
    -Itests/md770_keymap -I"$md770_test_dir" -I../qmk_firmware -I../qmk_firmware/quantum \
    '-DQMK_KEYBOARD_H="keyboards/mistel/md770rgb_bt/md770rgb_bt.h"' \
    -DDYNAMIC_KEYMAP_ENABLE -DDIP_SWITCH_ENABLE -DDYNAMIC_KEYMAP_MACRO_COUNT=20 \
    -DBLUETOOTH_ENABLE \
    keyboards/mistel/md770rgb_bt/keymaps/markwellis/keymap.c \
    keyboards/mistel/md770rgb_bt/keymaps/markwellis/programming.c \
    tests/md770_keymap/programming.c -o "$md770_test_dir/programming"

if [ "$#" -eq 0 ]; then
    set -- remap macro modifiers held reject invalid shared relocate default pn mac_assignment mac_relocation dip_reset middle slots dip_target dip_caps dip_pn original banks delays limit default_relocation default_banks default_mac playback_held playback_interrupt playback_bluetooth playback_modifiers playback_boundaries playback_invalid playback_dip playback_reports playback_overlap playback_repeat_tap relocated_fn_t relocated_fn_g relocated_fn_b relocated_pn_delay delay_key_release
fi
for case; do
    "$md770_test_dir/programming" "$case"
done
