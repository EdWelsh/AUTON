/* ARP: resolve IPv4 -> MAC and answer who-has requests for our address. */
#include "net.h"
#include "kernel.h"

#define ARP_CACHE 16
#define ARP_REQUEST 1
#define ARP_REPLY   2

struct arp_pkt {
	uint16_t htype;
	uint16_t ptype;
	uint8_t  hlen;
	uint8_t  plen;
	uint16_t oper;
	uint8_t  sha[6];
	uint32_t spa;           /* network order */
	uint8_t  tha[6];
	uint32_t tpa;           /* network order */
} __attribute__((packed));

struct arp_entry {
	ipv4_t  ip;
	uint8_t mac[6];
	int     valid;
};
static struct arp_entry cache[ARP_CACHE];

static const uint8_t bcast[6] = { 0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF };

static void cache_put(ipv4_t ip, const uint8_t mac[6])
{
	for (int i = 0; i < ARP_CACHE; i++) {
		if (cache[i].valid && cache[i].ip == ip) {
			kmemcpy(cache[i].mac, mac, 6);
			return;
		}
	}
	for (int i = 0; i < ARP_CACHE; i++) {
		if (!cache[i].valid) {
			cache[i].ip = ip;
			kmemcpy(cache[i].mac, mac, 6);
			cache[i].valid = 1;
			return;
		}
	}
	cache[0].ip = ip;       /* evict slot 0 if full */
	kmemcpy(cache[0].mac, mac, 6);
}

static void arp_request(ipv4_t ip)
{
	struct arp_pkt p;

	kmemset(&p, 0, sizeof(p));
	p.htype = htons(1);
	p.ptype = htons(ETHERTYPE_IP);
	p.hlen = 6;
	p.plen = 4;
	p.oper = htons(ARP_REQUEST);
	kmemcpy(p.sha, net_mac(), 6);
	p.spa = htonl(net_ip());
	p.tpa = htonl(ip);
	eth_send(bcast, ETHERTYPE_ARP, &p, sizeof(p));
}

void net_flush_kick(void)
{
	/* Any transmit makes QEMU flush queued inbound packets to the NIC. A
	 * gratuitous ARP for our own address is harmless and serves that role. */
	arp_request(net_ip());
}

int arp_resolve(ipv4_t ip, uint8_t mac_out[6])
{
	for (int i = 0; i < ARP_CACHE; i++) {
		if (cache[i].valid && cache[i].ip == ip) {
			kmemcpy(mac_out, cache[i].mac, 6);
			return 1;
		}
	}
	arp_request(ip);
	return 0;
}

void arp_input(const uint8_t *frame, uint16_t len)
{
	if (len < sizeof(struct eth_hdr) + sizeof(struct arp_pkt))
		return;
	const struct arp_pkt *p =
		(const struct arp_pkt *)(frame + sizeof(struct eth_hdr));

	if (ntohs(p->ptype) != ETHERTYPE_IP || p->plen != 4)
		return;

	ipv4_t spa = ntohl(p->spa);
	ipv4_t tpa = ntohl(p->tpa);
	cache_put(spa, p->sha);

	if (ntohs(p->oper) == ARP_REQUEST && tpa == net_ip() && net_ip() != 0) {
		struct arp_pkt r;
		kmemset(&r, 0, sizeof(r));
		r.htype = htons(1);
		r.ptype = htons(ETHERTYPE_IP);
		r.hlen = 6;
		r.plen = 4;
		r.oper = htons(ARP_REPLY);
		kmemcpy(r.sha, net_mac(), 6);
		r.spa = htonl(net_ip());
		kmemcpy(r.tha, p->sha, 6);
		r.tpa = p->spa;
		eth_send(p->sha, ETHERTYPE_ARP, &r, sizeof(r));
	}
}
