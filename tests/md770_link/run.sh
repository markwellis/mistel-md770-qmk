#!/usr/bin/env bash
set -euo pipefail
md770_qmk=${QMK_HOME:-../qmk_firmware}
md770_link_build=$(mktemp -d)
trap 'rm -rf "$md770_link_build"' EXIT
for half in right left; do
    md770_defines=()
    if [ "$half" = left ]; then md770_defines=(-DMD770_LEFT); fi
    g++ -std=gnu++17 -Wall -Wextra -Werror -Wno-missing-field-initializers -Wno-unused-parameter \
        -fsanitize=address,undefined,bounds -fno-sanitize-recover=all "${md770_defines[@]}" \
        -Itests/md770_link -I"$md770_qmk" tests/md770_link/test.cpp -o "$md770_link_build/$half"
    if [ "$half" = left ]; then
        md770_cases=(filter initial_low periodic disabled_counter glitch rgb_retention mode_rgb busy uart)
    else
        md770_cases=(periodic retention busy uart)
    fi
    for test in "${md770_cases[@]}"; do
        ASAN_OPTIONS=detect_leaks=0 "$md770_link_build/$half" "$test"
    done
done
python3 -B tests/md770_link/check_stock.py --native "$md770_link_build/left" --native-right "$md770_link_build/right" --qmk-home "$md770_qmk" \
    --json docs/mistel-md770-link-stock-conformance.json
