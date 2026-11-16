#!/usr/bin/env bash
set -euo pipefail
md770_qmk=${QMK_HOME:-../qmk_firmware}
md770_test_dir=$(mktemp -d)
trap 'rm -rf "$md770_test_dir"' EXIT
cat > "$md770_test_dir/spi_master.h" <<'EOF'
#pragma once
#include <stddef.h>
#include <stdint.h>
typedef int16_t spi_status_t;
void spi_init(void);
bool spi_start(unsigned pin, bool lsb, unsigned mode, unsigned divisor);
void spi_stop(void);
spi_status_t spi_write(uint8_t data);
spi_status_t spi_read(void);
spi_status_t spi_transmit(const uint8_t *data, size_t size);
spi_status_t spi_receive(uint8_t *data, size_t size);
EOF
cat > "$md770_test_dir/debug.h" <<'EOF'
#pragma once
#define dprint(...) ((void)0)
#define dprintf(...) ((void)0)
EOF
for header in util.h wait.h timer.h; do
    : > "$md770_test_dir/$header"
done
g++ -x c++ -std=gnu++17 -Wall -Wextra -Werror -Wno-missing-field-initializers \
    -fsanitize=address,undefined,bounds -fno-sanitize-recover=all \
    -I"$md770_test_dir" -Itests/md770_bluetooth -I"$md770_qmk/drivers/flash" -I"$md770_qmk" \
    -include tests/md770_bluetooth/quantum.h -include "$md770_qmk/keyboards/mistel/md770rgb_bt/config.h" \
    -DA9=9 -DB6=22 -DC2=34 -DC3=35 \
    "$md770_qmk/drivers/flash/flash_spi.c" tests/md770_storage/power.cpp -o "$md770_test_dir/power"
ASAN_OPTIONS=detect_leaks=0 "$md770_test_dir/power"
