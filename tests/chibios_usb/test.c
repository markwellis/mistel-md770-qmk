// SPDX-License-Identifier: GPL-2.0-or-later
#include <hal.h>
#include "usb_driver.h"
#include <stdio.h>
#include <string.h>

static uint8_t sent_report[32];
static size_t sent_size;
msg_t (*usb_wait_hook)(void);

void usbStartTransmitI(USBDriver *driver, usbep_t ep, const uint8_t *buffer, size_t size) {
    assert(size <= sizeof(sent_report));
    driver->transmitting |= 1U << ep;
    driver->epc[ep]->in_state->txsize = size;
    memcpy(sent_report, buffer, size);
    sent_size = size;
}

void usbInitEndpointI(USBDriver *driver, usbep_t ep, const USBEndpointConfig *config) {
    driver->epc[ep] = config;
}

void usbStartReceiveI(USBDriver *driver, usbep_t ep, uint8_t *buffer, size_t size) {
    (void)driver;
    (void)ep;
    (void)buffer;
    (void)size;
    assert(false);
}

int main(void) {
    USBDriver driver = {.state = USB_READY};
    _Alignas(size_t) uint8_t storage[BQ_BUFFER_SIZE(4, 32)] = {0};
    usb_endpoint_in_t endpoint = {.config = {.usbp = &driver, .ep = 2, .buffer_capacity = 4, .buffer_size = 32, .buffer = storage}};
    uint8_t before[32] = {4}, after[32] = {5};
    usb_endpoint_in_init(&endpoint);
    usb_endpoint_in_start(&endpoint);
    driver.state = USB_ACTIVE;
    usb_endpoint_in_configure_cb(&endpoint);
    assert(usb_endpoint_in_send(&endpoint, before, sizeof(before), TIME_IMMEDIATE, false));
    assert(sent_size == sizeof(before) && !memcmp(sent_report, before, sizeof(before)));
    driver.state = USB_SUSPENDED;
    usb_endpoint_in_suspend_cb(&endpoint);
    assert(obqIsEmptyI(&endpoint.obqueue));
    assert(!usb_endpoint_in_send(&endpoint, after, sizeof(after), TIME_IMMEDIATE, false));
    driver.transmitting = 0;
    sent_size = 0;
    driver.state = USB_ACTIVE;
    usb_endpoint_in_wakeup_cb(&endpoint);
    assert(!sent_size);
    assert(usb_endpoint_in_send(&endpoint, after, sizeof(after), TIME_IMMEDIATE, false));
    assert(sent_size == sizeof(after) && !memcmp(sent_report, after, sizeof(after)));
    puts("Native USB suspend discards queued input; fresh input works after wake");
}
