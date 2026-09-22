/* The in-kernel reader for errata.bin (SLM/tools/errata_format.py), as
 * specified in agent/kernel_spec/subsystems/slm.md "Errata Module". The module
 * is untrusted input, like the model: errata_open validates every length
 * before anything follows it, and a lookup never reads outside the module. */
#ifndef AUTON_ERRATA_LOOKUP_H
#define AUTON_ERRATA_LOOKUP_H
#include <stdint.h>

#define ERRATA_OK          0
#define ERRATA_EMAGIC     -1
#define ERRATA_EVERSION   -2
#define ERRATA_ETRUNC     -3
#define ERRATA_NOT_EXAMINED -4   /* no key for this silicon: not examined, not safe */

#define ERRATA_VENDOR_INTEL 1
#define ERRATA_VENDOR_AMD   2

typedef struct {
	const uint8_t *keys;      uint32_t key_count;
	const uint8_t *recs;      uint32_t rec_count;
	const char    *pool;      uint32_t pool_len;
	const uint8_t *docs;      uint32_t doc_count;   /* the raw document list */
} errata_mod_t;

typedef struct {
	const char *text;         /* "<erratum id>: <title>", NUL-terminated in the pool */
	uint8_t     verdict;      /* 0 does not apply, 1 applies, 2 unknown */
	uint8_t     status;       /* errata_format.STATUSES */
	uint8_t     doc;
	uint16_t    page;
} errata_answer_t;

int errata_open(errata_mod_t *m, const void *data, uint64_t len);
/* The key for this identity: first record index and count, or NOT_EXAMINED. */
int errata_find(const errata_mod_t *m, uint8_t vendor, uint16_t family, uint16_t model,
                uint8_t stepping, uint32_t *first, uint32_t *count);
int errata_get(const errata_mod_t *m, uint32_t index, errata_answer_t *out);
#endif
