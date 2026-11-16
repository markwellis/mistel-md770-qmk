// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include <cstdio>
#include <cstring>
#include "keyboards/mistel/md770rgb_bt/rgb.c"

bool                     pins[64];
static bool              locked, scan_asleep;
static uint32_t          now;
static std::vector<bool> bits;
void                     chSysLock(void) {
    assert(!locked);
    locked = true;
}
void chSysUnlock(void) {
    assert(locked);
    locked = false;
}
void gpio_write_pin(unsigned pin, bool value) {
    if (pin == LED_CLOCK && value && !pins[pin]) {
        assert(!locked);
        bits.push_back(pins[LED_DATA]);
    }
    pins[pin] = value;
}
void gpio_write_pin_high(unsigned pin) {
    gpio_write_pin(pin, true);
}
void gpio_write_pin_low(unsigned pin) {
    gpio_write_pin(pin, false);
}
bool gpio_read_pin(unsigned pin) {
    return pins[pin];
}
void gpio_set_pin_output(unsigned) {}
void gpio_set_pin_input_high(unsigned) {}
void palSetLineMode(unsigned, unsigned) {}
void wait_ms(unsigned ms) {
    assert(!locked);
    now += ms;
}
void wait_us(unsigned) {
    assert(!locked);
}
uint32_t timer_read32(void) {
    return now;
}
uint32_t timer_elapsed32(uint32_t start) {
    return now - start;
}
void md770_scan_set_idle(bool value) {
    scan_asleep = value;
}
void md770_power_activity(bool) {}

int main(void) {
    md770_rgb_init();
    assert(!pins[C11]);
    for (unsigned value = 0; value < 256; ++value) {
        memset(colours, value, sizeof(colours));
        publish();
        startup_count = 0;
        bits.clear();
        shift_row(0);
        std::vector<bool> expected;
        auto              shift = [&expected](uint16_t word, unsigned count) {
            while (count--) {
                expected.push_back(word & 0x8000);
                word <<= 1;
            }
        };
        for (unsigned group = 0; group < 16; ++group) {
#ifndef MD770_LEFT
            shift(uint16_t(pwm_buffers[active_buffer][0][31 - 2 * group]) * 0x0101U, 10);
            uint16_t word = uint16_t(pwm_buffers[active_buffer][0][30 - 2 * group]) * 0x0101U;
#else
            uint16_t word = uint16_t(pwm_buffers[active_buffer][0][15 - group]) * 0x0101U;
#endif
            shift(word, 9);
            expected.push_back(word & 0x40);
        }
        assert(bits == expected);
    }
    md770_rgb_sleep(true);
    for (auto &component : wire_colours)
        for (auto value : component)
            assert(value == 0);
    assert(pins[C11] && !GPTM1->CTR);
    bits.clear();
    md770_rgb_sleep(false);
    assert(!pins[C11] && !priming && !bits.empty());
    bits.clear();
    md770_rgb_latch();
    assert(!bits.empty());
    bits.clear();
    md770_rgb_update();
    assert(!priming && !pins[C11] && !bits.empty());
    md770_rgb_latch();
    md770_rgb_update();
    assert(GPTM1->CTR == 1);
#ifdef MD770_LEFT
    md770_rgb_sleep(true);
    uint8_t payload[126]{};
    md770_rgb_receive(payload);
    assert(asleep);
    payload[0] = 128;
    md770_rgb_receive(payload);
    assert(asleep && pins[C11]);
    assert(colours[0][0] == 128 && md770_rgb_left()[0] == 0);
#else
    assert(!scan_asleep);
#endif
    puts("RGB waveform, sleep pins and synchronous wake priming passed");
}
