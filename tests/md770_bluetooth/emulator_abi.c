// SPDX-License-Identifier: GPL-2.0-or-later
#include <quantum.h>
#include <usb_device_state.h>
#include <connection.h>
#include <host_driver.h>
#include <send_string.h>
#include <keycode_config.h>
#include <stddef.h>
#include "tmk_core/protocol/chibios/usb_main.h"
#include "keyboards/mistel/md770rgb_bt/keymaps/default/keymap.h"
#include "keyboards/mistel/md770rgb_bt/bluetooth.c"

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
    USB_STOP, USB_SELECTED, sizeof(keyevent_t), offsetof(keyevent_t, time),
    offsetof(keyrecord_t, event), QK_OUTPUT_USB, QK_OUTPUT_BLUETOOTH,
    QK_BLUETOOTH_PROFILE1,
    offsetof(host_driver_t, send_extra), offsetof(report_extra_t, report_id), offsetof(report_extra_t, usage),
    CH_CFG_ST_FREQUENCY,
    MO(PN), MO(FN), PN, USB_EVENT_WAKEUP, USB_EVENT_CONFIGURED,
    sizeof(usb_endpoint_in_t), offsetof(usb_endpoint_in_t, obqueue),
    offsetof(usb_endpoint_in_t, ep_config), offsetof(usb_endpoint_in_t, ep_in_state),
    offsetof(usb_endpoint_in_t, config) + offsetof(usb_endpoint_config_t, ep),
    offsetof(usb_endpoint_in_t, timed_out), offsetof(output_buffers_queue_t, bcounter),
    offsetof(output_buffers_queue_t, suspended), offsetof(output_buffers_queue_t, bn),
    offsetof(USBDriver, config), offsetof(USBDriver, transmitting),
    offsetof(USBDriver, in_params), offsetof(USBDriver, epc),
    offsetof(USBInEndpointState, txsize), USB_ENDPOINT_IN_KEYBOARD, USB_ENDPOINT_IN_SHARED,
    REPORT_ID_NKRO, USB_ENDPOINT_IN_COUNT, USB_EVENT_SUSPEND, USB_EVENT_RESET,
    USB_ENDPOINT_OUT_COUNT, sizeof(usb_endpoint_out_t),
    offsetof(usb_endpoint_out_t, ibqueue), offsetof(usb_endpoint_out_t, ep_config),
    offsetof(usb_endpoint_out_t, config) + offsetof(usb_endpoint_config_t, ep),
    offsetof(input_buffers_queue_t, suspended), offsetof(USBDriver, out_params),
    offsetof(USBDriver, receiving),
    sizeof(enum radio_phase), READY, FAILED, OFF,
    sizeof(enum radio_command), COMMAND_STOP, NO_COMMAND, COMMAND_KEYBOARD, COMMAND_SYSTEM,
};

const keymap_config_t emulator_nkro_flag = {.nkro = true};
