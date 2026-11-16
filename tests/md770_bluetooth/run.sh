#!/usr/bin/env bash
set -euo pipefail
md770_qmk=${QMK_HOME:-../qmk_firmware}
md770_test_dir=$(mktemp -d)
trap 'rm -rf "$md770_test_dir"' EXIT
g++ -std=gnu++17 -Wall -Wextra -Werror -Wno-missing-field-initializers \
    -fsanitize=address,undefined,bounds -fno-sanitize-recover=all \
    -Itests/md770_bluetooth -I"$md770_qmk" tests/md770_bluetooth/test.cpp -o "$md770_test_dir/test"
for test in reports macro media short timeout error pending_error tail_byte tail_error long_frame collision reconnect_retry late_irq startup_selection selection pair pair_boundary replace_pair shutdown shutdown_backlog queue_stall charging voltage idle usb leds updater; do
    ASAN_OPTIONS=detect_leaks=0 "$md770_test_dir/test" "$test"
done
mkdir "$md770_test_dir/headers"
for header in ch.h hal.h matrix.h action.h action_util.h mousekey.h programmable_button.h host.h led.h wait.h; do
    : > "$md770_test_dir/headers/$header"
done
g++ -std=gnu++17 -Wall -Wextra -Werror -DCONNECTION_ENABLE -DEXTRAKEY_ENABLE \
    -fsanitize=address,undefined,bounds -fno-sanitize-recover=all \
    -I"$md770_test_dir/headers" -Itests/md770_bluetooth -I"$md770_qmk" \
    tests/md770_bluetooth/test_suspend.cpp -o "$md770_test_dir/suspend"
ASAN_OPTIONS=detect_leaks=0 "$md770_test_dir/suspend"
for half in right left; do
    md770_defines=()
    if [ "$half" = left ]; then md770_defines=(-DMD770_LEFT); fi
    g++ -std=gnu++17 -Wall -Wextra -Werror -Wno-missing-field-initializers \
        -fsanitize=address,undefined,bounds -fno-sanitize-recover=all "${md770_defines[@]}" \
        -Itests/md770_bluetooth -I"$md770_qmk" tests/md770_bluetooth/test_rgb.cpp -o "$md770_test_dir/rgb-$half"
    ASAN_OPTIONS=detect_leaks=0 "$md770_test_dir/rgb-$half"
done
