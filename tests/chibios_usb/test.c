#include <hal.h>
#include "usb_driver.h"
#include <stdio.h>
#include <string.h>

static bool preserve;
static uint8_t sent_report[32];
static size_t sent_size;
msg_t (*usb_wait_hook)(void);
static usb_endpoint_in_t *waiting_endpoint;

static msg_t suspend_during_wait(void) {
    waiting_endpoint->config.usbp->state = USB_SUSPENDED;
    usb_endpoint_in_suspend_cb(waiting_endpoint);
    usb_wait_hook = NULL;
    return MSG_RESET;
}

bool host_preserve_keyboard_state(void) {
    return preserve;
}

void usbStartTransmitI(USBDriver *driver, usbep_t ep, const uint8_t *buffer, size_t size) {
    assert(size <= sizeof(sent_report));
    driver->transmitting |= 1U << ep;
    driver->epc[ep]->in_state->txsize = size;
    memcpy(sent_report, buffer, size);
    sent_size = size;
}

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

    for (unsigned keeping = 0; keeping < 2; ++keeping) {
        driver.state = USB_READY;
        driver.transmitting = 0;
        _Alignas(size_t) uint8_t in_storage[BQ_BUFFER_SIZE(4, 32)] = {0};
        usb_endpoint_in_t in = {.config = {.usbp = &driver, .ep = 2, .buffer_capacity = 4, .buffer_size = 32, .buffer = in_storage}};
        usb_endpoint_in_init(&in);
        usb_endpoint_in_start(&in);
        driver.state = USB_ACTIVE;
        usb_endpoint_in_configure_cb(&in);
        preserve = keeping;
        assert(usb_endpoint_in_send(&in, red, 32, TIME_IMMEDIATE, false));
        assert(usb_endpoint_in_has_report(&in, 0));
        assert(usb_endpoint_in_has_report(&in, red[0]));
        assert(!usb_endpoint_in_has_report(&in, 99));
        driver.state = USB_SUSPENDED;
        usb_endpoint_in_suspend_cb(&in);
        assert(usb_endpoint_in_has_report(&in, red[0]) == (bool)keeping);
        driver.transmitting = 0;
        sent_size = 0;
        driver.state = USB_ACTIVE;
        usb_endpoint_in_wakeup_cb(&in);
        assert(sent_size == (keeping ? 32 : 0));
        if (keeping) assert(!memcmp(sent_report, red, 32));
        driver.state = USB_READY;
        usb_endpoint_in_suspend_cb(&in);
        assert(obqIsEmptyI(&in.obqueue));
        assert(!usb_endpoint_in_has_report(&in, 0));
    }
    puts("PASS: MD770 keeps pending IN reports across suspend; reset clears them");
    for (unsigned sleeping = 0; sleeping < 2; ++sleeping) {
        driver.state = USB_READY;
        driver.transmitting = 0;
        _Alignas(size_t) uint8_t in_storage[BQ_BUFFER_SIZE(4, 32)] = {0};
        usb_endpoint_in_t in = {.config = {.usbp = &driver, .ep = 2, .buffer_capacity = 4, .buffer_size = 32, .buffer = in_storage}};
        usb_endpoint_in_init(&in);
        usb_endpoint_in_start(&in);
        driver.state = USB_ACTIVE;
        usb_endpoint_in_configure_cb(&in);
        preserve = true;
        for (unsigned index = 0; index < 4; ++index) assert(usb_endpoint_in_send(&in, red, 32, TIME_IMMEDIATE, false));
        if (sleeping) {
            waiting_endpoint = &in;
            usb_wait_hook = suspend_during_wait;
        }
        assert(!usb_endpoint_in_send(&in, green, 32, 1, false));
        assert(in.obqueue.bn - in.obqueue.bcounter == 4);
        assert(usb_endpoint_in_has_report(&in, red[0]));
        assert(in.obqueue.suspended == (bool)sleeping);
    }
    puts("PASS: failed or suspended submissions retain accepted IN reports");
    return 0;
}
