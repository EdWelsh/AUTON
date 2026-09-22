/* Host tests for the errata module reader (slm.md "Errata Module").
 *   errata_lookup_test <synthetic.bin> [real.bin]
 * The synthetic module is built by run_errata_lookup_test.sh through
 * SLM/tools/errata_format.pack; the real one from the ingested documents when
 * they are cached. */
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "errata_lookup.h"

static int fails;
static void ok(const char *name, int cond, const char *detail)
{
	if (cond) printf("PASS  %-58s\n", name);
	else { printf("FAIL  %-58s  %s\n", name, detail ? detail : ""); fails++; }
}

static uint8_t *slurp(const char *path, long *len)
{
	FILE *f = fopen(path, "rb");
	if (!f) return 0;
	fseek(f, 0, SEEK_END); *len = ftell(f); fseek(f, 0, SEEK_SET);
	uint8_t *b = malloc((size_t)*len);
	if (fread(b, 1, (size_t)*len, f) != (size_t)*len) { fclose(f); free(b); return 0; }
	fclose(f);
	return b;
}

int main(int argc, char **argv)
{
	long len;
	uint8_t *d = slurp(argv[1], &len);
	errata_mod_t m;
	uint32_t first, count;
	errata_answer_t a;

	ok("opens a well-formed module", d && errata_open(&m, d, (uint64_t)len) == ERRATA_OK, NULL);
	/* synthetic: Intel 6/151/2 -> 2 records; AMD 25/33/0 -> 1 record */
	ok("finds an identity the module covers",
	   errata_find(&m, 1, 6, 151, 2, &first, &count) == ERRATA_OK && count == 2, NULL);
	errata_get(&m, first, &a);
	ok("returns the verdict, status and citation",
	   strcmp(a.text, "ADL001: X87 FDP Value May be Saved Incorrectly") == 0 &&
	   a.verdict == 1 && a.status == 1 && a.page == 14, a.text);
	ok("finds the other vendor's key (vendor is part of the key)",
	   errata_find(&m, 2, 25, 33, 0, &first, &count) == ERRATA_OK && count == 1, NULL);
	ok("an identity it does not cover is NOT_EXAMINED, not safe",
	   errata_find(&m, 1, 6, 151, 3, &first, &count) == ERRATA_NOT_EXAMINED, NULL);
	ok("Intel family 25 is not AMD family 25",
	   errata_find(&m, 1, 25, 33, 0, &first, &count) == ERRATA_NOT_EXAMINED, NULL);

	/* Truncations: every prefix shorter than the module must be refused. */
	int all_refused = 1;
	for (long cut = 0; cut < len; cut++) {
		uint8_t *t = malloc((size_t)(cut ? cut : 1));
		memcpy(t, d, (size_t)cut);
		if (errata_open(&m, t, (uint64_t)cut) == ERRATA_OK) all_refused = 0;
		free(t);
	}
	ok("every truncation of the module is refused (ASan checks no over-read)", all_refused, NULL);
	uint8_t bad[12];
	memcpy(bad, d, 12);
	bad[0] ^= 0xFF;
	ok("a bad magic is refused", errata_open(&m, bad, 12) == ERRATA_EMAGIC, NULL);
	memcpy(bad, d, 12);
	bad[4] = 9;
	ok("another version is refused (exact match)", errata_open(&m, bad, 12) == ERRATA_EVERSION, NULL);

	if (argc > 2) {
		long rl;
		uint8_t *rd = slurp(argv[2], &rl);
		ok("the real module (Intel 682436) opens", rd && errata_open(&m, rd, (uint64_t)rl) == 0, NULL);
		ok("Alder Lake 6/151/2 has 94 verdicts",
		   errata_find(&m, 1, 6, 151, 2, &first, &count) == 0 && count == 94, NULL);
		free(rd);
	} else {
		printf("NOTE  no ingested errata document: real-module checks skipped\n");
	}
	free(d);
	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
