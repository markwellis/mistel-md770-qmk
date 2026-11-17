#!/usr/bin/env bash
set -euo pipefail

cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.."
md770_stop_qmk=${QMK_HOME:-../qmk_firmware}
md770_stop_build=$(mktemp -d)
trap 'rm -rf "$md770_stop_build"' EXIT
md770_stop_source=os/hal/ports/HT32/LLD/USBv1/hal_usb_lld.c
git -C "$md770_stop_qmk/lib/chibios-contrib" show \
    "5a9ad82b6ba4f649cdb800e8c2bbc9be2d3ce767:$md770_stop_source" \
    > "$md770_stop_build/original.c"

python3 - "$md770_stop_qmk" "$md770_stop_build" "$md770_stop_source" <<'PY'
from pathlib import Path
import sys

qmk, build, source = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]


def function(text, name):
    start = text.index('void ' + name + '(')
    position = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[position] == '{') - (text[position] == '}')
        position += 1
    return text[start:position] + '\n'


api = function((qmk / 'lib/chibios/os/hal/src/hal_usb.c').read_text(), 'usbStop')
original = function((build / 'original.c').read_text(), 'usb_lld_stop')
patched = original.replace('usbp->state == USB_READY', 'usbp->state != USB_STOP')
assert patched != original
for name, low_level in (('original', original), ('patched', patched)):
    folder = build / name
    folder.mkdir()
    (folder / 'stop_functions.inc').write_text(low_level + '\n' + api)
PY

for md770_stop_variant in original patched; do
    gcc -std=c11 -Wall -Wextra -Werror -fsanitize=address,undefined \
        -fno-sanitize-recover=all -I"$md770_stop_build/$md770_stop_variant" \
        tests/chibios_usb/test_stop.c -o "$md770_stop_build/$md770_stop_variant/test"
    md770_stop_status=0
    ASAN_OPTIONS=detect_leaks=0 "$md770_stop_build/$md770_stop_variant/test" || md770_stop_status=$?
    if [ "$md770_stop_variant" = original ]; then
        test "$md770_stop_status" -eq 1
    else
        test "$md770_stop_status" -eq 0
    fi
done
