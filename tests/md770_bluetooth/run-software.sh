#!/usr/bin/env bash
set -euo pipefail

md770_validation_symbols='-Wl,--undefined=md770_programming_task,--undefined=md770_programming_process,--undefined=md770_playback_cancel,--undefined=md770_playback_active,--undefined=nvm_dynamic_keymap_macro_read_buffer,--undefined=nvm_dynamic_keymap_macro_size,--undefined=host_task,--undefined=md770_power_init,--undefined=md770_power_task,--undefined=md770_radio_matrix_changed,--undefined=pre_process_keyevent_kb,--undefined=md770_system_tick_frequency,--undefined=action_exec,--undefined=suspend_wakeup_init,--undefined=usbStop,--undefined=led_init_ports,--undefined=host_keyboard_send,--undefined=usb_keyboard_report_pending,--undefined=usb_endpoint_in_init,--undefined=usb_endpoint_out_init'
md770_qmk=${QMK_HOME:-../qmk_firmware}
for md770_keymap in default markwellis; do
    qmk compile -kb mistel/md770rgb_bt/left -km "$md770_keymap" -j 4 \
        -e "TARGET=mistel_md770rgb_bt_left_${md770_keymap}_conformance"
    md770_normal="mistel_md770rgb_bt_right_${md770_keymap}_conformance"
    qmk compile -kb mistel/md770rgb_bt/right -km "$md770_keymap" -j 4 \
        -e "TARGET=$md770_normal"
    md770_target="mistel_md770rgb_bt_right_${md770_keymap}_conformance_validation"
    qmk compile -kb mistel/md770rgb_bt/right -km "$md770_keymap" -j 4 \
        -e "TARGET=$md770_target" -e "EXTRALDFLAGS=$md770_validation_symbols"
    md770_args=(--qmk-home "$md770_qmk"
        --elf "$md770_qmk/.build/mistel_md770rgb_bt_right_${md770_keymap}_conformance.elf"
        --macro-elf "$md770_qmk/.build/$md770_target.elf"
        --json "docs/mistel-md770-conformance-checks-${md770_keymap}.json" --conformance)
    if [ "$md770_keymap" = markwellis ]; then
        md770_args+=(--plan docs/mistel-md770-conformance-hardware-calibration.json)
    fi
    python3 -B tests/md770_bluetooth/check_emulator.py "${md770_args[@]}"
done
bash tests/md770_bluetooth/run.sh
bash tests/chibios_usb/run.sh
bash tests/md770_link/run.sh
bash tests/md770_storage/run-power.sh
bash tests/md770_bluetooth/run-clock.sh
bash tests/md770_keymap/run-programming.sh
python3 -B tests/md770_bluetooth/stock_probe.py mistel_md770rgb_bt_right_stock.bin
python3 -B tests/md770_bluetooth/stock_trace.py mistel_md770rgb_bt_right_stock.bin
python3 -B -m unittest discover -s tests -p 'test_md770*.py'
