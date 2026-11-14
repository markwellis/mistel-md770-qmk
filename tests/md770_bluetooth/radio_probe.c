// Copyright 2026 Mark Ellis (@markwellis)
// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include "raw_hid.h"
#include "radio_probe.h"
#include <string.h>

static uint8_t          rx[24];
static volatile uint8_t count;
static uint32_t         started;
static bool             released;
static bool             requested;
static uint32_t         requested_at;

static void capture_start(const uint8_t *packet, uint8_t length) {
    SPI0->IER        = 0;
    RSTCU->APBPRSTR0 = RSTCU_APBPRSTR0_SPI0RST;
    SPI0->CR1        = 0x0108;
    SPI0->CPR        = 0x17;
    SPI0->FCR        = 0x410;
    SPI0->CR0        = SPI_CR0_SPIEN;
    count            = 0;
    memset(rx, 0, sizeof(rx));
    for (uint8_t i = 0; i < 8; ++i) {
        SPI0->DR = i < length ? packet[i] : 0xff;
    }
    SPI0->IER = SPI_IER_RXBNEIEN;
}

void md770_radio_probe_init(void) {
    gpio_write_pin_low(C14);
    gpio_set_pin_output(C14);
    gpio_write_pin_high(D1);
    gpio_set_pin_output(D1);
    palSetLineMode(A10, PAL_MODE_HT32_AF(AFIO_GPIO) | PAL_MODE_INPUT_PULLDOWN);
    palSetGroupMode(GPIOB, 0x3c, 0, PAL_MODE_HT32_AF(AFIO_SPI) | PAL_MODE_INPUT);
    CKCU->APBCCR0 |= CKCU_APBCCR0_SPI0EN;
    nvicEnableVector(SPI0_IRQn, MD770_IRQ_PRIORITY(1));
    capture_start(NULL, 0);
    started = timer_read32();
}

OSAL_IRQ_HANDLER(HT32_SPI0_IRQ_VECTOR) {
    OSAL_IRQ_PROLOGUE();
    for (uint8_t i = 0; i < 8 && (SPI0->SR & SPI_SR_RXBNE); ++i) {
        uint8_t value = SPI0->DR;
        if (count < sizeof(rx)) {
            rx[count++] = value;
        }
        SPI0->DR = 0xff;
        if (count == sizeof(rx)) {
            SPI0->IER = 0;
            break;
        }
    }
    OSAL_IRQ_EPILOGUE();
}

void md770_radio_probe_task(void) {
    if (!released && timer_elapsed32(started) >= 1000) {
        gpio_write_pin_low(D1);
        released = true;
    }
    if (requested && ((count && gpio_read_pin(B2)) || timer_elapsed32(requested_at) >= 2000)) {
        gpio_write_pin_low(C14);
        requested = false;
    }
}

void raw_hid_receive(uint8_t *data, uint8_t length) {
    if (length != 32) {
        return;
    }
    if (data[0] != 'B' || data[1] != 'T' || data[2] != 1 || data[3] > 8) {
        data[0] = 0xff;
        raw_hid_send(data, length);
        return;
    }
    chSysLock();
    if (data[3]) {
        gpio_write_pin_low(C14);
        capture_start(data + 4, data[3]);
        requested_at = timer_read32();
        requested    = true;
        gpio_write_pin_high(C14);
    }
    memset(data, 0, length);
    data[0]         = 'B';
    data[1]         = 'T';
    data[2]         = 1;
    data[3]         = count;
    uint32_t status = SPI0->SR;
    memcpy(data + 4, &status, sizeof(status));
    memcpy(data + 8, rx, sizeof(rx));
    chSysUnlock();
    raw_hid_send(data, length);
}
