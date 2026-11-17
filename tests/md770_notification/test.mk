RGB_MATRIX_ENABLE = yes
RGB_MATRIX_DRIVER = custom
RAW_ENABLE = yes
SRC += $(QMK_USERSPACE)/users/markwellis/notification.c
OPT_DEFS += -DQMK_KEYBOARD_H=\"quantum.h\"
