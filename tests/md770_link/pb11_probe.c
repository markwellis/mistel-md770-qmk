// Copyright 2026 Mark Ellis (@markwellis)
// SPDX-License-Identifier: GPL-2.0-or-later
#include "md770rgb_bt.h"
#include "protocol.h"
#include <string.h>
#include "print.h"

static md770_parser_t     parser;
static uint32_t           last_sent;
static uint32_t           last_received;
static const SerialConfig serial_config = {.speed = 500000};

static uint32_t diag_rx_bytes;
static uint32_t diag_valid_frames;
static uint32_t diag_tx_queued;
static uint32_t diag_last_report;
static uint8_t diag_recent[16];

static void link_diagnostics(void) {
    if (timer_elapsed32(diag_last_report) < 1000) {
        return;
    }
    diag_last_report = timer_read32();
    chSysLock();
    unsigned input = iqGetFullI(&SD0.iqueue);
    unsigned output = oqGetEmptyI(&SD0.oqueue);
    uint32_t cr = USART0->CR, dl = USART0->DLR, ier = USART0->IER, status = USART0->SIFR;
    uint32_t enabled = NVIC->ISER[0], pending = NVIC->ISPR[0];
    uint32_t pins = GPIOB->DINR, direction = GPIOB->DIRCR, inputs = GPIOB->INER;
    uint32_t pullup = GPIOB->PUR, pulldown = GPIOB->PDR, functions = AFIO->GPxCFGR[1][0];
    uint32_t clocks = CKCU->APBCCR0, ahb = CKCU->AHBCFGR, apb = CKCU->APBPCSR0;
    chSysUnlock();
    uprintf("MD770 link t=%lu rx=%lu frames=%lu txq=%lu iq=%u free=%u\n", (unsigned long)diag_last_report, (unsigned long)diag_rx_bytes, (unsigned long)diag_valid_frames, (unsigned long)diag_tx_queued, input, output);
    uprintf("MD770 uart cr=%08lx dl=%lu ier=%08lx sifr=%08lx irq=%08lx/%08lx\n", (unsigned long)cr, (unsigned long)dl, (unsigned long)ier, (unsigned long)status, (unsigned long)enabled, (unsigned long)pending);
    uprintf("MD770 gpio din=%04lx dir=%04lx ine=%04lx pu=%04lx pd=%04lx af=%08lx clk=%08lx/%08lx/%08lx\n", (unsigned long)pins, (unsigned long)direction, (unsigned long)inputs, (unsigned long)pullup, (unsigned long)pulldown, (unsigned long)functions, (unsigned long)clocks, (unsigned long)ahb, (unsigned long)apb);
    uprintf("MD770 recent");
    uint32_t first = diag_rx_bytes > sizeof(diag_recent) ? diag_rx_bytes - sizeof(diag_recent) : 0;
    for (uint32_t i = first; i < diag_rx_bytes; ++i) {
        uprintf(" %02x", diag_recent[i % sizeof(diag_recent)]);
    }
    uprintf("\n");
}


void md770_link_init(void) {
    palSetLineMode(B0, PAL_MODE_HT32_AF(6) | PAL_MODE_OUTPUT_PUSHPULL);
    palSetLineMode(B1, PAL_MODE_HT32_AF(6) | PAL_MODE_INPUT);
#ifdef MD770_LEFT
    gpio_set_pin_input_low(B8);
#else
    gpio_set_pin_input_high(B8);
    gpio_write_pin_high(B11);
    palSetLineMode(B11, PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_INPUT);
#endif
    sdStart(&SD0, &serial_config);
}

void md770_link_task(matrix_row_t rows[MATRIX_ROWS]) {
    link_diagnostics();
#ifdef MD770_LEFT
    uint8_t payload[126];
#else
    uint8_t payload[8];
#endif
    msg_t byte;
    while ((byte = sdGetTimeout(&SD0, TIME_IMMEDIATE)) >= MSG_OK) {
        diag_recent[diag_rx_bytes++ % sizeof(diag_recent)] = byte;
        if (md770_receive(&parser, byte, payload, sizeof(payload))) {
            last_received = timer_read32();
            ++diag_valid_frames;
#ifdef MD770_LEFT
            md770_rgb_receive(payload);
#else
            for (uint8_t i = 0; i < 8; ++i) {
                rows[8 + i] = (uint8_t)~payload[i];
            }
#endif
        }
    }
#ifndef MD770_LEFT
    if (timer_elapsed32(last_received) >= 100) {
        memset(rows + 8, 0, 8 * sizeof(matrix_row_t));
    }
#endif
    if (timer_elapsed32(last_sent) < 32) {
        return;
    }
#ifdef MD770_LEFT
    if (!gpio_read_pin(B8)) {
        return;
    }
    uint8_t keys[8];
    for (uint8_t i = 0; i < 8; ++i) {
        keys[i] = (uint8_t)~matrix_get_row(8 + i);
    }
    const uint8_t *out    = keys;
    uint8_t        length = sizeof(keys);
#else
    const uint8_t *out    = md770_rgb_left();
    uint8_t        length = 126;
#endif
    uint8_t frame[MD770_FRAME_MAX];
    size_t  frame_length = md770_encode(frame, out, length);
    chSysLock();
    bool space = oqGetEmptyI(&SD0.oqueue) >= frame_length;
    chSysUnlock();
    if (space && sdWriteTimeout(&SD0, frame, frame_length, TIME_IMMEDIATE) == frame_length) {
        last_sent = timer_read32();
        ++diag_tx_queued;
    }
}
