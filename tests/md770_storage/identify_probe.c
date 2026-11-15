// Copyright 2026 Mark Ellis (@markwellis)
// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include "spi_master.h"
#include "print.h"

static uint8_t identity[3];
static uint8_t sfdp[256];
static bool    identity_ok;
static bool    sfdp_ok;

void housekeeping_task_kb(void) {
    static bool     sampled;
    static uint32_t last_print;
    if (!sampled) {
        sampled = true;
        if (spi_start(A9, false, 0, EXTERNAL_FLASH_SPI_CLOCK_DIVISOR)) {
            identity_ok = spi_write(0x9f) >= 0 && spi_receive(identity, sizeof(identity)) == SPI_STATUS_SUCCESS;
            spi_stop();
        }
        if (spi_start(A9, false, 0, EXTERNAL_FLASH_SPI_CLOCK_DIVISOR)) {
            const uint8_t command[] = {0x5a, 0, 0, 0, 0};
            sfdp_ok                 = spi_transmit(command, sizeof(command)) == SPI_STATUS_SUCCESS && spi_receive(sfdp, sizeof(sfdp)) == SPI_STATUS_SUCCESS;
            spi_stop();
        }
    }
    if (timer_elapsed32(last_print) < 1000) {
        return;
    }
    last_print = timer_read32();
    uprintf("MD770 JEDEC ok=%u id=%02X%02X%02X SFDP ok=%u\n", identity_ok, identity[0], identity[1], identity[2], sfdp_ok);
    for (uint16_t offset = 0; offset < sizeof(sfdp); offset += 16) {
        uprintf("MD770 SFDP %03X:", offset);
        for (uint8_t i = 0; i < 16; ++i) {
            uprintf("%02X", sfdp[offset + i]);
        }
        uprintf("\n");
    }
}
