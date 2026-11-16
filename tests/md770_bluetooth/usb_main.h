// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
void usb_driver_set_enabled(void *driver, bool enabled);

typedef unsigned usbevent_t;
enum { USB_EVENT_SUSPEND, USB_EVENT_WAKEUP, USB_EVENT_RESET, USB_EVENT_UNCONFIGURED, USB_EVENT_CONFIGURED };

bool usb_keyboard_report_pending(void);
