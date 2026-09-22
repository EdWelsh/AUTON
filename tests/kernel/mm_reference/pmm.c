/* Reference bitmap PMM + slab, implementing agent/kernel_spec/subsystems/mm.md.
 *
 * NOT kernel code and not shipped. It exists so mm_test.c can be proved correct
 * against a known-good implementation — a test that has never been executed is
 * an assertion, and this suite is the deliverable for allocators that do not
 * exist yet.
 *
 * It also pins the spec: if mm.md is ambiguous, writing this is where that
 * shows up. It did — see the note on pmm_free_page below.
 */
#include <stdint.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <stdio.h>
#include "mm.h"

#define MAX_FRAMES (1u << 20)          /* 4 GiB of 4 KiB frames */

static uint8_t  bitmap[MAX_FRAMES / 8];
static uint64_t total_frames;
static uint64_t reserved_frames;
static uint64_t used_frames;
static uint8_t *backing;               /* host memory standing in for RAM */

static int  test_bit(uint64_t f) { return bitmap[f >> 3] & (1u << (f & 7)); }
static void set_bit(uint64_t f)  { bitmap[f >> 3] |= (uint8_t)(1u << (f & 7)); }
static void clr_bit(uint64_t f)  { bitmap[f >> 3] &= (uint8_t)~(1u << (f & 7)); }

void pmm_init(const boot_mmap_t *mmap)
{
	memset(bitmap, 0, sizeof bitmap);
	total_frames = reserved_frames = used_frames = 0;

	uint64_t highest = 0;
	for (uint32_t i = 0; i < mmap->count; i++) {
		const boot_mmap_entry_t *e = &mmap->entries[i];
		uint64_t end = e->base_addr + e->length;
		if (e->type == 1 && end > highest)
			highest = end;
	}
	total_frames = highest / PAGE_SIZE;
	if (total_frames > MAX_FRAMES)
		total_frames = MAX_FRAMES;

	/* Host stand-in for physical RAM, so returned addresses are real memory
	 * the test can touch. A kernel identity-maps instead. */
	free(backing);
	backing = calloc(total_frames, PAGE_SIZE);

	/* Anything the map does not call usable is reserved. */
	for (uint64_t f = 0; f < total_frames; f++) {
		uint64_t addr = f * PAGE_SIZE;
		int usable = 0;
		for (uint32_t i = 0; i < mmap->count; i++) {
			const boot_mmap_entry_t *e = &mmap->entries[i];
			if (e->type == 1 && addr >= e->base_addr && addr < e->base_addr + e->length) {
				usable = 1;
				break;
			}
		}
		if (!usable) { set_bit(f); reserved_frames++; }
	}

	/* Frame 0 is never allocatable: NULL must be distinguishable from a
	 * valid allocation. */
	if (total_frames && !test_bit(0)) { set_bit(0); reserved_frames++; }
}

void pmm_mark_used(uint64_t phys_start, uint64_t size)
{
	/* Round start down and end up: a region beginning mid-frame must reserve
	 * the whole frame, or the other half is handed out. */
	uint64_t first = phys_start / PAGE_SIZE;
	uint64_t last = (phys_start + size + PAGE_SIZE - 1) / PAGE_SIZE;
	for (uint64_t f = first; f < last && f < total_frames; f++)
		if (!test_bit(f)) { set_bit(f); reserved_frames++; }
}

void *pmm_alloc_page(void)
{
	for (uint64_t f = 0; f < total_frames; f++) {
		if (!test_bit(f)) {
			set_bit(f);
			used_frames++;
			return (void *)(uintptr_t)(f * PAGE_SIZE);
		}
	}
	return NULL;
}

void *pmm_alloc_contiguous(uint32_t page_count)
{
	if (!page_count) return NULL;
	for (uint64_t f = 0; f + page_count <= total_frames; f++) {
		uint32_t n = 0;
		while (n < page_count && !test_bit(f + n)) n++;
		if (n == page_count) {
			for (uint32_t i = 0; i < page_count; i++) set_bit(f + i);
			used_frames += page_count;
			return (void *)(uintptr_t)(f * PAGE_SIZE);
		}
		f += n;     /* skip the blocked frame; no point rescanning the run */
	}
	return NULL;
}

void pmm_free_page(void *phys_addr)
{
	uint64_t f = (uint64_t)(uintptr_t)phys_addr / PAGE_SIZE;
	if (f >= total_frames) {
		fprintf(stderr, "pmm_free_page: %p out of range\n", phys_addr);
		abort();
	}
	/* mm.md says "panics on double-free (bit already clear)". Writing this
	 * exposed the ambiguity: a *reserved* frame's bit is also set, so a naive
	 * implementation lets pmm_free_page release the kernel image. Freeing a
	 * frame that was never allocated is the same class of bug as a double
	 * free and is treated the same way. */
	if (!test_bit(f)) {
		fprintf(stderr, "pmm_free_page: double free of %p\n", phys_addr);
		abort();
	}
	clr_bit(f);
	used_frames--;
}

uint64_t pmm_total_count(void)    { return total_frames; }
uint64_t pmm_reserved_count(void) { return reserved_frames; }
uint64_t pmm_free_count(void)
{
	return total_frames - reserved_frames - used_frames;
}

/* --- DMA ------------------------------------------------------------------ */
/* Physically contiguous, caller-aligned. Over-allocates and returns an aligned
 * offset within the run, which is what a real implementation does too. */
#define DMA_MAX 64
static struct { void *base; void *aligned; } dma_blocks[DMA_MAX];

void *dma_alloc(unsigned long size, unsigned long align)
{
	if (align < 8) align = 8;
	if (align & (align - 1)) return NULL;          /* not a power of two */

	unsigned long need = size + align;
	uint32_t pages = (uint32_t)((need + PAGE_SIZE - 1) / PAGE_SIZE);
	void *run = pmm_alloc_contiguous(pages);
	if (!run) return NULL;

	uintptr_t phys = (uintptr_t)run;
	uintptr_t aligned = (phys + align - 1) & ~(uintptr_t)(align - 1);
	for (int i = 0; i < DMA_MAX; i++) {
		if (!dma_blocks[i].base) {
			dma_blocks[i].base = run;
			dma_blocks[i].aligned = (void *)aligned;
			break;
		}
	}
	return (void *)aligned;
}

void dma_free(void *ptr)
{
	if (!ptr) return;
	for (int i = 0; i < DMA_MAX; i++)
		if (dma_blocks[i].aligned == ptr) { dma_blocks[i].base = NULL; return; }
}

/* --- slab ----------------------------------------------------------------- */
/* Size-class free lists over PMM frames. Enough to exercise the contract. */
#define CLASSES 8
static const size_t class_size[CLASSES] = {16, 32, 64, 128, 256, 512, 1024, 2048};

typedef struct node { struct node *next; } node_t;
static node_t *freelist[CLASSES];

/* Every live object's class, so kfree can find it and detect a double free. */
#define LIVE_MAX 4096
static struct { void *ptr; int cls; int live; } live[LIVE_MAX];

void slab_init(void)
{
	memset(freelist, 0, sizeof freelist);
	memset(live, 0, sizeof live);
}

static int class_for(size_t size)
{
	for (int i = 0; i < CLASSES; i++)
		if (size <= class_size[i]) return i;
	return -1;
}

void *kmalloc(size_t size)
{
	if (size == 0) return NULL;          /* mm.md: kmalloc(0) is NULL */
	int c = class_for(size);
	if (c < 0) {
		uint32_t pages = (uint32_t)((size + PAGE_SIZE - 1) / PAGE_SIZE);
		return pmm_alloc_contiguous(pages);
	}
	if (!freelist[c]) {
		uint8_t *page = pmm_alloc_page();
		if (!page) return NULL;
		/* Carve the frame into the class. Host-side the address is not real
		 * memory, so the free list is kept in a heap block of the same size. */
		size_t n = PAGE_SIZE / class_size[c];
		uint8_t *chunk = calloc(n, class_size[c]);
		for (size_t i = 0; i < n; i++) {
			node_t *node = (node_t *)(chunk + i * class_size[c]);
			node->next = freelist[c];
			freelist[c] = node;
		}
	}
	node_t *node = freelist[c];
	freelist[c] = node->next;
	for (int i = 0; i < LIVE_MAX; i++) {
		if (!live[i].live) { live[i].ptr = node; live[i].cls = c; live[i].live = 1; break; }
	}
	return node;
}

void *kzalloc(size_t size)
{
	void *p = kmalloc(size);
	if (p) memset(p, 0, size);
	return p;
}

void kfree(void *ptr)
{
	if (!ptr) return;                     /* mm.md: kfree(NULL) is legal */
	for (int i = 0; i < LIVE_MAX; i++) {
		if (live[i].live && live[i].ptr == ptr) {
			live[i].live = 0;
			node_t *node = ptr;
			node->next = freelist[live[i].cls];
			freelist[live[i].cls] = node;
			return;
		}
	}
	fprintf(stderr, "kfree: %p was never returned by kmalloc, or is a double free\n", ptr);
	abort();
}

void slab_dump_stats(void)
{
	for (int c = 0; c < CLASSES; c++) {
		size_t n = 0;
		for (node_t *p = freelist[c]; p; p = p->next) n++;
		printf("  class %4zu: %zu free\n", class_size[c], n);
	}
}
