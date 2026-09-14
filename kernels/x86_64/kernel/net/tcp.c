/* Minimal single-connection TCP server. No retransmit, no window scaling, one
 * connection at a time — enough to serve a request over QEMU's reliable SLIRP
 * loopback (hostfwd). Passive open only: LISTEN -> SYN_RCVD -> ESTABLISHED ->
 * (app replies, we FIN) -> back to LISTEN. */
#include "net.h"
#include "kernel.h"

#define TCP_WINDOW 8192u
#define TCP_ISS    0x00001000u
#define SEGBUF     1600

enum { S_CLOSED, S_LISTEN, S_SYN_RCVD, S_ESTABLISHED };

static int           st = S_CLOSED;
static ipv4_t        peer_ip;
static uint16_t      peer_port, listen_port;
static uint32_t      snd_nxt, rcv_nxt;
static tcp_handler_t app;

static void send_seg(uint8_t flags, const void *data, uint16_t dlen)
{
	static uint8_t seg[SEGBUF];
	struct tcp_hdr *th = (struct tcp_hdr *)seg;
	uint16_t total = (uint16_t)(sizeof(*th) + dlen);

	if (total > SEGBUF)
		return;
	kmemset(th, 0, sizeof(*th));
	th->src_port = htons(listen_port);
	th->dst_port = htons(peer_port);
	th->seq = htonl(snd_nxt);
	th->ack = htonl(rcv_nxt);
	th->data_off = (uint8_t)((sizeof(*th) / 4) << 4);
	th->flags = flags;
	th->window = htons(TCP_WINDOW);
	if (dlen)
		kmemcpy(seg + sizeof(*th), data, dlen);

	/* Pseudo-header + segment checksum. */
	uint32_t sum = 0;
	uint32_t s = htonl(net_ip()), d = htonl(peer_ip);
	uint8_t pseudo[12];
	kmemcpy(pseudo, &s, 4);
	kmemcpy(pseudo + 4, &d, 4);
	pseudo[8] = 0;
	pseudo[9] = IP_PROTO_TCP;
	pseudo[10] = (uint8_t)(total >> 8);
	pseudo[11] = (uint8_t)total;
	sum = csum_add(sum, pseudo, 12);
	sum = csum_add(sum, seg, total);
	th->checksum = htons(csum_fold(sum));

	ip_send(peer_ip, IP_PROTO_TCP, seg, total);
}

void tcp_listen(uint16_t port, tcp_handler_t handler)
{
	listen_port = port;
	app = handler;
	st = S_LISTEN;
}

void tcp_send(const void *data, uint16_t len)
{
	if (st != S_ESTABLISHED)
		return;
	send_seg(TCP_PSH | TCP_ACK, data, len);
	snd_nxt += len;
}

void tcp_close(void)
{
	if (st == S_CLOSED || st == S_LISTEN)
		return;
	send_seg(TCP_FIN | TCP_ACK, 0, 0);
	snd_nxt += 1;
	st = S_LISTEN;          /* ready for the next connection */
}

static void deliver(const uint8_t *payload, uint16_t plen)
{
	rcv_nxt += plen;
	send_seg(TCP_ACK, 0, 0);
	if (app)
		app(payload, plen);     /* app may tcp_send()+tcp_close() */
}

void tcp_input(ipv4_t src, const uint8_t *seg, uint16_t len)
{
	if (len < sizeof(struct tcp_hdr))
		return;
	const struct tcp_hdr *th = (const struct tcp_hdr *)seg;

	if (st == S_CLOSED || ntohs(th->dst_port) != listen_port)
		return;

	uint8_t  flags = th->flags;
	uint32_t their_seq = ntohl(th->seq);
	uint32_t their_ack = ntohl(th->ack);
	uint16_t off = (uint16_t)((th->data_off >> 4) * 4);
	if (off < sizeof(*th) || off > len)
		return;
	const uint8_t *payload = seg + off;
	uint16_t plen = (uint16_t)(len - off);

	if (flags & TCP_RST) {
		st = S_LISTEN;
		return;
	}

	switch (st) {
	case S_LISTEN:
		if (flags & TCP_SYN) {
			peer_ip = src;
			peer_port = ntohs(th->src_port);
			rcv_nxt = their_seq + 1;
			snd_nxt = TCP_ISS;
			send_seg(TCP_SYN | TCP_ACK, 0, 0);
			snd_nxt += 1;
			st = S_SYN_RCVD;
		}
		break;

	case S_SYN_RCVD:
		if ((flags & TCP_ACK) && their_ack == snd_nxt) {
			st = S_ESTABLISHED;
			if (plen > 0 && their_seq == rcv_nxt)
				deliver(payload, plen);
		}
		break;

	case S_ESTABLISHED:
		if (plen > 0 && their_seq == rcv_nxt)
			deliver(payload, plen);
		if ((flags & TCP_FIN) && st == S_ESTABLISHED &&
		    their_seq + plen == rcv_nxt) {
			rcv_nxt += 1;
			send_seg(TCP_FIN | TCP_ACK, 0, 0);
			snd_nxt += 1;
			st = S_LISTEN;
		}
		break;
	}
}
