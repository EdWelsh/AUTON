/* Reference reader for errata.bin. NOT kernel code; it proves the host test,
 * which then gates a generated kernel/slm/errata_lookup.c. */
#include <stdint.h>
#include "errata_lookup.h"

#define MAGIC   0x52524541u
#define VERSION 1u

static uint32_t rd32(const uint8_t *p) { uint32_t v; __builtin_memcpy(&v, p, 4); return v; }
static uint16_t rd16(const uint8_t *p) { uint16_t v; __builtin_memcpy(&v, p, 2); return v; }

int errata_open(errata_mod_t *m, const void *data, uint64_t len)
{
	const uint8_t *p = data, *end = p + len;
	if (len < 12)
		return ERRATA_ETRUNC;
	if (rd32(p) != MAGIC)
		return ERRATA_EMAGIC;
	if (rd32(p + 4) != VERSION)
		return ERRATA_EVERSION;
	m->doc_count = rd32(p + 8);
	m->docs = p + 12;
	const uint8_t *q = p + 12;
	for (uint32_t i = 0; i < m->doc_count * 2; i++) {
		if (end - q < 2) return ERRATA_ETRUNC;
		uint16_t n = rd16(q);
		if (end - q - 2 < n) return ERRATA_ETRUNC;
		q += 2 + n;
	}
	if (end - q < 4) return ERRATA_ETRUNC;
	m->key_count = rd32(q); q += 4;
	if ((uint64_t)(end - q) < (uint64_t)m->key_count * 16) return ERRATA_ETRUNC;
	m->keys = q; q += (uint64_t)m->key_count * 16;
	if (end - q < 4) return ERRATA_ETRUNC;
	m->rec_count = rd32(q); q += 4;
	if ((uint64_t)(end - q) < (uint64_t)m->rec_count * 12) return ERRATA_ETRUNC;
	m->recs = q; q += (uint64_t)m->rec_count * 12;
	if (end - q < 4) return ERRATA_ETRUNC;
	m->pool_len = rd32(q); q += 4;
	if ((uint64_t)(end - q) < m->pool_len) return ERRATA_ETRUNC;
	m->pool = (const char *)q;
	/* Every key's records, and every record's text, must lie inside. */
	for (uint32_t i = 0; i < m->key_count; i++) {
		const uint8_t *k = m->keys + 16 * i;
		if ((uint64_t)rd32(k + 8) + rd32(k + 12) > m->rec_count) return ERRATA_ETRUNC;
	}
	for (uint32_t i = 0; i < m->rec_count; i++) {
		uint32_t off = rd32(m->recs + 12 * i);
		uint32_t j = off;
		while (j < m->pool_len && m->pool[j]) j++;
		if (j >= m->pool_len) return ERRATA_ETRUNC;  /* no NUL before the end */
	}
	return ERRATA_OK;
}

static uint64_t key_of(uint8_t vendor, uint16_t family, uint16_t model, uint8_t stepping)
{
	return (uint64_t)vendor << 40 | (uint64_t)family << 24 | (uint64_t)model << 8 | stepping;
}

int errata_find(const errata_mod_t *m, uint8_t vendor, uint16_t family, uint16_t model,
                uint8_t stepping, uint32_t *first, uint32_t *count)
{
	uint64_t want = key_of(vendor, family, model, stepping);
	uint32_t lo = 0, hi = m->key_count;
	while (lo < hi) {
		uint32_t mid = lo + (hi - lo) / 2;
		const uint8_t *k = m->keys + 16 * mid;
		uint64_t got = key_of(k[0], rd16(k + 2), rd16(k + 4), k[1]);
		if (got == want) {
			*first = rd32(k + 8);
			*count = rd32(k + 12);
			return ERRATA_OK;
		}
		if (got < want) lo = mid + 1; else hi = mid;
	}
	return ERRATA_NOT_EXAMINED;
}

int errata_get(const errata_mod_t *m, uint32_t index, errata_answer_t *out)
{
	if (index >= m->rec_count)
		return ERRATA_ETRUNC;
	const uint8_t *r = m->recs + 12 * index;
	out->text = m->pool + rd32(r);
	out->verdict = r[4];
	out->status = r[5];
	out->doc = r[6];
	out->page = rd16(r + 8);
	return ERRATA_OK;
}
