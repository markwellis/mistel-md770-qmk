// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <cassert>
#include <cstddef>
#include <cstdint>
#include <deque>
#include <vector>

#define MATRIX_ROWS 16
#define MATRIX_COLS 7
#define QK_KB 0x7e00
#define B0 16
#define B1 17
#define B8 24
#define B11 27
#define PAL_MODE_HT32_AF(n) (0x8000U | ((n) << 8))
#define PAL_MODE_OUTPUT_PUSHPULL 1U
#define PAL_MODE_INPUT 2U
#define USART_SIFR_TXC (1U << 8)
#define USART_FCR_TXR 1U
#define USART_FCR_RXR 2U
#define USART0_IRQn 23
#define HT32_USART0_IRQ_PRIORITY 0x40
#define HT32_CK_USART_FREQUENCY 48000000U
#define TIME_IMMEDIATE 0
#define MSG_OK 0

typedef uint8_t matrix_row_t;
typedef uint32_t systime_t;
typedef int msg_t;
typedef struct { uint8_t mods, reserved, keys[6]; } report_keyboard_t;
typedef struct { uint32_t speed; } SerialConfig;
struct output_queue_t { size_t used; };
struct SerialDriver { output_queue_t oqueue; unsigned state; };
struct USART_TypeDef { uint32_t DLR, CR, IER, FCR, SIFR; };
extern SerialDriver SD0;
extern USART_TypeDef usart;
#define USART0 (&usart)
struct ResetRegister {
    operator uint32_t() const { return 0; }
    void operator=(uint32_t value);
};
struct { ResetRegister APBPRSTR1; } inline rst;
#define RSTCU (&rst)

void chSysLock(void);
void chSysUnlock(void);
systime_t chVTGetSystemTimeX(void);
void gpio_write_pin_high(unsigned pin);
void gpio_set_pin_input_low(unsigned pin);
void gpio_set_pin_input_high(unsigned pin);
bool gpio_read_pin(unsigned pin);
void palSetLineMode(unsigned pin, unsigned mode);
void nvicDisableVector(unsigned vector);
void nvicEnableVector(unsigned vector, unsigned priority);
void sdStart(SerialDriver *driver, const SerialConfig *config);
msg_t sdGetTimeout(SerialDriver *driver, unsigned timeout);
size_t sdWriteTimeout(SerialDriver *driver, const uint8_t *data, size_t length, unsigned timeout);
size_t oqGetEmptyI(output_queue_t *queue);
bool oqIsEmptyI(output_queue_t *queue);
matrix_row_t matrix_get_row(uint8_t row);

void sdStop(SerialDriver *driver);
void usbDisconnectBus(void *driver);
void usbConnectBus(void *driver);
