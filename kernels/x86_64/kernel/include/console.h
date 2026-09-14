/* Line-oriented console input on top of the serial UART. */
#ifndef AUTON_CONSOLE_H
#define AUTON_CONSOLE_H

#include <stdint.h>

/* Read one line of input into 'buf' (NUL-terminated, at most size-1 chars).
 * Echoes printable characters, handles backspace, and terminates on CR/LF.
 * Returns the number of characters stored (excluding the terminator). */
uint32_t console_readline(char *buf, uint32_t size);

#endif /* AUTON_CONSOLE_H */
