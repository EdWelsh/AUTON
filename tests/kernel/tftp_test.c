/* Gate tests for the TFTP server (agent/kernel_spec/services/tftp.md).
 *
 * Written and frozen BEFORE the F6 re-run (w13): this is the gate an
 * agent-authored server must pass, not a test fitted to its output. The
 * agent's own tests are measured separately. Every acceptance criterion in
 * tftp.md that the packet path can show has a case here; the serve loop
 * (criterion 1's "listening" marker) needs a NIC and is checked at boot.
 */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "tftp.h"

static int fails;
static void ok(const char *name, int cond, const char *detail)
{
	if (cond) printf("PASS  %-60s\n", name);
	else { printf("FAIL  %-60s  %s\n", name, detail ? detail : ""); fails++; }
}

/* --- captured log --------------------------------------------------------- */
static char logbuf[8192];
static size_t loglen;
int test_kprintf(const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	int n = vsnprintf(logbuf + loglen, sizeof logbuf - loglen, fmt, ap);
	va_end(ap);
	if (n > 0)
		loglen += (size_t)n < sizeof logbuf - loglen ? (size_t)n : sizeof logbuf - loglen - 1;
	return n;
}
static void log_reset(void) { loglen = 0; logbuf[0] = 0; }
static int logged(const char *s) { return strstr(logbuf, s) != NULL; }

/* --- a client ---------------------------------------------------------------- */
#define CLIENT  IPV4(10, 0, 2, 2)
#define STRAY   IPV4(10, 0, 2, 9)
static uint32_t now;
static tftp_reply_t r;

static uint16_t op(void) { return (uint16_t)(r.payload[0] << 8 | r.payload[1]); }
static uint16_t num(void) { return (uint16_t)(r.payload[2] << 8 | r.payload[3]); }

static void rrq(const char *name, const char *mode)
{
	uint8_t p[128];
	size_t n = 0;
	p[n++] = 0; p[n++] = 1;
	memcpy(p + n, name, strlen(name) + 1); n += strlen(name) + 1;
	memcpy(p + n, mode, strlen(mode) + 1); n += strlen(mode) + 1;
	tftp_handle(CLIENT, 3000, 69, p, (uint32_t)n, now, &r);
}

static void ack(ipv4_t from, uint16_t sport, uint16_t tid, uint16_t block)
{
	uint8_t p[4] = {0, 4, (uint8_t)(block >> 8), (uint8_t)block};
	tftp_handle(from, sport, tid, p, 4, now, &r);
}

static int is_data(uint16_t block, uint32_t size)
{
	return r.len == 4 + size && op() == 3 && num() == block;
}

/* Receive a whole file from the current transfer; returns bytes, -1 on error. */
static int fetch(uint16_t tid, uint8_t *out, int max_blocks, int *blocks)
{
	int total = 0;
	*blocks = 0;
	for (int b = 1; b <= max_blocks; b++) {
		if (r.len < 4 || op() != 3 || num() != b)
			return -1;
		uint32_t n = r.len - 4;
		memcpy(out + total, r.payload + 4, n);
		total += (int)n;
		(*blocks)++;
		ack(CLIENT, 3000, tid, (uint16_t)b);
		if (n < TFTP_BLOCK)
			return total;
	}
	return -1;
}

int main(void)
{
	char why[160];
	static uint8_t got[4096];
	int blocks;

	/* --- criteria 1-2: pattern.bin, markers, content ------------------------ */
	tftp_server_init();
	log_reset();
	rrq("pattern.bin", "octet");
	uint16_t tid = r.src_port;
	ok("an RRQ is answered with DATA block 1 of 512 bytes", is_data(1, 512), NULL);
	ok("DATA comes from a new TID, not port 69", tid != 69 && tid >= 49152, NULL);
	ok("DATA goes to the client's port", r.dst_ip == CLIENT && r.dst_port == 3000, NULL);
	ok("marker: [TFTP] RRQ pattern.bin octet", logged("[TFTP] RRQ pattern.bin octet"), logbuf);
	int n = fetch(tid, got, 10, &blocks);
	int bytes_ok = n == 1300;
	for (int i = 0; bytes_ok && i < 1300; i++)
		bytes_ok = got[i] == (uint8_t)(i & 0xFF);
	snprintf(why, sizeof why, "%d bytes in %d blocks", n, blocks);
	ok("pattern.bin arrives as 1300 bytes, byte i == i & 0xFF", bytes_ok, why);
	ok("... in exactly 3 blocks", blocks == 3, why);
	ok("the final ACK sends nothing", r.len == 0, NULL);
	ok("marker: [TFTP] sent pattern.bin 1300 bytes in 3 blocks",
	   logged("[TFTP] sent pattern.bin 1300 bytes in 3 blocks"), logbuf);
	rrq("pattern.bin", "OCTET");
	ok("the mode is compared case-insensitively", is_data(1, 512), NULL);
	uint16_t tid2 = r.src_port;
	ok("each transfer gets a fresh TID", tid2 != tid, NULL);
	fetch(tid2, got, 10, &blocks);

	/* --- criterion 3: exact.bin ends on an EMPTY block ----------------------- */
	rrq("exact.bin", "octet");
	tid = r.src_port;
	n = fetch(tid, got, 10, &blocks);
	snprintf(why, sizeof why, "%d bytes in %d blocks", n, blocks);
	ok("exact.bin arrives as 1024 bytes over 3 blocks, the last empty",
	   n == 1024 && blocks == 3, why);

	/* --- criterion 4: a duplicate ACK sends nothing -------------------------- */
	rrq("pattern.bin", "octet");
	tid = r.src_port;
	ack(CLIENT, 3000, tid, 1);
	ok("ACK 1 brings block 2", is_data(2, 512), NULL);
	ack(CLIENT, 3000, tid, 1);
	ok("a duplicate ACK 1 sends nothing (Sorcerer's Apprentice)", r.len == 0, NULL);

	/* An ACK for a block that was never sent: tftp.md's ACK rule 4, "any other
	 * block number -> ignore".
	 *
	 * This case was missing until w14, and its absence was found the way gaps
	 * are meant to be: by injecting the bug into an AGENT's implementation and
	 * watching the suite pass anyway. Accepting an out-of-range ACK advances
	 * the transfer to a block the client never asked for, which loses data
	 * silently. */
	ack(CLIENT, 3000, tid, 99);
	ok("an ACK for a block never sent is ignored", r.len == 0,
	   "accepting it advances past blocks the client never received");
	ack(CLIENT, 3000, tid, 0);
	ok("an ACK 0 mid-transfer is ignored too", r.len == 0, NULL);

	/* --- criterion 5: a stray TID gets ERROR 5; the transfer lives ----------- */
	ack(STRAY, 4444, tid, 2);
	ok("a datagram from another TID gets ERROR 5",
	   r.len >= 4 && op() == 5 && num() == 5 && r.dst_ip == STRAY && r.dst_port == 4444, NULL);
	ack(CLIENT, 3000, tid, 2);
	ok("... and the real client's transfer continues", is_data(3, 276), NULL);
	ack(CLIENT, 3000, tid, 3);

	/* --- busy --------------------------------------------------------------- */
	rrq("pattern.bin", "octet");
	tid = r.src_port;
	rrq("exact.bin", "octet");
	ok("a second RRQ mid-transfer gets ERROR 0 busy from port 69",
	   r.len >= 4 && op() == 5 && num() == 0 && r.src_port == 69 &&
	   strstr((const char *)r.payload + 4, "busy"), NULL);
	ack(CLIENT, 3000, tid, 1);
	ok("... without disturbing the first", is_data(2, 512), NULL);
	ack(CLIENT, 3000, tid, 2);
	ack(CLIENT, 3000, tid, 3);

	/* --- criterion 6: an unterminated filename never reads past the end ------ */
	uint8_t bad[] = {0, 1, 'p', 'a', 't', 't'};  /* no NUL: ASan catches an over-read */
	tftp_handle(CLIENT, 3000, 69, bad, sizeof bad, now, &r);
	ok("an unterminated filename is dropped", r.len == 0, NULL);
	uint8_t nomode[] = {0, 1, 'x', 0, 'o', 'c'};
	tftp_handle(CLIENT, 3000, 69, nomode, sizeof nomode, now, &r);
	ok("an unterminated mode is dropped", r.len == 0, NULL);
	uint8_t tiny[] = {0};
	tftp_handle(CLIENT, 3000, 69, tiny, 1, now, &r);
	ok("a datagram shorter than 2 bytes is dropped", r.len == 0, NULL);

	/* --- criterion 7: refusals ---------------------------------------------- */
	uint8_t wrq[] = {0, 2, 'a', 0, 'o', 'c', 't', 'e', 't', 0};
	tftp_handle(CLIENT, 3000, 69, wrq, sizeof wrq, now, &r);
	ok("WRQ gets ERROR 2", r.len >= 4 && op() == 5 && num() == 2, NULL);
	rrq("pattern.bin", "netascii");
	ok("netascii gets ERROR 0", r.len >= 4 && op() == 5 && num() == 0 &&
	   strstr((const char *)r.payload + 4, "netascii"), NULL);
	rrq("nope.bin", "octet");
	ok("an unknown file gets ERROR 1", r.len >= 4 && op() == 5 && num() == 1, NULL);
	rrq("pattern.bin", "mail");
	ok("another mode gets ERROR 4", r.len >= 4 && op() == 5 && num() == 4, NULL);
	ok("RRQ errors come from port 69", r.src_port == 69, NULL);

	/* --- criterion 8: 5 retransmissions, then abandon ------------------------ */
	log_reset();
	now = 10000;
	rrq("pattern.bin", "octet");
	tid = r.src_port;
	int resent = 0;
	for (int i = 1; i <= 6; i++) {
		now += 1000;
		tftp_tick(now, &r);
		if (is_data(1, 512))
			resent++;
	}
	snprintf(why, sizeof why, "%d resends", resent);
	ok("block 1 is resent exactly 5 times on timeout", resent == 5, why);
	ok("the 6th timeout abandons, logging it", r.len == 0 &&
	   logged("[TFTP] timeout pattern.bin at block 1"), logbuf);
	now += 999;
	tftp_tick(now, &r);
	ok("nothing is sent before the timeout elapses", r.len == 0, NULL);
	rrq("pattern.bin", "octet");
	ok("after abandoning, a new RRQ is accepted", is_data(1, 512), NULL);

	/* --- an ERROR from the peer ends the transfer silently ------------------- */
	tid = r.src_port;
	uint8_t perr[] = {0, 5, 0, 0, 'x', 0};
	tftp_handle(CLIENT, 3000, tid, perr, sizeof perr, now, &r);
	ok("an ERROR from the peer is not answered", r.len == 0, NULL);
	rrq("exact.bin", "octet");
	ok("... and frees the server for the next RRQ", is_data(1, 512), NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
