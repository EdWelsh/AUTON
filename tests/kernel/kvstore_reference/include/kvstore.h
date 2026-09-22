/* The KV store interface specified in agent/kernel_spec/services/kvstore.md.
 * Host-provable: the RESP2 parser, the command semantics and the log's replay.
 * NOT kernel code and NOT shipped. */
#ifndef AUTON_KVSTORE_H
#define AUTON_KVSTORE_H

#include <stdint.h>
#include <stddef.h>

#define KV_MAX_KEY      256
#define KV_MAX_VALUE    4096
#define KV_MAX_KEYS     1024
#define KV_MAX_LOG      (8u * 1024u * 1024u)

#define KV_OP_SET       1
#define KV_OP_DEL       2

/* The log lives behind these three calls so the host suite can put it in
 * memory and a kernel can put it on FAT32. */
typedef struct kv_log {
	uint8_t *bytes;
	uint32_t len;
	uint32_t cap;
	/* Written and flushed are separate, as they are on a real volume: appending
	 * bytes leaves them pending, and only kv_log_flush() puts them where a
	 * power loss cannot take them. A SET replies +OK only when pending is 0. */
	uint32_t pending;
	uint32_t flushes;
} kv_log_t;

/* Push appended bytes through to the volume. */
void kv_log_flush(kv_log_t *log);

void kv_reset(kv_log_t *log);

/* CRC-32 (IEEE 802.3, 0xEDB88320), over a record's bytes up to the crc field. */
uint32_t kv_crc32(const uint8_t *data, uint32_t len);

/* Replay the log into the store. Returns records applied, and truncates the
 * log at the first bad record, setting *bad_offset to where it stopped. */
int kv_replay(kv_log_t *log, uint32_t *bad_offset);

/* SHUTDOWN: flush, print "[KV] clean shutdown", halt. Distinct from 0, which
 * means "incomplete frame". */
#define KV_SHUTDOWN  (-2)

/* One request in, one reply out. Returns the reply length, 0 when the request
 * is incomplete, KV_SHUTDOWN, or -1 on a protocol error. `consumed` advances
 * the caller. */
int kv_handle(const uint8_t *in, uint32_t in_len, uint8_t *out, uint32_t out_cap,
              uint32_t *consumed, kv_log_t *log);

/* Live keys, for DBSIZE and for tests. */
int kv_count(void);

#endif
