// SPDX-License-Identifier: GPL-2.0-or-later
#include <quantum.h>
#include <stddef.h>

const uint32_t clock_abi[] = {
    offsetof(os_instance_t, rlist.current),
    offsetof(os_instance_t, mainthread),
    sizeof(matrix_row_t),
    MATRIX_ROWS,
    offsetof(os_instance_t, vtlist.dlist),
    offsetof(ch_delta_list_t, next),
    offsetof(ch_delta_list_t, prev),
    offsetof(ch_delta_list_t, delta),
    offsetof(os_instance_t, vtlist.systime),
};
