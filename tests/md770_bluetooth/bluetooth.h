#pragma once
#include "quantum.h"
void bluetooth_init(void);
void bluetooth_task(void);
bool bluetooth_is_connected(void);
uint8_t bluetooth_keyboard_leds(void);
void bluetooth_send_keyboard(report_keyboard_t *);
void bluetooth_send_consumer(uint16_t);
void bluetooth_send_system(uint16_t);
