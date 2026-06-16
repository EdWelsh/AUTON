/* Page-aligned bump allocator over a static low-RAM arena (see phys.h). */
#include "phys.h"
#include "kernel.h"

#define ARENA_SIZE (4u * 1024u * 1024u)     /* 4 MiB — rings + packet buffers */

/* 4 KiB-aligned so the first allocation can hand out page-aligned DMA memory.
 * Lives in .bss inside the kernel image, well under the 1 GiB mark. */
static uint8_t arena[ARENA_SIZE] __attribute__((aligned(4096)));
static size_t arena_off;

void *dma_alloc(size_t size, size_t align)
{
	if (align < 16)
		align = 16;

	size_t pos = (arena_off + (align - 1)) & ~(align - 1);
	if (pos + size > ARENA_SIZE)
		return 0;

	arena_off = pos + size;
	void *p = &arena[pos];
	kmemset(p, 0, size);
	return p;
}
