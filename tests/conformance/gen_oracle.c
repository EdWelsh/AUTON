/* The oracle: expected results computed by Berkeley SoftFloat, never by the
 * hardware under test (agent/kernel_spec/conformance/README.md).
 *
 *   gen_oracle <operands.txt> <oracle.bin>
 *
 * Operands arrive as bit patterns, one entry per line, so nothing here parses
 * a decimal literal — the host's strtod is host FP, and the point of an oracle
 * is that no host FP touches the answer. `agent/tools/conformance.py` does the
 * decimal-to-bits conversion once, on the host, in Python, and the corpus's
 * clause citation travels with it.
 *
 * Line format:  <id> <op> <rounding> <a_bits> [<b_bits>]
 * Output:       one record per line: <id> <result_bits> <exception_flags>
 *
 * Single-precision entries (f32_*) carry 32-bit patterns and produce 32-bit
 * results, printed in eight hex digits, so a single result can never be
 * mistaken for a double's.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#include "softfloat.h"

static uint8_t rounding_of(const char *name)
{
	if (!strcmp(name, "near_even"))
		return softfloat_round_near_even;
	if (!strcmp(name, "minMag"))
		return softfloat_round_minMag;
	if (!strcmp(name, "min"))
		return softfloat_round_min;
	if (!strcmp(name, "max"))
		return softfloat_round_max;
	if (!strcmp(name, "near_maxMag"))
		return softfloat_round_near_maxMag;
	fprintf(stderr, "unknown rounding mode %s\n", name);
	exit(2);
}

int main(int argc, char **argv)
{
	if (argc != 3) {
		fprintf(stderr, "usage: gen_oracle <operands.txt> <oracle.txt>\n");
		return 2;
	}
	FILE *in = fopen(argv[1], "r");
	FILE *out = fopen(argv[2], "w");
	if (!in || !out) {
		perror("open");
		return 2;
	}

	char id[128], op[32], rmode[32];
	unsigned long long a_bits, b_bits;
	int n = 0;
	while (fscanf(in, "%127s %31s %31s %llx", id, op, rmode, &a_bits) == 4) {
		float64_t a = {.v = (uint64_t)a_bits}, r;
		softfloat_roundingMode = rounding_of(rmode);
		softfloat_exceptionFlags = 0;
		softfloat_detectTininess = softfloat_tininess_afterRounding;   /* x86 */

		if (!strcmp(op, "f32_div") || !strcmp(op, "f32_sqrt")) {
			float32_t x = {.v = (uint32_t)a_bits}, y, z;
			if (!strcmp(op, "f32_div")) {
				if (fscanf(in, " %llx", &b_bits) != 1) {
					fprintf(stderr, "%s: f32_div needs two operands\n", id);
					return 2;
				}
				y.v = (uint32_t)b_bits;
				z = f32_div(x, y);
			} else {
				z = f32_sqrt(x);
			}
			fprintf(out, "%s %08lx %02x\n", id, (unsigned long)z.v,
			        softfloat_exceptionFlags);
			n++;
			continue;
		}

		if (!strcmp(op, "f64_div")) {
			if (fscanf(in, " %llx", &b_bits) != 1) {
				fprintf(stderr, "%s: f64_div needs two operands\n", id);
				return 2;
			}
			float64_t b = {.v = (uint64_t)b_bits};
			r = f64_div(a, b);
		} else if (!strcmp(op, "f64_sqrt")) {
			r = f64_sqrt(a);
		} else {
			fprintf(stderr, "unknown operation %s\n", op);
			return 2;
		}
		fprintf(out, "%s %016llx %02x\n", id, (unsigned long long)r.v,
		        softfloat_exceptionFlags);
		n++;
	}
	fclose(in);
	fclose(out);
	fprintf(stderr, "oracle: %d results\n", n);
	return 0;
}
