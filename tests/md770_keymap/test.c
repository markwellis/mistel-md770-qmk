// SPDX-License-Identifier: GPL-2.0-or-later
#include "keyboards/mistel/md770rgb_bt/keymaps/default_mistel/keymap.h"
#include "keyboards/mistel/md770rgb_bt/md770rgb_bt.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
#ifdef RAW_ENABLE
#    include "raw_hid.h"
void matrix_scan_user(void);
bool rgb_matrix_indicators_user(void);
#endif

bool          process_record_user(uint16_t code, keyrecord_t *record);
void          housekeeping_task_user(void);
void          eeconfig_init_user_datablock(void);
layer_state_t default_layer_state_set_user(layer_state_t state);
layer_state_t layer_state_set_user(layer_state_t state);
extern hsv_t  md770_custom_colours[RGB_MATRIX_LED_COUNT];

layer_state_t       default_layer_state = 1, layer_state;
led_config_t        g_led_config;
static matrix_row_t matrix[MATRIX_ROWS];
static uint32_t     now;
static unsigned     resets, rewrites, saves;
static uint8_t      indicator;
static uint8_t      stored[RGB_MATRIX_LED_COUNT * 3];
static hsv_t        hsv = {85, 255, 64};
static uint8_t      effect;
static bool         enabled;
static rgb_t        rendered[RGB_MATRIX_LED_COUNT];
static rgb_t        published[RGB_MATRIX_LED_COUNT];
static bool         suspended;
static unsigned     flushes, restarts, lighting_writes;
#ifdef RAW_ENABLE
static uint8_t  reply[32];
static unsigned replies;
void            raw_hid_send(uint8_t *data, uint8_t length) {
    assert(length == sizeof(reply));
    memcpy(reply, data, length);
    ++replies;
}
#endif

bool md770_programming_process(uint16_t code, keyrecord_t *record) {
    (void)code;
    (void)record;
    return true;
}
void    md770_programming_task(void) {}
void    md770_playback_cancel(void) {}
uint8_t md770_programming_indicator(uint8_t colour) {
    return colour;
}
bool md770_programming_blocks_fn_swap(layer_state_t state) {
    (void)state;
    return false;
}
layer_state_t md770_programming_layers(layer_state_t state, md770_profile_t profile) {
    (void)profile;
    return state;
}
layer_state_t layer_state_set(layer_state_t state) {
    return layer_state = layer_state_set_user(state);
}
void dynamic_keymap_macro_reset(void) {}

uint8_t rgb_matrix_get_val(void) {
    return hsv.v;
}
rgb_t rgb_matrix_hsv_to_rgb(hsv_t colour) {
    return hsv_to_rgb(colour);
}
rgb_t hsv_to_rgb(hsv_t colour) {
    if (!colour.s) return (rgb_t){colour.v, colour.v, colour.v};
    return hsv_to_rgb_nocie(colour);
}
void rgb_matrix_set_color(unsigned index, uint8_t red, uint8_t green, uint8_t blue) {
    assert(index < RGB_MATRIX_LED_COUNT);
    rendered[index] = (rgb_t){red, green, blue};
}
void rgb_matrix_set_color_all(uint8_t red, uint8_t green, uint8_t blue) {
    for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; ++i)
        rgb_matrix_set_color(i, red, green, blue);
}
void rgb_matrix_update_pwm_buffers(void) {
    memcpy(published, rendered, sizeof(published));
    ++flushes;
}
bool rgb_matrix_get_suspend_state(void) {
    return suspended;
}
void rgb_matrix_set_suspend_state(bool state) {
    if (state && !suspended) {
        rgb_matrix_set_color_all(0, 0, 0);
        rgb_matrix_update_pwm_buffers();
    }
    suspended = state;
}
void rgb_matrix_mode_noeeprom(uint8_t mode) {
    assert(enabled);
    effect = mode;
    ++restarts;
}
bool rgb_matrix_check_finished_leds(unsigned last) {
    return last == RGB_MATRIX_LED_COUNT;
}
#ifndef RAW_ENABLE
uint8_t scale8(uint8_t value, uint8_t scale) {
    return (uint16_t)value * (scale + 1) >> 8;
}
#endif

#define RGB_MATRIX_EFFECT(name)
#define RGB_MATRIX_CUSTOM_EFFECT_IMPLS
#define RGB_MATRIX_USE_LIMITS(first, last)          \
    uint8_t first = 0, last = RGB_MATRIX_LED_COUNT; \
    (void)params
#define RGB_MATRIX_TEST_LED_FLAGS()
#include "keyboards/mistel/md770rgb_bt/keymaps/default_mistel/rgb_matrix_user.inc"

uint8_t get_highest_layer(layer_state_t state) {
    uint8_t layer = 0;
    while (state >>= 1)
        ++layer;
    return layer;
}
void default_layer_set(layer_state_t state) {
    default_layer_state = default_layer_state_set_user(state);
}
bool layer_state_is(uint8_t layer) {
    return (layer_state & (1UL << layer)) != 0;
}
void clear_keyboard(void) {}
void eeconfig_update_default_layer(layer_state_t state) {
    (void)state;
}
void eeconfig_disable(void) {}
void soft_reset_keyboard(void) {
    ++resets;
}
uint32_t timer_read32(void) {
    return now;
}
uint32_t timer_elapsed32(uint32_t start) {
    return now - start;
}
matrix_row_t matrix_get_row(uint8_t row) {
    return row == 7 ? 0 : matrix[row];
}
void md770_set_layer_led(uint8_t colour) {
    indicator = colour;
}
uint32_t eeconfig_update_user_datablock(const void *data, uint32_t offset, uint32_t length) {
    assert(offset + length <= sizeof(stored));
    memcpy(stored + offset, data, length);
    ++saves;
    return length;
}
uint32_t eeconfig_read_user_datablock(void *data, uint32_t offset, uint32_t length) {
    assert(offset + length <= sizeof(stored));
    memcpy(data, stored + offset, length);
    return length;
}
void rgb_matrix_enable(void) {
    enabled = true;
    ++lighting_writes;
}
bool rgb_matrix_is_enabled(void) {
    return enabled;
}
void rgb_matrix_mode(uint8_t mode) {
    effect = mode;
    ++lighting_writes;
}
uint8_t rgb_matrix_get_mode(void) {
    return effect;
}
void rgb_matrix_sethsv(uint16_t h, uint8_t s, uint8_t v) {
    hsv = (hsv_t){h, s, v};
    ++lighting_writes;
}
hsv_t rgb_matrix_get_hsv(void) {
    return hsv;
}
void rgb_matrix_step(void) {
    ++effect;
    ++lighting_writes;
}
rgb_t hsv_to_rgb_nocie(hsv_t colour) {
    return (rgb_t){colour.h, colour.s, colour.v};
}
void dynamic_keymap_set_keycode(uint8_t layer, uint8_t row, uint8_t col, uint16_t code) {
    assert((layer == PROFILE2 || layer == FN2 || layer == PN2) && row < MATRIX_ROWS && col < MATRIX_COLS && code == KC_TRNS);
    ++rewrites;
}
uint16_t keycode_at_keymap_location_raw(uint8_t layer, uint8_t row, uint8_t col) {
    (void)layer;
    (void)row;
    (void)col;
    return KC_TRNS;
}

static bool event(uint16_t code, uint8_t row, uint8_t col, bool pressed) {
    keyrecord_t record = {.event = {.type = KEY_EVENT, .key = {.row = row, .col = col}, .pressed = pressed}};
#ifdef RAW_ENABLE
    if (pressed)
        matrix[row] |= (matrix_row_t)1U << col;
    else
        matrix[row] &= ~((matrix_row_t)1U << col);
    matrix_scan_user();
#endif
    return process_record_user(code, &record);
}
static void toggle_edit(void) {
    assert(!event(MD770_RGB_EDIT, 2, 6, true));
    assert(!event(MD770_RGB_EDIT, 2, 6, false));
}

#ifdef RAW_ENABLE
static void notify(uint8_t red, uint8_t green, uint8_t blue) {
    uint8_t data[32] = {'M', 'D', 1, red, green, blue};
    raw_hid_receive(data, sizeof(data));
    assert(!memcmp(reply, data, sizeof(data)) && data[0] == 'M');
}

static void check_red(const rgb_t *frame) {
    for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; ++i) {
        assert(frame[i].r > 120 && !frame[i].g && !frame[i].b);
    }
}

static void notification_tests(void) {
    enabled                     = true;
    effect                      = RGB_MATRIX_CUSTOM_MD770_CUSTOM;
    hsv                         = (hsv_t){85, 255, 64};
    md770_custom_colours[0]     = (hsv_t){170, 255, 255};
    lighting_writes             = 0;
    unsigned        prior_saves = saves;
    effect_params_t params      = {0};
    assert(MD770_CUSTOM(&params));
    rgb_t original[RGB_MATRIX_LED_COUNT];
    memcpy(original, rendered, sizeof(original));
    assert(rgb_matrix_indicators_user());
    assert(!memcmp(original, rendered, sizeof(original)));

    notify(255, 255, 255);
    assert(rgb_matrix_indicators_user());
    for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; ++i) {
        assert(rendered[i].r && rendered[i].r <= RGB_MATRIX_MAXIMUM_BRIGHTNESS);
        assert(rendered[i].g && rendered[i].g <= RGB_MATRIX_MAXIMUM_BRIGHTNESS);
        assert(rendered[i].b && rendered[i].b <= RGB_MATRIX_MAXIMUM_BRIGHTNESS);
    }
    notify(255, 0, 0);
    assert(rgb_matrix_indicators_user());
    check_red(rendered);
    now += 1024;
    assert(rgb_matrix_indicators_user());
    assert(rendered[0].r < 4);
    now += 1024;
    assert(rgb_matrix_indicators_user());
    check_red(rendered);
    assert(effect == RGB_MATRIX_CUSTOM_MD770_CUSTOM && enabled);
    assert(hsv.h == 85 && hsv.s == 255 && hsv.v == 64);
    assert(!lighting_writes && saves == prior_saves);

    keyrecord_t release = {.event = {.type = KEY_EVENT, .key = {.row = 12, .col = 2}, .pressed = false}};
    assert(process_record_user(KC_A, &release));
    keyrecord_t synthetic = {.event = {.type = 6, .key = {.row = 12, .col = 2}, .pressed = true}};
    assert(process_record_user(KC_A, &synthetic));
    synthetic.event.type    = KEY_EVENT;
    synthetic.event.key.row = MATRIX_ROWS;
    assert(process_record_user(KC_A, &synthetic));
    assert(rgb_matrix_indicators_user());
    check_red(rendered);
    unsigned prior_restarts = restarts;
    assert(event(MO(FN), 2, 4, true));
    assert(restarts == prior_restarts + 1);
    assert(event(MO(FN), 2, 4, false));
    assert(MD770_CUSTOM(&params));
    assert(rgb_matrix_indicators_user());
    assert(!memcmp(original, rendered, sizeof(original)));
    assert(!lighting_writes && saves == prior_saves);

    enabled                = false;
    unsigned prior_flushes = flushes;
    notify(255, 0, 0);
    housekeeping_task_user();
    assert(flushes == prior_flushes + 1 && !enabled);
    check_red(published);
    enabled = true;
    rgb_matrix_set_color_all(4, 5, 6);
    assert(rgb_matrix_indicators_user());
    rgb_matrix_update_pwm_buffers();
    check_red(published);
    enabled       = false;
    prior_flushes = flushes;
    rgb_matrix_set_color_all(0, 0, 0);
    ++now;
    housekeeping_task_user();
    assert(flushes == prior_flushes);
    rgb_matrix_update_pwm_buffers();
    check_red(published);
    now += 1023;
    housekeeping_task_user();
    assert(published[0].r < 4);

    notify(0, 0, 255);
    housekeeping_task_user();
    assert(!published[0].r && !published[0].g && published[0].b > 120);
    uint8_t  invalid[32]   = {'M', 'D', 1, 255, 0, 0};
    unsigned prior_replies = replies;
    raw_hid_receive(invalid, 6);
    raw_hid_receive(NULL, 0);
    assert(replies == prior_replies);
    uint8_t bad_magic[32] = {'X', 'D', 1, 255, 0, 0};
    raw_hid_receive(bad_magic, sizeof(bad_magic));
    assert(reply[0] == 0xff);
    uint8_t unsupported_version[32] = {'M', 'D', 2, 255, 0, 0};
    raw_hid_receive(unsupported_version, sizeof(unsupported_version));
    assert(reply[0] == 0xff);
    housekeeping_task_user();
    assert(!rendered[0].r && !rendered[0].g && rendered[0].b > 120);

    suspended = true;
    rgb_matrix_set_color_all(0, 0, 0);
    rgb_matrix_update_pwm_buffers();
    prior_flushes = flushes;
    now += 512;
    housekeeping_task_user();
    assert(rgb_matrix_indicators_user());
    assert(flushes == prior_flushes && !published[0].r && !published[0].b);
    suspended = false;
    housekeeping_task_user();
    assert(published[0].b > 0);
    assert(event(KC_A, 12, 2, true));
    assert(event(KC_A, 12, 2, false));
    for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; ++i) {
        assert(!published[i].r && !published[i].g && !published[i].b);
    }
    prior_flushes = flushes;
    housekeeping_task_user();
    assert(flushes == prior_flushes && !enabled);
    assert(effect == RGB_MATRIX_CUSTOM_MD770_CUSTOM && hsv.h == 85 && hsv.s == 255 && hsv.v == 64);
    assert(!lighting_writes && saves == prior_saves);

    now = UINT32_MAX - 511;
    notify(255, 0, 0);
    housekeeping_task_user();
    check_red(published);
    now += 1024;
    housekeeping_task_user();
    assert(published[0].r < 4);
    assert(event(KC_A, 12, 2, true));
    assert(event(KC_A, 12, 2, false));

    enabled = true;
    toggle_edit();
    prior_saves           = saves;
    unsigned prior_writes = lighting_writes;
    notify(255, 0, 0);
    housekeeping_task_user();
    assert(indicator == 7 && saves == prior_saves && lighting_writes == prior_writes);
    assert(!event(KC_A, 12, 2, true));
    assert(!event(KC_A, 12, 2, false));
    toggle_edit();
    assert(saves == prior_saves + 1);
    puts("Personal notifications: breathing, repeated colours, key dismissal, off-mode render/flush ordering, suspend, timer wrap and unchanged lighting settings passed.");
}
#endif

int main(void) {
    memset(g_led_config.matrix_co, UINT8_MAX, sizeof(g_led_config.matrix_co));
    g_led_config.matrix_co[12][2] = 0;
    eeconfig_init_user_datablock();
    saves = 0;

    assert(event(MO(FN), 2, 4, true));
    assert(event(KC_B, 15, 4, true));
    toggle_edit();
    assert(indicator == 7 && enabled && effect == RGB_MATRIX_CUSTOM_MD770_CUSTOM);
    assert(event(MO(FN), 2, 4, false));
    assert(event(KC_B, 15, 4, false));

    keyrecord_t synthetic = {.event = {.key = {.row = 251, .col = 0}, .type = 6, .pressed = false}};
    assert(process_record_user(KC_A, &synthetic));
    synthetic.event.type    = 4;
    synthetic.event.key.row = 0;
    synthetic.event.pressed = true;
    assert(process_record_user(KC_A, &synthetic));
    synthetic.event.type    = KEY_EVENT;
    synthetic.event.key.row = 255;
    synthetic.event.key.col = 255;
    assert(process_record_user(KC_A, &synthetic));
    assert(md770_custom_colours[0].v == 0);

    layer_state = 1UL << PN;
    assert(!event(KC_A, 12, 2, true));
    assert(md770_custom_colours[0].v == 0);
    layer_state = 0;
    assert(!event(KC_A, 12, 2, false));
    assert(event(RM_VALU, 5, 4, true));
    assert(event(RM_VALU, 5, 4, false));
    assert(event(QK_BOOT, 6, 6, true));
    assert(event(QK_BOOT, 6, 6, false));

    assert(!event(KC_A, 12, 2, true));
    assert(md770_custom_colours[0].h == 85 && md770_custom_colours[0].v == 255);
    toggle_edit();
    assert(saves == 1 && indicator == 0 && stored[2] == 255);
    assert(!event(KC_A, 12, 2, false));
    assert(event(KC_A, 12, 2, true));
    assert(event(KC_A, 12, 2, false));

    toggle_edit();
    assert(!event(KC_A, 12, 2, true));
    assert(!event(KC_A, 12, 2, false));
    assert(md770_custom_colours[0].v == 0);
    assert(!event(KC_LALT, 12, 4, true));
    assert(!event(KC_LALT, 12, 4, false));
    assert(!event(KC_RALT, 1, 4, true));
    now += 2000;
    housekeeping_task_user();
    assert(resets == 0);
    assert(!event(KC_RALT, 1, 4, false));
    toggle_edit();

    toggle_edit();
    unsigned prior_saves = saves;
    assert(!event(MD770_RGB_NEXT, 0, 6, true));
    assert(!event(MD770_RGB_NEXT, 0, 6, false));
    assert(saves == prior_saves + 1 && indicator == 0);
    assert(event(KC_A, 12, 2, true));
    assert(event(KC_A, 12, 2, false));
    toggle_edit();
    prior_saves = saves;
    rgb_matrix_mode(RGB_MATRIX_SOLID_COLOR);
    housekeeping_task_user();
    assert(saves == prior_saves + 1 && indicator == 0);
    assert(event(KC_A, 12, 2, true));
    assert(event(KC_A, 12, 2, false));

    default_layer_set((1UL << BASE) | (1UL << PROFILE2));
    assert(indicator == 2);
    matrix[2] = 1;
    assert(!event(MD770_RESET_PROFILE, 10, 2, true));
    now += 1000;
    housekeeping_task_user();
    assert(rewrites == 0);
    assert(!event(MD770_RESET_PROFILE, 10, 2, false));
    housekeeping_task_user();
    assert(rewrites == 0);
    matrix[2] = 0;
    housekeeping_task_user();
    assert(rewrites == 3 * MATRIX_ROWS * MATRIX_COLS && indicator == 7);
    now += 1000;
    housekeeping_task_user();
    assert(indicator == 2);

    assert(event(KC_LALT, 12, 4, true));
    assert(event(KC_RALT, 1, 4, true));
    now += 999;
    housekeeping_task_user();
    assert(resets == 0);
    now += 1;
    housekeeping_task_user();
    assert(resets == 1);
    housekeeping_task_user();
    assert(resets == 1);
    assert(event(KC_LALT, 12, 4, false));
    assert(event(KC_RALT, 1, 4, false));
    memset(g_led_config.matrix_co, UINT8_MAX, sizeof(g_led_config.matrix_co));
    const uint8_t positions[][2] = {{15, 2}, {12, 2}, {12, 3}, {11, 2}, {5, 4}, {3, 4}, {0, 5}, {6, 3}, {13, 2}};
    for (unsigned i = 0; i < ARRAY_SIZE(positions); ++i)
        g_led_config.matrix_co[positions[i][0]][positions[i][1]] = i;
    effect_params_t params = {0};
    assert(MD770_CUSTOM(&params));
    assert(MD770_WASD(&params));
    for (unsigned i = 0; i < RGB_MATRIX_LED_COUNT; ++i) {
        assert(rendered[i].b == (i < 8 ? hsv.v : 0));
    }
    puts("RGB editing releases, saved colours, WASD positions, held-key profile "
         "reset and factory reset passed.");
#ifdef RAW_ENABLE
    notification_tests();
#endif
}
