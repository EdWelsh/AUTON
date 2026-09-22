/* Reference for the KV store (see include/kvstore.h and services/kvstore.md).
 * NOT kernel code and NOT shipped: it exists so the host suite is proved before
 * it judges a generated implementation. */
#include "kvstore.h"

#include <string.h>
#include <stdio.h>

typedef struct entry {
	uint8_t  key[KV_MAX_KEY];
	uint8_t  key_len;
	uint8_t  value[KV_MAX_VALUE];
	uint16_t value_len;
	int      live;
} entry_t;

static entry_t store[KV_MAX_KEYS];
static int store_count;

void kv_reset(kv_log_t *log)
{
	memset(store, 0, sizeof store);
	store_count = 0;
	if (log) {
		log->len = 0;
		log->pending = 0;
		log->flushes = 0;
	}
}

int kv_count(void)
{
	return store_count;
}

uint32_t kv_crc32(const uint8_t *data, uint32_t len)
{
	uint32_t crc = 0xFFFFFFFFu;
	for (uint32_t i = 0; i < len; i++) {
		crc ^= data[i];
		for (int b = 0; b < 8; b++)
			crc = (crc >> 1) ^ (0xEDB88320u & (uint32_t)(-(int32_t)(crc & 1)));
	}
	return ~crc;
}

static entry_t *find(const uint8_t *key, uint8_t key_len)
{
	for (int i = 0; i < KV_MAX_KEYS; i++)
		if (store[i].live && store[i].key_len == key_len &&
		    memcmp(store[i].key, key, key_len) == 0)
			return &store[i];
	return NULL;
}

static int put(const uint8_t *key, uint8_t key_len, const uint8_t *value, uint16_t value_len)
{
	entry_t *e = find(key, key_len);
	if (!e) {
		if (store_count >= KV_MAX_KEYS)
			return -1;
		for (int i = 0; i < KV_MAX_KEYS; i++)
			if (!store[i].live) {
				e = &store[i];
				break;
			}
		e->live = 1;
		e->key_len = key_len;
		memcpy(e->key, key, key_len);
		store_count++;
	}
	e->value_len = value_len;
	memcpy(e->value, value, value_len);
	return 0;
}

static int drop(const uint8_t *key, uint8_t key_len)
{
	entry_t *e = find(key, key_len);
	if (!e)
		return 0;
	e->live = 0;
	store_count--;
	return 1;
}

/* --- the log ----------------------------------------------------------- */

#define REC_HEADER 8u        /* len u32, op u8, key_len u8, value_len u16 */

static int append(kv_log_t *log, uint8_t op, const uint8_t *key, uint8_t key_len,
                  const uint8_t *value, uint16_t value_len)
{
	uint32_t body = 4u + (uint32_t)key_len + value_len;   /* op..value */
	uint32_t need = 4u + body + 4u;                       /* len + body + crc */
	if (log->len + need > KV_MAX_LOG || log->len + need > log->cap)
		return -1;

	uint8_t *p = log->bytes + log->len;
	p[0] = (uint8_t)body; p[1] = (uint8_t)(body >> 8);
	p[2] = (uint8_t)(body >> 16); p[3] = (uint8_t)(body >> 24);
	p[4] = op;
	p[5] = key_len;
	p[6] = (uint8_t)value_len; p[7] = (uint8_t)(value_len >> 8);
	memcpy(p + REC_HEADER, key, key_len);
	memcpy(p + REC_HEADER + key_len, value, value_len);
	uint32_t crc = kv_crc32(p, REC_HEADER + key_len + value_len);
	uint8_t *c = p + REC_HEADER + key_len + value_len;
	c[0] = (uint8_t)crc; c[1] = (uint8_t)(crc >> 8);
	c[2] = (uint8_t)(crc >> 16); c[3] = (uint8_t)(crc >> 24);
	log->len += need;
	log->pending += need;   /* written, not yet durable */
	return 0;
}

void kv_log_flush(kv_log_t *log)
{
	log->pending = 0;
	log->flushes++;
}

static uint32_t rd32(const uint8_t *p)
{
	return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) |
	       ((uint32_t)p[3] << 24);
}

int kv_replay(kv_log_t *log, uint32_t *bad_offset)
{
	int applied = 0;
	uint32_t at = 0;
	*bad_offset = 0;
	while (at + 4 <= log->len) {
		uint32_t body = rd32(log->bytes + at);
		uint32_t need = 4 + body + 4;
		if (body < 4 || at + need > log->len)
			break;                       /* short: a torn final record */
		const uint8_t *p = log->bytes + at;
		uint8_t op = p[4], key_len = p[5];
		uint16_t value_len = (uint16_t)(p[6] | (p[7] << 8));
		if (4u + key_len + value_len != body)
			break;
		uint32_t want = kv_crc32(p, REC_HEADER + key_len + value_len);
		if (want != rd32(p + REC_HEADER + key_len + value_len))
			break;                       /* torn write: stop here, keep the rest */
		if (op == KV_OP_SET)
			put(p + REC_HEADER, key_len, p + REC_HEADER + key_len, value_len);
		else if (op == KV_OP_DEL)
			drop(p + REC_HEADER, key_len);
		else
			break;
		applied++;
		at += need;
	}
	if (at != log->len) {
		*bad_offset = at;
		log->len = at;                       /* truncate at the first bad record */
	}
	return applied;
}

/* --- RESP2 -------------------------------------------------------------- */

#define MAX_ARGS 4

typedef struct req {
	const uint8_t *arg[MAX_ARGS];
	uint32_t       len[MAX_ARGS];
	int            argc;
} req_t;

static int reply(uint8_t *out, uint32_t cap, const char *s)
{
	uint32_t n = (uint32_t)strlen(s);
	if (n > cap)
		return -1;
	memcpy(out, s, n);
	return (int)n;
}

/* Find CRLF from `at`; returns its offset or -1 when the frame is incomplete. */
static int crlf(const uint8_t *in, uint32_t len, uint32_t at)
{
	for (uint32_t i = at; i + 1 < len; i++)
		if (in[i] == '\r' && in[i + 1] == '\n')
			return (int)i;
	return -1;
}

/* 0 incomplete, -1 protocol error, 1 parsed. */
static int parse(const uint8_t *in, uint32_t len, req_t *r, uint32_t *consumed,
                 const char **err)
{
	*err = NULL;
	r->argc = 0;
	if (len == 0)
		return 0;

	if (in[0] != '*') {                         /* inline command */
		int end = crlf(in, len, 0);
		if (end < 0)
			return 0;
		uint32_t at = 0;
		while (at < (uint32_t)end && r->argc < MAX_ARGS) {
			while (at < (uint32_t)end && in[at] == ' ')
				at++;
			uint32_t start = at;
			while (at < (uint32_t)end && in[at] != ' ')
				at++;
			if (at > start) {
				r->arg[r->argc] = in + start;
				r->len[r->argc] = at - start;
				r->argc++;
			}
		}
		*consumed = (uint32_t)end + 2;
		return r->argc ? 1 : -1;
	}

	int end = crlf(in, len, 0);
	if (end < 0)
		return 0;
	int count = 0;
	for (int i = 1; i < end; i++) {
		if (in[i] < '0' || in[i] > '9')
			return -1;
		count = count * 10 + (in[i] - '0');
	}
	if (count <= 0 || count > MAX_ARGS)
		return -1;
	uint32_t at = (uint32_t)end + 2;
	for (int a = 0; a < count; a++) {
		if (at >= len)
			return 0;
		if (in[at] != '$')
			return -1;
		int hdr = crlf(in, len, at);
		if (hdr < 0)
			return 0;
		long n = 0;
		for (uint32_t i = at + 1; i < (uint32_t)hdr; i++) {
			if (in[i] < '0' || in[i] > '9')
				return -1;
			n = n * 10 + (in[i] - '0');
		}
		/* Refused before the bytes are buffered: a length trusted first is a
		 * remote memory-exhaustion primitive. */
		if (n > KV_MAX_VALUE) {
			*err = "-ERR value exceeds 4096 bytes\r\n";
			return -1;
		}
		uint32_t body = (uint32_t)hdr + 2;
		if (body + (uint32_t)n + 2 > len)
			return 0;
		r->arg[a] = in + body;
		r->len[a] = (uint32_t)n;
		at = body + (uint32_t)n + 2;
	}
	r->argc = count;
	*consumed = at;
	return 1;
}

static int eq(const req_t *r, int i, const char *word)
{
	uint32_t n = (uint32_t)strlen(word);
	if (r->len[i] != n)
		return 0;
	for (uint32_t k = 0; k < n; k++) {
		uint8_t c = r->arg[i][k];
		if (c >= 'a' && c <= 'z')
			c = (uint8_t)(c - 'a' + 'A');
		if (c != (uint8_t)word[k])
			return 0;
	}
	return 1;
}

int kv_handle(const uint8_t *in, uint32_t in_len, uint8_t *out, uint32_t out_cap,
              uint32_t *consumed, kv_log_t *log)
{
	req_t r;
	const char *err = NULL;
	*consumed = 0;
	int p = parse(in, in_len, &r, consumed, &err);
	if (p == 0)
		return 0;
	if (p < 0) {
		if (err)
			return reply(out, out_cap, err);
		return -1;
	}

	if (eq(&r, 0, "PING")) {
		if (r.argc == 1)
			return reply(out, out_cap, "+PONG\r\n");
		char buf[64];
		snprintf(buf, sizeof buf, "$%u\r\n", r.len[1]);
		int n = reply(out, out_cap, buf);
		if (n < 0 || (uint32_t)n + r.len[1] + 2 > out_cap)
			return -1;
		memcpy(out + n, r.arg[1], r.len[1]);
		memcpy(out + n + r.len[1], "\r\n", 2);
		return n + (int)r.len[1] + 2;
	}

	if (eq(&r, 0, "SET")) {
		if (r.argc != 3)
			return reply(out, out_cap,
			             "-ERR wrong number of arguments for 'set' command\r\n");
		if (r.len[1] > KV_MAX_KEY)
			return reply(out, out_cap, "-ERR key exceeds 256 bytes\r\n");
		if (r.len[2] > KV_MAX_VALUE)
			return reply(out, out_cap, "-ERR value exceeds 4096 bytes\r\n");
		if (!find(r.arg[1], (uint8_t)r.len[1]) && kv_count() >= KV_MAX_KEYS)
			return reply(out, out_cap, "-ERR key limit 1024 reached\r\n");
		if (append(log, KV_OP_SET, r.arg[1], (uint8_t)r.len[1], r.arg[2],
		           (uint16_t)r.len[2]) < 0)
			return reply(out, out_cap,
			             "-ERR log full (8 MiB); compaction is not implemented\r\n");
		put(r.arg[1], (uint8_t)r.len[1], r.arg[2], (uint16_t)r.len[2]);
		/* +OK only after the record is durable. A reply sent before the flush
		 * is a lie the client will believe and act on. */
		kv_log_flush(log);
		return reply(out, out_cap, "+OK\r\n");
	}

	if (eq(&r, 0, "GET")) {
		if (r.argc != 2)
			return reply(out, out_cap,
			             "-ERR wrong number of arguments for 'get' command\r\n");
		entry_t *e = find(r.arg[1], (uint8_t)r.len[1]);
		if (!e)
			return reply(out, out_cap, "$-1\r\n");
		char buf[64];
		snprintf(buf, sizeof buf, "$%u\r\n", e->value_len);
		int n = reply(out, out_cap, buf);
		if (n < 0 || (uint32_t)n + e->value_len + 2 > out_cap)
			return -1;
		memcpy(out + n, e->value, e->value_len);
		memcpy(out + n + e->value_len, "\r\n", 2);
		return n + e->value_len + 2;
	}

	if (eq(&r, 0, "DEL")) {
		if (r.argc != 2)
			return reply(out, out_cap,
			             "-ERR wrong number of arguments for 'del' command\r\n");
		/* An absent key's deletion changes nothing, and logs nothing. */
		if (!find(r.arg[1], (uint8_t)r.len[1]))
			return reply(out, out_cap, ":0\r\n");
		if (append(log, KV_OP_DEL, r.arg[1], (uint8_t)r.len[1], NULL, 0) < 0)
			return reply(out, out_cap,
			             "-ERR log full (8 MiB); compaction is not implemented\r\n");
		drop(r.arg[1], (uint8_t)r.len[1]);
		kv_log_flush(log);
		return reply(out, out_cap, ":1\r\n");
	}

	if (eq(&r, 0, "EXISTS")) {
		if (r.argc != 2)
			return reply(out, out_cap,
			             "-ERR wrong number of arguments for 'exists' command\r\n");
		return reply(out, out_cap, find(r.arg[1], (uint8_t)r.len[1]) ? ":1\r\n" : ":0\r\n");
	}

	if (eq(&r, 0, "DBSIZE")) {
		char buf[32];
		snprintf(buf, sizeof buf, ":%d\r\n", kv_count());
		return reply(out, out_cap, buf);
	}

	/* No reply, and NOT 0: 0 means "incomplete frame", and a caller that
	 * confused the two would wait forever for bytes the client will not send. */
	if (eq(&r, 0, "SHUTDOWN"))
		return KV_SHUTDOWN;

	{
		char buf[128];
		char name[32] = {0};
		uint32_t n = r.len[0] < sizeof name - 1 ? r.len[0] : sizeof name - 1;
		memcpy(name, r.arg[0], n);
		snprintf(buf, sizeof buf, "-ERR unknown command '%s'\r\n", name);
		return reply(out, out_cap, buf);
	}
}
