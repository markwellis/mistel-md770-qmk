// SPDX-License-Identifier: GPL-2.0-or-later
#include <quantum.h>
#include <usb_device_state.h>
#include <connection.h>
#include <stddef.h>

const uint32_t emulator_abi[] = {
    offsetof(USBDriver, configuration), offsetof(USBDriver, status),
    offsetof(struct usb_device_state, configure_state),
    offsetof(PWMDriver, state), offsetof(PWMDriver, config),
    offsetof(PWMDriver, period), offsetof(PWMDriver, channels), offsetof(PWMDriver, TM),
    PWM_STOP, PWM_READY,
    offsetof(GPTDriver, state), offsetof(GPTDriver, config), offsetof(GPTDriver, BFTM),
    GPT_CONTINUOUS, sizeof(gptcnt_t),
    CONNECTION_HOST_USB, CONNECTION_HOST_BLUETOOTH,
    USB_DEVICE_STATE_CONFIGURED, USB_DEVICE_STATE_SUSPEND,
};
