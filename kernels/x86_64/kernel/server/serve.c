/* Shared server poll loop: halt until the next timer tick (so QEMU's main loop
 * can deliver inbound packets), service the network, and stop on a keypress. */
#include "server.h"
#include "net.h"
#include "kernel.h"

void server_serve_loop(void)
{
	for (;;) {
		__asm__ volatile("hlt");
		net_poll();
		if (serial_rx_ready()) {
			(void)serial_getc();
			break;
		}
	}
}
