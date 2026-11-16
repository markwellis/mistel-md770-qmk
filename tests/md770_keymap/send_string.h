// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "quantum/send_string/send_string_keycodes.h"
void send_char(char code);

#define pgm_read_byte(address) (*(address))
#define KCLUT_ENTRY(a,b,c,d,e,f,g,h) ((a)|((b)<<1)|((c)<<2)|((d)<<3)|((e)<<4)|((f)<<5)|((g)<<6)|((h)<<7))
extern const uint8_t ascii_to_shift_lut[16], ascii_to_altgr_lut[16], ascii_to_dead_lut[16], ascii_to_keycode_lut[128];
