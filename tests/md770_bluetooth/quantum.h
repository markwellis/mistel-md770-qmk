#pragma once
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <deque>
#include <vector>

#define MATRIX_ROWS 16
#define QK_KB 0x7e00
#define QK_BLUETOOTH_PROFILE1 0x7793
#define QK_BLUETOOTH_PROFILE3 0x7795
#define ARRAY_SIZE(a) (sizeof(a) / sizeof((a)[0]))
#define OSAL_IRQ_HANDLER(name) void name(void)
#define OSAL_IRQ_PROLOGUE()
#define OSAL_IRQ_EPILOGUE()
#define HT32_SPI0_IRQ_VECTOR radio_irq
#define SPI0_IRQn 21
#define MD770_IRQ_PRIORITY(n) (n)
#define CKCU_APBCCR0_SPI0EN 1
#define RSTCU_APBPRSTR0_SPI0RST 1
#define GPIOB nullptr
#define PAL_LINE(port, pad) (pad)
#define CKCU_APBCCR1_GPTM1EN 1
#define PAL_MODE_HT32_AF(n) ((n) << 8)
#define PAL_MODE_INPUT 0
#define PAL_MODE_OUTPUT_PUSHPULL 1
#define PWM_OUTPUT_DISABLED 0
#define PWM_OUTPUT_ACTIVE_LOW 1
#define A10 10
#define A14 14
#define A15 15
#define B10 26
#define B12 28
#define C4 36
#define C5 37
#define C8 40
#define C10 42
#define C11 43
#define C12 44
#define C13 45
#define C14 46
#define C15 47
#define D1 49
#define D3 51
#define LED_CAPS_LOCK_PIN C8
typedef uint8_t matrix_row_t;
typedef struct {
    uint8_t report_id, mods, reserved, keys[6];
} report_keyboard_t;
typedef struct {
    struct {
        bool pressed;
    } event;
} keyrecord_t;
typedef union {
    uint8_t raw;
    struct {
        bool num_lock : 1, caps_lock : 1;
    };
} led_t;
typedef struct {
    unsigned mode;
    void (*callback)(void);
} PWMChannelConfig;
typedef struct {
    unsigned frequency;
    uint16_t period;
    void (*callback)(void);
    PWMChannelConfig channels[4];
} PWMConfig;
typedef struct {
    const PWMConfig *config;
    uint16_t         width[4];
} PWMDriver;
extern PWMDriver           PWMD_GPTM0, PWMD_MCTM0;
extern bool                pins[64];
extern std::deque<uint8_t> fifo_rx, fifo_tx;
extern bool                sel;
extern unsigned            errors;
inline void (*status_hook)(void) = nullptr;

struct DataRegister {
    operator uint32_t() const {
        assert(!fifo_rx.empty());
        auto v = fifo_rx.front();
        fifo_rx.pop_front();
        return v;
    }
    void operator=(uint32_t v) {
        assert(fifo_tx.size() < 7);
        fifo_tx.push_back(v);
    }
};
struct FifoRegister {
    operator uint32_t() const {
        return fifo_rx.size() << 4 | fifo_tx.size();
    }
};
struct StatusRegister {
    operator uint32_t() const {
        if (status_hook) status_hook();
        return errors | (sel ? 0x100 : 0);
    }
    void operator=(uint32_t v) {
        errors &= ~v;
    }
};
struct ResetRegister {
    void operator=(uint32_t) {
        fifo_rx.clear();
        fifo_tx.clear();
        errors = 0;
    }
};
struct {
    unsigned       CR0, CR1, CPR, FCR, IER;
    DataRegister   DR;
    FifoRegister   FSR;
    StatusRegister SR;
} inline spi [[maybe_unused]];
struct {
    ResetRegister APBPRSTR0;
} inline rst [[maybe_unused]];
struct {
    unsigned APBCCR0, APBCCR1;
} inline ckcu [[maybe_unused]];
struct {
    unsigned CTR, CNTR, CNTCFR, MDCFR, TRCFR, CHPOLR, CHnOCFR[4], CHCTR, DICTR, PSCR, CRR, CHnCCR[4];
} inline gptm1 [[maybe_unused]];
struct {
    unsigned RR;
} inline gpioa [[maybe_unused]];
struct {
    unsigned LVDCSR;
} inline pwrcu [[maybe_unused]];
struct {
    unsigned status, configuration;
} inline USBD1 [[maybe_unused]];
#define SPI0 (&spi)
#define RSTCU (&rst)
#define CKCU (&ckcu)
#define PWRCU (&pwrcu)
#define GPTM1 (&gptm1)
#define GPIOA (&gpioa)

void     chSysLock(void);
void     chSysUnlock(void);
void     nvicEnableVector(unsigned vector, unsigned priority);
void     palSetGroupMode(void *, unsigned, unsigned, unsigned);
void     palSetLineMode(unsigned pin, unsigned mode);
void     gpio_write_pin(unsigned pin, bool value);
void     gpio_write_pin_high(unsigned pin);
void     gpio_write_pin_low(unsigned pin);
bool     gpio_read_pin(unsigned pin);
void     gpio_set_pin_output(unsigned pin);
void     gpio_set_pin_input_low(unsigned pin);
void     gpio_set_pin_input_high(unsigned pin);
void     usbWakeupHost(void *);
void     clear_keyboard(void);
bool     process_record_user(uint16_t keycode, keyrecord_t *record);
uint32_t timer_read32(void);
uint32_t timer_elapsed32(uint32_t start);
void     wait_ms(unsigned ms);
void     wait_us(unsigned us);
void     pwmStart(PWMDriver *, const PWMConfig *);
void     pwmEnableChannel(PWMDriver *, unsigned, uint16_t);
void     suspend_power_down_user(void);
void     suspend_wakeup_init_user(void);
bool     shutdown_user(bool);
