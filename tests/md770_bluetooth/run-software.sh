#!/usr/bin/env bash
set -euo pipefail

md770_validation_symbols='-Wl,--undefined=md770_programming_task,--undefined=md770_programming_process,--undefined=md770_playback_cancel,--undefined=nvm_dynamic_keymap_macro_read_buffer,--undefined=nvm_dynamic_keymap_macro_size,--undefined=host_task,--undefined=md770_power_init'
md770_qmk=${QMK_HOME:-../qmk_firmware}
for md770_keymap in default markwellis; do
    qmk compile -kb mistel/md770rgb_bt/right -km "$md770_keymap" -j 4
    md770_target="mistel_md770rgb_bt_right_${md770_keymap}_validation"
    qmk compile -kb mistel/md770rgb_bt/right -km "$md770_keymap" -j 4 \
        -e "TARGET=$md770_target" -e "EXTRALDFLAGS=$md770_validation_symbols"
    md770_args=(--qmk-home "$md770_qmk"
        --elf "$md770_qmk/.build/mistel_md770rgb_bt_right_${md770_keymap}.elf"
        --macro-elf "$md770_qmk/.build/$md770_target.elf"
        --json "docs/mistel-md770-emulator-checks-${md770_keymap}.json")
    if [ "$md770_keymap" = markwellis ]; then
        md770_args+=(--plan docs/mistel-md770-hardware-calibration.json)
    fi
    python3 -B tests/md770_bluetooth/check_emulator.py "${md770_args[@]}"
done
bash tests/md770_bluetooth/run.sh
bash tests/md770_keymap/run-programming.sh
python3 -B tests/md770_bluetooth/stock_probe.py mistel_md770rgb_bt_right_stock.bin
python3 -B tests/md770_bluetooth/stock_trace.py mistel_md770rgb_bt_right_stock.bin
python3 -B -m unittest discover -s tests -p 'test_md770*.py'
