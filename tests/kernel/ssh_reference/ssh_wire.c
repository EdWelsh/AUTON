/* Reference for the SSH wire encodings (see include/ssh_wire.h).
 * NOT kernel code and NOT shipped: it exists so the host suite is proved
 * before it judges a generated implementation. */
#include "ssh_wire.h"

#include <string.h>

void ssh_buf_init(ssh_buf_t *b, uint8_t *storage, size_t cap)
{
	b->data = storage;
	b->cap = cap;
	b->len = 0;
	b->over = 0;
}

static void put(ssh_buf_t *b, const uint8_t *src, size_t n)
{
	if (b->len + n > b->cap) {
		b->over = 1;
		return;
	}
	memcpy(b->data + b->len, src, n);
	b->len += n;
}

void ssh_put_u32(ssh_buf_t *b, uint32_t v)
{
	uint8_t be[4] = {(uint8_t)(v >> 24), (uint8_t)(v >> 16), (uint8_t)(v >> 8), (uint8_t)v};
	put(b, be, 4);
}

void ssh_put_string(ssh_buf_t *b, const uint8_t *s, size_t n)
{
	ssh_put_u32(b, (uint32_t)n);
	put(b, s, n);
}

void ssh_put_mpint(ssh_buf_t *b, const uint8_t *be, size_t n)
{
	size_t i = 0;
	while (i < n && be[i] == 0)     /* minimum length: strip leading zeros */
		i++;
	if (i == n) {                   /* zero is the empty string */
		ssh_put_u32(b, 0);
		return;
	}
	if (be[i] & 0x80) {             /* keep it positive */
		uint8_t zero = 0;
		ssh_put_u32(b, (uint32_t)(n - i + 1));
		put(b, &zero, 1);
		put(b, be + i, n - i);
		return;
	}
	ssh_put_string(b, be + i, n - i);
}

size_t ssh_packet_frame(const uint8_t *payload, size_t payload_len, uint8_t block,
                        uint8_t *out, size_t out_cap)
{
	size_t bs = block < 8 ? 8 : block;
	/* 4 (length) + 1 (padding length) + payload + padding is a multiple of bs,
	 * with at least SSH_MIN_PADDING bytes of padding. */
	size_t unpadded = 4 + 1 + payload_len;
	size_t pad = bs - (unpadded % bs);
	if (pad < SSH_MIN_PADDING)
		pad += bs;
	size_t total = unpadded + pad;
	if (total < SSH_MIN_PACKET_BYTES) {
		pad += bs * ((SSH_MIN_PACKET_BYTES - total + bs - 1) / bs);
		total = unpadded + pad;
	}
	if (total > out_cap || pad > 255)
		return 0;

	uint32_t packet_len = (uint32_t)(1 + payload_len + pad);
	out[0] = (uint8_t)(packet_len >> 24);
	out[1] = (uint8_t)(packet_len >> 16);
	out[2] = (uint8_t)(packet_len >> 8);
	out[3] = (uint8_t)packet_len;
	out[4] = (uint8_t)pad;
	memcpy(out + 5, payload, payload_len);
	memset(out + 5 + payload_len, 0, pad);   /* a real server uses random bytes */
	return total;
}

int ssh_packet_parse(const uint8_t *in, size_t in_len, const uint8_t **payload,
                     size_t *payload_len, const char **why)
{
	*why = "";
	if (in_len < 5) {
		*why = "short read: no length and padding byte yet";
		return 0;
	}
	uint32_t packet_len = ((uint32_t)in[0] << 24) | ((uint32_t)in[1] << 16) |
	                      ((uint32_t)in[2] << 8) | in[3];
	/* Checked before anything is sized from it: this field is attacker
	 * controlled on the first bytes of a connection. */
	if (packet_len > SSH_MAX_PACKET) {
		*why = "packet_length above 35000";
		return 0;
	}
	if (packet_len < 1 + SSH_MIN_PADDING) {
		*why = "packet_length too small for its own padding";
		return 0;
	}
	if (in_len < 4 + (size_t)packet_len) {
		*why = "short read: less than the packet claims";
		return 0;
	}
	uint8_t pad = in[4];
	if (pad < SSH_MIN_PADDING) {
		*why = "padding below 4 bytes";
		return 0;
	}
	if ((size_t)pad + 1 > packet_len) {
		*why = "padding longer than the packet";
		return 0;
	}
	*payload = in + 5;
	*payload_len = packet_len - pad - 1;
	return 1;
}

static size_t name_len(const uint8_t *p, size_t len, size_t at)
{
	size_t n = at;
	while (n < len && p[n] != ',')
		n++;
	return n - at;
}

int ssh_namelist_has(const uint8_t *list, size_t list_len, const char *ours)
{
	size_t want = strlen(ours);
	for (size_t at = 0; at <= list_len;) {
		size_t n = name_len(list, list_len, at);
		if (n == want && memcmp(list + at, ours, want) == 0)
			return 1;
		at += n + 1;
	}
	return 0;
}

int ssh_kexinit_namelist(const uint8_t *payload, size_t len, int index,
                         const uint8_t **out, size_t *out_len)
{
	if (len < 17 || payload[0] != SSH_MSG_KEXINIT || index < 0 || index > 9)
		return 0;
	size_t at = 17;                 /* message number + 16-byte cookie */
	for (int i = 0; i <= index; i++) {
		if (at + 4 > len)
			return 0;
		uint32_t n = ((uint32_t)payload[at] << 24) | ((uint32_t)payload[at + 1] << 16) |
		             ((uint32_t)payload[at + 2] << 8) | payload[at + 3];
		if (at + 4 + (size_t)n > len)
			return 0;
		if (i == index) {
			*out = payload + at + 4;
			*out_len = n;
			return 1;
		}
		at += 4 + n;
	}
	return 0;
}

void ssh_exchange_hash_input(ssh_buf_t *b,
                             const uint8_t *v_c, size_t v_c_len,
                             const uint8_t *v_s, size_t v_s_len,
                             const uint8_t *i_c, size_t i_c_len,
                             const uint8_t *i_s, size_t i_s_len,
                             const uint8_t *k_s, size_t k_s_len,
                             const uint8_t *q_c, const uint8_t *q_s,
                             const uint8_t *k, size_t k_len)
{
	ssh_put_string(b, v_c, v_c_len);
	ssh_put_string(b, v_s, v_s_len);
	ssh_put_string(b, i_c, i_c_len);
	ssh_put_string(b, i_s, i_s_len);
	ssh_put_string(b, k_s, k_s_len);
	ssh_put_string(b, q_c, 32);
	ssh_put_string(b, q_s, 32);
	ssh_put_mpint(b, k, k_len);     /* K is an integer, not a 32-byte string */
}
