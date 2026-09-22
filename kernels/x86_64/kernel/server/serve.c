/* Shared server poll loop: halt until the next timer tick (so QEMU's main loop
 * can deliver inbound packets), service the network, and stop on a keypress. */
#include "server.h"
#include "net.h"
#include "kernel.h"
#include "hal.h"

void server_serve_loop(void)
{
	for (;;) {
		arch_halt();
		net_poll();
		if (serial_rx_ready()) {
			(void)serial_getc();
			break;
		}
	}
}
