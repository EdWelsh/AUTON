/* The SSH wire encodings a generated kernel/services/ssh/ must provide, as
 * specified in agent/kernel_spec/services/ssh.md. Host-provable: no crypto,
 * no sockets — the framing and the encodings, which is where SSH
 * implementations actually go wrong.
 *
 * NOT kernel code and NOT shipped. */
#ifndef AUTON_SSH_WIRE_H
#define AUTON_SSH_WIRE_H

#include <stdint.h>
#include <stddef.h>

#define SSH_MSG_KEXINIT       20
#define SSH_MAX_PACKET        35000   /* RFC 4253 6.1 */
#define SSH_MIN_PADDING       4
#define SSH_MIN_PACKET_BYTES  16

/* A bounded output buffer. `over` latches once anything did not fit, so a
 * caller checks it once at the end instead of after every put. */
typedef struct ssh_buf {
	uint8_t *data;
	size_t   cap;
	size_t   len;
	int      over;
} ssh_buf_t;

void ssh_buf_init(ssh_buf_t *b, uint8_t *storage, size_t cap);
void ssh_put_u32(ssh_buf_t *b, uint32_t v);
void ssh_put_string(ssh_buf_t *b, const uint8_t *s, size_t n);

/* An SSH mpint: two's-complement, big-endian, minimum length, with a leading
 * 0x00 when the high bit is set. Zero is the empty string. */
void ssh_put_mpint(ssh_buf_t *b, const uint8_t *be, size_t n);

/* Frame `payload` into a binary packet (RFC 4253 6): returns the whole packet
 * length, or 0 when it does not fit. `block` is 8 before a cipher is in place. */
size_t ssh_packet_frame(const uint8_t *payload, size_t payload_len, uint8_t block,
                        uint8_t *out, size_t out_cap);

/* Parse one packet. Returns 1 and sets *payload/*payload_len, or 0 and sets
 * *why to a stable reason string. Never trusts the length field first. */
int ssh_packet_parse(const uint8_t *in, size_t in_len, const uint8_t **payload,
                     size_t *payload_len, const char **why);

/* Pick the one algorithm this server implements from a client's comma-separated
 * name-list. Returns 1 when `ours` is present, 0 otherwise (no fallback). */
int ssh_namelist_has(const uint8_t *list, size_t list_len, const char *ours);

/* The KEXINIT payload's first name-list (kex algorithms), by index:
 * 0 kex, 1 host key, 2 cipher c2s, 3 cipher s2c, ... (RFC 4253 7.1).
 * Returns 1 and sets *out/*out_len, or 0 when the payload is malformed. */
int ssh_kexinit_namelist(const uint8_t *payload, size_t len, int index,
                         const uint8_t **out, size_t *out_len);

/* Assemble the exchange hash input (RFC 4253 8, RFC 8731 3). The hash itself is
 * SHA-256 over this buffer, and comes from the vetted third-party source. */
void ssh_exchange_hash_input(ssh_buf_t *b,
                             const uint8_t *v_c, size_t v_c_len,
                             const uint8_t *v_s, size_t v_s_len,
                             const uint8_t *i_c, size_t i_c_len,
                             const uint8_t *i_s, size_t i_s_len,
                             const uint8_t *k_s, size_t k_s_len,
                             const uint8_t *q_c, const uint8_t *q_s,
                             const uint8_t *k, size_t k_len);

#endif
