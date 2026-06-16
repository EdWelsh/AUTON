/* Minimal polled IPv4 stack: Ethernet + ARP + IPv4/ICMP + UDP (+ TCP later).
 * IPs are carried as host-order uint32 (ipv4_t) and byte-swapped at the wire. */
#ifndef AUTON_NET_H
#define AUTON_NET_H

#include <stdint.h>

typedef uint32_t ipv4_t;

#define ETHERTYPE_IP   0x0800
#define ETHERTYPE_ARP  0x0806
#define IP_PROTO_ICMP  1
#define IP_PROTO_TCP   6
#define IP_PROTO_UDP   17

#define IPV4(a, b, c, d) \
	(((ipv4_t)(a) << 24) | ((ipv4_t)(b) << 16) | ((ipv4_t)(c) << 8) | (ipv4_t)(d))
#define IP_BROADCAST IPV4(255, 255, 255, 255)

/* ---- wire headers (all multi-byte fields are network byte order) ---- */
struct eth_hdr {
	uint8_t  dst[6];
	uint8_t  src[6];
	uint16_t type;
} __attribute__((packed));

struct ip_hdr {
	uint8_t  ver_ihl;
	uint8_t  tos;
	uint16_t total_len;
	uint16_t id;
	uint16_t frag;
	uint8_t  ttl;
	uint8_t  proto;
	uint16_t checksum;
	uint32_t src;
	uint32_t dst;
} __attribute__((packed));

struct udp_hdr {
	uint16_t src_port;
	uint16_t dst_port;
	uint16_t len;
	uint16_t checksum;
} __attribute__((packed));

struct tcp_hdr {
	uint16_t src_port;
	uint16_t dst_port;
	uint32_t seq;
	uint32_t ack;
	uint8_t  data_off;      /* high nibble: header length in 32-bit words */
	uint8_t  flags;
	uint16_t window;
	uint16_t checksum;
	uint16_t urgent;
} __attribute__((packed));

#define TCP_FIN 0x01
#define TCP_SYN 0x02
#define TCP_RST 0x04
#define TCP_PSH 0x08
#define TCP_ACK 0x10

/* ---- byte order (x86 is little-endian) ---- */
static inline uint16_t htons(uint16_t x) { return (uint16_t)((x << 8) | (x >> 8)); }
static inline uint16_t ntohs(uint16_t x) { return htons(x); }
static inline uint32_t htonl(uint32_t x)
{
	return ((x & 0xFFu) << 24) | ((x & 0xFF00u) << 8) |
	       ((x >> 8) & 0xFF00u) | ((x >> 24) & 0xFFu);
}
static inline uint32_t ntohl(uint32_t x) { return htonl(x); }

/* ---- checksum (Internet ones-complement over big-endian 16-bit words) ---- */
uint32_t csum_add(uint32_t sum, const void *data, uint16_t len);
uint16_t csum_fold(uint32_t sum);
/* Returns the host-order checksum; store into a wire field via htons(...). */
uint16_t net_checksum(const void *data, uint16_t len);

/* ---- runtime state ---- */
void   net_init(const uint8_t mac[6]);
void   net_set_ipcfg(ipv4_t ip, ipv4_t mask, ipv4_t gw, ipv4_t dns);
ipv4_t net_ip(void);
ipv4_t net_mask(void);
ipv4_t net_gw(void);
ipv4_t net_dns(void);
const uint8_t *net_mac(void);
int    net_is_up(void);                 /* 1 once an IP is configured */

/* Pump one RX frame through the stack. Call frequently (polled). */
void net_poll(void);

/* Run the DHCP exchange (after net_init). Returns 0 if an IP was leased. */
int dhcp_run(void);

/* Find a supported NIC among the scanned PCI devices, bring it up, and run
 * DHCP. Prints [NET] markers. Returns 0 if the link is up (even without a
 * lease), -1 if no supported NIC was found. */
struct pci_device;
int net_bringup(const struct pci_device *devs, uint32_t ndev);

/* ---- layer send paths ---- */
void eth_send(const uint8_t dst[6], uint16_t ethertype,
	      const void *payload, uint16_t len);
void ip_send(ipv4_t dst, uint8_t proto, const void *payload, uint16_t len);
void udp_send(ipv4_t dst, uint16_t dst_port, uint16_t src_port,
	      const void *payload, uint16_t len);

/* ---- inbound dispatch (called by net_poll) ---- */
void arp_input(const uint8_t *frame, uint16_t len);
void ip_input(const uint8_t *frame, uint16_t len);
void udp_input(ipv4_t src, const struct udp_hdr *udp, uint16_t udp_total);
void tcp_input(ipv4_t src, const uint8_t *seg, uint16_t len);  /* Phase H */

/* Resolve 'ip' to a MAC (cache; sends a request on miss). Returns 1 if known. */
int  arp_resolve(ipv4_t ip, uint8_t mac_out[6]);

/* Register a UDP port handler. Returns 0 on success. */
typedef void (*udp_handler_t)(ipv4_t src, uint16_t src_port,
			      const uint8_t *data, uint16_t len);
int  udp_bind(uint16_t port, udp_handler_t handler);

/* ---- minimal single-connection TCP (server side) ---- */
/* Called when request bytes arrive on an established connection. The handler
 * typically replies with tcp_send() then tcp_close(). */
typedef void (*tcp_handler_t)(const uint8_t *data, uint16_t len);

/* Passively listen on 'port'. One connection at a time. */
void tcp_listen(uint16_t port, tcp_handler_t handler);
/* Send response bytes on the active connection (PSH|ACK). */
void tcp_send(const void *data, uint16_t len);
/* Half-close the active connection (FIN) and return to listening. */
void tcp_close(void);

/* Emit a benign frame (gratuitous ARP) to coax the SLIRP backend into
 * flushing any queued inbound packet — see the polled-RX note in e1000.c.
 * Call periodically from idle/serve loops so a client's first packet (e.g. a
 * TCP SYN) is delivered even when we are not otherwise transmitting. */
void net_flush_kick(void);

#endif /* AUTON_NET_H */
