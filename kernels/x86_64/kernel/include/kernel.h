/* Core seed-kernel prototypes: serial console, formatted output, libk. */
#ifndef AUTON_KERNEL_H
#define AUTON_KERNEL_H

#include <stdint.h>
#include <stddef.h>

/* ---- serial console (16550 UART, COM1) ---- */
void serial_init(void);
void serial_putc(char c);
void serial_write(const char *s);
int  serial_rx_ready(void);
char serial_getc(void);

/* ---- formatted output ----
 * Supports %s %c %d %u %x %% and a leading width digit (e.g. %8x is ignored
 * width but parsed). Output goes to the serial console. */
void kprintf(const char *fmt, ...);

/* ---- libk ---- */
void  *kmemset(void *dst, int c, size_t n);
void  *kmemcpy(void *dst, const void *src, size_t n);
size_t kstrlen(const char *s);
int    kstrcmp(const char *a, const char *b);

#endif /* AUTON_KERNEL_H */
