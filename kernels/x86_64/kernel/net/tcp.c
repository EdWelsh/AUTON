/* TCP — placeholder for Phase G so ip_input can dispatch. The real minimal
 * state machine (LISTEN/SYN_RCVD/ESTABLISHED/CLOSE) lands in Phase H. */
#include "net.h"

void tcp_input(ipv4_t src, const uint8_t *seg, uint16_t len)
{
	(void)src;
	(void)seg;
	(void)len;
}
