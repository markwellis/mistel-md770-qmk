#!/usr/bin/env bash
set -euo pipefail

md770_clock_symbols='-Wl,--undefined=md770_power_service,--undefined=md770_power_rgb_allowed,--undefined=md770_power_init,--undefined=md770_power_idle,--undefined=md770_power_sleeping,--undefined=md770_scan_init,--undefined=md770_scan_idle_changed,--undefined=md770_link_init,--undefined=matrix_init_custom,--undefined=wait_us,--undefined=gpt_lld_init,--undefined=sd_lld_init,--undefined=st_lld_init,--undefined=board_init,--undefined=led_init_ports,--undefined=early_hardware_init_pre,--undefined=chSysTimerHandlerI,--undefined=SysTick_Handler'
md770_qmk=${QMK_HOME:-../qmk_firmware}
for md770_side in left right; do
    md770_target="mistel_md770rgb_bt_${md770_side}_default_clock_conformance"
    md770_symbols="$md770_clock_symbols"
    if [ "$md770_side" = right ]; then
        md770_symbols+=',--undefined=pwm_lld_init,--undefined=md770_storage_sleep,--undefined=md770_storage_wake,--undefined=matrix_scan_custom,--undefined=host_task'
    fi
    qmk compile -kb "mistel/md770rgb_bt/$md770_side" -km default -j 4 \
        -e "TARGET=$md770_target" -e "EXTRALDFLAGS=$md770_symbols"
    python3 -B tests/md770_bluetooth/check_clock.py --qmk-home "$md770_qmk" \
        --elf "$md770_qmk/.build/$md770_target.elf" \
        --json "docs/mistel-md770-clock-checks-${md770_side}.json"
done
