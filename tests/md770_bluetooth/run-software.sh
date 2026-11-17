#!/usr/bin/env bash
set -euo pipefail

md770_validation_symbols='-Wl,--undefined=bluetooth_init,--undefined=md770_programming_task,--undefined=md770_programming_process,--undefined=md770_playback_cancel,--undefined=md770_playback_active,--undefined=nvm_dynamic_keymap_macro_read_buffer,--undefined=nvm_dynamic_keymap_macro_size,--undefined=host_task,--undefined=md770_power_init,--undefined=md770_power_task,--undefined=md770_radio_matrix_changed,--undefined=pre_process_record_kb,--undefined=md770_system_tick_frequency,--undefined=keyboard_post_init_kb,--undefined=usb_event_queue_task,--undefined=usbWakeupHost,--undefined=md770_power_usb_suspended,--undefined=md770_power_rgb_allowed,--undefined=md770_power_usb_wake,--undefined=md770_radio_key_ready,--undefined=action_exec,--undefined=suspend_wakeup_init,--undefined=led_init_ports,--undefined=host_keyboard_send,--undefined=usb_endpoint_in_init,--undefined=usb_endpoint_out_init'
md770_qmk=${QMK_HOME:-../qmk_firmware}
for md770_half in right left; do
    qmk compile -kb "mistel/md770rgb_bt/$md770_half" -km default -j 4 \
        -e "TARGET=mistel_md770rgb_bt_${md770_half}_default_conformance"
done
for md770_build in default_mistel markwellis; do
    md770_userspace=()
    if [ "$md770_build" = markwellis ]; then md770_userspace=(-e USER_NAME=markwellis); fi
    qmk compile -kb mistel/md770rgb_bt/left -km default_mistel -j 4 "${md770_userspace[@]}" \
        -e "TARGET=mistel_md770rgb_bt_left_${md770_build}_conformance"
    md770_normal="mistel_md770rgb_bt_right_${md770_build}_conformance"
    qmk compile -kb mistel/md770rgb_bt/right -km default_mistel -j 4 "${md770_userspace[@]}" \
        -e "TARGET=$md770_normal"
    md770_target="mistel_md770rgb_bt_right_${md770_build}_conformance_validation"
    qmk compile -kb mistel/md770rgb_bt/right -km default_mistel -j 4 "${md770_userspace[@]}" \
        -e "TARGET=$md770_target" -e "EXTRALDFLAGS=$md770_validation_symbols"
    md770_args=(--qmk-home "$md770_qmk"
        --elf "$md770_qmk/.build/$md770_normal.elf"
        --macro-elf "$md770_qmk/.build/$md770_target.elf"
        --json "docs/mistel-md770-conformance-checks-${md770_build}.json" --conformance)
    if [ "$md770_build" = markwellis ]; then
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
