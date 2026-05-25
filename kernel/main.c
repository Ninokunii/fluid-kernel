#include <fluid/html.h>
#include <fluid/serial.h>
#include <fluid/fb.h>

extern const char _binary_kernel_assets_order_agent_html_start[];
extern const char _binary_kernel_assets_order_agent_html_end[];

void kmain(void) {
    serial_init();
    serial_write("fluid.kernel.c entry protected-mode=1 runtime=c/asm\r\n");
    fb_init_mode13();

    struct html_doc doc;
    const char *html = _binary_kernel_assets_order_agent_html_start;
    unsigned len = (unsigned)(_binary_kernel_assets_order_agent_html_end - _binary_kernel_assets_order_agent_html_start);
    serial_write("initramfs.builtin file=/agent-order-task.html source=objcopy-blob status=mounted\r\n");
    html_parse(html, len, &doc);
    html_render(&doc);
    serial_write("kernel.halt reason=demo-complete\r\n");
    for (;;) __asm__ volatile ("hlt");
}
