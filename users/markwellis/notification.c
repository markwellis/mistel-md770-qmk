// Copyright 2026 Mark Ellis (@markwellis)
// SPDX-License-Identifier: GPL-2.0-or-later
#include "notification.h"

#if defined(RAW_ENABLE) && defined(RGB_MATRIX_ENABLE)
#    include "lib/lib8tion/lib8tion.h"
#    include "raw_hid.h"
#    ifndef RGB_MATRIX_SLEEP
#        error Notifications require RGB_MATRIX_SLEEP
#    endif

enum { NOTIFICATION_VERSION = 1 };

static bool         active;
static rgb_t        colour;
static uint32_t     started, last_flush;
static matrix_row_t previous[MATRIX_ROWS];

static void draw_notification(void) {
    uint8_t level = scale8(sin8((timer_elapsed32(started) >> 3) + 64), RGB_MATRIX_MAXIMUM_BRIGHTNESS);
    level         = hsv_to_rgb((hsv_t){0, 0, level}).r;
    rgb_matrix_set_color_all(scale8(colour.r, level), scale8(colour.g, level), scale8(colour.b, level));
}

void raw_hid_receive(uint8_t *data, uint8_t length) {
    if (length != 32) return;
    if (data[0] != 'M' || data[1] != 'D' || data[2] != NOTIFICATION_VERSION) {
        data[0] = 0xff;
        raw_hid_send(data, length);
        return;
    }
    colour     = (rgb_t){data[3], data[4], data[5]};
    started    = timer_read32();
    last_flush = started - RGB_MATRIX_LED_FLUSH_LIMIT;
    for (uint8_t row = 0; row < MATRIX_ROWS; ++row)
        previous[row] = matrix_get_row(row);
    active = true;
    raw_hid_send(data, length);
}

static void dismiss_notification(void) {
    active = false;
    rgb_matrix_set_color_all(0, 0, 0);
    if (rgb_matrix_is_enabled()) {
        if (!rgb_matrix_get_suspend_state()) {
            // Incremental effects need a fresh frame after the overlay.
            rgb_matrix_set_suspend_state(true);
            rgb_matrix_set_suspend_state(false);
            rgb_matrix_mode_noeeprom(rgb_matrix_get_mode());
        }
    } else {
        rgb_matrix_update_pwm_buffers();
    }
}

void matrix_scan_user(void) {
    if (!active) return;
    for (uint8_t row = 0; row < MATRIX_ROWS; ++row) {
        matrix_row_t current = matrix_get_row(row);
        if (current & ~previous[row]) {
            dismiss_notification();
            return;
        }
        previous[row] = current;
    }
}

void suspend_power_down_user(void) {
    if (active && !rgb_matrix_get_suspend_state()) {
        // QMK skips clearing an off effect that was already initialised.
        rgb_matrix_set_color_all(0, 0, 0);
        rgb_matrix_set_suspend_state(true);
    }
}

bool rgb_matrix_indicators_user(void) {
    if (active && !rgb_matrix_get_suspend_state()) {
        draw_notification();
    }
    return true;
}

void housekeeping_task_keymap(void) {
    md770_notification_task();
}

void md770_notification_task(void) {
    if (!active || rgb_matrix_is_enabled() || rgb_matrix_get_suspend_state()) return;
    // QMK can clear the off-mode buffer between our timed flushes.
    draw_notification();
    if (timer_elapsed32(last_flush) >= RGB_MATRIX_LED_FLUSH_LIMIT) {
        rgb_matrix_update_pwm_buffers();
        last_flush = timer_read32();
    }
}
#endif
