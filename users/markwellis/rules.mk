ifeq ($(KEYBOARD),mistel/md770rgb_bt/right)
    RAW_ENABLE = yes
    SRC += $(USER_PATH)/notification.c
    ifeq ($(KEYMAP),default_mistel)
        # QMK needs per-event keycodes to handle remapped presses and releases.
        REPEAT_KEY_ENABLE = yes
        OPT_DEFS += -DMD770_NUMPAD_ENABLE
        SRC += $(USER_PATH)/numpad.c
    endif
endif
