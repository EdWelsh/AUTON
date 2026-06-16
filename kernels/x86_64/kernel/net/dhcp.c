/* DHCP client: DISCOVER -> OFFER -> REQUEST -> ACK, then apply the lease.
 * Polled: dhcp_run() pumps net_poll() until configured or it gives up. */
#include "net.h"
#include "e1000.h"
#include "kernel.h"

#define DHCP_XID    0x41555401u         /* "AUT\1" */
#define DHCP_MAGIC  0x63825363u
#define DHCP_CLIENT_PORT 68
#define DHCP_SERVER_PORT 67

#define DHCP_DISCOVER 1
#define DHCP_OFFER    2
#define DHCP_REQUEST  3
#define DHCP_ACK      5

struct dhcp_msg {
	uint8_t  op, htype, hlen, hops;
	uint32_t xid;
	uint16_t secs, flags;
	uint32_t ciaddr, yiaddr, siaddr, giaddr;
	uint8_t  chaddr[16];
	uint8_t  sname[64];
	uint8_t  file[128];
	uint32_t magic;
	uint8_t  options[64];
} __attribute__((packed));

enum { ST_INIT, ST_OFFERED, ST_DONE, ST_FAIL };
static int      g_state;
static ipv4_t   g_offered, g_server, g_mask, g_gw, g_dns;
static uint32_t g_dhcp_rx;              /* DHCP messages received (diagnostic) */

static uint16_t base_fields(struct dhcp_msg *m)
{
	kmemset(m, 0, sizeof(*m));
	m->op = 1;
	m->htype = 1;
	m->hlen = 6;
	m->xid = htonl(DHCP_XID);
	m->flags = htons(0x8000);       /* ask the server to broadcast its reply */
	kmemcpy(m->chaddr, net_mac(), 6);
	m->magic = htonl(DHCP_MAGIC);
	return (uint16_t)(sizeof(*m) - sizeof(m->options));
}

static void send_discover(void)
{
	struct dhcp_msg m;
	uint16_t base = base_fields(&m);
	uint8_t *o = m.options;
	uint16_t i = 0;

	o[i++] = 53; o[i++] = 1; o[i++] = DHCP_DISCOVER;
	o[i++] = 55; o[i++] = 3; o[i++] = 1; o[i++] = 3; o[i++] = 6;
	o[i++] = 255;
	udp_send(IP_BROADCAST, DHCP_SERVER_PORT, DHCP_CLIENT_PORT, &m,
		 (uint16_t)(base + i));
}

static void send_request(void)
{
	struct dhcp_msg m;
	uint16_t base = base_fields(&m);
	uint8_t *o = m.options;
	uint16_t i = 0;
	uint32_t yip = htonl(g_offered), sid = htonl(g_server);

	o[i++] = 53; o[i++] = 1; o[i++] = DHCP_REQUEST;
	o[i++] = 50; o[i++] = 4; kmemcpy(&o[i], &yip, 4); i += 4;
	o[i++] = 54; o[i++] = 4; kmemcpy(&o[i], &sid, 4); i += 4;
	o[i++] = 55; o[i++] = 3; o[i++] = 1; o[i++] = 3; o[i++] = 6;
	o[i++] = 255;
	udp_send(IP_BROADCAST, DHCP_SERVER_PORT, DHCP_CLIENT_PORT, &m,
		 (uint16_t)(base + i));
}

/* Walk options, returning the message type (53) and filling the lease fields. */
static uint8_t parse_options(const uint8_t *opt, uint16_t len)
{
	uint8_t type = 0;
	uint16_t i = 0;

	while (i + 1 < len) {
		uint8_t code = opt[i++];
		if (code == 255)
			break;
		if (code == 0)
			continue;
		uint8_t olen = opt[i++];
		if (i + olen > len)
			break;
		const uint8_t *v = &opt[i];
		uint32_t w;
		switch (code) {
		case 53: type = v[0]; break;
		case 1:  kmemcpy(&w, v, 4); g_mask = ntohl(w); break;
		case 3:  kmemcpy(&w, v, 4); g_gw   = ntohl(w); break;
		case 6:  kmemcpy(&w, v, 4); g_dns  = ntohl(w); break;
		case 54: kmemcpy(&w, v, 4); g_server = ntohl(w); break;
		default: break;
		}
		i += olen;
	}
	return type;
}

static void dhcp_on_udp(ipv4_t src, uint16_t sport,
			const uint8_t *data, uint16_t len)
{
	(void)src;
	(void)sport;
	const struct dhcp_msg *m = (const struct dhcp_msg *)data;
	uint16_t hdr = (uint16_t)(sizeof(*m) - sizeof(m->options));

	if (len < hdr + 4 || ntohl(m->xid) != DHCP_XID ||
	    ntohl(m->magic) != DHCP_MAGIC)
		return;

	g_dhcp_rx++;
	uint8_t type = parse_options(m->options, (uint16_t)(len - hdr));
	if (type == DHCP_OFFER && g_state == ST_INIT) {
		g_offered = ntohl(m->yiaddr);
		g_state = ST_OFFERED;
		send_request();
	} else if (type == DHCP_ACK && g_state == ST_OFFERED) {
		g_offered = ntohl(m->yiaddr);
		net_set_ipcfg(g_offered, g_mask, g_gw, g_dns);
		g_state = ST_DONE;
	}
}

/* Run the DHCP exchange. Returns 0 on success (IP configured), -1 on timeout.
 *
 * Each iteration halts until the next timer tick (~1 ms), which lets QEMU's
 * main loop run and deliver any queued reply, then drains the RX ring. We
 * re-send DISCOVER/REQUEST periodically as a retransmit. */
#define DHCP_RESEND_EVERY 50            /* ticks (~ms) between retransmits */
#define DHCP_MAX_TICKS    4000          /* ~4 s overall timeout */

int dhcp_run(void)
{
	g_state = ST_INIT;
	udp_bind(DHCP_CLIENT_PORT, dhcp_on_udp);

	for (int i = 0; i < DHCP_MAX_TICKS && g_state != ST_DONE; i++) {
		if (i % DHCP_RESEND_EVERY == 0) {
			if (g_state == ST_INIT)
				send_discover();
			else if (g_state == ST_OFFERED)
				send_request();
		}
		__asm__ volatile("hlt");        /* yield to QEMU until next tick */
		net_poll();                     /* drain whatever arrived */
	}
	if (g_state != ST_DONE) {
		e1000_debug();
		kprintf("[NET] dhcp: state=%u dhcp_rx=%u\n", g_state, g_dhcp_rx);
	}
	return g_state == ST_DONE ? 0 : -1;
}
