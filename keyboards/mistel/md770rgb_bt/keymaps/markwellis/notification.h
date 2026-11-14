// Copyright 2026 Mark Ellis (@markwellis)
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include QMK_KEYBOARD_H

#if defined(RAW_ENABLE) && defined(RGB_MATRIX_ENABLE)
void md770_notification_task(void);
#else
static inline void md770_notification_task(void) {}
#endif
