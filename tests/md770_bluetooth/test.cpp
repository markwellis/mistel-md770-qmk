// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include "connection.h"
#include "usb_device_state.h"
#include <cstdio>
#include <string>
#include "keyboards/mistel/md770rgb_bt/bluetooth.c"
#include "keyboards/mistel/md770rgb_bt/power.c"
#include "keyboards/mistel/md770rgb_bt/indicators.c"

bool                                     pins[64], sel;
unsigned                                 errors;
std::deque<uint8_t>                      fifo_rx, fifo_tx;
PWMDriver                                PWMD_GPTM0{}, PWMD_MCTM0{};
static uint32_t                          now;
static bool                              locked, automatic, consumed, rgb_asleep, scan_idle;
static unsigned                          resets, wake_requests, sleeps, wakes, saved_hosts;
static unsigned                          cue_edges;
static unsigned                          status_reads, tail_error;
static bool                              checking_cue;
static connection_host_t                 host      = CONNECTION_HOST_BLUETOOTH;
static usb_configure_state_t             usb_state = USB_DEVICE_STATE_INIT;
static std::vector<std::vector<uint8_t>> frames;

void chSysLock(void) {
    assert(!locked);
    locked = true;
}
void chSysUnlock(void) {
    assert(locked);
    locked = false;
}
void nvicEnableVector(unsigned v, unsigned p) {
    assert(v == 21 && p == 1);
}
void palSetGroupMode(void *, unsigned mask, unsigned shift, unsigned mode) {
    assert(mask == 0x3c && shift == 0 && mode == PAL_MODE_HT32_AF(5));
}
void palSetLineMode(unsigned pin, unsigned mode) {
    assert(pin < 64 && mode == (PAL_MODE_HT32_AF(4) | PAL_MODE_OUTPUT_PUSHPULL));
}
void gpio_write_pin(unsigned pin, bool value) {
    assert(pin < 64);
    if (pin == D1 && value && !pins[pin]) ++resets;
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
void     gpio_set_pin_output(unsigned) {}
void     gpio_set_pin_input_low(unsigned) {}
void     gpio_set_pin_input_high(unsigned) {}
uint32_t timer_read32(void) {
    return now;
}
uint32_t timer_elapsed32(uint32_t start) {
    return now - start;
}
connection_host_t connection_get_host(void) {
    return host;
}
void connection_set_host_noeeprom(connection_host_t next) {
    host = next;
}
void connection_set_host(connection_host_t next) {
    host = next;
    ++saved_hosts;
}
usb_configure_state_t usb_device_state_get_configure_state(void) {
    return usb_state;
}
bool process_record_user(uint16_t, keyrecord_t *) {
    return !consumed;
}
void clear_keyboard(void) {
    report_keyboard_t zero{};
    bluetooth_send_keyboard(&zero);
    bluetooth_send_consumer(0);
    bluetooth_send_system(0);
}
void md770_rgb_sleep(bool value) {
    rgb_asleep = value;
}
void md770_scan_set_idle(bool value) {
    scan_idle = value;
}
void suspend_power_down_quantum(void) {
    ++sleeps;
}
void suspend_wakeup_init_quantum(void) {
    ++wakes;
}
void usbWakeupHost(void *) {
    ++wake_requests;
}
void pwmStart(PWMDriver *driver, const PWMConfig *config) {
    assert(config->frequency == 24000000 && config->period == UINT16_MAX);
    driver->config = config;
}
void pwmEnableChannel(PWMDriver *driver, unsigned channel, uint16_t width) {
    assert(channel < 4 && width <= 6000);
    driver->width[channel] = width;
}
void suspend_power_down_user(void) {}
void suspend_wakeup_init_user(void) {}
bool shutdown_user(bool) {
    return true;
}

static std::vector<uint8_t> clocks(std::vector<uint8_t> incoming, bool late_irq = false) {
    std::vector<uint8_t> outgoing;
    sel = true;
    for (auto byte : incoming) {
        outgoing.push_back(fifo_tx.empty() ? 0 : fifo_tx.front());
        if (!fifo_tx.empty()) fifo_tx.pop_front();
        fifo_rx.push_back(byte);
        if (!late_irq) radio_irq();
    }
    sel = false;
    if (late_irq) radio_irq();
    return outgoing;
}

void wait_ms(unsigned ms) {
    assert(!locked);
    if (checking_cue) {
        assert(ms == 100);
        unsigned width = cue_edges++ % 2 ? 0 : 6000;
        assert(PWMD_GPTM0.width[0] == width && PWMD_GPTM0.width[1] == width && PWMD_GPTM0.width[2] == width && PWMD_MCTM0.width[0] == width);
    }
    while (ms--) {
        ++now;
        if (automatic && pins[C14]) {
            frames.push_back(clocks(std::vector<uint8_t>(tx_length)));
        }
    }
}

static void tick(unsigned ms = 1) {
    wait_ms(ms);
    bluetooth_task();
}
static void boot(bool select_early = false) {
    bluetooth_init();
    if (select_early) md770_radio_select(2, false);
    assert(pins[D1] && !pins[C14]);
    tick(999);
    assert(pins[D1]);
    tick();
    assert(!pins[D1]);
    tick(1499);
    assert(!SPI0->IER);
    tick();
    assert(SPI0->CR0 == 1 && SPI0->CR1 == 0x108 && SPI0->FCR == 0x410 && SPI0->IER == 0xfc);
    tick(10);
    assert(pins[C14]);
    assert(clocks({0, 0, 0, 0}) == std::vector<uint8_t>({0xa7, 2, 0, 2}));
    tick();
    assert(!pins[C14] && radio_state == 2);
    clocks({0xb6, 0, 2});
    tick();
    assert(bluetooth_is_connected());
    automatic = true;
    for (unsigned i = 0; i < 100; ++i)
        tick();
    assert(!count && !pins[C14]);
    frames.clear();
}

static void drain(void) {
    automatic = true;
    for (unsigned i = 0; i < 1000 && (count || pins[C14] || resynchronise); ++i)
        tick();
    assert(!count && !pins[C14]);
}

static void radio_tests(const std::string &test) {
    boot(test == "startup_selection");
    if (test == "startup_selection") {
        assert(!pending_slot && radio_state == 2);
        return;
    }
    if (test == "reports" || test == "macro") {
        unsigned presses = test == "macro" ? 128 : 1;
        for (unsigned i = 0; i < presses; ++i) {
            report_keyboard_t report{99, 2, 99, {4, 5, 6, 7, 8, 9}};
            bluetooth_send_keyboard(&report);
            report = {};
            bluetooth_send_keyboard(&report);
        }
        drain();
        assert(resets == 1 && frames.size() == presses * 2);
        for (unsigned i = 0; i < presses; ++i) {
            assert(frames[i * 2] == std::vector<uint8_t>({0xa1, 2, 0, 4, 5, 6, 7, 8, 9}));
            assert(frames[i * 2 + 1] == std::vector<uint8_t>({0xa1, 0, 0, 0, 0, 0, 0, 0, 0}));
        }
    } else if (test == "media") {
        const uint16_t usages[] = {0x183, 0x18a, 0x192, 0x194, 0xcd, 0xb7, 0xb6, 0xb5, 0xe2, 0xea, 0xe9, 0x221, 0x223, 0x224, 0x225, 0x226, 0x227, 0x22a};
        for (auto usage : usages) {
            bluetooth_send_consumer(usage);
            bluetooth_send_consumer(0);
        }
        bluetooth_send_consumer(0xffff);
        for (auto usage : {0x81, 0x82, 0x83, 0x80, 0xffff})
            bluetooth_send_system(usage);
        drain();
        for (unsigned i = 0; i < ARRAY_SIZE(usages); ++i) {
            std::vector<uint8_t> expected{0xa2, 0, 0, 0, 0};
            expected[1 + i / 8] = 1U << (i % 8);
            assert(frames[i * 2] == expected && frames[i * 2 + 1] == std::vector<uint8_t>({0xa2, 0, 0, 0, 0}));
        }
        assert(frames[36] == std::vector<uint8_t>({0xa2, 0, 0, 0, 0}));
        for (unsigned i = 0; i < 5; ++i)
            assert(frames[37 + i] == std::vector<uint8_t>({0xa3, static_cast<uint8_t>(i < 3 ? 1U << i : 0)}));
    } else if (test == "tail_byte" || test == "tail_error") {
        automatic = false;
        report_keyboard_t report{0, 2, 0, {4}};
        bluetooth_send_keyboard(&report);
        tick(10);
        clocks(std::vector<uint8_t>(8));
        sel         = true;
        tail_error  = test == "tail_error" ? 0x10 : 0;
        status_hook = [] {
            if (++status_reads != 2) return;
            assert(fifo_tx.size() == 1);
            fifo_tx.pop_front();
            fifo_rx.push_back(0);
            sel         = false;
            errors      = tail_error;
            status_hook = nullptr;
        };
        tick();
        assert(status_reads == 2 && !count);
        assert(bluetooth_is_connected() == (tail_error == 0));
        assert(pins[D1] == (tail_error != 0));
    } else if (test == "short" || test == "timeout" || test == "error" || test == "pending_error") {
        automatic = false;
        report_keyboard_t report{0, 2, 0, {4}};
        bluetooth_send_keyboard(&report);
        tick(10);
        assert(pins[C14]);
        if (test == "short") clocks({0, 0});
        if (test == "error") {
            errors = 0x10;
            radio_irq();
        }
        if (test == "pending_error") {
            clocks(std::vector<uint8_t>(9));
            errors = 0x10;
        }
        tick(test == "timeout" ? 2000 : 1);
        assert(pins[D1] && !pins[C14] && !bluetooth_is_connected());
        tick(1000);
        tick(1500);
        tick(10);
        clocks({0, 0, 0, 0});
        tick();
        clocks({0xb6, 0, 2});
        tick();
        drain();
        assert(frames.size() == 6);
        assert(frames[0] == std::vector<uint8_t>({0xa1, 0, 0, 0, 0, 0, 0, 0, 0}));
        assert(frames[3] == std::vector<uint8_t>({0xa1, 2, 0, 4, 0, 0, 0, 0, 0}));
    } else if (test == "long_frame" || test == "collision") {
        automatic = false;
        report_keyboard_t report{0, 2, 0, {4}};
        bluetooth_send_keyboard(&report);
        tick(10);
        if (test == "long_frame") {
            auto outgoing = clocks(std::vector<uint8_t>(16));
            assert(outgoing[0] == 0xa1 && outgoing[1] == 2 && outgoing[3] == 4);
            tick();
            assert(!count && bluetooth_is_connected());
        } else {
            clocks({0xb1, 2});
            tick();
            assert(count == 1 && bluetooth_is_connected() && radio_leds == 2);
            tick(10);
            assert(pins[C14]);
            clocks({0xb7, 2, 0, 0, 0, 0, 0, 0, 0});
            tick();
            assert(count == 1);
            drain();
            assert(frames[0] == std::vector<uint8_t>({0xa1, 2, 0, 4, 0, 0, 0, 0, 0}));
        }
    } else if (test == "reconnect_retry") {
        automatic = false;
        report_keyboard_t report{0, 2, 0, {4}};
        bluetooth_send_keyboard(&report);
        tick(10);
        clocks({0xb1, 2});
        tick();
        assert(retry);
        clocks({0xb6, 0, 0});
        tick();
        assert(!retry && !bluetooth_is_connected());
        clocks({0xb6, 0, 2});
        tick();
        report.keys[0] = 5;
        bluetooth_send_keyboard(&report);
        report = {};
        bluetooth_send_keyboard(&report);
        drain();
        assert(frames[0] == std::vector<uint8_t>({0xa1, 2, 0, 5, 0, 0, 0, 0, 0}));
        assert(frames[1] == std::vector<uint8_t>({0xa1, 0, 0, 0, 0, 0, 0, 0, 0}));
    } else if (test == "late_irq") {
        automatic = false;
        clocks({0xb1, 2}, true);
        tick();
        assert(bluetooth_keyboard_leds() == 2 && phase == READY);
        clocks({0xb6, 0}, true);
        tick();
        assert(bluetooth_is_connected());
        clocks({0xb6, 0, 0}, true);
        tick();
        assert(!bluetooth_is_connected());
    } else if (test == "replace_pair") {
        md770_radio_select(1, true);
        for (unsigned i = 0; i < 100 && phase != PAIR_DELAY; ++i)
            tick();
        assert(phase == PAIR_DELAY);
        md770_radio_select(2, false);
        for (unsigned i = 0; i < 300; ++i)
            tick();
        for (auto frame : frames)
            assert(frame != std::vector<uint8_t>({0xaa, 0, 1}));
        assert(frames.back() == std::vector<uint8_t>({0xaa, 3, 2}));
    } else if (test == "selection" || test == "pair") {
        keyrecord_t record{{true}};
        process_record_kb(QK_BLUETOOTH_PROFILE1, &record);
        if (test == "pair")
            tick(3000);
        else {
            record.event.pressed = false;
            process_record_kb(QK_BLUETOOTH_PROFILE1, &record);
        }
        for (unsigned i = 0; i < 500; ++i)
            tick();
        unsigned select = 0;
        for (; select < frames.size(); ++select)
            if (frames[select] == std::vector<uint8_t>({0xaa, 3, 1})) break;
        assert(select >= 3 && select < frames.size() && saved_hosts == 1);
        for (unsigned i = 0; i < select; ++i)
            for (unsigned j = 1; j < frames[i].size(); ++j)
                assert(frames[i][j] == 0);
        if (test == "pair") assert(frames[select + 1] == std::vector<uint8_t>({0xaa, 0, 1}));
        assert(radio_phases != 0);
    } else if (test == "shutdown" || test == "shutdown_backlog") {
        report_keyboard_t report{0, 2, 0, {4}};
        bluetooth_send_keyboard(&report);
        drain();
        frames.clear();
        if (test == "shutdown_backlog") {
            for (unsigned i = 0; i < 15; ++i)
                bluetooth_send_keyboard(&report);
            tick(10);
            frames.clear();
        }
        md770_radio_shutdown();
        assert(stopped && !SPI0->IER && !pins[C14]);
        assert(frames.size() >= 3);
        unsigned start = test == "shutdown_backlog" ? 1 : 0;
        for (unsigned j = start; j < frames.size(); ++j)
            for (unsigned i = 1; i < frames[j].size(); ++i)
                assert(frames[j][i] == 0);
    } else if (test == "queue_stall") {
        automatic = false;
        for (unsigned i = 0; i < 32; ++i) {
            report_keyboard_t report{0, 0, 0, {static_cast<uint8_t>(i + 4)}};
            bluetooth_send_keyboard(&report);
        }
        assert(!bluetooth_is_connected() && phase == RESET_HIGH && now < 6000);
    } else
        assert(false);
}

static void power_tests(const std::string &test) {
    pins[B12] = test != "voltage" && test != "idle";
    md770_power_init();
    md770_power_task();
    if (test == "charging") {
        assert(md770_charge_indicated());
        USBD1.configuration = 1;
        usb_state           = USB_DEVICE_STATE_CONFIGURED;
        md770_power_task();
        assert(host == CONNECTION_HOST_USB && eligible);
        connection_set_host_noeeprom(CONNECTION_HOST_BLUETOOTH);
        md770_power_task();
        assert(host == CONNECTION_HOST_BLUETOOTH);
        USBD1.configuration = 0;
        usb_state           = USB_DEVICE_STATE_INIT;
        md770_power_task();
        assert(!eligible);
        USBD1.configuration = 1;
        usb_state           = USB_DEVICE_STATE_CONFIGURED;
        md770_power_task();
        assert(eligible);
        pins[B12] = false;
        md770_power_task();
        assert(!eligible && host == CONNECTION_HOST_BLUETOOTH);
        radio_state   = 4;
        pins[A10]     = true;
        pins[B12]     = true;
        battery_level = 4;
        PWRCU->LVDCSR = 0x70000;
        md770_power_task();
        assert(md770_battery_low() && PWRCU->LVDCSR == 0x70000 && !eligible);
        pins[A10] = false;
        md770_power_task();
        assert(!md770_battery_low() && eligible && !(PWRCU->LVDCSR & 0x10000));
    } else if (test == "voltage") {
        for (unsigned level = 7; level; --level) {
            md770_power_task();
            assert(battery_level == level);
            PWRCU->LVDCSR |= 0x80000;
            md770_power_task();
            now += 24;
            md770_power_task();
            assert(battery_level == level);
            PWRCU->LVDCSR &= ~0x80000U;
            md770_power_task();
            PWRCU->LVDCSR |= 0x80000;
            md770_power_task();
            now += 25;
            md770_power_task();
            assert(battery_level == level - 1);
            assert(md770_battery_low() == (level - 1 < 5));
        }
        md770_power_task();
        assert(rgb_asleep);
        pins[B12] = true;
        md770_power_task();
        assert(!md770_battery_low() && !rgb_asleep);
        pins[B12] = false;
        md770_power_task();
        assert(md770_battery_low());
    } else if (test == "idle") {
        now = 599999;
        md770_power_task();
        assert(!idle);
        ++now;
        md770_power_task();
        assert(idle && scan_idle && rgb_asleep);
        md770_power_activity(false);
        md770_power_task();
        assert(idle);
        md770_power_activity(true);
        md770_power_task();
        assert(!idle && !rgb_asleep);
        now = UINT32_MAX - 100;
        md770_power_activity(true);
        now = 200;
        md770_power_task();
        assert(!idle);
    } else if (test == "usb") {
        usb_state = USB_DEVICE_STATE_SUSPEND;
        md770_power_task();
        assert(host == CONNECTION_HOST_BLUETOOTH && !md770_power_usb_suspended());
        USBD1.configuration = 1;
        usb_state           = USB_DEVICE_STATE_CONFIGURED;
        md770_power_task();
        usb_state = USB_DEVICE_STATE_SUSPEND;
        md770_power_task();
        assert(md770_power_usb_suspended() && sleeps == 1);
        md770_power_usb_wake();
        assert(wake_requests == 0);
        USBD1.status = 2;
        md770_power_usb_wake();
        assert(wake_requests == 1);
        md770_power_usb_wake();
        assert(wake_requests == 1);
        now += 99;
        md770_power_task();
        md770_power_usb_wake();
        assert(wake_requests == 1);
        ++now;
        md770_power_task();
        md770_power_usb_wake();
        assert(wake_requests == 2);
        host = CONNECTION_HOST_BLUETOOTH;
        md770_power_task();
        assert(!md770_power_usb_suspended() && wakes == 1 && !rgb_asleep);
        host      = CONNECTION_HOST_USB;
        usb_state = USB_DEVICE_STATE_CONFIGURED;
        md770_power_task();
        assert(!md770_power_usb_suspended());
    } else if (test == "updater") {
        led_init_ports();
        checking_cue = true;
        shutdown_kb(true);
        assert(cue_edges == 6 && !PWMD_GPTM0.width[2]);
    } else if (test == "leds") {
        led_init_ports();
        host      = CONNECTION_HOST_USB;
        pins[C13] = false;
        for (auto t : {0, 25, 50, 75, 100, 125, 3124, 3125}) {
            now = t;
            md770_indicators_task();
            bool on = t == 0 || t == 50 || t == 100 || t == 3125;
            assert(PWMD_MCTM0.width[3] == (on ? 6000 : 0));
        }
        pins[C13] = true;
        now       = 200;
        led_update_ports((led_t){.raw = 2});
        assert(PWMD_GPTM0.width[2] == 6000 && PWMD_MCTM0.width[3] == 6000);
        host       = CONNECTION_HOST_BLUETOOTH;
        radio_leds = 2;
        md770_radio_led_update();
        md770_indicators_task();
        assert(PWMD_GPTM0.width[2] == 6000);
        now += 2000;
        md770_indicators_task();
        assert(PWMD_GPTM0.width[2] == 0);
        md770_radio_led_update();
        md770_indicators_task();
        assert(PWMD_GPTM0.width[2] == 6000);
        battery_level = 4;
        pins[B12]     = false;
        md770_power_task();
        now = 125;
        md770_indicators_task();
        assert(PWMD_GPTM0.width[2] == 0);
    } else
        assert(false);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    std::string test = argv[1];
    if (test == "charging" || test == "voltage" || test == "idle" || test == "usb" || test == "leds" || test == "updater")
        power_tests(test);
    else
        radio_tests(test);
    std::printf("%s passed\n", argv[1]);
}
