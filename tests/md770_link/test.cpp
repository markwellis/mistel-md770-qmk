// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include "keyboards/mistel/md770rgb_bt/protocol.c"
#include "keyboards/mistel/md770rgb_bt/link.c"
#include <cstdio>
#include <cstring>
#include <string>

SerialDriver SD0{};
USART_TypeDef usart{};
static bool locked, uart_irq, usb_enabled = true;
static unsigned sd_starts, uart_resets, usb_changes, rgb_sleeps, activity_calls;
static uint32_t ticks;
static bool pins[32];
static unsigned pin_modes[32];
static matrix_row_t matrix[MATRIX_ROWS], remote_rows[MATRIX_ROWS];
static uint8_t rgb[126];
static std::deque<uint8_t> input, hardware_rx;
static std::vector<std::vector<uint8_t>> frames;

void chSysLock(void) { assert(!locked); locked = true; }
void chSysUnlock(void) { assert(locked); locked = false; }
systime_t chVTGetSystemTimeX(void) { return ticks; }
void gpio_write_pin_high(unsigned pin) { pins[pin] = true; }
void gpio_set_pin_input_low(unsigned pin) { assert(pin == B8); }
void gpio_set_pin_input_high(unsigned pin) { assert(pin == B8); }
bool gpio_read_pin(unsigned pin) { assert(pin < 32); return pins[pin]; }
void palSetLineMode(unsigned pin, unsigned value) { pin_modes[pin] = value; }
void nvicDisableVector(unsigned vector) { assert(locked && vector == USART0_IRQn); uart_irq = false; }
void nvicEnableVector(unsigned vector, unsigned priority) { assert(locked && vector == USART0_IRQn && priority == HT32_USART0_IRQ_PRIORITY); uart_irq = true; }
void sdStart(SerialDriver *driver, const SerialConfig *config) {
    assert(driver == &SD0 && config->speed == 500000 && !locked);
    ++sd_starts;
    driver->state = 1;
    usart.CR = 0x1b0;
    usart.IER = 7;
    usart.DLR = HT32_CK_USART_FREQUENCY / config->speed;
    usart.SIFR = USART_SIFR_TXC;
    uart_irq = true;
}
msg_t sdGetTimeout(SerialDriver *driver, unsigned timeout) {
    assert(driver == &SD0 && timeout == TIME_IMMEDIATE && !locked);
    if (input.empty()) return -1;
    auto byte = input.front();
    input.pop_front();
    return byte;
}
size_t sdWriteTimeout(SerialDriver *driver, const uint8_t *data, size_t length, unsigned timeout) {
    assert(driver == &SD0 && timeout == TIME_IMMEDIATE && !locked);
    assert(length <= MD770_FRAME_MAX);
    frames.emplace_back(data, data + length);
    return length;
}
size_t oqGetEmptyI(output_queue_t *queue) { assert(locked); return 256 - queue->used; }
bool oqIsEmptyI(output_queue_t *queue) { assert(locked); return !queue->used; }
matrix_row_t matrix_get_row(uint8_t row) { assert(row < MATRIX_ROWS); return matrix[row]; }
void sdStop(SerialDriver *driver) {
    assert(driver == &SD0 && !locked);
    driver->state = 0;
    driver->oqueue.used = 0;
    input.clear();
    uart_irq = false;
    usart.IER = 0;
}
void md770_power_activity(bool local) { assert(!local); ++activity_calls; }
void md770_rgb_sleep(bool value) { assert(value); ++rgb_sleeps; }
const uint8_t *md770_rgb_left(void) { return rgb; }
void md770_rgb_receive(const uint8_t *payload) { memcpy(rgb, payload, sizeof(rgb)); }
void usbDisconnectBus(void *) { usb_enabled = false; ++usb_changes; }
void usbConnectBus(void *) { usb_enabled = true; ++usb_changes; }
#ifdef MD770_LEFT
void connection_set_host_noeeprom(connection_host_t host) { assert(host == (usb_enabled ? CONNECTION_HOST_USB : CONNECTION_HOST_NONE) || host == CONNECTION_HOST_NONE); }
#endif
void ResetRegister::operator=(uint32_t value) {
    assert(locked && value == 0x100);
    ++uart_resets;
    usart = {};
    usart.SIFR = 0x180;
    hardware_rx.clear();
}

static void task(uint32_t elapsed = 0) { ticks += elapsed; md770_link_task(remote_rows); }
static void receive(const uint8_t *payload, uint8_t size) {
    uint8_t frame[MD770_FRAME_MAX];
    size_t length = md770_encode(frame, payload, size);
    input.insert(input.end(), frame, frame + length);
}
static std::vector<uint8_t> payload(const std::vector<uint8_t> &frame, uint8_t size) {
    md770_parser_t decoded{};
    std::vector<uint8_t> result(size);
    unsigned packets = 0;
    for (auto byte : frame) packets += md770_receive(&decoded, byte, result.data(), size);
    assert(packets == 1);
    return result;
}
#ifdef MD770_LEFT
static void connect(void) {
    pins[B8] = true;
    for (unsigned i = 0; i < 16; ++i) task();
    assert(md770_link_connected() && !usb_enabled);
}
#endif

int main(int argc, char **argv) {
    assert(argc == 2);
    std::string test = argv[1];
    md770_link_init();
#ifndef MD770_LEFT
    assert(pin_modes[B11] == (PAL_MODE_HT32_AF(1) | PAL_MODE_OUTPUT_PUSHPULL | PAL_MODE_INPUT));
#endif
    if (test == "trace") {
        unsigned pin, elapsed;
        while (std::scanf("%u %u", &pin, &elapsed) == 2) {
            pins[B8] = pin;
            task(elapsed);
#ifdef MD770_LEFT
            std::printf("%u %u %u %zu %u %u\n", mode, mode_count, send_ticks, frames.size(), usb_changes, usb_enabled);
#else
            std::printf("%u %zu\n", send_ticks, frames.size());
#endif
        }
        return 0;
    }
#ifdef MD770_LEFT
    if (test == "filter") {
        pins[B8] = true;
        for (unsigned i = 0; i < 15; ++i) task();
        assert(!md770_link_connected() && usb_changes == 0);
        task();
        assert(md770_link_connected() && !usb_enabled && usb_changes == 1);
        pins[B8] = false;
        for (unsigned i = 0; i < 15; ++i) task();
        assert(md770_link_connected());
        task();
        assert(!md770_link_connected() && usb_enabled && usb_changes == 2);
        for (unsigned i = 0; i < 40; ++i) task();
        assert(mode_count == 0 && usb_changes == 2);
    } else if (test == "initial_low") {
        task();
        assert(mode == 0 && mode_count == 255);
        for (unsigned i = 0; i < 254; ++i) task();
        assert(mode == 0 && mode_count == 1);
        task();
        assert(mode == 1 && mode_count == 0 && usb_changes == 1);
    } else if (test == "periodic") {
        connect();
        for (unsigned i = 0; i < 63; ++i) { matrix[8] ^= 1; task(1); }
        assert(frames.size() == 63);
        matrix[8] = 7;
        task(1);
        assert(frames.size() == 64 && payload(frames.back(), 8)[0] == uint8_t(~7));
        task();
        assert(frames.size() == 64);
        for (unsigned i = 0; i < 63; ++i) task(100);
        assert(frames.size() == 64);
        task(100);
        assert(frames.size() == 65);
    } else if (test == "disabled_counter") {
        connect();
        for (unsigned i = 0; i < 10; ++i) task(1);
        pins[B8] = false;
        for (unsigned i = 0; i < 16; ++i) task();
        for (unsigned i = 0; i < 100; ++i) task(1);
        assert(send_ticks == 10);
        pins[B8] = true;
        for (unsigned i = 0; i < 16; ++i) task(1);
        assert(send_ticks == 10);
        for (unsigned i = 0; i < 53; ++i) task(1);
        assert(frames.empty());
        task(1);
        assert(frames.size() == 1);
    } else if (test == "glitch") {
        connect();
        for (unsigned i = 0; i < 63; ++i) task(1);
        pins[B8] = false;
        task(1);
        assert(frames.size() == 1 && md770_link_connected());
    } else if (test == "rgb_retention") {
        connect();
        uint8_t data[126] = {7};
        receive(data, sizeof(data));
        task();
        assert(md770_link_rgb_active() && rgb[0] == 7 && activity_calls == 1);
        task(300);
        assert(md770_link_rgb_active() && rgb[0] == 7 && !rgb_sleeps);
        receive(data, sizeof(data));
        task();
        assert(activity_calls == 2);
        memset(data, 0, sizeof(data));
        receive(data, sizeof(data));
        task();
        assert(!md770_link_rgb_active() && rgb[0] == 0);
    } else if (test == "mode_rgb") {
        connect();
        uint8_t data[126] = {1};
        receive(data, sizeof(data));
        task();
        pins[B8] = false;
        for (unsigned i = 0; i < 16; ++i) task();
        assert(!md770_link_rgb_active() && rgb_sleeps == 1);
        pins[B8] = true;
        for (unsigned i = 0; i < 16; ++i) task();
        assert(md770_link_connected() && !md770_link_rgb_active());
    } else
#else
    if (test == "periodic") {
        task(63);
        assert(frames.empty());
        rgb[0] = 9;
        task(1);
        assert(frames.size() == 1 && payload(frames[0], 126)[0] == 9);
        task(128);
        assert(frames.size() == 2);
        task();
        assert(frames.size() == 2);
    } else if (test == "retention") {
        uint8_t data[8] = {0xf0, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
        receive(data, sizeof(data));
        task();
        assert(remote_rows[8] == 15);
        task(300);
        assert(remote_rows[8] == 15);
    } else
#endif
    if (test == "busy") {
#ifdef MD770_LEFT
        connect();
#endif
        SD0.oqueue.used = 256;
#ifdef MD770_LEFT
        for (unsigned i = 0; i < 64; ++i) task(1);
#else
        task(64);
#endif
        assert(frames.empty());
        SD0.oqueue.used = 0;
        task();
        assert(frames.empty());
#ifdef MD770_LEFT
        for (unsigned i = 0; i < 63; ++i) task(1);
#else
        task(63);
#endif
        assert(frames.empty());
        task(1);
        assert(frames.size() == 1);
    } else if (test == "uart") {
        SD0.oqueue.used = 1;
        chSysLock();
        assert(!md770_link_can_sleep());
        SD0.oqueue.used = 0;
        usart.SIFR = 0;
        assert(!md770_link_can_sleep());
        usart.SIFR = USART_SIFR_TXC;
        usart.FCR = 0x50;
        assert(md770_link_can_sleep());
        assert(usart.DLR == 96 && usart.CR == 0x1b0 && !uart_resets && sd_starts == 1);
        assert(usart.FCR == 0x50 && usart.IER == 7 && usart.SIFR == USART_SIFR_TXC);
        chSysUnlock();
#ifdef MD770_LEFT
        uint8_t data[126] = {7};
#else
        uint8_t data[8] = {0xf0};
#endif
        uint8_t packet[MD770_FRAME_MAX];
        size_t length = md770_encode(packet, data, sizeof(data));
        input.insert(input.end(), packet, packet + 3);
        task();
        assert(parser.length == 3);
        input.insert(input.end(), packet + 3, packet + length);
        hardware_rx.push_back(0x55);
        md770_link_sleep(true);
        assert(sleeping && !uart_irq && !usart.CR && uart_resets == 1);
        assert(!parser.length && input.empty() && hardware_rx.empty() && SD0.state == 0);
        assert(pin_modes[B0] == PAL_MODE_HT32_AF(0) && pin_modes[B1] == (PAL_MODE_HT32_AF(6) | PAL_MODE_INPUT));
        task(100);
        assert(input.empty());
        md770_link_sleep(false);
        assert(!sleeping && uart_irq && usart.DLR == 96 && usart.CR == 0x1b0 && usart.IER == 7 && sd_starts == 2);
        assert(!parser.length && input.empty() && pins[B0]);
        receive(data, sizeof(data));
        task();
        assert(!parser.length && input.empty());
#ifdef MD770_LEFT
        assert(rgb[0] == 7 && md770_link_rgb_active());
#else
        assert(remote_rows[8] == 15);
#endif
    } else assert(false);
    std::puts((test + " passed").c_str());
}
