// SPDX-License-Identifier: GPL-2.0-or-later
#include "dynamic_keymap.h"
#include "keyboards/mistel/md770rgb_bt/keymaps/default/keymap.h"
#include "keyboards/mistel/md770rgb_bt/md770rgb_bt.h"
#include "send_string.h"
#include "keymap_data.h"
#include "connection.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

bool          process_record_user(uint16_t code, keyrecord_t *record);
void          housekeeping_task_user(void);
bool          dip_switch_update_mask_user(uint32_t state);
layer_state_t default_layer_state_set_user(layer_state_t state);
layer_state_t layer_state_set_user(layer_state_t state);

layer_state_t       default_layer_state = 1, layer_state;
keymap_config_t     keymap_config;
static uint16_t     keycodes[19][MATRIX_ROWS][MATRIX_COLS];
static uint8_t      macros[1800], cached_layers[MATRIX_ROWS][MATRIX_COLS];
static matrix_row_t matrix[MATRIX_ROWS];
static uint32_t     now;
static unsigned     writes, resets, played;
static uint8_t      indicator, mods, weak_mods;
static uint16_t     consumer_usage, system_usage;
static bool         physical_report, host_keys[256];
static bool         bluetooth_mode;
static unsigned     radio_reports;

connection_host_t connection_get_host(void) {
    return bluetooth_mode ? CONNECTION_HOST_BLUETOOTH : CONNECTION_HOST_USB;
}
bool md770_radio_key_ready(uint16_t code) {
    (void)code;
    return radio_reports <= 8;
}
bool md770_power_usb_ready(void) {
    return true;
}
void host_task(void) {}
void md770_radio_discard_reports(void) { radio_reports = 0; }
void md770_radio_sync_reports(void) {}
void md770_playback_cancel_physical(void);
static struct {
    uint8_t  code;
    bool     down;
    uint32_t time;
} playback[512];
static uint16_t capacity = sizeof(macros);

uint8_t get_highest_layer(layer_state_t state) {
    uint8_t layer = 0;
    while (state >>= 1) {
        ++layer;
    }
    return layer;
}
void default_layer_set(layer_state_t state) {
    default_layer_state = default_layer_state_set_user(state);
}
layer_state_t layer_state_set(layer_state_t state) {
    return layer_state = layer_state_set_user(state);
}
bool layer_state_is(uint8_t layer) {
    return layer_state & (1UL << layer);
}
void clear_keyboard(void) {
    mods = weak_mods = 0;
    consumer_usage = system_usage = 0;
    memset(host_keys, 0, sizeof(host_keys));
}
void eeconfig_update_default_layer(layer_state_t state) {
    (void)state;
}
void eeconfig_disable(void) {}
void soft_reset_keyboard(void) {
    ++resets;
}
uint8_t get_mods(void) {
    return mods;
}
void set_mods(uint8_t value) {
    mods = value;
}
void send_keyboard_report(void) {
    if (bluetooth_mode) ++radio_reports;
}
uint8_t get_weak_mods(void) {
    return weak_mods;
}
void add_weak_mods(uint8_t value) {
    weak_mods |= value;
}
void del_weak_mods(uint8_t value) {
    weak_mods &= ~value;
}
void register_code(uint8_t code) {
    if (bluetooth_mode) ++radio_reports;
    if (IS_MODIFIER_KEYCODE(code))
        mods |= MOD_BIT(code);
    else if (IS_CONSUMER_KEYCODE(code))
        consumer_usage = code;
    else if (IS_SYSTEM_KEYCODE(code))
        system_usage = code;
    else {
        if (IS_BASIC_KEYCODE(code) && host_keys[code]) unregister_code(code);
        host_keys[code] = true;
    }
    if (physical_report) return;
    assert(played < ARRAY_SIZE(playback));
    playback[played].code   = code;
    playback[played].down   = true;
    playback[played++].time = now;
}
void unregister_code(uint8_t code) {
    if (bluetooth_mode) ++radio_reports;
    if (IS_MODIFIER_KEYCODE(code))
        mods &= ~MOD_BIT(code);
    else if (IS_CONSUMER_KEYCODE(code))
        consumer_usage = 0;
    else if (IS_SYSTEM_KEYCODE(code))
        system_usage = 0;
    else
        host_keys[code] = false;
    if (physical_report) return;
    assert(played < ARRAY_SIZE(playback));
    playback[played].code   = code;
    playback[played].down   = false;
    playback[played++].time = now;
}
void tap_code(uint8_t code) {
    register_code(code);
    unregister_code(code);
}
bool is_key_pressed(uint8_t code) {
    return host_keys[code];
}
uint8_t has_anykey(void) {
    for (uint8_t code = KC_A; code < KC_LCTL; ++code) {
        if (host_keys[code]) return 1;
    }
    return 0;
}
uint16_t host_last_consumer_usage(void) {
    return consumer_usage;
}
uint16_t host_last_system_usage(void) {
    return system_usage;
}
void send_char(char code) {
    tap_code(code);
}
uint32_t timer_read32(void) {
    return now;
}
uint32_t timer_elapsed32(uint32_t start) {
    return now - start;
}
matrix_row_t matrix_get_row(uint8_t row) {
    assert(row < MATRIX_ROWS);
    return matrix[row];
}
void md770_set_layer_led(uint8_t colour) {
    indicator = colour;
}
uint16_t keycode_at_keymap_location_raw(uint8_t layer, uint8_t row, uint8_t col) {
    assert(layer < 19 && row < MATRIX_ROWS && col < MATRIX_COLS);
    return compiled_keymaps[layer][row][col];
}
uint8_t dynamic_keymap_get_layer_count(void) {
    return 19;
}
uint16_t dynamic_keymap_get_keycode(uint8_t layer, uint8_t row, uint8_t col) {
    assert(layer < 19 && row < MATRIX_ROWS && col < MATRIX_COLS);
    return keycodes[layer][row][col];
}
void dynamic_keymap_set_keycode(uint8_t layer, uint8_t row, uint8_t col, uint16_t code) {
    assert(layer < 19 && row < MATRIX_ROWS && col < MATRIX_COLS);
    for (uint8_t row_index = 0; row_index < MATRIX_ROWS; ++row_index) {
        assert(!matrix[row_index]);
    }
    keycodes[layer][row][col] = code;
    ++writes;
}
uint16_t dynamic_keymap_macro_get_buffer_size(void) {
    return capacity;
}
void dynamic_keymap_macro_get_buffer(uint16_t offset, uint16_t size, uint8_t *data) {
    assert((uint32_t)offset + size <= capacity);
    memcpy(data, macros + offset, size);
}
void dynamic_keymap_macro_set_buffer(uint16_t offset, uint16_t size, uint8_t *data) {
    assert((uint32_t)offset + size <= capacity);
    memcpy(macros + offset, data, size);
}
void dynamic_keymap_macro_reset(void) {
    memset(macros, 0, sizeof(macros));
}
uint16_t keycode_config(uint16_t code) {
    if (keymap_config.swap_control_capslock && (code == KC_CAPS || code == KC_LCTL)) {
        return code == KC_CAPS ? KC_LCTL : KC_CAPS;
    }
    if (keymap_config.swap_lalt_lgui && (code == KC_LALT || code == KC_LGUI)) {
        return code == KC_LALT ? KC_LGUI : KC_LALT;
    }
    return code;
}

static uint16_t event(uint8_t row, uint8_t col, bool pressed) {
    uint8_t layer = cached_layers[row][col];
    if (pressed) {
        matrix[row] |= 1U << col;
        layer_state_t active = layer_state | default_layer_state;
        for (int candidate = 18; candidate >= 0; --candidate) {
            if ((active & (1UL << candidate)) && keycodes[candidate][row][col] != KC_TRNS) {
                layer = candidate;
                break;
            }
        }
        cached_layers[row][col] = layer;
        if (!IS_QK_MACRO(keycodes[layer][row][col])) md770_playback_cancel_physical();
        weak_mods = 0;
    } else {
        matrix[row] &= ~(1U << col);
    }
    uint16_t    code   = keycodes[layer][row][col];
    keyrecord_t record = {.event = {.key = {.row = row, .col = col}, .pressed = pressed, .type = KEY_EVENT}};
    if (process_record_user(code, &record)) {
        if (IS_QK_MOMENTARY(code)) {
            uint32_t bit = 1UL << (code & 0x1f);
            layer_state_set(pressed ? layer_state | bit : layer_state & ~bit);
        } else if (code > KC_TRNS && code <= UINT8_MAX) {
            physical_report = true;
            if (pressed)
                register_code(keycode_config(code));
            else
                unregister_code(keycode_config(code));
            physical_report = false;
        }
    }
    housekeeping_task_user();
    return code;
}
static void tap(uint8_t row, uint8_t col) {
    event(row, col, true);
    event(row, col, false);
}
static void profile_select(uint8_t selected) {
    default_layer_set((1UL << BASE) | (1UL << selected));
}
static void toggle_editor(void) {
    event(2, 4, true);
    tap(4, 4);
    event(2, 4, false);
}
static void select_target(void) {
    toggle_editor();
    assert(indicator == 7);
    tap(3, 2);
}
static void save(void) {
    tap(6, 5);
    assert(!(layer_state & ((1UL << FN) | (1UL << PN))));
}
static uint16_t macro_start(uint8_t slot) {
    uint16_t offset = 0;
    while (slot--) {
        while (macros[offset++]) {
            assert(offset < capacity);
        }
    }
    return offset;
}
static void record_pair(void) {
    tap(12, 2);
    tap(1, 2);
}
static void check_bytes(const uint8_t *bytes, size_t count) {
    uint16_t code = keycodes[PROFILE1][3][2];
    assert(IS_QK_MACRO(code));
    uint8_t  actual[256];
    unsigned used   = 0;
    uint16_t offset = macro_start(code - QK_MACRO);
    while (macros[offset]) {
        assert(macros[offset++] == SS_QMK_PREFIX);
        uint8_t command = macros[offset++];
        if (command == SS_DELAY_CODE) {
            while (macros[offset] >= '0' && macros[offset] <= '9')
                ++offset;
            assert(macros[offset++] == '|');
        } else {
            assert(used + 3 < sizeof(actual));
            actual[used++] = SS_QMK_PREFIX;
            actual[used++] = command;
            actual[used++] = macros[offset++];
        }
    }
    actual[used++] = 0;
    assert(used == count && !memcmp(actual, bytes, count));
}

static void reassignment(void) {
    profile_select(PROFILE1);
    select_target();
    tap(4, 1);
    event(6, 5, true);
    assert(writes == 0);
    event(6, 5, false);
    assert(keycodes[PROFILE1][3][2] == KC_P && writes == 1);
    toggle_editor();
    assert(indicator == 1);
    assert(event(3, 2, true) == KC_P);
    assert(event(3, 2, false) == KC_P);
    profile_select(PROFILE2);
    assert(event(3, 2, true) == KC_L);
    event(3, 2, false);
}
static void macro_recording(void) {
    profile_select(PROFILE1);
    select_target();
    record_pair();
    save();
    const uint8_t expected[] = {1, SS_DOWN_CODE, KC_A, 1, SS_UP_CODE, KC_A, 1, SS_DOWN_CODE, KC_J, 1, SS_UP_CODE, KC_J, 0};
    check_bytes(expected, sizeof(expected));
    toggle_editor();
    mods = 1;
    tap(3, 2);
    assert(played == 1 && mods == 1);
    for (unsigned i = 0; i < 200; ++i) {
        ++now;
        housekeeping_task_user();
    }
    assert(played == 4 && playback[0].code == KC_A && playback[1].code == KC_A && playback[2].code == KC_J && playback[3].code == KC_J);
    assert(playback[1].time - playback[0].time == 40 && playback[2].time - playback[1].time == 40);
    assert(macros[capacity - 1] == 0);
}
static void modifier_recording(void) {
    profile_select(PROFILE1);
    select_target();
    dip_switch_update_mask_user(1 | 2);
    event(12, 4, true);
    event(13, 3, true);
    tap(8, 2);
    event(13, 3, false);
    event(12, 4, false);
    save();
    const uint8_t expected[] = {1, 2, KC_LGUI, 1, 2, KC_LCTL, 1, 2, KC_C, 1, 3, KC_C, 1, 3, KC_LCTL, 1, 3, KC_LGUI, 0};
    check_bytes(expected, sizeof(expected));
}
static void held_recording(void) {
    profile_select(PROFILE1);
    select_target();
    event(12, 4, true);
    tap(1, 2);
    event(6, 5, true);
    event(6, 5, false);
    assert(writes == 0);
    event(12, 4, false);
    assert(writes == 1);
    const uint8_t expected[] = {1, 2, KC_LALT, 1, 2, KC_J, 1, 3, KC_J, 1, 3, KC_LALT, 0};
    check_bytes(expected, sizeof(expected));
}
static void rejected_save(void) {
    profile_select(PROFILE1);
    select_target();
    record_pair();
    save();
    uint8_t snapshot[sizeof(macros)];
    memcpy(snapshot, macros, sizeof(macros));
    uint16_t previous = keycodes[PROFILE1][3][2];
    toggle_editor();
    select_target();
    for (unsigned i = 0; i < 120; ++i) {
        tap(12, 2);
    }
    save();
    assert(keycodes[PROFILE1][3][2] == previous && !memcmp(macros, snapshot, sizeof(macros)));
    toggle_editor();
    select_target();
    record_pair();
    tap(4, 1);
    capacity             = DYNAMIC_KEYMAP_MACRO_COUNT + 30;
    macros[capacity - 1] = 0;
    memcpy(snapshot, macros, sizeof(macros));
    save();
    assert(keycodes[PROFILE1][3][2] == previous && !memcmp(macros, snapshot, sizeof(macros)));
}
static void invalid_store(void) {
    profile_select(PROFILE1);
    select_target();
    record_pair();
    macros[capacity - 1] = 0xff;
    uint8_t snapshot[sizeof(macros)];
    memcpy(snapshot, macros, sizeof(macros));
    save();
    assert(keycodes[PROFILE1][3][2] == KC_TRNS && !memcmp(macros, snapshot, sizeof(macros)));
}
static void shared_macro(void) {
    profile_select(PROFILE1);
    select_target();
    record_pair();
    save();
    uint16_t original        = keycodes[PROFILE1][3][2];
    keycodes[PROFILE2][1][2] = original;
    uint8_t  snapshot[100];
    uint16_t length = macro_start(original - QK_MACRO + 1) - macro_start(original - QK_MACRO);
    assert(length <= sizeof(snapshot));
    memcpy(snapshot, macros + macro_start(original - QK_MACRO), length);
    tap(3, 2);
    tap(4, 1);
    tap(1, 2);
    save();
    assert(keycodes[PROFILE1][3][2] != original && keycodes[PROFILE2][1][2] == original);
    assert(!memcmp(snapshot, macros + macro_start(original - QK_MACRO), length));
}
static void relocation(void) {
    profile_select(PROFILE1);
    event(2, 4, true);
    event(14, 2, true);
    now += 2999;
    housekeeping_task_user();
    assert(indicator == 1);
    now += 1;
    housekeeping_task_user();
    event(14, 2, false);
    event(2, 4, false);
    event(12, 2, true);
    assert(writes == 0);
    event(12, 2, false);
    assert(keycodes[PROFILE1][12][2] == MO(FN));
    assert(keycodes[PROFILE1][2][4] == KC_RGUI);
    event(12, 2, true);
    assert(layer_state_is(FN));
    event(12, 2, false);
    assert(!layer_state_is(FN));
    dip_switch_update_mask_user(8);
    assert(!layer_state_is(CAPS_FN));
    assert(event(12, 2, true) == MO(FN));
    event(12, 2, false);
    dip_switch_update_mask_user(0);
    assert(event(12, 2, true) == MO(FN));
    event(12, 2, false);
    profile_select(PROFILE2);
    assert(event(2, 4, true) == MO(FN));
    event(2, 4, false);
}
static void default_profile(void) {
    toggle_editor();
    assert(indicator == 7);
    tap(12, 2);
    tap(1, 2);
    save();
    toggle_editor();
    assert(writes == 1 && keycodes[DEFAULT_PROFILE][12][2] == KC_J);
    assert(event(12, 2, true) == KC_J);
    event(12, 2, false);
}
static void begin_move(uint8_t row, uint8_t col) {
    event(row, col, true);
    event(14, 2, true);
    now += 3000;
    housekeeping_task_user();
    event(14, 2, false);
    event(row, col, false);
}
static void pn_relocation(void) {
    profile_select(PROFILE1);
    begin_move(6, 5);
    tap(5, 3);
    assert(writes == 0);
    tap(8, 1);
    assert(keycodes[PROFILE1][8][1] == MO(PN));
    assert(keycodes[PROFILE1][6][5] == KC_APP);
    select_target();
    record_pair();
    tap(8, 1);
    assert(IS_QK_MACRO(keycodes[PROFILE1][3][2]));
}
static void mac_assignment(void) {
    profile_select(PROFILE1);
    dip_switch_update_mask_user(1);
    toggle_editor();
    tap(10, 0);
    tap(4, 1);
    save();
    toggle_editor();
    assert(event(10, 0, true) == KC_P);
    event(10, 0, false);
    profile_select(PROFILE2);
    assert(event(10, 0, true) == RM_VALD);
    event(10, 0, false);
}
static void mac_relocation(void) {
    profile_select(PROFILE1);
    dip_switch_update_mask_user(1);
    begin_move(2, 4);
    tap(10, 0);
    assert(event(10, 0, true) == MO(FN));
    assert(layer_state_is(FN));
    event(10, 0, false);
    assert(!layer_state_is(FN));
}
static void dip_reset(void) {
    profile_select(PROFILE1);
    dip_switch_update_mask_user(8);
    assert(layer_state_is(CAPS_FN));
    begin_move(13, 3);
    tap(12, 2);
    assert(!layer_state_is(CAPS_FN));
    event(12, 2, true);
    assert(layer_state_is(FN));
    assert(event(14, 3, true) == MD770_RESET_PROFILE);
    now += 1000;
    housekeeping_task_user();
    event(14, 3, false);
    unsigned previous_writes = writes;
    assert(keycodes[PROFILE1][12][2] == MO(FN));
    event(12, 2, false);
    assert(writes == previous_writes + 3 * MATRIX_ROWS * MATRIX_COLS);
    assert(keycodes[PROFILE1][12][2] == KC_TRNS);
    assert(layer_state_is(CAPS_FN));
    assert(event(13, 3, true) == MO(FN));
    event(13, 3, false);
    for (unsigned edge = 1; edge <= 10; ++edge) {
        now += 100;
        housekeeping_task_user();
        assert(indicator == (edge == 10 ? 1 : edge % 2 ? 0 : 7));
    }
}
static void middle_slot(void) {
    memcpy(macros, "abc\0x\0last\0", 11);
    keycodes[PROFILE1][12][2] = QK_MACRO;
    keycodes[PROFILE1][3][2]  = QK_MACRO + 1;
    keycodes[PROFILE1][1][2]  = QK_MACRO + 2;
    profile_select(PROFILE1);
    select_target();
    tap(8, 2);
    tap(8, 3);
    tap(4, 1);
    save();
    assert(keycodes[PROFILE1][3][2] == QK_MACRO + 1);
    assert(!memcmp(macros, "abc\0", 4));
    assert(!memcmp(macros + macro_start(2), "last\0", 5));
    tap(3, 2);
    tap(8, 2);
    tap(8, 3);
    save();
    assert(macros[macro_start(2) - 1] == 0);
    assert(!memcmp(macros, "abc\0", 4));
    assert(!memcmp(macros + macro_start(2), "last\0", 5));
}
static void full_slots(void) {
    for (uint8_t slot = 0; slot < DYNAMIC_KEYMAP_MACRO_COUNT; ++slot) {
        keycodes[PROFILE2][slot / MATRIX_COLS][slot % MATRIX_COLS] = QK_MACRO + slot;
    }
    uint8_t snapshot[sizeof(macros)];
    memcpy(snapshot, macros, sizeof(macros));
    profile_select(PROFILE1);
    select_target();
    record_pair();
    save();
    assert(keycodes[PROFILE1][3][2] == KC_TRNS && !memcmp(macros, snapshot, sizeof(macros)));
}
static void dip_target(void) {
    profile_select(PROFILE1);
    dip_switch_update_mask_user(8);
    event(13, 3, true);
    tap(4, 4);
    event(13, 3, false);
    tap(2, 4);
    assert(indicator == 7 && keycodes[PROFILE1][2][4] == KC_TRNS);
    tap(3, 2);
    tap(4, 1);
    save();
    event(13, 3, true);
    tap(4, 4);
    event(13, 3, false);
    profile_select(PROFILE2);
    profile_select(PROFILE1);
    assert(layer_state_is(CAPS_FN));
    assert(event(13, 3, true) == MO(FN));
    event(13, 3, false);
    dip_switch_update_mask_user(0);
    assert(event(2, 4, true) == MO(FN));
    event(2, 4, false);
}
static void dip_caps_override(void) {
    profile_select(PROFILE1);
    toggle_editor();
    tap(13, 3);
    tap(12, 2);
    save();
    toggle_editor();
    dip_switch_update_mask_user(8);
    assert(!layer_state_is(CAPS_FN));
    assert(event(13, 3, true) == KC_A);
    event(13, 3, false);
    assert(event(2, 4, true) == MO(FN));
    event(2, 4, false);
    profile_select(PROFILE2);
    assert(layer_state_is(CAPS_FN));
    profile_select(PROFILE1);
    assert(!layer_state_is(CAPS_FN));
}
static void dip_pn_target(void) {
    profile_select(PROFILE1);
    dip_switch_update_mask_user(8);
    begin_move(6, 5);
    tap(2, 4);
    assert(writes == 0);
    tap(8, 1);
    dip_switch_update_mask_user(0);
    assert(event(2, 4, true) == MO(FN));
    event(2, 4, false);
    assert(event(8, 1, true) == MO(PN));
    event(8, 1, false);
}
static void original_source(void) {
    profile_select(PROFILE1);
    select_target();
    record_pair();
    save();
    assert(IS_QK_MACRO(keycodes[PROFILE1][3][2]));
    tap(2, 2);
    tap(3, 2);
    save();
    assert(keycodes[PROFILE1][2][2] == KC_L);
}
static void function_banks(void) {
    profile_select(PROFILE1);
    toggle_editor();
    event(2, 4, true);
    tap(3, 2);
    event(2, 4, false);
    tap(4, 1);
    save();
    assert(keycodes[FN1][3][2] == KC_P);
    event(6, 5, true);
    tap(0, 1);
    event(6, 5, false);
    tap(1, 2);
    save();
    assert(keycodes[PN1][0][1] == KC_J);
    toggle_editor();
    assert(event(3, 2, true) == KC_L);
    event(3, 2, false);
    event(2, 4, true);
    assert(event(3, 2, true) == KC_P);
    event(3, 2, false);
    event(2, 4, false);
    event(6, 5, true);
    assert(event(0, 1, true) == KC_J);
    event(0, 1, false);
    event(6, 5, false);
    profile_select(PROFILE2);
    event(2, 4, true);
    assert(event(3, 2, true) == KC_RGHT);
    event(3, 2, false);
    event(2, 4, false);
}
static void macro_delays(void) {
    profile_select(PROFILE1);
    select_target();
    tap(12, 2);
    event(2, 4, true);
    tap(13, 2);
    event(2, 4, false);
    tap(1, 2);
    save();
    toggle_editor();
    tap(3, 2);
    for (unsigned i = 0; i < 200; ++i) {
        ++now;
        housekeeping_task_user();
    }
    assert(played == 4);
    assert(playback[1].time - playback[0].time == 40);
    assert(playback[2].time - playback[1].time == 15);
    assert(playback[3].time - playback[2].time == 40);
}
static void macro_limit(void) {
    profile_select(PROFILE1);
    select_target();
    for (unsigned i = 0; i < 100; ++i)
        tap(12, 2);
    save();
    assert(IS_QK_MACRO(keycodes[PROFILE1][3][2]) && indicator == 7);
}
static void default_relocation(void) {
    begin_move(2, 4);
    tap(8, 1);
    assert(keycodes[DEFAULT_PROFILE][8][1] == MO(FN) && keycodes[DEFAULT_PROFILE][2][4] == KC_RGUI);
    event(8, 1, true);
    assert(event(14, 3, true) == MD770_RESET_PROFILE);
    now += 1000;
    housekeeping_task_user();
    event(14, 3, false);
    event(8, 1, false);
    assert(keycodes[DEFAULT_PROFILE][8][1] == KC_TRNS && keycodes[DEFAULT_PROFILE][2][4] == KC_TRNS);
}
static void run_for(uint32_t milliseconds) {
    while (milliseconds--) {
        ++now;
        housekeeping_task_user();
    }
}

static void default_banks(void) {
    toggle_editor();
    tap(3, 2);
    tap(4, 1);
    save();
    toggle_editor();
    assert(event(3, 2, true) == KC_P);
    event(3, 2, false);
    event(2, 4, true);
    assert(event(3, 2, true) == KC_RGHT);
    event(3, 2, false);
    event(2, 4, false);
    toggle_editor();
    event(2, 4, true);
    tap(3, 2);
    event(2, 4, false);
    tap(1, 2);
    save();
    event(6, 5, true);
    tap(0, 1);
    event(6, 5, false);
    tap(12, 2);
    save();
    toggle_editor();
    assert(keycodes[DEFAULT_PROFILE][3][2] == KC_P);
    assert(keycodes[DEFAULT_FN][3][2] == KC_J);
    assert(keycodes[DEFAULT_PN][0][1] == KC_A);
    assert(event(3, 2, true) == KC_P);
    event(3, 2, false);
    event(2, 4, true);
    assert(event(3, 2, true) == KC_J);
    event(3, 2, false);
    event(2, 4, false);
    event(6, 5, true);
    assert(event(0, 1, true) == KC_A);
    event(0, 1, false);
    event(6, 5, false);
    profile_select(PROFILE1);
    assert(event(3, 2, true) == KC_L);
    event(3, 2, false);
    event(2, 4, true);
    assert(event(3, 2, true) == KC_RGHT);
    event(3, 2, false);
    event(2, 4, false);
    assert(!memcmp(keycodes, compiled_keymaps, 3 * sizeof(keycodes[0])));
}

static void default_mac(void) {
    dip_switch_update_mask_user(1);
    toggle_editor();
    tap(10, 0);
    tap(4, 1);
    save();
    toggle_editor();
    assert(event(10, 0, true) == KC_P);
    event(10, 0, false);
    profile_select(PROFILE1);
    assert(event(10, 0, true) == RM_VALD);
    event(10, 0, false);
    default_layer_set(1UL << BASE);
    begin_move(2, 4);
    tap(10, 0);
    assert(event(10, 0, true) == MO(FN));
    event(10, 0, false);
    profile_select(PROFILE1);
    assert(event(2, 4, true) == MO(FN));
    event(2, 4, false);
    assert(!memcmp(keycodes, compiled_keymaps, 3 * sizeof(keycodes[0])));
}

static void load_macro(const uint8_t *data, size_t size) {
    assert(size < capacity);
    profile_select(PROFILE1);
    memcpy(macros, data, size);
    keycodes[PROFILE1][3][2] = QK_MACRO;
}

static void playback_held(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_A, 1, SS_DELAY_CODE, '1', '0', '0', '|', 1, SS_UP_CODE, KC_A, 1, SS_TAP_CODE, KC_A, 'a', 0};
    load_macro(data, sizeof(data));
    event(12, 2, true);
    tap(3, 2);
    run_for(200);
    assert(played == 0 && host_keys[KC_A]);
    event(12, 2, false);
    assert(!host_keys[KC_A]);
}

static void playback_interrupt(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_LCTL, 1, SS_DOWN_CODE, KC_A, 1, SS_DELAY_CODE, '1', '0', '0', '0', '|', 1, SS_UP_CODE, KC_A, 1, SS_UP_CODE, KC_LCTL, 0};
    load_macro(data, sizeof(data));
    tap(3, 2);
    assert(played == 1 && host_keys[KC_A] && weak_mods == MOD_BIT(KC_LCTL));
    event(12, 2, true);
    assert(played == 2 && host_keys[KC_A] && !weak_mods);
    run_for(1100);
    assert(played == 2 && host_keys[KC_A]);
    event(12, 2, false);
    assert(!host_keys[KC_A]);
}

static void playback_bluetooth(void) {
    const uint8_t data[] = "abcdefghijklmnop";
    load_macro(data, sizeof(data));
    bluetooth_mode = true;
    tap(3, 2);
    assert(played > 0 && played < 32 && radio_reports <= 16);
    unsigned previous = played;
    run_for(100);
    assert(played == previous);
    event(12, 2, true);
    event(12, 2, false);
    radio_reports = 0;
    run_for(100);
    assert(played == previous);
}

static void playback_modifiers(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_LCTL, 1, SS_DELAY_CODE, '1', '0', '0', '|', 1, SS_UP_CODE, KC_LCTL, 0};
    load_macro(data, sizeof(data));
    event(14, 4, true);
    tap(3, 2);
    assert(mods == MOD_BIT(KC_LCTL) && weak_mods == MOD_BIT(KC_LCTL));
    event(14, 4, false);
    assert(!mods && weak_mods == MOD_BIT(KC_LCTL));
    run_for(100);
    assert(!mods && !weak_mods);
}

static void playback_boundaries(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_A, 1, SS_DELAY_CODE, '1', '0', 0, 1, SS_TAP_CODE, KC_C, 0};
    load_macro(data, sizeof(data));
    tap(3, 2);
    run_for(20);
    assert(played == 2 && playback[0].code == KC_A && playback[1].code == KC_A);
    assert(!host_keys[KC_A] && !host_keys[KC_C]);
}

static void playback_invalid(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_A, 0xff, 0};
    load_macro(data, sizeof(data));
    tap(3, 2);
    assert(played == 2 && !host_keys[KC_A]);
}

static void playback_dip(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_LCTL, 1, SS_DOWN_CODE, KC_A, 1, SS_DELAY_CODE, '1', '0', '0', '|', 1, SS_UP_CODE, KC_A, 1, SS_UP_CODE, KC_LCTL, 0};
    load_macro(data, sizeof(data));
    tap(3, 2);
    assert(host_keys[KC_A] && weak_mods);
    dip_switch_update_mask_user(1);
    assert(!host_keys[KC_A] && !weak_mods);
    run_for(200);
    assert(played == 2);
}

static void playback_reports(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_VOLU, 1, SS_UP_CODE, KC_VOLU, 1, SS_TAP_CODE, KC_SLEP, 0};
    load_macro(data, sizeof(data));
    keycodes[PROFILE1][12][2] = KC_VOLU;
    event(12, 2, true);
    assert(consumer_usage && !has_anykey());
    tap(3, 2);
    assert(played == 0 && consumer_usage == KC_VOLU);
    event(12, 2, false);
    keycodes[PROFILE1][12][2] = KC_SLEP;
    event(12, 2, true);
    assert(system_usage && !has_anykey());
    tap(3, 2);
    assert(played == 0 && system_usage == KC_SLEP);
    event(12, 2, false);
    tap(3, 2);
    assert(played == 4 && !consumer_usage && !system_usage);
}

static void check_repeated_key(uint8_t keycode) {
    unsigned presses = 0;
    bool     down    = false;
    for (unsigned i = 0; i < played; ++i) {
        assert(playback[i].code == keycode);
        if (playback[i].down && !down) ++presses;
        down = playback[i].down;
    }
    assert(presses == 2 && !down && !host_keys[keycode]);
}

static void playback_overlap(void) {
    profile_select(PROFILE1);
    select_target();
    event(11, 4, true);
    event(0, 4, true);
    event(11, 4, false);
    event(0, 4, false);
    save();
    const uint8_t expected[] = {1, SS_DOWN_CODE, KC_SPC, 1, SS_DOWN_CODE, KC_SPC, 1, SS_UP_CODE, KC_SPC, 1, SS_UP_CODE, KC_SPC, 0};
    check_bytes(expected, sizeof(expected));
    toggle_editor();
    tap(3, 2);
    run_for(200);
    check_repeated_key(KC_SPC);
}

static void playback_repeat_tap(void) {
    const uint8_t data[] = {1, SS_DOWN_CODE, KC_A, 1, SS_TAP_CODE, KC_A, 1, SS_UP_CODE, KC_A, 0};
    load_macro(data, sizeof(data));
    tap(3, 2);
    check_repeated_key(KC_A);
}

static void relocated_fn_delay(uint8_t row, uint8_t col) {
    profile_select(PROFILE1);
    begin_move(2, 4);
    tap(row, col);
    event(row, col, true);
    tap(4, 4);
    event(row, col, false);
    tap(3, 2);
    event(row, col, true);
    assert(layer_state_is(FN));
    event(row, col, false);
    assert(!layer_state_is(FN));
    tap(12, 2);
    save();
    assert(keycodes[PROFILE1][3][2] == KC_A);
}

static void relocated_pn_delay(void) {
    profile_select(PROFILE1);
    begin_move(6, 5);
    tap(13, 2);
    select_target();
    tap(12, 2);
    event(2, 4, true);
    tap(13, 2);
    event(2, 4, false);
    assert(keycodes[PROFILE1][3][2] == KC_A && !layer_state_is(FN));
}

static void delay_key_release(void) {
    profile_select(PROFILE1);
    select_target();
    event(13, 2, true);
    event(2, 4, true);
    event(13, 2, false);
    event(2, 4, false);
    tap(1, 2);
    save();
    const uint8_t expected[] = {1, SS_DOWN_CODE, KC_T, 1, SS_UP_CODE, KC_T, 1, SS_DOWN_CODE, KC_J, 1, SS_UP_CODE, KC_J, 0};
    check_bytes(expected, sizeof(expected));
}

int main(int argc, char **argv) {
    assert(argc == 2);
    memcpy(keycodes, compiled_keymaps, sizeof(keycodes));
    default_layer_set(default_layer_state);
    if (!strcmp(argv[1], "playback_bluetooth"))
        playback_bluetooth();
    else if (!strcmp(argv[1], "remap"))
        reassignment();
    else if (!strcmp(argv[1], "macro"))
        macro_recording();
    else if (!strcmp(argv[1], "modifiers"))
        modifier_recording();
    else if (!strcmp(argv[1], "held"))
        held_recording();
    else if (!strcmp(argv[1], "reject"))
        rejected_save();
    else if (!strcmp(argv[1], "invalid"))
        invalid_store();
    else if (!strcmp(argv[1], "shared"))
        shared_macro();
    else if (!strcmp(argv[1], "relocate"))
        relocation();
    else if (!strcmp(argv[1], "default"))
        default_profile();
    else if (!strcmp(argv[1], "pn"))
        pn_relocation();
    else if (!strcmp(argv[1], "mac_assignment"))
        mac_assignment();
    else if (!strcmp(argv[1], "mac_relocation"))
        mac_relocation();
    else if (!strcmp(argv[1], "dip_reset"))
        dip_reset();
    else if (!strcmp(argv[1], "middle"))
        middle_slot();
    else if (!strcmp(argv[1], "slots"))
        full_slots();
    else if (!strcmp(argv[1], "dip_target"))
        dip_target();
    else if (!strcmp(argv[1], "dip_caps"))
        dip_caps_override();
    else if (!strcmp(argv[1], "dip_pn"))
        dip_pn_target();
    else if (!strcmp(argv[1], "original"))
        original_source();
    else if (!strcmp(argv[1], "banks"))
        function_banks();
    else if (!strcmp(argv[1], "delays"))
        macro_delays();
    else if (!strcmp(argv[1], "limit"))
        macro_limit();
    else if (!strcmp(argv[1], "default_relocation"))
        default_relocation();
    else if (!strcmp(argv[1], "default_banks"))
        default_banks();
    else if (!strcmp(argv[1], "default_mac"))
        default_mac();
    else if (!strcmp(argv[1], "playback_held"))
        playback_held();
    else if (!strcmp(argv[1], "playback_interrupt"))
        playback_interrupt();
    else if (!strcmp(argv[1], "playback_modifiers"))
        playback_modifiers();
    else if (!strcmp(argv[1], "playback_boundaries"))
        playback_boundaries();
    else if (!strcmp(argv[1], "playback_invalid"))
        playback_invalid();
    else if (!strcmp(argv[1], "playback_dip"))
        playback_dip();
    else if (!strcmp(argv[1], "playback_reports"))
        playback_reports();
    else if (!strcmp(argv[1], "playback_overlap"))
        playback_overlap();
    else if (!strcmp(argv[1], "playback_repeat_tap"))
        playback_repeat_tap();
    else if (!strcmp(argv[1], "relocated_fn_t"))
        relocated_fn_delay(13, 2);
    else if (!strcmp(argv[1], "relocated_fn_g"))
        relocated_fn_delay(10, 2);
    else if (!strcmp(argv[1], "relocated_fn_b"))
        relocated_fn_delay(15, 4);
    else if (!strcmp(argv[1], "relocated_pn_delay"))
        relocated_pn_delay();
    else if (!strcmp(argv[1], "delay_key_release"))
        delay_key_release();
    else
        abort();
    assert(resets == 0);
    printf("%s passed\n", argv[1]);
}
