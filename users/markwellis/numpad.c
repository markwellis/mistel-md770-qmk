// Copyright 2026 Mark Ellis (@markwellis)
// SPDX-License-Identifier: GPL-2.0-or-later
#include "numpad.h"
#include "keyboards/mistel/md770rgb_bt/keymaps/default_mistel/keymap.h"

enum { NUMPAD_CAPS = QK_USER, NUMPAD_EXIT };

static const keypos_t caps   = {.row = 13, .col = 3};
static const keypos_t escape = {.row = 15, .col = 0};

static const uint8_t numpad[MATRIX_ROWS][MATRIX_COLS] = {
    [15][2] = KC_7, [15][3] = KC_8, [14][3] = KC_9,
    [12][3] = KC_4, [11][2] = KC_5, [11][3] = KC_6,
    [9][3]  = KC_1, [8][2]  = KC_2, [8][3]  = KC_3, [15][4] = KC_ENT,
    [11][4] = KC_0, [9][2]  = KC_DOT, [8][1] = KC_BSPC,

    [1][1] = KC_7, [2][1] = KC_8, [3][1] = KC_9,
    [1][2] = KC_4, [2][2] = KC_5, [3][2] = KC_6, [4][2] = KC_DOT,
    [1][3] = KC_1, [2][3] = KC_2, [3][3] = KC_3, [6][2] = KC_ENT,
    [0][4] = KC_0, [5][5] = KC_BSPC,
};

static matrix_row_t remapped[MATRIX_ROWS];
static bool         latched, caps_down, chorded;
static uint32_t     caps_started;

static bool caps_is_hold(void) {
    return chorded || timer_elapsed32(caps_started) >= TAPPING_TERM;
}

md770_numpad_side_t md770_numpad_side(void) {
    if (caps_down && caps_is_hold()) return MD770_NUMPAD_RIGHT;
    return latched ? MD770_NUMPAD_LEFT : MD770_NUMPAD_OFF;
}

static uint16_t numpad_keycode(keypos_t key) {
    if (KEYEQ(key, caps)) return NUMPAD_CAPS;
    if (KEYEQ(key, escape)) return NUMPAD_EXIT;
    return numpad[key.row][key.col];
}

bool pre_process_record_user(uint16_t keycode, keyrecord_t *record) {
    keypos_t key = record->event.key;
    if (!IS_KEYEVENT(record->event) || key.row >= MATRIX_ROWS || key.col >= MATRIX_COLS) return true;

    matrix_row_t bit = (matrix_row_t)1 << key.col;
    uint16_t     code = numpad_keycode(key);
    if (!record->event.pressed) {
        // A release must use the mapping its press used.
        if (remapped[key.row] & bit) {
            remapped[key.row] &= ~bit;
            record->keycode = code;
        }
        return true;
    }

    if (caps_down && code != NUMPAD_CAPS) chorded = true;
    if (!code || layer_state_is(FN) || layer_state_is(PN) || IS_QK_MOMENTARY(keycode)) return true;
    if (code == NUMPAD_CAPS) {
        if (keycode_config(keycode) != KC_CAPS) return true;
    } else if (!latched && !caps_down) {
        return true;
    }

    remapped[key.row] |= bit;
    record->keycode = code;
    return true;
}

void post_process_record_user(uint16_t keycode, keyrecord_t *record) {
    if (keycode == NUMPAD_CAPS) {
        if (record->event.pressed) {
            caps_started = timer_read32();
            caps_down    = true;
            chorded      = false;
        } else if (caps_down) {
            if (!caps_is_hold()) latched = !latched;
            caps_down = false;
        }
    } else if (keycode == NUMPAD_EXIT && record->event.pressed) {
        latched = caps_down = false;
    }
}

void md770_numpad_draw(md770_numpad_side_t side) {
#ifdef RGB_MATRIX_ENABLE
    uint8_t first = side == MD770_NUMPAD_RIGHT ? 0 : MATRIX_ROWS / 2;
    hsv_t   colour = {HSV_GREEN};
    colour.v      = RGB_MATRIX_MAXIMUM_BRIGHTNESS;
    rgb_t green   = hsv_to_rgb(colour);
    for (uint8_t row = first; row < first + MATRIX_ROWS / 2; ++row) {
        for (uint8_t col = 0; col < MATRIX_COLS; ++col) {
            uint8_t led = g_led_config.matrix_co[row][col];
            if (led < RGB_MATRIX_LED_COUNT && numpad_keycode((keypos_t){.row = row, .col = col})) {
                rgb_matrix_set_color(led, green.r, green.g, green.b);
            }
        }
    }
#else
    (void)side;
#endif
}
