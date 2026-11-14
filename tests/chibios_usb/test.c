#include <hal.h>
#include "usb_driver.h"
#include <stdio.h>
#include <string.h>

void usbInitEndpointI(USBDriver *d, usbep_t ep, const USBEndpointConfig *c) {
    d->epc[ep] = c;
}
void usbStartReceiveI(USBDriver *d, usbep_t ep, uint8_t *buffer, size_t size) {
    assert(!usbGetReceiveStatusI(d, ep));
    d->receiving |= 1U << ep;
    USBOutEndpointState *s = d->epc[ep]->out_state;
    s->rxbuf               = buffer;
    s->rxsize              = size;
    s->rxcnt               = 0;
}

static void host_packet(USBDriver *d, usbep_t ep, const uint8_t packet[32]) {
    USBOutEndpointState *s = d->epc[ep]->out_state;
    assert(s->rxsize >= 32);
    /* HT32 receives into the retained transfer pointer, then signals completion. */
    memcpy(s->rxbuf, packet, 32);
    s->rxbuf += 32;
    s->rxsize -= 32;
    s->rxcnt += 32;
    d->receiving &= ~(1U << ep);
    usb_endpoint_out_rx_complete_cb(d, ep);
}

int main(void) {
    USBDriver                driver                         = {.state = USB_READY};
    _Alignas(size_t) uint8_t storage[BQ_BUFFER_SIZE(4, 32)] = {0};
    usb_endpoint_out_t       endpoint                       = {.config = {.usbp = &driver, .ep = 1, .buffer_capacity = 4, .buffer_size = 32, .buffer = storage}};
    uint8_t                  green[32]                      = {'M', 'D', 1, 0, 255, 68};
    uint8_t                  red[32]                        = {'M', 'D', 1, 255, 0, 0};
    uint8_t                  actual[32];
    usb_endpoint_out_init(&endpoint);
    usb_endpoint_out_start(&endpoint);
    driver.state = USB_ACTIVE;
    usb_endpoint_out_configure_cb(&endpoint);
    host_packet(&driver, 1, green);
    assert(usb_endpoint_out_receive(&endpoint, actual, 32, TIME_IMMEDIATE));
    assert(!memcmp(actual, green, 32));
    assert(endpoint.ep_out_state.rxbuf == storage + endpoint.ibqueue.bsize + sizeof(size_t));

    /* ChibiOS _usb_suspend resets queues via the callback, then cancels transfers. */
    driver.state = USB_SUSPENDED;
    usb_endpoint_out_suspend_cb(&endpoint);
    driver.receiving = 0;
    assert(endpoint.ibqueue.bwrptr == storage);
    driver.state = USB_ACTIVE;
    usb_endpoint_out_wakeup_cb(&endpoint);
    host_packet(&driver, 1, red);
    assert(usb_endpoint_out_receive(&endpoint, actual, 32, TIME_IMMEDIATE));
    printf("First post-wake packet: sent red, delivered RGB(%u,%u,%u)\n", actual[3], actual[4], actual[5]);
    if (memcmp(actual, red, 32)) {
        assert(!memcmp(actual, green, 32));
        puts("FAIL: previous green packet was replayed");
        return 1;
    }
    puts("PASS: first post-wake packet is fresh");
    return 0;
}
