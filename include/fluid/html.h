#pragma once
#include <fluid/types.h>

#define HTML_MAX_BUTTONS 16
#define HTML_MAX_TEXT 32

struct html_button {
    const char *label;
    u32 label_len;
    u8 class_color;
};

struct html_doc {
    const char *title;
    u32 title_len;
    struct html_button buttons[HTML_MAX_BUTTONS];
    u32 button_count;
};

void html_parse(const char *html, u32 len, struct html_doc *doc);
void html_render(const struct html_doc *doc);
