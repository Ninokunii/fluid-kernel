#include <fluid/html.h>
#include <fluid/fb.h>
#include <fluid/serial.h>

static int starts(const char *p, const char *s) {
    while (*s) if (*p++ != *s++) return 0;
    return 1;
}

static const char *find_char(const char *p, const char *end, char c) {
    while (p < end) {
        if (*p == c) return p;
        ++p;
    }
    return 0;
}

static const char *find_tag_end(const char *p, const char *end) {
    return find_char(p, end, '>');
}

static u8 class_color(const char *tag, const char *tag_end) {
    const char *p = tag;
    while (p + 7 < tag_end) {
        if (starts(p, "class=\"")) {
            p += 7;
            if (starts(p, "info")) return 3;
            if (starts(p, "danger")) return 4;
            if (starts(p, "warm")) return 5;
            if (starts(p, "gold")) return 6;
            return 2;
        }
        ++p;
    }
    return 2;
}

static void trim_label(const char **p, u32 *len) {
    while (*len && (**p == ' ' || **p == '\n' || **p == '\r' || **p == '\t')) { ++*p; --*len; }
    while (*len) {
        char c = (*p)[*len - 1];
        if (c != ' ' && c != '\n' && c != '\r' && c != '\t') break;
        --*len;
    }
}

void html_parse(const char *html, u32 len, struct html_doc *doc) {
    const char *p = html;
    const char *end = html + len;
    doc->title = "AGENT HTML";
    doc->title_len = 10;
    doc->button_count = 0;

    serial_write("html.parser.c start source=initramfs engine=c-tokenizer\r\n");
    while (p < end) {
        if (p + 4 < end && starts(p, "<h2")) {
            const char *gt = find_tag_end(p, end);
            const char *close = gt ? gt : p;
            while (close + 5 < end && !starts(close, "</h2>")) ++close;
            if (gt && close < end) {
                doc->title = gt + 1;
                doc->title_len = (u32)(close - (gt + 1));
                trim_label(&doc->title, &doc->title_len);
            }
            p = close;
        } else if (p + 7 < end && starts(p, "<button")) {
            const char *gt = find_tag_end(p, end);
            const char *close = gt ? gt : p;
            while (close + 9 < end && !starts(close, "</button>")) ++close;
            if (gt && close < end && doc->button_count < HTML_MAX_BUTTONS) {
                struct html_button *b = &doc->buttons[doc->button_count++];
                b->label = gt + 1;
                b->label_len = (u32)(close - (gt + 1));
                b->class_color = class_color(p, gt);
                trim_label(&b->label, &b->label_len);
            }
            p = close;
        }
        ++p;
    }
    serial_write("html.parser.c complete buttons=");
    serial_putc('0' + (char)(doc->button_count / 10));
    serial_putc('0' + (char)(doc->button_count % 10));
    serial_write(" status=ok\r\n");
}

void html_render(const struct html_doc *doc) {
    fb_clear(1);
    fb_rect(10, 10, 300, 22, 2);
    fb_text(18, 17, "FLUID KERNEL C/ASM", 15);
    fb_rect(18, 42, 284, 46, 3);
    fb_text_n(26, 50, doc->title, doc->title_len > 28 ? 28 : (int)doc->title_len, 15);
    fb_text(26, 65, "HTML PARSED IN KERNEL", 15);

    int x0 = 18, y0 = 104;
    for (u32 i = 0; i < doc->button_count && i < 12; ++i) {
        int x = x0 + (int)(i % 4) * 72;
        int y = y0 + (int)(i / 4) * 24;
        fb_rect(x, y, 66, 18, doc->buttons[i].class_color);
        fb_rect(x + 4, y + 4, 4, 4, 6);
        int n = doc->buttons[i].label_len > 8 ? 8 : (int)doc->buttons[i].label_len;
        fb_text_n(x + 10, y + 6, doc->buttons[i].label, n, 15);
    }
    fb_text(18, 184, "QEMU BOOTED - NO WEBVIEW", 15);
    serial_write("html.render.c framebuffer=mode13 dom=kernel-memory status=complete\r\n");
}
