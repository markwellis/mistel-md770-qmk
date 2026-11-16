// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
struct { unsigned state; } inline USBD1;
void usb_driver_set_enabled(void *driver, bool enabled);
