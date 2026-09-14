/* Minimal freestanding printf -> serial console. */
#include <stdarg.h>
#include <stdint.h>
#include "kernel.h"

static void print_unsigned(uint64_t val, unsigned base, int upper)
{
	const char *digits = upper ? "0123456789ABCDEF" : "0123456789abcdef";
	char buf[32];
	int i = 0;

	if (val == 0) {
		serial_putc('0');
		return;
	}
	while (val > 0 && i < (int)sizeof(buf)) {
		buf[i++] = digits[val % base];
		val /= base;
	}
	while (i > 0)
		serial_putc(buf[--i]);
}

static void print_signed(int64_t val)
{
	if (val < 0) {
		serial_putc('-');
		print_unsigned((uint64_t)(-val), 10, 0);
	} else {
		print_unsigned((uint64_t)val, 10, 0);
	}
}

void kprintf(const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);

	for (const char *p = fmt; *p; p++) {
		if (*p != '%') {
			serial_putc(*p);
			continue;
		}
		p++;
		/* Skip an optional width digit; we do not pad (seed kernel). */
		while (*p >= '0' && *p <= '9')
			p++;
		switch (*p) {
		case 's': {
			const char *s = va_arg(ap, const char *);
			serial_write(s ? s : "(null)");
			break;
		}
		case 'c':
			serial_putc((char)va_arg(ap, int));
			break;
		case 'd':
			print_signed(va_arg(ap, int));
			break;
		case 'u':
			print_unsigned((uint64_t)va_arg(ap, unsigned int), 10, 0);
			break;
		case 'x':
			print_unsigned((uint64_t)va_arg(ap, unsigned int), 16, 0);
			break;
		case 'X':
			print_unsigned((uint64_t)va_arg(ap, unsigned int), 16, 1);
			break;
		case '%':
			serial_putc('%');
			break;
		case '\0':
			va_end(ap);
			return;
		default:
			serial_putc('%');
			serial_putc(*p);
			break;
		}
	}
	va_end(ap);
}
