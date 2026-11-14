// SPDX-License-Identifier: GPL-2.0-or-later
#include "gtest/gtest.h"
#include <array>
#include <cstring>
extern "C" {
#include "quantum.h"
#include "raw_hid.h"
#include "test_matrix.h"
void md770_notification_task(void);
void advance_time(uint32_t ms);
}

static std::array<rgb_t, RGB_MATRIX_LED_COUNT> frame, displayed;

extern "C" {
led_config_t g_led_config;

static void set_colour(int index, uint8_t red, uint8_t green, uint8_t blue) {
    frame.at(index) = {red, green, blue};
}

static void set_all(uint8_t red, uint8_t green, uint8_t blue) {
    frame.fill({red, green, blue});
}

static void flush(void) {
    displayed = frame;
}

const rgb_matrix_driver_t rgb_matrix_driver = {[] {}, set_colour, set_all, flush};
}

class MD770Notification : public testing::Test {
   protected:
    void pump(unsigned milliseconds) {
        while (milliseconds--) {
            advance_time(1);
            rgb_matrix_task();
            md770_notification_task();
        }
    }

    void notify(uint8_t red = 255, uint8_t green = 0, uint8_t blue = 0) {
        uint8_t packet[32] = {'M', 'D', 1, red, green, blue};
        raw_hid_receive(packet, sizeof(packet));
    }

    void press(void) {
        press_key(0, 0);
        matrix_scan_user();
        ASSERT_TRUE(matrix_is_on(0, 0));
        release_key(0, 0);
        matrix_scan_user();
    }

    uint8_t ceiling(void) {
        return hsv_to_rgb({0, 0, RGB_MATRIX_MAXIMUM_BRIGHTNESS}).r;
    }

    void SetUp() override {
        timer_init();
        sync_timer_init();
        clear_all_keys();
        matrix_scan_user();
        press();
        eeconfig_init_quantum();
        rgb_matrix_init();
        memset(&g_led_config, 0, sizeof(g_led_config));
        memset(g_led_config.matrix_co, NO_LED, sizeof(g_led_config.matrix_co));
        for (uint8_t i = 0; i < RGB_MATRIX_LED_COUNT; ++i)
            g_led_config.flags[i] = LED_FLAG_KEYLIGHT;
        g_led_config.flags[3] = LED_FLAG_UNDERGLOW;
        rgb_matrix_set_suspend_state(false);
        rgb_matrix_enable_noeeprom();
        rgb_matrix_mode_noeeprom(RGB_MATRIX_RAINDROPS);
        rgb_matrix_set_flags_noeeprom(LED_FLAG_KEYLIGHT);
        rgb_matrix_sethsv_noeeprom(170, 255, 128);
        pump(50);
        eeconfig_force_flush_rgb_matrix();
    }
};

TEST_F(MD770Notification, ReinitialisesRaindropsAndClearsExcludedLeds) {
    notify();
    pump(40);
    for (auto colour : displayed) {
        ASSERT_GT(colour.r, ceiling() * 3 / 4);
        ASSERT_LE(colour.r, ceiling());
        ASSERT_EQ(colour.g, 0);
        ASSERT_EQ(colour.b, 0);
    }
    press();
    pump(40);
    for (unsigned i = 0; i < 3; ++i)
        EXPECT_GT(displayed[i].g + displayed[i].b, 0);
    EXPECT_EQ(displayed[3].r + displayed[3].g + displayed[3].b, 0);
    EXPECT_EQ(rgb_matrix_get_mode(), RGB_MATRIX_RAINDROPS);
    EXPECT_TRUE(rgb_matrix_is_enabled());
}

TEST_F(MD770Notification, PreservesConfigurationDuringPendingAndForcedWrites) {
    rgb_matrix_sethsv(85, 200, 80);
    const hsv_t expected = rgb_matrix_get_hsv();
    notify();
    pump(40);
    eeconfig_force_flush_rgb_matrix();
    rgb_config_t saved;
    eeconfig_read_rgb_matrix(&saved);
    EXPECT_EQ(saved.mode, RGB_MATRIX_RAINDROPS);
    EXPECT_TRUE(saved.enable);
    EXPECT_EQ(saved.flags, LED_FLAG_KEYLIGHT);
    EXPECT_EQ(saved.hsv.h, expected.h);
    EXPECT_EQ(saved.hsv.s, expected.s);
    EXPECT_EQ(saved.hsv.v, expected.v);
    press();
    pump(40);
    EXPECT_EQ(rgb_matrix_get_hsv().h, expected.h);
    EXPECT_EQ(rgb_matrix_get_hsv().s, expected.s);
    EXPECT_EQ(rgb_matrix_get_hsv().v, expected.v);
}

TEST_F(MD770Notification, OverlaysOffFramesAndRestoresOff) {
    rgb_matrix_disable_noeeprom();
    notify();
    pump(40);
    for (auto colour : displayed) {
        EXPECT_GT(colour.r, ceiling() * 3 / 4);
        EXPECT_LE(colour.r, ceiling());
    }
    EXPECT_FALSE(rgb_matrix_is_enabled());
    press();
    pump(40);
    for (auto colour : displayed)
        EXPECT_EQ(colour.r + colour.g + colour.b, 0);
    EXPECT_FALSE(rgb_matrix_is_enabled());
}

TEST_F(MD770Notification, KeepsSuspendDarkAndReinitialisesOnResume) {
    notify();
    pump(40);
    suspend_power_down_quantum();
    for (auto colour : displayed)
        EXPECT_EQ(colour.r + colour.g + colour.b, 0);
    press_key(0, 0);
    matrix_scan_user();
    ASSERT_TRUE(suspend_wakeup_condition());
    EXPECT_TRUE(keypress_is_wakeup_key(0, 0));
    EXPECT_TRUE(rgb_matrix_get_suspend_state());
    rgb_matrix_set_suspend_state(false);
    pump(40);
    for (unsigned i = 0; i < 3; ++i)
        EXPECT_GT(displayed[i].g + displayed[i].b, 0);
    EXPECT_EQ(displayed[3].r + displayed[3].g + displayed[3].b, 0);
    release_key(0, 0);
    matrix_scan_user();
    wakeup_matrix_handle_key_event(0, 0, false);
}

TEST_F(MD770Notification, KeepsOffModeSuspendDarkWithoutForegroundTasks) {
    rgb_matrix_disable_noeeprom();
    pump(40);
    notify();
    pump(40);
    for (auto colour : displayed)
        ASSERT_GT(colour.r, 0);
    suspend_power_down_quantum();
    for (auto colour : displayed)
        EXPECT_EQ(colour.r + colour.g + colour.b, 0);
    suspend_wakeup_init_quantum();
    pump(40);
    for (auto colour : displayed)
        EXPECT_GT(colour.r, 0);
    EXPECT_FALSE(rgb_matrix_is_enabled());
    press();
    pump(40);
    for (auto colour : displayed)
        EXPECT_EQ(colour.r + colour.g + colour.b, 0);
}

TEST_F(MD770Notification, KeepsResuspendDarkBeforeFirstResumedFrameFlush) {
    notify();
    pump(40);
    suspend_power_down_quantum();
    suspend_wakeup_init_quantum();
    advance_time(20);
    rgb_matrix_task();
    rgb_matrix_task();
    suspend_power_down_quantum();
    for (auto colour : displayed)
        EXPECT_EQ(colour.r + colour.g + colour.b, 0);
    suspend_wakeup_init_quantum();
    press();
    pump(40);
}

TEST_F(MD770Notification, RespectsTheBoardBrightnessLimitForWhite) {
    notify(255, 255, 255);
    pump(40);
    for (auto colour : displayed) {
        EXPECT_GT(colour.r, ceiling() * 3 / 4);
        EXPECT_GT(colour.g, ceiling() * 3 / 4);
        EXPECT_GT(colour.b, ceiling() * 3 / 4);
        EXPECT_LE(colour.r, ceiling());
        EXPECT_LE(colour.g, ceiling());
        EXPECT_LE(colour.b, ceiling());
    }
    press();
}

TEST_F(MD770Notification, IgnoresHeldKeysUntilAnotherPress) {
    press_key(0, 0);
    notify();
    matrix_scan_user();
    pump(40);
    for (auto colour : displayed)
        EXPECT_GT(colour.r, ceiling() * 3 / 4);
    release_key(0, 0);
    matrix_scan_user();
    pump(20);
    for (auto colour : displayed)
        EXPECT_GT(colour.r, ceiling() * 3 / 4);
    press();
    pump(40);
    EXPECT_EQ(displayed[3].r + displayed[3].g + displayed[3].b, 0);
}
