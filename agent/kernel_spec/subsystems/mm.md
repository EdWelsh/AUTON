# Memory Management Specification

## Overview

The memory management subsystem provides physical page allocation (bitmap PMM), four-level virtual address translation (VMM), a slab allocator for kernel objects, and a dedicated SLM memory pool for model weights and inference buffers. The SLM pool is reserved early in boot to guarantee contiguous memory for the language model runtime regardless of system memory pressure.

## Data Structures

### Physical Memory Manager

```c
/* Page size constant */
#define PAGE_SIZE       4096
#define PAGE_SHIFT      12

/* Maximum supported physical memory: 4GB (1M pages) */
#define PMM_MAX_PAGES   (1024 * 1024)

/* Bitmap: 1 bit per page. 0 = free, 1 = used */
typedef struct pmm_state {
    uint8_t  bitmap[PMM_MAX_PAGES / 8];  /* 128KB for 4GB */
    uint64_t total_pages;       /* total usable pages */
    uint64_t used_pages;        /* currently allocated pages */
    uint64_t highest_page;      /* highest usable page frame number */
    uint64_t search_start;      /* hint: first potentially free page index */
} pmm_state_t;
```

### Virtual Memory Manager

```c
/* Page table entry flags */
#define PTE_PRESENT     (1ULL << 0)
#define PTE_WRITABLE    (1ULL << 1)
#define PTE_USER        (1ULL << 2)
#define PTE_WRITETHROUGH (1ULL << 3)
#define PTE_NOCACHE     (1ULL << 4)
#define PTE_ACCESSED    (1ULL << 5)
#define PTE_DIRTY       (1ULL << 6)
#define PTE_HUGE        (1ULL << 7)   /* 2MB page (in PD level) */
#define PTE_GLOBAL      (1ULL << 8)
#define PTE_NO_EXECUTE  (1ULL << 63)

/* Address mask to extract physical frame from PTE */
#define PTE_ADDR_MASK   0x000FFFFFFFFFF000ULL

/* Page table levels */
#define PT_LEVEL_PML4   3
#define PT_LEVEL_PDPT   2
#define PT_LEVEL_PD     1
#define PT_LEVEL_PT     0

/* Entries per page table (512 entries, 8 bytes each = 4KB) */
#define PT_ENTRIES      512

/* Virtual address space regions */
#define KERNEL_VBASE    0xFFFF800000000000ULL  /* higher-half kernel base */
#define USER_VBASE      0x0000000000400000ULL  /* user space start */
#define USER_VTOP       0x00007FFFFFFFFFFFULL  /* user space end */

/* VMM state */
typedef struct vmm_state {
    uint64_t kernel_pml4_phys;  /* physical address of kernel PML4 */
    uint64_t *kernel_pml4_virt; /* virtual address of kernel PML4 */
} vmm_state_t;
```

### Slab Allocator

```c
/* Size classes for slab allocator (power-of-2) */
#define SLAB_MIN_SIZE       32
#define SLAB_MAX_SIZE       2048
#define SLAB_NUM_CLASSES    7   /* 32, 64, 128, 256, 512, 1024, 2048 */

/* Free object header (embedded in free object memory) */
typedef struct slab_free_obj {
    struct slab_free_obj *next;
} slab_free_obj_t;

/* Slab descriptor: one physical page divided into fixed-size objects */
typedef struct slab {
    struct slab      *next;         /* next slab in this size class */
    slab_free_obj_t  *free_list;    /* linked list of free objects */
    uint32_t          obj_size;     /* size of each object in bytes */
    uint32_t          total_objs;   /* total objects per slab (PAGE_SIZE / obj_size) */
    uint32_t          free_count;   /* number of free objects */
    uint64_t          page_phys;    /* physical page backing this slab */
} slab_t;

/* Slab cache: manages all slabs for one size class */
typedef struct slab_cache {
    uint32_t  obj_size;         /* object size for this cache */
    slab_t   *partial_slabs;    /* slabs with some free objects */
    slab_t   *full_slabs;       /* slabs with no free objects */
    slab_t   *empty_slabs;      /* slabs with all objects free */
    uint64_t  total_allocs;     /* statistics: total allocations */
    uint64_t  total_frees;      /* statistics: total frees */
} slab_cache_t;
```

### SLM Memory Pool

```c
/* SLM pool configuration */
#define SLM_POOL_BASE_PHYS     0x00400000ULL   /* 4MB physical start */
#define SLM_POOL_DEFAULT_SIZE  (4 * 1024 * 1024)  /* 4MB default pool */
#define SLM_POOL_MAX_SIZE      (256 * 1024 * 1024) /* 256MB if RAM allows */

/* Sub-region types within the SLM pool */
typedef enum slm_region_type {
    SLM_REGION_WEIGHTS,         /* model weight storage (read-only after load) */
    SLM_REGION_KV_CACHE,        /* key-value cache for inference */
    SLM_REGION_SCRATCH,         /* scratch buffers for matrix operations */
    SLM_REGION_CONTEXT,         /* conversation context and state */
    SLM_REGION_KNOWLEDGE,       /* knowledge base (device DB, driver catalog) */
    SLM_REGION_COUNT
} slm_region_type_t;

/* SLM pool sub-region descriptor */
typedef struct slm_region {
    uint64_t base_phys;         /* physical start address */
    uint64_t base_virt;         /* virtual mapping address */
    uint64_t size;              /* region size in bytes */
    uint64_t used;              /* bytes currently used */
    int      read_only;         /* 1 if region should be mapped read-only */
} slm_region_t;

/* SLM memory pool state */
typedef struct slm_pool {
    uint64_t      pool_base_phys;   /* physical start of entire pool */
    uint64_t      pool_base_virt;   /* virtual mapping start */
    uint64_t      pool_size;        /* total pool size in bytes */
    slm_region_t  regions[SLM_REGION_COUNT];
    int           initialized;
} slm_pool_t;
```

## Interface

### Physical Memory Manager (`kernel/include/mm.h`)

```c
/* Initialize PMM from Multiboot2-parsed memory map.
 * Marks kernel, boot structures, and SLM pool as used.
 * Must be called before any other memory allocation. */
void pmm_init(const boot_mmap_t *mmap);

/* Allocate a single 4KB page. Returns physical address.
 * Returns NULL (0) if out of memory.
 * Scans bitmap from search_start hint for first free bit. */
void *pmm_alloc_page(void);

/* Allocate N contiguous physical pages. Returns physical address of first page.
 * Returns NULL if no contiguous run of N pages is available.
 * Used for DMA buffers and large allocations. */
void *pmm_alloc_contiguous(uint32_t page_count);

/* Free a single previously allocated page.
 * Panics on double-free (bit already clear). */
void pmm_free_page(void *phys_addr);

/* Return count of free pages */
uint64_t pmm_free_count(void);

/* Return total usable pages detected at boot */
uint64_t pmm_total_count(void);

/* Mark a physical address range as used (for reserved regions) */
void pmm_mark_used(uint64_t phys_start, uint64_t size);
```

### Virtual Memory Manager (`kernel/include/mm.h`)

```c
/* Initialize VMM: set up kernel PML4, map kernel higher-half,
 * identity map critical regions. Must be called after pmm_init(). */
void vmm_init(void);

/* Map a single 4KB virtual page to a physical frame with given flags.
 * Allocates intermediate page tables as needed.
 * Returns 0 on success, -1 on failure (out of memory for page tables). */
int vmm_map_page(uint64_t virt, uint64_t phys, uint64_t flags);

/* Map a contiguous range of virtual pages to physical frames.
 * Convenience wrapper over vmm_map_page for multi-page mappings. */
int vmm_map_range(uint64_t virt_start, uint64_t phys_start,
                  uint64_t size, uint64_t flags);

/* Unmap a virtual page. Invalidates TLB entry via invlpg.
 * Does NOT free the physical page (caller must do that separately). */
void vmm_unmap_page(uint64_t virt);

/* Translate virtual address to physical address.
 * Walks page tables. Returns 0 if not mapped. */
uint64_t vmm_get_physical(uint64_t virt);

/* Create a new address space (allocate and initialize a PML4).
 * Copies kernel mappings into new PML4. Returns physical address of PML4. */
uint64_t vmm_create_address_space(void);

/* Switch to a different address space by loading CR3. */
void vmm_switch_address_space(uint64_t pml4_phys);

/* Destroy an address space: free all user page tables and mapped pages. */
void vmm_destroy_address_space(uint64_t pml4_phys);
```

### Slab Allocator (`kernel/include/mm.h`)

```c
/* Initialize slab caches for all size classes.
 * Must be called after vmm_init(). */
void slab_init(void);

/* Allocate at least 'size' bytes of kernel memory.
 * Rounds up to nearest size class. Returns virtual address.
 * Returns NULL if out of memory. */
void *kmalloc(size_t size);

/* Allocate and zero-fill memory. */
void *kzalloc(size_t size);

/* Free previously allocated kernel memory.
 * Determines size class from slab metadata. */
void kfree(void *ptr);

/* Print slab allocator statistics to serial (debug). */
void slab_dump_stats(void);
```

### SLM Memory Pool (`kernel/include/mm.h`)

```c
/* Initialize SLM memory pool. Reserves physical pages and creates
 * virtual mappings. Called during boot after VMM is ready.
 * 'available_ram' determines pool size (larger RAM = larger pool).
 * Returns 0 on success, -1 if insufficient memory. */
int slm_pool_init(uint64_t available_ram);

/* Allocate memory from a specific SLM pool region.
 * Returns virtual address within the pool. Bump allocator within region.
 * Returns NULL if region is exhausted. */
void *slm_pool_alloc(slm_region_type_t region, size_t size);

/* Reset a region (free all allocations in that region).
 * Used to clear scratch buffers between inference runs. */
void slm_pool_reset(slm_region_type_t region);

/* Get info about a specific SLM pool region. */
const slm_region_t *slm_pool_get_region(slm_region_type_t region);

/* Get total and used memory for the entire SLM pool. */
void slm_pool_stats(uint64_t *total, uint64_t *used);

/* Resize the SLM pool (grow only, cannot shrink while in use).
 * Returns 0 on success, -1 if insufficient memory. */
int slm_pool_resize(uint64_t new_size);
```

## Behavior

### PMM Initialization Algorithm

1. Zero the entire bitmap (all pages marked free initially)
2. Iterate `boot_mmap_t` entries:
   - For each entry with `type != 1` (not available): mark pages as used
   - For entries below 1MB: mark as used (BIOS/legacy area)
3. Mark kernel image pages as used (from linker symbols `_kernel_start` to `_kernel_end`)
4. Mark SLM pool region as used (`SLM_POOL_BASE_PHYS` to `SLM_POOL_BASE_PHYS + pool_size`)
5. Count total free pages, set `search_start = 0`
6. Compute `highest_page` for bounds checking

### PMM Allocation Algorithm (First-Fit)

1. Start scanning bitmap at `search_start`
2. For each byte, check if any bit is 0 (free)
3. On finding free bit: set it to 1, increment `used_pages`
4. Update `search_start` to current position (locality hint)
5. Return `page_index * PAGE_SIZE` as physical address
6. If scan wraps past `highest_page` without finding free page: return NULL

### PMM Contiguous Allocation

1. Scan bitmap for a run of `page_count` consecutive 0 bits
2. If found: set all bits in run, return base address
3. If not found: return NULL
4. Used for: DMA buffers, SLM weight loading, large I/O buffers

### VMM Page Table Walk

```
Virtual address: [PML4 idx : 9 bits][PDPT idx : 9 bits][PD idx : 9 bits][PT idx : 9 bits][Offset : 12 bits]

vmm_map_page(virt, phys, flags):
  1. Extract PML4 index = (virt >> 39) & 0x1FF
  2. If PML4[index] not present: allocate page for PDPT, zero it, set PML4 entry
  3. Extract PDPT index = (virt >> 30) & 0x1FF
  4. If PDPT[index] not present: allocate page for PD, zero it, set PDPT entry
  5. Extract PD index = (virt >> 21) & 0x1FF
  6. If PD[index] not present: allocate page for PT, zero it, set PD entry
  7. Extract PT index = (virt >> 12) & 0x1FF
  8. Set PT[index] = phys | flags | PTE_PRESENT
  9. invlpg(virt)  -- flush TLB for this address
```

### Slab Allocator Algorithm

**kmalloc(size):**
1. Round `size` up to nearest power-of-2 size class (min 32, max 2048)
2. If `size > SLAB_MAX_SIZE`: fall back to `pmm_alloc_contiguous()` for large allocations
3. Look up `slab_cache[class_index]`
4. If `partial_slabs != NULL`: pop object from `partial_slabs->free_list`
5. If no partial slabs: allocate new page, initialize as slab, add to partial list
6. If slab becomes full after allocation: move to `full_slabs` list
7. Return pointer to allocated object

**kfree(ptr):**
1. Find which slab owns this pointer (page-aligned base of ptr's page)
2. Read slab metadata to determine size class
3. Push object onto slab's free_list
4. If slab was full: move from `full_slabs` to `partial_slabs`
5. If slab is now empty: optionally move to `empty_slabs` or free page back to PMM

### SLM Pool Layout

Given `pool_size` total bytes, regions are allocated as follows:

| Region | Fraction | Purpose |
|--------|----------|---------|
| WEIGHTS | 50% | Model weights (read-only after load) |
| KV_CACHE | 20% | Key-value attention cache |
| SCRATCH | 15% | Temporary matrix multiplication buffers |
| CONTEXT | 10% | Conversation state, intent history |
| KNOWLEDGE | 5% | Device DB, driver catalog, package registry |

**Pool sizing by available RAM:**

| Available RAM | Pool Size | Backend |
|--------------|-----------|---------|
| < 32MB | 2MB | Rule engine only |
| 32-128MB | 4MB | Rule engine with large knowledge base |
| 128-512MB | 32MB | Small neural model (INT8) |
| 512MB-2GB | 128MB | Medium neural model (INT4) |
| > 2GB | 256MB | Full neural model |

### Edge Cases

- **Out of physical memory**: `pmm_alloc_page()` returns NULL; caller must handle gracefully
- **Double free**: `pmm_free_page()` panics with diagnostic (address, caller RIP)
- **Page table allocation failure during mapping**: `vmm_map_page()` returns -1
- **Slab large allocation**: sizes > 2048 bytes bypass slab, use direct page allocation
- **SLM pool exhaustion**: `slm_pool_alloc()` returns NULL; SLM falls back to simpler inference or reports error
- **SLM pool too small for neural backend**: SLM runtime detects this and falls back to rule engine

## Files

| File | Purpose |
|------|---------|
| `kernel/mm/pmm.c`       | Physical memory manager (bitmap allocator) |
| `kernel/mm/vmm.c`       | Virtual memory manager (4-level paging) |
| `kernel/mm/slab.c`      | Slab allocator (kmalloc/kfree) |
| `kernel/mm/slm_pool.c`  | SLM dedicated memory pool |
| `kernel/include/mm.h`   | All memory management interfaces |

## Dependencies

- **boot**: provides `boot_mmap_t` (parsed Multiboot2 memory map)
- **boot**: provides kernel physical address range (linker symbols)
- PMM has no dependencies (first subsystem initialized after serial)
- VMM depends on PMM (needs pages for page tables)
- Slab depends on PMM + VMM
- SLM pool depends on PMM + VMM

## Acceptance Criteria

1. PMM correctly parses Multiboot2 memory map; `pmm_total_count()` matches expected RAM
2. `pmm_alloc_page()` returns valid physical addresses; no two calls return the same address
3. `pmm_free_page()` followed by `pmm_alloc_page()` returns the freed page (first-fit)
4. Double-free triggers kernel panic with diagnostic output
5. `pmm_alloc_contiguous(N)` returns N consecutive pages verified by address arithmetic
6. VMM maps page: write to virtual address, read back via physical address (identity window) matches
7. VMM unmap: accessing unmapped virtual address triggers page fault (caught by handler)
8. `vmm_get_physical()` correctly translates mapped addresses
9. `vmm_create_address_space()` produces isolated address space (user writes don't cross)
10. `kmalloc(N)` returns usable memory for all size classes (32, 64, 128, 256, 512, 1024, 2048)
11. `kfree()` recycles memory; 10000 alloc/free cycles with no leaks (free count stable)
12. `kzalloc()` returns zero-filled memory
13. SLM pool initializes with correct size based on available RAM
14. `slm_pool_alloc()` returns addresses within the correct region bounds
15. `slm_pool_reset()` allows the same region to be reallocated from the beginning
16. Weights region is mapped read-only; write attempt triggers page fault
17. Stress test: concurrent allocation from multiple kernel threads shows no corruption
