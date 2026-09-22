/* Venue 1, semantic: run the operation on THIS CPU and compare with the oracle.
 *
 *   native_semantic <operands.txt> <oracle.txt>
 *
 * x86-64 only; on any other host it prints SKIP and exits 0, naming the
 * architecture. A silent pass on hardware that never ran the test is the
 * failure mode this whole harness exists to avoid.
 *
 * The operands are read from a file at run time and passed through `volatile`
 * inline asm, so the compiler cannot constant-fold the division it is supposed
 * to be measuring. MXCSR's rounding-control field is set per entry.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#if defined(__x86_64__)
#include <immintrin.h>

static uint32_t mxcsr_rc(const char *rounding)
{
	if (!strcmp(rounding, "near_even"))
		return 0u << 13;
	if (!strcmp(rounding, "min"))
		return 1u << 13;
	if (!strcmp(rounding, "max"))
		return 2u << 13;
	if (!strcmp(rounding, "minMag"))
		return 3u << 13;
	fprintf(stderr, "rounding %s has no MXCSR encoding\n", rounding);
	exit(2);
}

static uint64_t run_div(uint64_t a_bits, uint64_t b_bits, uint32_t rc)
{
	uint32_t saved, set;
	uint64_t out;
	__asm__ __volatile__("stmxcsr %0" : "=m"(saved));
	set = (saved & ~(3u << 13)) | rc;
	__asm__ __volatile__("ldmxcsr %0" : : "m"(set));
	__asm__ __volatile__(
		"movq %1, %%xmm0\n\t"
		"movq %2, %%xmm1\n\t"
		"divsd %%xmm1, %%xmm0\n\t"
		"movq %%xmm0, %0"
		: "=r"(out) : "r"(a_bits), "r"(b_bits) : "xmm0", "xmm1");
	__asm__ __volatile__("ldmxcsr %0" : : "m"(saved));
	return out;
}

static uint64_t run_sqrt(uint64_t a_bits, uint32_t rc)
{
	uint32_t saved, set;
	uint64_t out;
	__asm__ __volatile__("stmxcsr %0" : "=m"(saved));
	set = (saved & ~(3u << 13)) | rc;
	__asm__ __volatile__("ldmxcsr %0" : : "m"(set));
	__asm__ __volatile__(
		"movq %1, %%xmm0\n\t"
		"sqrtsd %%xmm0, %%xmm0\n\t"
		"movq %%xmm0, %0"
		: "=r"(out) : "r"(a_bits) : "xmm0");
	__asm__ __volatile__("ldmxcsr %0" : : "m"(saved));
	return out;
}

int main(int argc, char **argv)
{
	if (argc != 3) {
		fprintf(stderr, "usage: native_semantic <operands.txt> <oracle.txt>\n");
		return 2;
	}
	FILE *ops = fopen(argv[1], "r");
	FILE *orc = fopen(argv[2], "r");
	if (!ops || !orc) {
		perror("open");
		return 2;
	}

	char id[128], op[32], rmode[32], oid[128];
	unsigned long long a_bits, b_bits, want;
	unsigned flags;
	int checked = 0, diverged = 0;

	while (fscanf(ops, "%127s %31s %31s %llx", id, op, rmode, &a_bits) == 4) {
		int two = !strcmp(op, "f64_div");
		if (two && fscanf(ops, " %llx", &b_bits) != 1)
			return 2;
		if (fscanf(orc, "%127s %llx %x", oid, &want, &flags) != 3) {
			fprintf(stderr, "oracle ran out at %s\n", id);
			return 2;
		}
		if (strcmp(id, oid)) {
			fprintf(stderr, "oracle out of step: %s vs %s\n", id, oid);
			return 2;
		}
		uint32_t rc = mxcsr_rc(rmode);
		uint64_t got = two ? run_div(a_bits, b_bits, rc) : run_sqrt(a_bits, rc);
		checked++;
		if (got != want) {
			/* A NaN's payload is 8086-SSE specialised; a quiet NaN where a
			 * quiet NaN was expected is reported with both patterns and left
			 * for a person, not silently forgiven. */
			printf("DIVERGE %s got %016llx want %016llx\n", id,
			       (unsigned long long)got, want);
			diverged++;
		} else {
			printf("OK %s %016llx\n", id, want);
		}
	}
	printf("SUMMARY semantic checked=%d diverged=%d\n", checked, diverged);
	return diverged ? 1 : 0;
}

#else

int main(int argc, char **argv)
{
	(void)argc;
	(void)argv;
	printf("SKIP semantic: this host is not x86-64 (%s). The instructions under "
	       "test do not exist here; running them under emulation would measure "
	       "the emulator.\n",
#if defined(__aarch64__)
	       "aarch64"
#else
	       "unknown"
#endif
	);
	printf("SUMMARY semantic checked=0 diverged=0 skipped=1\n");
	return 0;
}

#endif
