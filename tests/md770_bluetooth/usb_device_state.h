#pragma once
enum usb_configure_state_t { USB_DEVICE_STATE_INIT, USB_DEVICE_STATE_CONFIGURED, USB_DEVICE_STATE_SUSPEND };
usb_configure_state_t usb_device_state_get_configure_state(void);
