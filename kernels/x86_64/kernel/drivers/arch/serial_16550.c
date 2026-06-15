/* 16550A UART driver (COM1). The acceptance harness reads everything the
 * kernel emits here via QEMU `-serial stdio`. */
#include <stdint.h>
#include "kernel.h"
#include "../../arch/x86_64/io/io.h"

#define COM1        0x3F8
#define REG_DATA    (COM1 + 0)
#define REG_IER     (COM1 + 1)
#define REG_FCR     (COM1 + 2)
#define REG_LCR     (COM1 + 3)
#define REG_MCR     (COM1 + 4)
#define REG_LSR     (COM1 + 5)

#define LSR_THR_EMPTY 0x20

void serial_init(void)
{
	io_write8(REG_IER, 0x00);       /* disable interrupts */
	io_write8(REG_LCR, 0x80);       /* enable DLAB to set baud divisor */
	io_write8(REG_DATA, 0x01);      /* divisor low: 115200 baud */
	io_write8(REG_IER, 0x00);       /* divisor high */
	io_write8(REG_LCR, 0x03);       /* 8 bits, no parity, 1 stop; clears DLAB */
	io_write8(REG_FCR, 0xC7);       /* enable + clear FIFOs, 14-byte threshold */
	io_write8(REG_MCR, 0x0B);       /* DTR, RTS, OUT2 */
}

void serial_putc(char c)
{
	if (c == '\n')
		serial_putc('\r');
	while ((io_read8(REG_LSR) & LSR_THR_EMPTY) == 0)
		;
	io_write8(REG_DATA, (uint8_t)c);
}

void serial_write(const char *s)
{
	for (; *s; s++)
		serial_putc(*s);
}
