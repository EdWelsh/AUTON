# Memory Management Specification

## Overview

The memory management subsystem provides physical page allocation, virtual memory mapping, and a slab allocator for kernel objects.

## Physical Memory Manager (PMM)

### Design
- Bitmap-based page allocator
- Page size: 4096 bytes (4KB)
- Bitmap stored in kernel BSS
- Memory map obtained from Multiboot2 memory map tag

### Interface (`kernel/include/mm.h`)
```c
void pmm_init(multiboot_info_t *mbi);
void *pmm_alloc_page(void);        // Returns physical address
void pmm_free_page(void *page);
size_t pmm_free_count(void);        // Number of free pages
size_t pmm_total_count(void);       // Total usable pages
```

### Algorithm
1. Parse Multiboot2 memory map to find usable regions
2. Initialize bitmap (1 bit per page, 0 = free, 1 = used)
3. Mark kernel pages and bitmap pages as used
4. `pmm_alloc_page()`: scan bitmap for first free bit, set it, return address
5. `pmm_free_page()`: clear the corresponding bit

## Virtual Memory Manager (VMM)

### Design
- 4-level paging: PML4 → PDPT → PD → PT
- Each level: 512 entries × 8 bytes = 4KB
- Recursive page table mapping for easy manipulation
- Higher-half kernel mapping: kernel at 0xFFFF800000000000

### Interface
```c
void vmm_init(void);
int vmm_map_page(uint64_t virt, uint64_t phys, uint64_t flags);
void vmm_unmap_page(uint64_t virt);
uint64_t vmm_get_physical(uint64_t virt);
uint64_t vmm_create_address_space(void);  // For agent VMs
void vmm_switch_address_space(uint64_t pml4_phys);
```

### Page Flags
```c
#define PAGE_PRESENT   (1 << 0)
#define PAGE_WRITABLE  (1 << 1)
#define PAGE_USER      (1 << 2)
#define PAGE_NO_EXEC   (1ULL << 63)
```

## Slab Allocator

### Design
- kmalloc/kfree for arbitrary-sized kernel allocations
- Power-of-2 size classes: 32, 64, 128, 256, 512, 1024, 2048 bytes
- Each slab is one physical page
- Free list per size class

### Interface
```c
void slab_init(void);
void *kmalloc(size_t size);
void kfree(void *ptr);
```

## Acceptance Criteria

- PMM correctly parses Multiboot2 memory map
- Page allocation and free round-trips work: alloc → free → alloc returns same page
- No double-free or use-after-free
- VMM maps and unmaps pages correctly
- Virtual addresses resolve to correct physical addresses
- Slab allocator handles all size classes
- Stress test: 10000 alloc/free cycles without leaks
