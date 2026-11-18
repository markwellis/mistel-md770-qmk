// Copyright 2026 Mark Ellis (@markwellis)
// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once

#include "quantum.h"

typedef enum { MD770_NUMPAD_OFF, MD770_NUMPAD_LEFT, MD770_NUMPAD_RIGHT } md770_numpad_side_t;

#ifdef MD770_NUMPAD_ENABLE
md770_numpad_side_t md770_numpad_side(void);
void md770_numpad_draw(md770_numpad_side_t side);
#else
static inline md770_numpad_side_t md770_numpad_side(void) { return MD770_NUMPAD_OFF; }
static inline void md770_numpad_draw(md770_numpad_side_t side) { (void)side; }
#endif
