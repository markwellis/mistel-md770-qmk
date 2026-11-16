// SPDX-License-Identifier: GPL-2.0-or-later
#include <quantum.h>
#include <usb_device_state.h>
#include <connection.h>
#include <host_driver.h>
#include <send_string.h>
#include <keycode_config.h>
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
    offsetof(USBDriver, state), USB_READY, USB_ACTIVE, USB_SUSPENDED,
    USB_DEVICE_STATE_INIT,
    sizeof(((USBDriver *)0)->state), sizeof(((struct usb_device_state *)0)->configure_state),
    REPORT_ID_SYSTEM, REPORT_ID_CONSUMER,
    sizeof(keyrecord_t), offsetof(keyrecord_t, event.key.row), offsetof(keyrecord_t, event.key.col),
    offsetof(keyrecord_t, event.type), sizeof(((keyrecord_t *)0)->event.type),
    offsetof(keyrecord_t, event.pressed), KEY_EVENT, QK_MACRO,
    offsetof(host_driver_t, send_keyboard), offsetof(report_keyboard_t, mods), offsetof(report_keyboard_t, keys),
    SS_QMK_PREFIX, SS_TAP_CODE, SS_DOWN_CODE, SS_UP_CODE, SS_DELAY_CODE,
    DYNAMIC_KEYMAP_MACRO_COUNT,
    offsetof(host_driver_t, send_nkro), offsetof(report_nkro_t, mods),
    offsetof(report_nkro_t, bits), sizeof(((report_nkro_t *)0)->bits),
    offsetof(struct usb_device_state, protocol), USB_PROTOCOL_BOOT, USB_PROTOCOL_REPORT,
    sizeof(((struct usb_device_state *)0)->protocol),
    MATRIX_ROWS, MATRIX_COLS,
    CONNECTION_HOST_NONE,
};

const keymap_config_t emulator_nkro_flag = {.nkro = true};
