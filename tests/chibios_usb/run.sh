#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
md770_usb_build=$(mktemp -d)
trap 'rm -rf "$md770_usb_build"' EXIT

gcc -std=gnu11 -Wall -Wextra -Werror -Wno-ignored-qualifiers \
    -ffunction-sections -fdata-sections \
    -fsanitize=address,undefined -fno-sanitize-recover=all \
    -Itests/chibios_usb -I../qmk_firmware/lib/chibios/os/hal/include \
    -I../qmk_firmware/tmk_core/protocol/chibios -I../qmk_firmware/quantum \
    tests/chibios_usb/test.c ../qmk_firmware/tmk_core/protocol/chibios/usb_driver.c \
    ../qmk_firmware/lib/chibios/os/hal/src/hal_buffers.c \
    -Wl,--gc-sections -o "$md770_usb_build/test"
"$md770_usb_build/test"
