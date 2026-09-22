/* The VMM interface as specified in agent/kernel_spec/subsystems/mm.md.
 * A generated kernel's kernel/include/mm.h must provide exactly these. */
#ifndef AUTON_TEST_VMM_MM_H
#define AUTON_TEST_VMM_MM_H
#include <stdint.h>

#define PAGE_SIZE           4096ULL
#define HUGE_PAGE_SIZE      (2ULL * 1024 * 1024)

/* Portable flags (mm.md "Virtual Memory Manager"). */
#define VMM_FLAG_PRESENT    (1ULL << 0)
#define VMM_FLAG_WRITABLE   (1ULL << 1)
#define VMM_FLAG_USER       (1ULL << 2)
#define VMM_FLAG_NOCACHE    (1ULL << 3)
#define VMM_FLAG_NO_EXECUTE (1ULL << 4)

void     vmm_init(void);
int      vmm_map_page(uint64_t virt, uint64_t phys, uint64_t flags);
int      vmm_map_range(uint64_t virt_start, uint64_t phys_start,
                       uint64_t size, uint64_t flags);
void     vmm_unmap_page(uint64_t virt);
uint64_t vmm_get_physical(uint64_t virt);
/* mm.md "Permission change (REQUIRED)": change a mapped page's flags, keep its
 * frame, split a covering 2 MiB mapping first, invalidate. -1 if unmapped. */
int      vmm_protect(uint64_t virt, uint64_t flags);

#endif
