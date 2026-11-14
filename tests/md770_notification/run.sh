#!/usr/bin/env bash
set -euo pipefail

md770_test_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
md770_relative_root=$(realpath --relative-to="$md770_test_root/../qmk_firmware" "$md770_test_root")
md770_native_dir=$(mktemp -d)
trap 'rm -rf "$md770_native_dir"' EXIT
cd "$md770_test_root"

gcc -std=gnu11 -Wall -Wextra -Werror -fsanitize=address,undefined,bounds -fno-sanitize-recover=all \
    -Itests/md770_keymap -I../qmk_firmware -I../qmk_firmware/quantum \
    '-DQMK_KEYBOARD_H="keyboards/mistel/md770rgb_bt/md770rgb_bt.h"' \
    -DRGB_MATRIX_ENABLE -DDYNAMIC_KEYMAP_ENABLE -DRAW_ENABLE \
    keyboards/mistel/md770rgb_bt/keymaps/markwellis/keymap.c \
    keyboards/mistel/md770rgb_bt/keymaps/markwellis/notification.c \
    tests/md770_keymap/test.c -o "$md770_native_dir/notification"
"$md770_native_dir/notification"

make -r -R -C "$md770_test_root/../qmk_firmware" -f builddefs/build_test.mk -j2 \
    TEST=md770_notification TEST_OUTPUT=md770_notification \
    TEST_PATH="$md770_relative_root/tests/md770_notification" FULL_TESTS=md770_notification \
    QMK_USERSPACE="$md770_relative_root" SANITIZE=yes SILENT=false
"$md770_test_root/../qmk_firmware/.build/test/md770_notification.elf" --gtest_color=no
python3 -m unittest discover -s tests -p test_md770_notify.py
