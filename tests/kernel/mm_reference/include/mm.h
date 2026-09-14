/* The allocator interface as specified in agent/kernel_spec/subsystems/mm.md.
 * A generated kernel must provide exactly this. */
#ifndef AUTON_TEST_MM_H
#define AUTON_TEST_MM_H
#include <stdint.h>
#include <stddef.h>
#include "boot.h"

#define PAGE_SIZE 4096

void     pmm_init(const boot_mmap_t *mmap);
void    *pmm_alloc_page(void);
void    *pmm_alloc_contiguous(uint32_t page_count);
void     pmm_free_page(void *phys_addr);
uint64_t pmm_free_count(void);
uint64_t pmm_total_count(void);
uint64_t pmm_reserved_count(void);
void     pmm_mark_used(uint64_t phys_start, uint64_t size);
void    *dma_alloc(unsigned long size, unsigned long align);
void     dma_free(void *ptr);

void     slab_init(void);
void    *kmalloc(size_t size);
void    *kzalloc(size_t size);
void     kfree(void *ptr);
void     slab_dump_stats(void);

#endif
