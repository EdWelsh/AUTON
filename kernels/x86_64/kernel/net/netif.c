/* Net core: device glue, checksum, Ethernet framing, RX dispatch, UDP demux. */
#include "net.h"
#include "e1000.h"
#include "kernel.h"

#define FRAME_MAX 1600
#define UDP_BINDINGS 8

static uint8_t  g_mac[6];
static ipv4_t   g_ip, g_mask, g_gw, g_dns;
static int      g_up;

struct udp_binding {
	uint16_t      port;
	udp_handler_t handler;
};
static struct udp_binding g_udp[UDP_BINDINGS];

/* ---- checksum ---- */
uint32_t csum_add(uint32_t sum, const void *data, uint16_t len)
{
	const uint8_t *p = data;
	uint16_t i = 0;

	for (; i + 1 < len; i += 2)
		sum += (uint32_t)((p[i] << 8) | p[i + 1]);
	if (i < len)
		sum += (uint32_t)(p[i] << 8);
	return sum;
}

uint16_t csum_fold(uint32_t sum)
{
	while (sum >> 16)
		sum = (sum & 0xFFFF) + (sum >> 16);
	return (uint16_t)(~sum & 0xFFFF);
}

uint16_t net_checksum(const void *data, uint16_t len)
{
	return csum_fold(csum_add(0, data, len));
}

/* ---- state ---- */
void net_init(const uint8_t mac[6])
{
	kmemcpy(g_mac, mac, 6);
	g_ip = g_mask = g_gw = g_dns = 0;
	g_up = 0;
}

void net_set_ipcfg(ipv4_t ip, ipv4_t mask, ipv4_t gw, ipv4_t dns)
{
	g_ip = ip;
	g_mask = mask;
	g_gw = gw;
	g_dns = dns;
	g_up = (ip != 0);
}

ipv4_t net_ip(void)   { return g_ip; }
ipv4_t net_mask(void) { return g_mask; }
ipv4_t net_gw(void)   { return g_gw; }
ipv4_t net_dns(void) { return g_dns; }
const uint8_t *net_mac(void) { return g_mac; }
int net_is_up(void)  { return g_up; }

/* ---- Ethernet ---- */
void eth_send(const uint8_t dst[6], uint16_t ethertype,
	      const void *payload, uint16_t len)
{
	static uint8_t frame[FRAME_MAX];
	struct eth_hdr *eth = (struct eth_hdr *)frame;

	if (len > FRAME_MAX - sizeof(*eth))
		return;
	kmemcpy(eth->dst, dst, 6);
	kmemcpy(eth->src, g_mac, 6);
	eth->type = htons(ethertype);
	kmemcpy(frame + sizeof(*eth), payload, len);
	e1000_tx(frame, (uint16_t)(sizeof(*eth) + len));
}

/* ---- RX dispatch ---- */
void net_poll(void)
{
	static uint8_t buf[FRAME_MAX];
	uint16_t n = e1000_poll(buf, sizeof(buf));

	if (n < sizeof(struct eth_hdr))
		return;
	struct eth_hdr *eth = (struct eth_hdr *)buf;
	uint16_t type = ntohs(eth->type);

	if (type == ETHERTYPE_ARP)
		arp_input(buf, n);
	else if (type == ETHERTYPE_IP)
		ip_input(buf, n);
}

/* ---- UDP ---- */
int udp_bind(uint16_t port, udp_handler_t handler)
{
	for (int i = 0; i < UDP_BINDINGS; i++) {
		if (g_udp[i].handler == 0) {
			g_udp[i].port = port;
			g_udp[i].handler = handler;
			return 0;
		}
	}
	return -1;
}

void udp_send(ipv4_t dst, uint16_t dst_port, uint16_t src_port,
	      const void *payload, uint16_t len)
{
	static uint8_t seg[FRAME_MAX];
	struct udp_hdr *udp = (struct udp_hdr *)seg;
	uint16_t total = (uint16_t)(sizeof(*udp) + len);

	if (total > FRAME_MAX)
		return;
	udp->src_port = htons(src_port);
	udp->dst_port = htons(dst_port);
	udp->len = htons(total);
	udp->checksum = 0;
	kmemcpy(seg + sizeof(*udp), payload, len);

	/* Pseudo-header + segment checksum. */
	uint32_t sum = 0;
	uint32_t s = htonl(g_ip ? g_ip : 0), d = htonl(dst);
	uint8_t pseudo[12];
	kmemcpy(pseudo, &s, 4);
	kmemcpy(pseudo + 4, &d, 4);
	pseudo[8] = 0;
	pseudo[9] = IP_PROTO_UDP;
	pseudo[10] = (uint8_t)(total >> 8);
	pseudo[11] = (uint8_t)total;
	sum = csum_add(sum, pseudo, 12);
	sum = csum_add(sum, seg, total);
	udp->checksum = htons(csum_fold(sum));
	if (udp->checksum == 0)
		udp->checksum = 0xFFFF;

	ip_send(dst, IP_PROTO_UDP, seg, total);
}

void udp_input(ipv4_t src, const struct udp_hdr *udp, uint16_t udp_total)
{
	uint16_t dport = ntohs(udp->dst_port);
	uint16_t sport = ntohs(udp->src_port);

	if (udp_total < sizeof(*udp))
		return;
	const uint8_t *data = (const uint8_t *)udp + sizeof(*udp);
	uint16_t dlen = (uint16_t)(udp_total - sizeof(*udp));

	for (int i = 0; i < UDP_BINDINGS; i++) {
		if (g_udp[i].handler && g_udp[i].port == dport) {
			g_udp[i].handler(src, sport, data, dlen);
			return;
		}
	}
}
