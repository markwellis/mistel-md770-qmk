#pragma once
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>
#define TRUE 1
#define FALSE 0
#define HAL_USE_USB TRUE
#define USB_EP_MODE_TYPE_BULK 2
#define TIME_IMMEDIATE 0
#define TIME_INFINITE UINT32_MAX
#define MSG_OK 0
#define MSG_RESET (-1)
#define MSG_TIMEOUT (-2)
typedef uint32_t         sysinterval_t, systime_t, time_msecs_t;
typedef int              msg_t, threads_queue_t;
typedef uint8_t          usbep_t;
typedef struct USBDriver USBDriver;
typedef bool (*usbreqhandler_t)(USBDriver *);
typedef struct {
    uint8_t *rxbuf;
    size_t   rxsize, rxcnt;
} USBOutEndpointState;
typedef struct {
    size_t txsize;
} USBInEndpointState;
typedef struct {
    unsigned             ep_mode;
    USBInEndpointState  *in_state;
    USBOutEndpointState *out_state;
    size_t               in_maxsize;
} USBEndpointConfig;
struct USBDriver {
    unsigned                 state, receiving, transmitting;
    void                    *in_params[8], *out_params[8];
    const USBEndpointConfig *epc[9];
    uint8_t                  setup[8];
};
enum { USB_STOP, USB_READY, USB_ACTIVE, USB_SUSPENDED };
#define usbGetDriverStateI(d) ((d)->state)
#define usbGetReceiveStatusI(d, e) ((d)->receiving & (1U << (e)))
#define usbGetTransmitStatusI(d, e) ((d)->transmitting & (1U << (e)))
#define usbGetReceiveTransactionSizeX(d, e) ((d)->epc[e]->out_state->rxcnt)
#define osalDbgCheck(x) assert(x)
#define osalDbgAssert(x, message) assert(x)
#define osalDbgCheckClassI() ((void)0)
#define osalDbgCheckClassS() ((void)0)
#define osalSysLock() ((void)0)
#define osalSysUnlock() ((void)0)
#define osalSysLockFromISR() ((void)0)
#define osalSysUnlockFromISR() ((void)0)
#define osalOsRescheduleS() ((void)0)
static inline void osalThreadQueueObjectInit(threads_queue_t *q) {
    *q = 0;
}
static inline void osalThreadDequeueAllI(threads_queue_t *q, msg_t m) {
    (void)q;
    (void)m;
}
static inline void osalThreadDequeueNextI(threads_queue_t *q, msg_t m) {
    (void)q;
    (void)m;
}
extern msg_t (*usb_wait_hook)(void);
static inline msg_t osalThreadEnqueueTimeoutS(threads_queue_t *q, sysinterval_t t) {
    (void)q;
    (void)t;
    return usb_wait_hook ? usb_wait_hook() : MSG_TIMEOUT;
}
void usbStartReceiveI(USBDriver *, usbep_t, uint8_t *, size_t);
void usbStartTransmitI(USBDriver *, usbep_t, const uint8_t *, size_t);
void usbInitEndpointI(USBDriver *, usbep_t, const USBEndpointConfig *);
#include <hal_buffers.h>
