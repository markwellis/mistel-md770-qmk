// SPDX-License-Identifier: GPL-2.0-or-later
#include <assert.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>

typedef enum { USB_UNINIT, USB_STOP, USB_READY, USB_SELECTED, USB_ACTIVE, USB_SUSPENDED } usbstate_t;
#define TRUE 1
#define USB_USE_WAIT TRUE
#define HT32_USB_USE_USB0 TRUE
#define USB_MAX_ENDPOINTS 7
#define USB_IRQn 35
#define RSTCU_AHBPRSTR_USBRST (1U << 14)
#define MSG_RESET (-1)

typedef struct { int thread; } EPState;
typedef struct { EPState *in_state, *out_state; } EPConfig;
typedef struct { usbstate_t state; const void *config; const EPConfig *epc[USB_MAX_ENDPOINTS + 1]; } USBDriver;
static USBDriver USBD1;
static struct { volatile uint32_t AHBPRSTR; } reset_registers;
#define RSTCU (&reset_registers)
static bool irq_enabled;
static unsigned disables, resumes, depth;
#define osalDbgCheck(c) assert(c)
#define osalDbgAssert(c, m) assert(c)
static void osalSysLock(void) { assert(!depth); ++depth; }
static void osalSysUnlock(void) { assert(depth == 1); --depth; }
static void osalOsRescheduleS(void) { assert(depth == 1); }
static void osalThreadResumeI(int *thread, int result) { assert(depth == 1 && result == MSG_RESET); *thread = result; ++resumes; }
static void nvicDisableVector(int irq) { assert(depth == 1 && irq == USB_IRQn); irq_enabled = false; ++disables; }

#include "stop_functions.inc"

int main(void) {
    static const char *names[] = {"UNINIT", "STOP", "READY", "SELECTED", "ACTIVE", "SUSPENDED"};
    unsigned failures = 0;
    for (usbstate_t entry = USB_STOP; entry <= USB_SUSPENDED; ++entry) {
        EPState in = {1}, out = {1};
        EPConfig ep = {&in, &out};
        USBD1 = (USBDriver){.state = entry, .config = &ep, .epc = {[1] = &ep}};
        irq_enabled = entry != USB_STOP;
        reset_registers.AHBPRSTR = 0;
        disables = resumes = depth = 0;
        usbStop(&USBD1);
        assert(USBD1.state == USB_STOP && !USBD1.config && !USBD1.epc[1]);
        assert(resumes == 2 && in.thread == MSG_RESET && out.thread == MSG_RESET);
        bool shutdown = !irq_enabled && (entry == USB_STOP
            ? !disables && !reset_registers.AHBPRSTR
            : disables == 1 && reset_registers.AHBPRSTR == RSTCU_AHBPRSTR_USBRST);
        printf("%s -> STOP: IRQ enabled=%u, peripheral reset=%u, contract=%s\n",
               names[entry], irq_enabled, reset_registers.AHBPRSTR != 0, shutdown ? "PASS" : "FAIL");
        failures += !shutdown;
        unsigned previous_disables = disables;
        usbStop(&USBD1);
        assert(disables == previous_disables && !depth);
    }
    return failures ? 1 : 0;
}
