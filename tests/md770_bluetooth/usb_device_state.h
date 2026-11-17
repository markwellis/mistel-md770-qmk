#pragma once
enum usb_configure_state_t { USB_DEVICE_STATE_INIT, USB_DEVICE_STATE_CONFIGURED, USB_DEVICE_STATE_SUSPEND };
struct usb_device_state { usb_configure_state_t configure_state; };
usb_configure_state_t usb_device_state_get_configure_state(void);
void notify_usb_device_state_change_user(struct usb_device_state state);
