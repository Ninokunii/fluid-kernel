#pragma once
void serial_init(void);
void serial_putc(char c);
void serial_write(const char *s);
void serial_write_hex(unsigned value);
