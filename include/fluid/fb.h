#pragma once
#include <fluid/types.h>

#define FB_WIDTH 320
#define FB_HEIGHT 200
#define FB_ADDR ((volatile u8 *)0xA0000)

void fb_init_mode13(void);
void fb_clear(u8 color);
void fb_rect(int x, int y, int w, int h, u8 color);
void fb_text(int x, int y, const char *s, u8 color);
void fb_text_n(int x, int y, const char *s, int n, u8 color);
