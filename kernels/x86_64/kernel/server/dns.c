/* Tiny authoritative-ish DNS responder: answers every A query with this host's
 * own IP. Demonstrates a second chat-driven role on the same UDP stack. */
#include "server.h"
#include "net.h"
#include "kernel.h"

#define DNS_PORT 53

static void dns_on_udp(ipv4_t src, uint16_t sport,
		       const uint8_t *data, uint16_t len)
{
	static uint8_t resp[512];

	if (len < 12)
		return;

	/* Walk the (single) question's QNAME labels to find its end. */
	uint16_t q = 12;
	while (q < len && data[q] != 0) {
		if (data[q] & 0xC0)             /* compression in a query: skip */
			return;
		q = (uint16_t)(q + data[q] + 1);
	}
	q = (uint16_t)(q + 1 + 4);              /* null label + QTYPE + QCLASS */
	if (q > len || (uint32_t)q + 16 > sizeof(resp))
		return;

	kmemcpy(resp, data, q);
	resp[2] = 0x81;                         /* QR=1, RD copied */
	resp[3] = 0x80;                         /* RA=1, RCODE=0 */
	resp[6] = 0x00; resp[7] = 0x01;         /* ANCOUNT = 1 */
	resp[8] = 0; resp[9] = 0; resp[10] = 0; resp[11] = 0;

	uint16_t p = q;
	resp[p++] = 0xC0; resp[p++] = 0x0C;     /* name -> offset 12 (the QNAME) */
	resp[p++] = 0x00; resp[p++] = 0x01;     /* TYPE A */
	resp[p++] = 0x00; resp[p++] = 0x01;     /* CLASS IN */
	resp[p++] = 0x00; resp[p++] = 0x00;
	resp[p++] = 0x00; resp[p++] = 0x3C;     /* TTL 60s */
	resp[p++] = 0x00; resp[p++] = 0x04;     /* RDLENGTH 4 */
	uint32_t ip = htonl(net_ip());
	kmemcpy(&resp[p], &ip, 4);
	p = (uint16_t)(p + 4);

	udp_send(src, sport, DNS_PORT, resp, p);
}

void dns_server_run(void)
{
	udp_bind(DNS_PORT, dns_on_udp);
	kprintf("[DNS] answering on :53 (press any key to stop)\n");
	server_serve_loop();
	kprintf("[DNS] stopped\n");
}
