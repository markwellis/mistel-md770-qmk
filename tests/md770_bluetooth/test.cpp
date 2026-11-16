// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include "connection.h"
#include <cstdio>
#include <string>
#include "keyboards/mistel/md770rgb_bt/bluetooth.c"
#include "keyboards/mistel/md770rgb_bt/power.c"
#include "keyboards/mistel/md770rgb_bt/indicators.c"

bool pins[64], sel;
unsigned errors;
std::deque<uint8_t> fifo_rx, fifo_tx;
PWMDriver PWMD_GPTM0{}, PWMD_MCTM0{};
static uint32_t now;
static bool locked;
static matrix_row_t rows[MATRIX_ROWS];
static uint16_t keycodes[MATRIX_ROWS][MATRIX_COLS], system_usage, consumer_usage;
static unsigned resets, wake_requests, saved_hosts, usb_flushes;
static unsigned radio_pin_mode;
static connection_host_t host = CONNECTION_HOST_BLUETOOTH;

void chSysLock(void) { assert(!locked); locked = true; }
void chSysUnlock(void) { assert(locked); locked = false; }
void nvicEnableVector(unsigned vector, unsigned priority) { assert(vector == 21 && priority == 1); }
void palSetGroupMode(void *, unsigned mask, unsigned shift, unsigned mode) {
    assert(mask == 0x3c && !shift && (mode == PAL_MODE_HT32_AF(0) || mode == (PAL_MODE_HT32_AF(5) | PAL_MODE_INPUT)));
    radio_pin_mode = mode;
}
void palSetLineMode(unsigned pin, unsigned mode) { assert(pin < 64 && mode == (PAL_MODE_HT32_AF(4) | PAL_MODE_OUTPUT_PUSHPULL)); }
void gpio_write_pin(unsigned pin, bool value) {
    if (pin == D1 && value && !pins[pin]) ++resets;
    pins[pin] = value;
}
void gpio_write_pin_high(unsigned pin) { gpio_write_pin(pin, true); }
void gpio_write_pin_low(unsigned pin) { gpio_write_pin(pin, false); }
bool gpio_read_pin(unsigned pin) { return pins[pin]; }
void gpio_set_pin_output(unsigned) {}
void gpio_set_pin_input_low(unsigned) {}
void gpio_set_pin_input_high(unsigned) {}
uint32_t timer_read32(void) { return now; }
uint32_t timer_elapsed32(uint32_t start) { return now - start; }
uint32_t chVTGetSystemTimeX(void) { return now * 2; }
bool md770_power_sleeping(void) { return false; }
void md770_power_request(uint8_t) {}
void md770_clock_service(void) {}
matrix_row_t matrix_get_row(uint8_t row) { return rows[row]; }
uint8_t layer_switch_get_layer(keypos_t) { return 0; }
uint16_t keymap_key_to_keycode(uint8_t, keypos_t key) { return keycodes[key.row][key.col]; }
uint16_t get_event_keycode(keyevent_t event, bool) { return keycodes[event.key.row][event.key.col]; }
connection_host_t connection_get_host(void) { return host; }
void connection_set_host_noeeprom(connection_host_t next) { host = next; }
void connection_set_host(connection_host_t next) { host = next; ++saved_hosts; }
void host_task(void) {}
void host_set_system_usage(uint16_t usage) { system_usage = usage; }
void host_set_consumer_usage(uint16_t usage) { consumer_usage = usage; }
void host_system_send(uint16_t usage) { system_usage = usage; if (host == CONNECTION_HOST_BLUETOOTH) bluetooth_send_system(usage); }
void host_consumer_send(uint16_t usage) { consumer_usage = usage; if (host == CONNECTION_HOST_BLUETOOTH) bluetooth_send_consumer(usage); }
void host_resend_extra(uint8_t) { ++usb_flushes; }
void resend_keyboard_report(void) { ++usb_flushes; }
bool process_record_user(uint16_t, keyrecord_t *) { return true; }
void clear_keyboard(void) {
    report_keyboard_t zero{};
    bluetooth_send_keyboard(&zero);
    bluetooth_send_consumer(0);
    bluetooth_send_system(0);
}
void md770_rgb_sleep(bool) {}
void md770_scan_set_idle(bool) {}
void suspend_power_down_quantum(void) {}
void suspend_wakeup_init_quantum(void) {}
void suspend_power_down_user(void) {}
void suspend_wakeup_init_user(void) {}
bool shutdown_user(bool) { return true; }
void usbWakeupHost(void *) { ++wake_requests; }
bool usb_keyboard_report_pending(void) { return false; }
void usb_driver_set_enabled(void *, bool enabled) {
    if (!enabled) { USBD1.configuration = 0; USBD1.state = USB_STOP; }
    else if (USBD1.state == USB_STOP) { USBD1.configuration = 0; USBD1.state = USB_READY; }
}
void pwmStart(PWMDriver *driver, const PWMConfig *config) { driver->config = config; }
void pwmEnableChannel(PWMDriver *driver, unsigned channel, uint16_t width) { assert(channel < 4 && width <= 6000); driver->width[channel] = width; }
void wait_ms(unsigned ms) {
    assert(!locked);
    while (ms--) {
        ++now;
        md770_power_tick();
        md770_power_tick();
    }
}

static void tick(unsigned ms = 1) { wait_ms(ms); bluetooth_task(); }
static std::vector<uint8_t> clocks(const std::vector<uint8_t> &incoming, bool batched = false) {
    std::vector<uint8_t> outgoing;
    sel = true;
    for (auto byte : incoming) {
        outgoing.push_back(fifo_tx.empty() ? 0 : fifo_tx.front());
        if (!fifo_tx.empty()) fifo_tx.pop_front();
        fifo_rx.push_back(byte);
        if (!batched) radio_irq();
    }
    sel = false;
    radio_irq();
    bluetooth_task();
    return outgoing;
}
static std::vector<uint8_t> finish(void) { return clocks(std::vector<uint8_t>(tx_length)); }
static std::vector<std::vector<uint8_t>> drain(void) {
    std::vector<std::vector<uint8_t>> result;
    for (unsigned i = 0; i < 100; ++i) {
        tick(10);
        if (pins[C14]) result.push_back(finish());
        else if (!dirty && pending_command == NO_COMMAND) return result;
    }
    assert(false);
    return result;
}
static void boot(void) {
    led_init_ports();
    bluetooth_init();
    assert(pins[D1]);
    tick(1000);
    assert(!pins[D1]);
    tick(1500);
    assert(startup_attempts == 3);
    tick(10);
    assert(finish() == std::vector<uint8_t>({0xa7, 2, 0, 2}));
    clocks({0xb6, 0, 2});
    tick(10);
    assert(bluetooth_is_connected() && pending_command == NO_COMMAND);
}

int main(int argc, char **argv) {
    assert(argc == 2);
    std::string test = argv[1];
    boot();
    if (test == "sleep") {
        for (auto old_phase : {READY, OFF, FAILED}) {
            for (uint8_t command : {uint8_t(NO_COMMAND), uint8_t(0x50)}) {
                for (unsigned guard : {0, 150, 2000}) {
                    arm_receiver();
                    phase = old_phase;
                    pending_command = old_phase == READY ? command : 0;
                    ready_at = now + guard;
                    gpio_write_pin_low(C14);
                    md770_radio_power_prepare();
                    unsigned expected = old_phase == READY && command == 0x50 ? (guard ? guard : 2000) : 10;
                    bool request = pins[C14], reset = pins[D1];
                    md770_radio_power_downI();
                    assert(radio_suspended && !(CKCU->APBCCR0 & CKCU_APBCCR0_SPI0EN) && !radio_pin_mode);
                    errors = 8;
                    radio_irq();
                    assert(errors == 8 && !failed);
                    now += 5000;
                    md770_radio_power_upI();
                    assert(!radio_suspended && phase == READY && ready_at == now + expected);
                    assert(radio_pin_mode == (PAL_MODE_HT32_AF(5) | PAL_MODE_INPUT));
                    assert(pins[C14] == request && pins[D1] == reset && SPI0->CPR == 0x17);
                }
            }
        }
        md770_radio_set_clockI(8000000);
        assert(SPI0->CPR == 3);
        md770_radio_set_clockI(48000000);
        assert(SPI0->CPR == 0x17);
    } else if (test == "reports") {
        report_keyboard_t report{.mods = 2, .keys = {4}};
        bluetooth_send_keyboard(&report);
        assert(!md770_radio_key_ready(4));
        tick(10);
        assert(md770_radio_key_ready(4));
        report = {};
        bluetooth_send_keyboard(&report);
        assert(finish() == std::vector<uint8_t>({0xa1, 2, 0, 4, 0, 0, 0, 0, 0}));
        assert(drain() == std::vector<std::vector<uint8_t>>({{0xa1, 0, 0, 0, 0, 0, 0, 0, 0}}));
    } else if (test == "media") {
        host_consumer_key_event(0x183, true);
        assert(drain()[0][1] == 1);
        host_consumer_key_event(0x18a, true);
        assert(drain()[0][1] == 3);
        host_consumer_key_event(0x183, false);
        assert(drain()[0][1] == 2 && consumer_usage == 0x18a);
        host_consumer_key_event(0x18a, false);
        assert(drain()[0][1] == 0 && !consumer_usage);
        host_system_key_event(0x81, true);
        host_system_key_event(0x82, true);
        assert(drain()[0][1] == 3);
        host_system_key_event(0x81, false);
        assert(drain()[0][1] == 2 && system_usage == 0x82);
    } else if (test == "short" || test == "error" || test == "long" || test == "collision") {
        report_keyboard_t report{.keys = {4}};
        bluetooth_send_keyboard(&report);
        tick(10);
        unsigned before = resets;
        if (test == "error") { errors = 8; radio_irq(); bluetooth_task(); assert(pins[C14]); }
        else if (test == "collision") clocks({0xb6, 0, 2});
        else if (test == "short") clocks({0, 0, 0});
        else clocks(std::vector<uint8_t>(1024));
        assert(resets == before && radio_state == 4);
        if (test != "long") assert(drain()[0][3] == 4);
        else assert(drain().empty());
    } else if (test == "timeout") {
        report_keyboard_t report{.keys = {4}};
        bluetooth_send_keyboard(&report);
        tick(10);
        tick(2000);
        assert(pins[D1] && radio_state == 4 && pending_command == 0xf0);
        tick(1000);
        tick(1500);
        assert(drain()[0][3] == 4);
    } else if (test == "rx_busy") {
        sel = true;
        radio_irq();
        tick(3000);
        assert(!pins[D1]);
    } else if (test == "control_priority") {
        report_keyboard_t report{.keys = {4}};
        bluetooth_send_keyboard(&report);
        md770_radio_select(2, true);
        tick(10);
        assert(finish() == std::vector<uint8_t>({0xaa, 3, 2}));
        auto packets = drain();
        assert(packets.size() == 2 && packets[0] == std::vector<uint8_t>({0xaa, 0, 1}) && packets[1][0] == 0xa1);
    } else if (test == "pair") {
        md770_radio_select(2, true);
        tick(10);
        assert(finish() == std::vector<uint8_t>({0xaa, 3, 2}));
        tick(149);
        assert(!pins[C14]);
        tick();
        assert(finish() == std::vector<uint8_t>({0xaa, 0, 1}));
    } else if (test == "shutdown") {
        md770_radio_select(2, true);
        tick(10);
        finish();
        md770_radio_shutdown();
        tick(1000);
        assert(!pins[C14] && !SPI0->IER && !pending_command);
    } else if (test == "voltage") {
        md770_power_init();
        md770_power_task();
        PWRCU->LVDCSR |= 0x80000;
        for (unsigned i = 0; i < 49; ++i) md770_power_tick();
        md770_power_task();
        assert(battery_level == 7 && lvd_remaining == 1);
        md770_power_tick();
        PWRCU->LVDCSR &= ~0x80000U;
        md770_power_tick();
        assert(lvd_remaining == 0);
        md770_power_task();
        assert(battery_level == 6);
    } else if (test == "usb_wake") {
        host = CONNECTION_HOST_USB;
        pins[B12] = true;
        external = true;
        supply = SUPPLY_CONFIGURED;
        USBD1.state = USB_SUSPENDED;
        USBD1.configuration = 1;
        USBD1.status = 2;
        report_keyboard_t report{};
        host_keyboard_send_kb(&report);
        assert(!wake_requests);
        md770_power_task();
        assert(wake_requests == 1);
    } else if (test == "escape") {
        dirty = DIRTY_KEYBOARD;
        keycodes[0][0] = 4;
        keycodes[0][1] = QK_BLUETOOTH_PROFILE1;
        assert(!pre_process_keyevent_kb({{0, 0}, false}));
        assert(pre_process_keyevent_kb({{1, 0}, true}));
    } else if (test == "leds") {
        radio_state = 2;
        md770_radio_indicate(false);
        md770_indicators_task();
        assert(PWMD_MCTM0.width[3] == 6000);
        wait_ms(250);
        md770_indicators_task();
        assert(!PWMD_MCTM0.width[3]);
        md770_radio_indicate(true);
        md770_indicators_task();
        assert(!PWMD_MCTM0.width[3]);
    } else assert(false);
    std::puts((test + " passed").c_str());
}
