#include <fluid/fb.h>
#include <fluid/io.h>

void fb_init_mode13(void) {
    /* stage1 enters VGA mode 13h before protected mode; BIOS calls are unavailable here. */
}

void fb_clear(u8 color) {
    for (u32 i = 0; i < FB_WIDTH * FB_HEIGHT; ++i) FB_ADDR[i] = color;
}

void fb_rect(int x, int y, int w, int h, u8 color) {
    if (w <= 0 || h <= 0) return;
    if (x < 0) { w += x; x = 0; }
    if (y < 0) { h += y; y = 0; }
    if (x + w > FB_WIDTH) w = FB_WIDTH - x;
    if (y + h > FB_HEIGHT) h = FB_HEIGHT - y;
    if (w <= 0 || h <= 0) return;
    for (int yy = 0; yy < h; ++yy) {
        volatile u8 *row = FB_ADDR + (y + yy) * FB_WIDTH + x;
        for (int xx = 0; xx < w; ++xx) row[xx] = color;
    }
}
