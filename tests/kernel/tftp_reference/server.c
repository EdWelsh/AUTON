/* Reference TFTP server (read-only), implementing services/tftp.md.
 *
 * NOT kernel code and not shipped. It proves tftp_test.c, the gate an
 * agent-authored server must pass in F6. RFC 1350 + RFC 1123 §4.2.3.1.
 */
#include <stdint.h>
#include "tftp.h"
#include "kernel.h"

#define OP_RRQ   1
#define OP_WRQ   2
#define OP_DATA  3
#define OP_ACK   4
#define OP_ERROR 5
#define TFTP_PORT 69

static uint8_t pattern[TFTP_FILE_PATTERN_LEN];
static uint8_t exact[TFTP_FILE_EXACT_LEN];
static tftp_xfer_t x;
static const char *x_name;
static uint32_t transfers;

static const struct { const char *name; const uint8_t *data; uint32_t len; } files[] = {
	{"pattern.bin", pattern, TFTP_FILE_PATTERN_LEN},
	{"exact.bin", exact, TFTP_FILE_EXACT_LEN},
};

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }
static void wr16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }

static char lower(char c) { return (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c; }
static int same_ci(const char *a, const char *b)
{
	for (; *a && *b; a++, b++)
		if (lower(*a) != lower(*b))
			return 0;
	return *a == *b;
}
static int same(const char *a, const char *b)
{
	for (; *a && *b; a++, b++)
		if (*a != *b)
			return 0;
	return *a == *b;
}

void tftp_server_init(void)
{
	for (uint32_t i = 0; i < TFTP_FILE_PATTERN_LEN; i++)
		pattern[i] = (uint8_t)(i & 0xFF);
	for (uint32_t i = 0; i < TFTP_FILE_EXACT_LEN; i++)
		exact[i] = (uint8_t)(i & 0xFF);
	x.active = 0;
	transfers = 0;
}

static void error(tftp_reply_t *out, ipv4_t ip, uint16_t port, uint16_t from,
                  uint16_t code, const char *msg)
{
	out->dst_ip = ip;
	out->dst_port = port;
	out->src_port = from;
	wr16(out->payload, OP_ERROR);
	wr16(out->payload + 2, code);
	uint32_t n = 4;
	while (*msg && n < sizeof out->payload - 1)
		out->payload[n++] = (uint8_t)*msg++;
	out->payload[n++] = 0;
	out->len = n;
}

static void send_block(tftp_reply_t *out, uint32_t now_ms)
{
	uint32_t off = (uint32_t)(x.block - 1) * TFTP_BLOCK;
	uint32_t n = x.file_len > off ? x.file_len - off : 0;
	if (n > TFTP_BLOCK)
		n = TFTP_BLOCK;
	out->dst_ip = x.peer_ip;
	out->dst_port = x.peer_tid;
	out->src_port = x.our_tid;
	wr16(out->payload, OP_DATA);
	wr16(out->payload + 2, x.block);
	for (uint32_t i = 0; i < n; i++)
		out->payload[4 + i] = x.file[off + i];
	out->len = 4 + n;
	x.sent_at_ms = now_ms;
}

/* The block number of the final block: the first whose DATA is < 512 bytes,
 * which is an empty block when the length is a multiple of 512 (RFC 1350 §6). */
static uint16_t last_block(void) { return (uint16_t)(x.file_len / TFTP_BLOCK + 1); }

/* A NUL-terminated string starting at p within [p, end), or 0. */
static const char *cstr(const uint8_t *p, const uint8_t *end)
{
	for (const uint8_t *q = p; q < end; q++)
		if (*q == 0)
			return (const char *)p;
	return 0;
}

static void rrq(ipv4_t src, uint16_t sport, const uint8_t *pl, uint32_t len,
                uint32_t now_ms, tftp_reply_t *out)
{
	const uint8_t *end = pl + len;
	const char *name = cstr(pl + 2, end);
	if (!name)
		return;                     /* unterminated: drop, never read past */
	const uint8_t *m = (const uint8_t *)name;
	while (*m)
		m++;
	const char *mode = cstr(m + 1, end);
	if (!mode)
		return;

	if (same_ci(mode, "netascii")) {
		error(out, src, sport, TFTP_PORT, 0, "netascii not supported");
		return;
	}
	if (!same_ci(mode, "octet")) {
		error(out, src, sport, TFTP_PORT, 4, "illegal TFTP operation");
		return;
	}
	int f = -1;
	for (int i = 0; i < 2; i++)
		if (same(name, files[i].name))
			f = i;
	if (f < 0) {
		error(out, src, sport, TFTP_PORT, 1, "file not found");
		return;
	}
	if (x.active) {
		error(out, src, sport, TFTP_PORT, 0, "busy");
		return;
	}
	x.active = 1;
	x.peer_ip = src;
	x.peer_tid = sport;
	x.our_tid = (uint16_t)(49152 + transfers % 16384);
	transfers++;
	x.file = files[f].data;
	x.file_len = files[f].len;
	x.block = 1;
	x.retries = 0;
	x_name = files[f].name;
	kprintf("[TFTP] RRQ %s %s\n", name, mode);
	send_block(out, now_ms);
}

void tftp_handle(ipv4_t src, uint16_t sport, uint16_t dport,
                 const uint8_t *payload, uint32_t len, uint32_t now_ms,
                 tftp_reply_t *out)
{
	out->len = 0;
	if (len < 2)
		return;
	uint16_t op = rd16(payload);

	if (dport == TFTP_PORT) {
		if (op == OP_RRQ)
			rrq(src, sport, payload, len, now_ms, out);
		else if (op == OP_WRQ)
			error(out, src, sport, TFTP_PORT, 2, "read-only");
		/* DATA, ACK, ERROR on port 69: dropped */
		return;
	}

	if (!x.active || dport != x.our_tid)
		return;
	if (src != x.peer_ip || sport != x.peer_tid) {
		/* RFC 1350 §4: a stranger on our TID gets ERROR 5; the transfer lives. */
		error(out, src, sport, x.our_tid, 5, "unknown transfer ID");
		return;
	}
	if (op == OP_ERROR) {
		x.active = 0;               /* RFC 1350 §7: not acknowledged */
		return;
	}
	if (op != OP_ACK || len < 4)
		return;
	uint16_t block = rd16(payload + 2);
	if (block == x.block) {
		if (x.block == last_block()) {
			kprintf("[TFTP] sent %s %u bytes in %u blocks\n", x_name,
			        (unsigned)x.file_len, (unsigned)x.block);
			x.active = 0;
			return;
		}
		x.block++;
		x.retries = 0;
		send_block(out, now_ms);
	}
	/* A duplicate ACK (block - 1) sends nothing: RFC 1123 §4.2.3.1, the
	 * Sorcerer's Apprentice fix. Anything else is ignored. */
}

void tftp_tick(uint32_t now_ms, tftp_reply_t *out)
{
	out->len = 0;
	if (!x.active || now_ms - x.sent_at_ms < TFTP_TIMEOUT_MS)
		return;
	if (x.retries >= TFTP_MAX_RETRIES) {
		kprintf("[TFTP] timeout %s at block %u\n", x_name, (unsigned)x.block);
		x.active = 0;
		return;
	}
	x.retries++;
	send_block(out, now_ms);
}

void tftp_serve(void)
{
	/* The loop is not host-testable (no NIC); the packet path above is. */
}
