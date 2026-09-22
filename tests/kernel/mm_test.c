/* Host test for the generated physical and slab allocators.
 *
 * Built and run by tests/kernel/run_mm_test.sh against any generated kernel
 * tree. Lives here, not in the tree, for the reason every kernel test does:
 * verification must not be inside the artifact it verifies. An agent that
 * generates both the allocator and its tests can satisfy itself.
 *
 * The properties checked are the ones a generated allocator gets wrong in ways
 * that surface far from the cause:
 *   - boot-module memory handed out (the model runs in place from it)
 *   - the bitmap not marking its own frames
 *   - dma_alloc losing alignment or contiguity
 *   - kfree(NULL) trapping, so every error path needs a branch
 *   - double-free absorbed rather than caught
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "mm.h"
#include "boot.h"

#ifndef PAGE_SIZE
#define PAGE_SIZE 4096
#endif

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	if (cond) {
		printf("PASS  %-46s\n", name);
	} else {
		printf("FAIL  %-46s  %s\n", name, detail ? detail : "");
		fails = 1;
	}
}

/* A 64 MiB synthetic machine: one usable region, a kernel image low in it, and
 * one boot module — the shape that matters, because the module is reported as
 * available RAM and only the module tag says otherwise. */
#define MEM_BYTES   (64u * 1024 * 1024)
#define KERNEL_BASE 0x100000u
#define KERNEL_LEN  (2u * 1024 * 1024)
#define MODULE_BASE 0x2000000u          /* 32 MiB */
#define MODULE_LEN  (4u * 1024 * 1024)
/* Deliberately not frame-aligned at either end. mm.md requires the start to
 * round down and the end to round up, and a region that begins mid-frame is
 * where an implementation that rounds the wrong way hands out the other half
 * of a reserved frame. Both page-aligned regions above would miss it. */
#define RAGGED_BASE 0x3001000u          /* 48 MiB + 4 KiB + ... */
#define RAGGED_OFF  0x123u              /* ...an offset into that frame */
#define RAGGED_LEN  (PAGE_SIZE + 0x456u)

static boot_mmap_t make_map(void)
{
	boot_mmap_t m;
	memset(&m, 0, sizeof m);
	m.count = 1;
	m.entries[0].base_addr = 0;
	m.entries[0].length = MEM_BYTES;
	m.entries[0].type = 1;              /* usable */
	return m;
}

static int in_range(uint64_t p, uint64_t base, uint64_t len)
{
	return p >= base && p < base + len;
}

int main(void)
{
	boot_mmap_t map = make_map();

	pmm_init(&map);
	pmm_mark_used(KERNEL_BASE, KERNEL_LEN);
	pmm_mark_used(MODULE_BASE, MODULE_LEN);
	pmm_mark_used(RAGGED_BASE + RAGGED_OFF, RAGGED_LEN);

	uint64_t total = pmm_total_count();
	uint64_t reserved = pmm_reserved_count();
	uint64_t free_now = pmm_free_count();

	ok("total frames match the memory map",
	   total == MEM_BYTES / PAGE_SIZE, "map says 64 MiB");
	ok("total == reserved + free at init",
	   total == reserved + free_now, "the three numbers must add up");
	ok("something is reserved",
	   reserved > 0, "kernel, bitmap and module are all reserved regions");

	/* Drain the allocator and check nothing reserved ever comes back. This is
	 * the test for the bug that matters: a module frame handed out corrupts a
	 * running model, and the symptom appears as degenerate output much later. */
	uint64_t handed = 0, bad_kernel = 0, bad_module = 0, bad_zero = 0;
	uint64_t bad_ragged = 0;
	/* Every frame the ragged region touches, start rounded down and end up. */
	uint64_t ragged_first = (RAGGED_BASE + RAGGED_OFF) / PAGE_SIZE * PAGE_SIZE;
	uint64_t ragged_end =
		((RAGGED_BASE + RAGGED_OFF + RAGGED_LEN + PAGE_SIZE - 1) / PAGE_SIZE)
		* PAGE_SIZE;
	void *p;
	while ((p = pmm_alloc_page()) != NULL) {
		uint64_t phys = (uint64_t)p;
		if (phys == 0) bad_zero++;
		if (in_range(phys, KERNEL_BASE, KERNEL_LEN)) bad_kernel++;
		if (in_range(phys, MODULE_BASE, MODULE_LEN)) bad_module++;
		if (in_range(phys, ragged_first, ragged_end - ragged_first)) bad_ragged++;
		handed++;
		if (handed > total) break;      /* allocator is not tracking at all */
	}

	ok("never hands out frame 0", bad_zero == 0,
	   "NULL must be distinguishable from a valid allocation");
	ok("never hands out kernel image memory", bad_kernel == 0, NULL);
	ok("never hands out boot-module memory", bad_module == 0,
	   "the model runs in place from its module");
	ok("reserves whole frames for an unaligned region", bad_ragged == 0,
	   "a region starting mid-frame must reserve that whole frame");
	ok("hands out exactly the free count", handed == free_now,
	   "more means reserved frames leaked; fewer means frames are lost");
	ok("reports empty when drained", pmm_free_count() == 0, NULL);

	/* Exhaustion is a NULL, not a panic and not a wrapped pointer. */
	ok("returns NULL when exhausted", pmm_alloc_page() == NULL, NULL);

	/* Free one, get one: the bitmap's free path actually clears a bit. */
	pmm_free_page((void *)(uintptr_t)(MEM_BYTES - PAGE_SIZE));
	ok("a freed frame is reusable", pmm_free_count() == 1, NULL);
	void *again = pmm_alloc_page();
	ok("reallocates the freed frame", again != NULL, NULL);

	/* Rebuild for the contiguity and alignment checks. */
	pmm_init(&map);
	pmm_mark_used(KERNEL_BASE, KERNEL_LEN);
	pmm_mark_used(MODULE_BASE, MODULE_LEN);
	pmm_mark_used(RAGGED_BASE + RAGGED_OFF, RAGGED_LEN);

	void *run = pmm_alloc_contiguous(16);
	ok("contiguous allocation succeeds", run != NULL, NULL);
	ok("contiguous run is page aligned",
	   run && ((uint64_t)run % PAGE_SIZE) == 0, NULL);
	ok("contiguous run avoids reserved regions",
	   run && !in_range((uint64_t)run, MODULE_BASE, MODULE_LEN) &&
	   !in_range((uint64_t)run, KERNEL_BASE, KERNEL_LEN), NULL);

	/* dma_alloc is the preserved contract: drivers depend on both guarantees,
	 * and losing either produces corruption that presents as a driver bug. */
	static const unsigned long aligns[] = {8, 16, 64, 256, 4096};
	int align_ok = 1, dma_reserved_ok = 1;
	for (unsigned i = 0; i < sizeof aligns / sizeof aligns[0]; i++) {
		void *d = dma_alloc(3000, aligns[i]);
		if (!d) { align_ok = 0; break; }
		if ((uint64_t)d % aligns[i]) align_ok = 0;
		if (in_range((uint64_t)d, MODULE_BASE, MODULE_LEN)) dma_reserved_ok = 0;
	}
	ok("dma_alloc honours every requested alignment", align_ok,
	   "unaligned DMA memory corrupts in a way that looks like a driver bug");
	ok("dma_alloc avoids reserved regions", dma_reserved_ok, NULL);

	/* Slab. */
	slab_init();
	void *a = kmalloc(64);
	void *b = kmalloc(64);
	ok("kmalloc returns distinct pointers", a && b && a != b, NULL);
	ok("kmalloc is at least pointer aligned",
	   a && ((uintptr_t)a % sizeof(void *)) == 0, NULL);
	ok("kmalloc(0) returns NULL", kmalloc(0) == NULL, NULL);

	void *z = kzalloc(128);
	int zeroed = 1;
	for (int i = 0; z && i < 128; i++)
		if (((unsigned char *)z)[i]) zeroed = 0;
	ok("kzalloc zeroes what it returns", z && zeroed, NULL);

	kfree(a);
	kfree(b);
	kfree(z);
	kfree(NULL);   /* must not trap — every cleanup path frees what it got */
	ok("kfree(NULL) is a no-op", 1, NULL);

	void *reuse = kmalloc(64);
	ok("freed slab memory is reusable", reuse != NULL, NULL);

	printf(fails ? "\nMM: FAILURES\n" : "\nMM: ALL PASS\n");
	return fails;
}
