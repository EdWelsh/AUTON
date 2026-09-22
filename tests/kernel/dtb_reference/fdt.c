/* Reference FDT parser (see include/fdt.h and arch/aarch64.md).
 * NOT kernel code and NOT shipped: it exists so the host suite is proved
 * before it judges a generated aarch64 arch layer.
 *
 * Every offset read out of the blob is checked against the blob's own
 * totalsize before it is followed. The DTB is firmware-supplied input, and a
 * parser that trusts its length fields is the same defect as a network stack
 * that trusts a header. */
#include "fdt.h"

#include <stdio.h>
#include <string.h>

#define FDT_BEGIN_NODE 1u
#define FDT_END_NODE   2u
#define FDT_PROP       3u
#define FDT_NOP        4u
#define FDT_END        9u

typedef struct {
	uint32_t magic, totalsize, off_dt_struct, off_dt_strings, off_mem_rsvmap;
	uint32_t version, last_comp_version, boot_cpuid_phys;
	uint32_t size_dt_strings, size_dt_struct;
} header_t;

static uint32_t be32(const void *p)
{
	const uint8_t *b = p;
	return ((uint32_t)b[0] << 24) | ((uint32_t)b[1] << 16) | ((uint32_t)b[2] << 8) | b[3];
}

static uint64_t be64(const void *p)
{
	return ((uint64_t)be32(p) << 32) | be32((const uint8_t *)p + 4);
}

static int header_of(const void *dtb, header_t *h)
{
	const uint8_t *b = dtb;
	if (!dtb)
		return -1;
	h->magic = be32(b);
	h->totalsize = be32(b + 4);
	h->off_dt_struct = be32(b + 8);
	h->off_dt_strings = be32(b + 12);
	h->off_mem_rsvmap = be32(b + 16);
	h->version = be32(b + 20);
	h->last_comp_version = be32(b + 24);
	h->boot_cpuid_phys = be32(b + 28);
	h->size_dt_strings = be32(b + 32);
	h->size_dt_struct = be32(b + 36);
	if (h->magic != FDT_MAGIC)
		return -1;
	if (h->version < FDT_MIN_VERSION)
		return -1;
	if (h->totalsize < 40)
		return -1;
	/* Both blocks must lie inside the blob the header itself describes. */
	if ((uint64_t)h->off_dt_struct + h->size_dt_struct > h->totalsize)
		return -1;
	if ((uint64_t)h->off_dt_strings + h->size_dt_strings > h->totalsize)
		return -1;
	return 0;
}

int fdt_validate(const void *dtb)
{
	header_t h;
	return header_of(dtb, &h);
}

/* Walk properties, calling `visit` for each. `visit` returns non-zero to stop.
 * `node` is the current node's name. */
typedef int (*visitor)(const char *node, const char *prop, const uint8_t *value,
                       uint32_t len, void *ctx);

static int walk(const void *dtb, visitor visit, void *ctx)
{
	header_t h;
	if (header_of(dtb, &h) < 0)
		return -1;
	const uint8_t *base = dtb;
	const uint8_t *p = base + h.off_dt_struct;
	const uint8_t *end = p + h.size_dt_struct;
	const char *strings = (const char *)(base + h.off_dt_strings);
	char node[128] = "";

	while (p + 4 <= end) {
		uint32_t token = be32(p);
		p += 4;
		if (token == FDT_BEGIN_NODE) {
			size_t n = strnlen((const char *)p, (size_t)(end - p));
			if (n == (size_t)(end - p))
				return -1;                       /* unterminated name */
			if (n < sizeof node)
				memcpy(node, p, n + 1);
			p += (n + 4) & ~3u;
		} else if (token == FDT_END_NODE) {
			node[0] = 0;
		} else if (token == FDT_PROP) {
			if (p + 8 > end)
				return -1;
			uint32_t len = be32(p), nameoff = be32(p + 4);
			p += 8;
			if (p + len > end || nameoff >= h.size_dt_strings)
				return -1;                       /* a length trusted past the blob */
			if (visit(node, strings + nameoff, p, len, ctx))
				return 0;
			p += (len + 3) & ~3u;
		} else if (token == FDT_NOP) {
			continue;
		} else if (token == FDT_END) {
			break;
		} else {
			return -1;                           /* unknown token */
		}
	}
	return 0;
}

struct memctx { uint64_t base, size; int found; };

static int memory_visit(const char *node, const char *prop, const uint8_t *value,
                        uint32_t len, void *ctx)
{
	struct memctx *m = ctx;
	if (m->found || strncmp(node, "memory", 6) != 0 || strcmp(prop, "reg") != 0)
		return 0;
	if (len < 16)
		return 0;
	m->base = be64(value);
	m->size = be64(value + 8);
	m->found = 1;
	return 1;
}

int fdt_memory(const void *dtb, uint64_t *base, uint64_t *size)
{
	struct memctx m = {0, 0, 0};
	if (walk(dtb, memory_visit, &m) < 0 || !m.found)
		return -1;
	if (base)
		*base = m.base;
	if (size)
		*size = m.size;
	return 0;
}

struct argctx { char *out; size_t cap; int found; };

static int bootargs_visit(const char *node, const char *prop, const uint8_t *value,
                          uint32_t len, void *ctx)
{
	struct argctx *a = ctx;
	if (strcmp(node, "chosen") != 0 || strcmp(prop, "bootargs") != 0)
		return 0;
	size_t n = len < a->cap ? len : a->cap - 1;
	memcpy(a->out, value, n);
	a->out[n] = 0;                    /* NUL-terminated even if the blob is not */
	a->found = 1;
	return 1;
}

int fdt_bootargs(const void *dtb, char *out, size_t cap)
{
	struct argctx a = {out, cap, 0};
	if (!out || cap == 0)
		return -1;
	out[0] = 0;
	if (walk(dtb, bootargs_visit, &a) < 0 || !a.found)
		return -1;
	return 0;
}

struct compatctx {
	const char *want;
	char cur[128];          /* the node these cached fields belong to */
	uint64_t base;
	int has_reg, matched, found;
};

/* A node's properties arrive in whatever order the tree stores them, and real
 * QEMU trees put `reg` BEFORE `compatible`. So both are remembered per node
 * and the decision is taken when the second one arrives; assuming `compatible`
 * comes first finds nothing on a real machine. */
static int compat_visit(const char *node, const char *prop, const uint8_t *value,
                        uint32_t len, void *ctx)
{
	struct compatctx *c = ctx;

	if (strcmp(node, c->cur) != 0) {           /* a new node: forget the last */
		snprintf(c->cur, sizeof c->cur, "%s", node);
		c->has_reg = 0;
		c->matched = 0;
	}

	if (strcmp(prop, "reg") == 0 && len >= 8) {
		c->base = len >= 16 ? be64(value) : be32(value);
		c->has_reg = 1;
	} else if (strcmp(prop, "compatible") == 0) {
		/* `compatible` is a LIST of NUL-separated strings; matching the whole
		 * property as one string finds only single-entry nodes. */
		for (uint32_t at = 0; at < len; ) {
			const char *s = (const char *)value + at;
			size_t n = strnlen(s, len - at);
			if (strcmp(s, c->want) == 0) {
				c->matched = 1;
				break;
			}
			at += (uint32_t)n + 1;
		}
	}

	if (c->matched && c->has_reg) {
		c->found = 1;
		return 1;
	}
	return 0;
}

int fdt_find_compatible(const void *dtb, const char *want, uint64_t *base)
{
	struct compatctx c = {want, "", 0, 0, 0, 0};
	if (walk(dtb, compat_visit, &c) < 0 || !c.found)
		return -1;
	if (base)
		*base = c.base;
	return 0;
}
