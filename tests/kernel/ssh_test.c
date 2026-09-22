/* Host suite for the SSH service (agent/kernel_spec/services/ssh.md).
 *
 * What a host can prove about SSH without a network or a key: the binary
 * packet protocol and its refusals, name-list negotiation against a REAL
 * OpenSSH client's recorded KEXINIT, and the exchange-hash input byte for byte
 * against a fixture built independently in Python from the RFCs
 * (ssh_fixtures/make_fixtures.py).
 *
 * The encodings are the point. An SSH server that gets the crypto right and
 * `mpint` wrong fails every handshake, and the failure says nothing useful.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "ssh_wire.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-62s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

static uint8_t *slurp(const char *path, size_t *len)
{
	FILE *f = fopen(path, "rb");
	if (!f) {
		fprintf(stderr, "cannot open %s\n", path);
		exit(2);
	}
	fseek(f, 0, SEEK_END);
	long n = ftell(f);
	fseek(f, 0, SEEK_SET);
	uint8_t *b = malloc((size_t)n);
	if (fread(b, 1, (size_t)n, f) != (size_t)n) {
		fprintf(stderr, "short read %s\n", path);
		exit(2);
	}
	fclose(f);
	*len = (size_t)n;
	return b;
}

int main(int argc, char **argv)
{
	const char *dir = argc > 1 ? argv[1] : "tests/kernel/ssh_fixtures";
	char path[512];
	size_t hello_len, want_len, i_s_len;

	snprintf(path, sizeof path, "%s/openssh_client_hello.bin", dir);
	uint8_t *hello = slurp(path, &hello_len);
	snprintf(path, sizeof path, "%s/exchange_hash_input.bin", dir);
	uint8_t *want = slurp(path, &want_len);
	snprintf(path, sizeof path, "%s/server_kexinit.bin", dir);
	uint8_t *i_s = slurp(path, &i_s_len);

	/* --- the recorded client: version line, then one KEXINIT packet ----- */
	uint8_t *crlf = (uint8_t *)memmem(hello, hello_len, "\r\n", 2);
	ok("the recording starts with a version line", crlf != NULL, NULL);
	size_t v_c_len = (size_t)(crlf - hello);
	ok("the client is an OpenSSH client",
	   v_c_len > 8 && memcmp(hello, "SSH-2.0-OpenSSH", 15) == 0, NULL);

	const uint8_t *payload;
	size_t payload_len;
	const char *why;
	int parsed = ssh_packet_parse(crlf + 2, hello_len - v_c_len - 2, &payload, &payload_len, &why);
	ok("its first packet parses", parsed, why);
	ok("and it is a KEXINIT", parsed && payload[0] == SSH_MSG_KEXINIT, NULL);

	/* --- negotiation against what a real client offers ------------------ */
	const uint8_t *list;
	size_t list_len;
	ok("the kex name-list is readable",
	   ssh_kexinit_namelist(payload, payload_len, 0, &list, &list_len), NULL);
	ok("the client offers curve25519-sha256",
	   ssh_namelist_has(list, list_len, "curve25519-sha256"),
	   "a real OpenSSH client offers it; if this fails the parser is wrong");
	ok("an algorithm we do not implement is not chosen",
	   !ssh_namelist_has(list, list_len, "curve25519-sha256-and-a-half"), NULL);
	ok("a prefix of an offered name does not match",
	   !ssh_namelist_has(list, list_len, "curve25519"),
	   "matching a prefix would accept an algorithm nobody offered");
	ok("the host-key list is a different list",
	   ssh_kexinit_namelist(payload, payload_len, 1, &list, &list_len) &&
	   ssh_namelist_has(list, list_len, "ssh-ed25519"), NULL);
	ok("an index past the ten name-lists is refused",
	   !ssh_kexinit_namelist(payload, payload_len, 10, &list, &list_len), NULL);
	ok("a truncated KEXINIT is refused, not read past",
	   !ssh_kexinit_namelist(payload, 20, 3, &list, &list_len), NULL);

	/* --- framing -------------------------------------------------------- */
	uint8_t out[256];
	const uint8_t msg[5] = {21, 1, 2, 3, 4};
	size_t n = ssh_packet_frame(msg, sizeof msg, 8, out, sizeof out);
	ok("a framed packet is a multiple of the block size", n % 8 == 0 && n > 0, NULL);
	ok("a framed packet is at least 16 bytes", n >= SSH_MIN_PACKET_BYTES, NULL);
	ok("its padding is at least 4 bytes", n > 0 && out[4] >= SSH_MIN_PADDING, NULL);
	ok("it round-trips", ssh_packet_parse(out, n, &payload, &payload_len, &why) &&
	   payload_len == sizeof msg && memcmp(payload, msg, sizeof msg) == 0, why);

	uint8_t big[64];
	memset(big, 7, sizeof big);
	n = ssh_packet_frame(big, sizeof big, 8, out, sizeof out);
	ok("a larger payload still frames to a multiple of 8", n % 8 == 0 && n > 0, NULL);
	ok("and round-trips", ssh_packet_parse(out, n, &payload, &payload_len, &why) &&
	   payload_len == sizeof big, why);
	ok("a payload that does not fit is refused, not truncated",
	   ssh_packet_frame(big, sizeof big, 8, out, 16) == 0, NULL);

	/* --- refusals ------------------------------------------------------- */
	uint8_t bad[32] = {0};
	bad[0] = 0x00; bad[1] = 0x01; bad[2] = 0x00; bad[3] = 0x00;   /* 65536 > 35000 */
	ok("packet_length above 35000 is refused",
	   !ssh_packet_parse(bad, sizeof bad, &payload, &payload_len, &why) &&
	   strstr(why, "35000") != NULL, why);
	memset(bad, 0, sizeof bad);
	bad[3] = 16; bad[4] = 3;                                       /* padding 3 < 4 */
	ok("padding below four bytes is refused",
	   !ssh_packet_parse(bad, sizeof bad, &payload, &payload_len, &why), why);
	memset(bad, 0, sizeof bad);
	bad[3] = 16; bad[4] = 200;                                     /* padding > packet */
	ok("padding longer than the packet is refused",
	   !ssh_packet_parse(bad, sizeof bad, &payload, &payload_len, &why), why);
	memset(bad, 0, sizeof bad);
	bad[3] = 16;
	ok("a packet shorter than it claims is a short read, not a parse",
	   !ssh_packet_parse(bad, 8, &payload, &payload_len, &why), why);

	/* --- mpint ---------------------------------------------------------- */
	uint8_t buf[2048];
	ssh_buf_t b;
	const uint8_t high[2] = {0x80, 0x01};
	ssh_buf_init(&b, buf, sizeof buf);
	ssh_put_mpint(&b, high, 2);
	ok("an mpint with the high bit set gains a leading zero",
	   b.len == 7 && buf[3] == 3 && buf[4] == 0x00 && buf[5] == 0x80,
	   "without it the value is negative and every handshake fails");
	const uint8_t lead[3] = {0x00, 0x00, 0x09};
	ssh_buf_init(&b, buf, sizeof buf);
	ssh_put_mpint(&b, lead, 3);
	ok("leading zeros are stripped (minimum length)",
	   b.len == 5 && buf[3] == 1 && buf[4] == 0x09, NULL);
	const uint8_t zero[4] = {0, 0, 0, 0};
	ssh_buf_init(&b, buf, sizeof buf);
	ssh_put_mpint(&b, zero, 4);
	ok("zero is the empty string", b.len == 4 && buf[3] == 0, NULL);
	const uint8_t plain[2] = {0x7f, 0xff};
	ssh_buf_init(&b, buf, sizeof buf);
	ssh_put_mpint(&b, plain, 2);
	ok("a value with the high bit clear gains nothing",
	   b.len == 6 && buf[3] == 2 && buf[4] == 0x7f, NULL);

	/* --- the exchange hash input, against the independent fixture ------- */
	const uint8_t v_s[] = "SSH-2.0-AUTON_0.1";
	uint8_t k_s[4 + 11 + 4 + 32];
	ssh_buf_t kb;
	ssh_buf_init(&kb, k_s, sizeof k_s);
	uint8_t hostkey[32];
	for (int i = 0; i < 32; i++)
		hostkey[i] = (uint8_t)i;
	ssh_put_string(&kb, (const uint8_t *)"ssh-ed25519", 11);
	ssh_put_string(&kb, hostkey, 32);

	uint8_t q_c[32], q_s[32], k[32];
	for (int i = 0; i < 32; i++) {
		q_c[i] = (uint8_t)(32 + i);
		q_s[i] = (uint8_t)(64 + i);
		k[i] = (uint8_t)(i == 0 ? 0x80 : i - 1);
	}
	/* I_C is the client's KEXINIT payload, re-parsed from the recording (the
	 * framing tests above left `payload` pointing at their own packet). */
	ssh_packet_parse(crlf + 2, hello_len - v_c_len - 2, &payload, &payload_len, &why);
	ssh_buf_init(&b, buf, sizeof buf);
	ssh_exchange_hash_input(&b, hello, v_c_len, v_s, sizeof v_s - 1,
	                        payload, payload_len, i_s, i_s_len,
	                        k_s, kb.len, q_c, q_s, k, 32);
	ok("the exchange hash input did not overflow", !b.over, NULL);
	ok("the exchange hash input matches the RFC fixture byte for byte",
	   b.len == want_len && memcmp(buf, want, want_len) == 0,
	   "built independently in Python from RFC 4253 8 and RFC 8731 3");

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	free(hello);
	free(want);
	free(i_s);
	return fails ? 1 : 0;
}
