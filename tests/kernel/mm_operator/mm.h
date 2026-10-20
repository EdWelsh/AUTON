/* kernel/include/mm.h of the operator-authored R1 fallback tree: the allocator interface of
 * agent/kernel_spec/subsystems/mm.md, exactly, plus the VMM's and the hooks both call. */
#ifndef AUTON_MM_H
#define AUTON_MM_H

#include <stdint.h>
#include <stddef.h>
#include "boot.h"

#ifndef PAGE_SIZE
#define PAGE_SIZE 4096
#endif
#define HUGE_PAGE_SIZE      (2ULL * 1024 * 1024)

/* --- Physical memory manager and slab ------------------------------------- */
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

/* --- Virtual memory manager ----------------------------------------------- */
#define VMM_FLAG_PRESENT    (1ULL << 0)
#define VMM_FLAG_WRITABLE   (1ULL << 1)
#define VMM_FLAG_USER       (1ULL << 2)
#define VMM_FLAG_NOCACHE    (1ULL << 3)
#define VMM_FLAG_NO_EXECUTE (1ULL << 4)

void     vmm_init(void);
int      vmm_map_page(uint64_t virt, uint64_t phys, uint64_t flags);
int      vmm_map_range(uint64_t virt_start, uint64_t phys_start, uint64_t size, uint64_t flags);
void     vmm_unmap_page(uint64_t virt);
uint64_t vmm_get_physical(uint64_t virt);
int      vmm_protect(uint64_t virt, uint64_t flags);
uint64_t vmm_create_address_space(void);
void     vmm_switch_address_space(uint64_t root_table_phys);
void     vmm_destroy_address_space(uint64_t root_table_phys);

/* What the memory managers need from the HAL (the same declarations as the host suites'
 * vmm_host.h). phys_to_virt is the only door to a physical address. */
void    *phys_to_virt(uint64_t phys);
void     arch_invlpg(uint64_t virt);
uint64_t arch_read_root(void);
void     arch_write_root(uint64_t root);
int      arch_nx_supported(void);

#endif
