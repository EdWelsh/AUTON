/* Host harness: compile the in-kernel neural backend natively and run a greedy
 * generation so it can be diffed against the PyTorch reference
 * (SLM/scripts compare). Proves the freestanding forward pass matches torch
 * without booting QEMU. See tests/neural_parity.sh.
 *
 * Build:
 *   clang -O2 -Ikernel/include kernel/slm/neural/neural_backend.c \
 *         kernel/lib/kmath.c tests/neural_forward_host.c -lm -o /tmp/nf
 *   /tmp/nf model.bin 2 4 5      # prints generated token ids
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include "neural.h"

/* The kernel's DMA bump allocator, shimmed to calloc for the host. */
void *dma_alloc(unsigned long n, unsigned long align)
{
	(void)align;
	return calloc(1, n);
}

int main(int argc, char **argv)
{
	if (argc < 3) {
		fprintf(stderr, "usage: %s model.bin id [id...]\n", argv[0]);
		return 2;
	}
	FILE *f = fopen(argv[1], "rb");
	if (!f) {
		fprintf(stderr, "cannot open %s\n", argv[1]);
		return 2;
	}
	fseek(f, 0, SEEK_END);
	long sz = ftell(f);
	fseek(f, 0, SEEK_SET);
	void *buf = malloc(sz);
	if (fread(buf, 1, sz, f) != (size_t)sz) {
		fprintf(stderr, "short read\n");
		return 2;
	}
	fclose(f);

	if (slm_neural_load_model(buf, sz, MODEL_FORMAT_AUTON) != 0) {
		printf("LOAD FAIL\n");
		return 1;
	}

	uint32_t ids[64];
	uint32_t n = 0;
	for (int i = 2; i < argc && n < 64; i++)
		ids[n++] = (uint32_t)atoi(argv[i]);

	uint32_t out[16];
	inference_config_t cfg = { 0.0f, 1.0f, 12, 1 };
	uint32_t no = slm_neural_infer(ids, n, out, 12, &cfg);

	printf("gen:");
	for (uint32_t i = 0; i < no; i++)
		printf(" %u", out[i]);
	printf("\n");
	return 0;
}
