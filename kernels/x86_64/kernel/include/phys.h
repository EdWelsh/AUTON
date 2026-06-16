/* Tiny page-aligned bump allocator over a static low-RAM arena.
 *
 * The kernel is loaded at 1 MiB and runs identity-mapped, so any address inside
 * this arena satisfies phys == virt — which is exactly what device DMA engines
 * (e.g. the e1000 descriptor rings/buffers) require. */
#ifndef AUTON_PHYS_H
#define AUTON_PHYS_H

#include <stdint.h>
#include <stddef.h>

/* Allocate 'size' bytes aligned up to 'align' (a power of two, >= 16).
 * Returns NULL if the arena is exhausted. Memory is zeroed. */
void *dma_alloc(size_t size, size_t align);

#endif /* AUTON_PHYS_H */
