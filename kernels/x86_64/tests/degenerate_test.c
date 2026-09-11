/* Host test for the degenerate-output guard.
 *
 * Built and run by tests/run_degenerate_test.sh. The guard decides whether the
 * OS speaks or falls back to the rule engine, so its logic is tested directly
 * rather than only when some model happens to misbehave.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

/* neural_backend.c is kernel code; the host link needs the one allocator it
 * calls. The guard itself allocates nothing (that is a requirement of it). */
void *dma_alloc(unsigned long size, unsigned long align)
{
	void *p = NULL;
	if (posix_memalign(&p, align < sizeof(void *) ? sizeof(void *) : align, size))
		return NULL;
	return p;
}

int slm_neural_is_degenerate(const uint32_t *out, uint32_t n);

static int fails;

static void check(const char *name, const uint32_t *o, uint32_t n, int want)
{
	int got = slm_neural_is_degenerate(o, n);
	if (got == want) {
		printf("PASS  %-34s -> %s\n", name, got ? "degenerate" : "ok");
	} else {
		printf("FAIL  %-34s -> %s, wanted %s\n", name,
		       got ? "degenerate" : "ok", want ? "degenerate" : "ok");
		fails = 1;
	}
}

int main(void)
{
	/* Must be caught. */
	check("empty", (const uint32_t[]){0}, 0, 1);
	check("four identical", (const uint32_t[]){7, 7, 7, 7}, 4, 1);
	check("run after a good start",
	      (const uint32_t[]){5, 9, 2, 8, 8, 8, 8}, 7, 1);
	check("period-2 cycle at the tail",
	      (const uint32_t[]){5, 9, 3, 4, 3, 4, 3, 4}, 8, 1);
	check("period-3 cycle at the tail",
	      (const uint32_t[]){9, 1, 2, 3, 1, 2, 3, 1, 2, 3}, 10, 1);

	/* Must NOT be caught — a false fallback silences a good answer. */
	check("normal sentence", (const uint32_t[]){12, 44, 9, 7, 91, 3, 55}, 7, 0);
	check("three identical only",
	      (const uint32_t[]){4, 7, 7, 7, 12, 9}, 6, 0);
	check("repeated word, not adjacent",
	      (const uint32_t[]){7, 3, 7, 4, 7, 5, 7}, 7, 0);
	check("single token", (const uint32_t[]){42}, 1, 0);
	check("two tokens", (const uint32_t[]){42, 43}, 2, 0);
	check("pair repeated twice only",
	      (const uint32_t[]){8, 1, 2, 1, 2}, 5, 0);

	printf(fails ? "DEGENERATE GUARD: FAILURES\n" : "DEGENERATE GUARD: ALL PASS\n");
	return fails;
}
