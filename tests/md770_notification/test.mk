RGB_MATRIX_ENABLE = yes
RGB_MATRIX_DRIVER = custom
RAW_ENABLE = yes
SRC += $(QMK_USERSPACE)/keyboards/mistel/md770rgb_bt/keymaps/markwellis/notification.c
OPT_DEFS += -DQMK_KEYBOARD_H=\"quantum.h\"
