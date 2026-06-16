/* Serial line editor: assembles a line from raw UART bytes with local echo
 * and backspace handling. The chat REPL reads user input through this. */
#include "console.h"
#include "kernel.h"

#define CH_BACKSPACE 0x08
#define CH_DELETE    0x7F
#define CH_CR        '\r'
#define CH_LF        '\n'

uint32_t console_readline(char *buf, uint32_t size)
{
	uint32_t len = 0;

	if (size == 0)
		return 0;

	for (;;) {
		char c = serial_getc();

		/* Enter: terminals send CR (\r) over serial; accept LF too. */
		if (c == CH_CR || c == CH_LF) {
			serial_putc('\n');
			break;
		}

		/* Backspace / delete: erase the last char on screen and in buf. */
		if (c == CH_BACKSPACE || c == CH_DELETE) {
			if (len > 0) {
				len--;
				serial_write("\b \b");
			}
			continue;
		}

		/* Ignore other control chars; only buffer printable ASCII. */
		if ((unsigned char)c < 0x20)
			continue;

		if (len < size - 1) {
			buf[len++] = c;
			serial_putc(c);
		}
	}

	buf[len] = '\0';
	return len;
}
