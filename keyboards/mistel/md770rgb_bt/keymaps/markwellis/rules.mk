RGB_MATRIX_CUSTOM_USER = yes
SRC += $(KEYMAP_PATH)/programming.c

ifeq ($(KEYBOARD),mistel/md770rgb_bt/right)
    DYNAMIC_KEYMAP_ENABLE = yes
    RAW_ENABLE = yes
    SRC += $(KEYMAP_PATH)/notification.c
endif
