/* IPv4: build/parse datagrams, route to the next hop via ARP, demux to
 * ICMP/UDP. (TCP demux is added in Phase H.) */
#include "net.h"
#include "kernel.h"

#define FRAME_MAX 1600

static const uint8_t bcast[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };
static uint16_t g_ip_id = 1;

void ip_send(ipv4_t dst, uint8_t proto, const void *payload, uint16_t len)
{
	static uint8_t pkt[FRAME_MAX];
	struct ip_hdr *ip = (struct ip_hdr *)pkt;
	uint16_t total = (uint16_t)(sizeof(*ip) + len);
	uint8_t mac[6];

	if (total > FRAME_MAX)
		return;

	/* Resolve the next-hop link address. */
	if (dst == IP_BROADCAST) {
		kmemcpy(mac, bcast, 6);
	} else {
		ipv4_t nh = ((dst ^ net_ip()) & net_mask()) ? net_gw() : dst;
		if (nh == 0)
			nh = dst;
		if (!arp_resolve(nh, mac))
			return;         /* request sent; caller retries later */
	}

	ip->ver_ihl = 0x45;
	ip->tos = 0;
	ip->total_len = htons(total);
	ip->id = htons(g_ip_id++);
	ip->frag = 0;
	ip->ttl = 64;
	ip->proto = proto;
	ip->checksum = 0;
	ip->src = htonl(net_ip());
	ip->dst = htonl(dst);
	ip->checksum = htons(net_checksum(ip, sizeof(*ip)));

	kmemcpy(pkt + sizeof(*ip), payload, len);
	eth_send(mac, ETHERTYPE_IP, pkt, total);
}

static void icmp_echo_reply(ipv4_t src, uint8_t *icmp, uint16_t len)
{
	if (len < 8 || icmp[0] != 8 /* echo request */)
		return;
	icmp[0] = 0;                    /* echo reply */
	icmp[2] = 0;                    /* zero checksum before recompute */
	icmp[3] = 0;
	uint16_t c = net_checksum(icmp, len);
	icmp[2] = (uint8_t)(c >> 8);
	icmp[3] = (uint8_t)c;
	ip_send(src, IP_PROTO_ICMP, icmp, len);
}

void ip_input(const uint8_t *frame, uint16_t len)
{
	if (len < sizeof(struct eth_hdr) + sizeof(struct ip_hdr))
		return;
	struct ip_hdr *ip = (struct ip_hdr *)(frame + sizeof(struct eth_hdr));

	if ((ip->ver_ihl >> 4) != 4)
		return;
	uint16_t ihl = (uint16_t)((ip->ver_ihl & 0x0F) * 4);
	uint16_t total = ntohs(ip->total_len);
	if (ihl < sizeof(struct ip_hdr) || total < ihl)
		return;

	ipv4_t src = ntohl(ip->src);
	uint8_t *l4 = (uint8_t *)ip + ihl;
	uint16_t l4_len = (uint16_t)(total - ihl);

	switch (ip->proto) {
	case IP_PROTO_ICMP:
		icmp_echo_reply(src, l4, l4_len);
		break;
	case IP_PROTO_UDP:
		udp_input(src, (const struct udp_hdr *)l4, l4_len);
		break;
	case IP_PROTO_TCP:
		tcp_input(src, l4, l4_len);
		break;
	default:
		break;
	}
}
