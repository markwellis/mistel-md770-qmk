// SPDX-License-Identifier: GPL-2.0-or-later
#include "quantum.h"
#include "connection.h"
#include <cstdio>
static uint8_t           mods = 2, weak_mods = 8, keys = 4;
static uint16_t          consumer = 0xe9, system_usage = 0x82;
static unsigned          wakes;
static bool preserve;
bool host_preserve_keyboard_state(void) { return preserve; }
static connection_host_t host = CONNECTION_HOST_BLUETOOTH;
void                     clear_mods(void) {
    mods = 0;
}
void clear_weak_mods(void) {
    weak_mods = 0;
}
void clear_keys(void) {
    keys = 0;
}
void host_consumer_send(uint16_t value) {
    consumer = value;
}
void host_system_send(uint16_t value) {
    system_usage = value;
}
connection_host_t connection_get_host(void) {
    return host;
}
void suspend_wakeup_init_quantum(void) {
    ++wakes;
}
void suspend_power_down_quantum(void) {}
void wait_ms(unsigned) {}
#include "platforms/chibios/suspend.c"

int main(void) {
    suspend_wakeup_init();
    assert(mods == 2 && weak_mods == 8 && keys == 4 && consumer == 0xe9 && system_usage == 0x82 && wakes == 1);
    host = CONNECTION_HOST_USB;
    suspend_wakeup_init();
    assert(!mods && !weak_mods && !keys && !consumer && !system_usage && wakes == 2);
    preserve = true;
    mods = 2; weak_mods = 8; keys = 4; consumer = 0xe9; system_usage = 0x82;
    suspend_wakeup_init();
    assert(mods == 2 && weak_mods == 8 && keys == 4 && consumer == 0xe9 && system_usage == 0x82 && wakes == 3);
    puts("ChibiOS wake retains MD770 input and keeps the default USB clearing policy");
}
