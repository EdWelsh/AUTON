---
subsystem: mm
provides: [allocator, pmm, vmm, slab, slm-pool]
depends_on: [boot, arch]
optional: [slm-pool]
# PMM has no dependency beyond boot's memory map; VMM needs PMM for page tables.
---

# Memory Management Specification

## Overview

The memory management subsystem provides physical page allocation (bitmap PMM), virtual address translation via the MMU HAL, a slab allocator for kernel objects, and a dedicated SLM memory pool for model weights and inference buffers. Page table format and manipulation are architecture-specific (accessed through `arch_map_page()`, `arch_flush_tlb()`, etc. from the HAL). The SLM pool is reserved early in boot to guarantee contiguous memory for the language model runtime regardless of system memory pressure.

## Data Structures

### Physical Memory Manager

```c
/* Page size from architecture constants */
#define PAGE_SIZE       ARCH_PAGE_SIZE   /* typically 4096 */
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
/* Portable page mapping flags (architecture HAL translates to native format) */
#define VMM_FLAG_PRESENT    (1ULL << 0)
#define VMM_FLAG_WRITABLE   (1ULL << 1)
#define VMM_FLAG_USER       (1ULL << 2)
#define VMM_FLAG_NOCACHE    (1ULL << 3)
#define VMM_FLAG_NO_EXECUTE (1ULL << 4)

/* Virtual address space regions (from architecture constants) */
#define KERNEL_VBASE    ARCH_KERNEL_VBASE   /* higher-half kernel base */
#define USER_VBASE      ARCH_USER_VBASE     /* user space start */
#define USER_VTOP       ARCH_USER_VTOP      /* user space end */

/* Page table levels and entries are architecture-defined:
 * - x86_64: 4-level (PML4 -> PDPT -> PD -> PT), 512 entries each
 * - AArch64: 4-level translation tables (4KB granule), 512 entries
 * - RISC-V: 3-level Sv39, 512 entries
 * See ARCH_PT_LEVELS in arch_memory.h */

/* VMM state */
typedef struct vmm_state {
    uint64_t kernel_root_phys;  /* physical address of root page table */
    uint64_t *kernel_root_virt; /* virtual address of root page table */
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
/* Initialize PMM from boot-parsed memory map.
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

/* Return count of free pages. Queryable at any time, not only at boot:
 * slm_init() sizes its headroom from this rather than from a constant, and
 * the chat answers "how much memory is free" from it. Answering with the
 * total instead is graded as garbage by the eval rubric, and was. */
uint64_t pmm_free_count(void);

/* Return total usable pages detected at boot */
uint64_t pmm_total_count(void);

/* Return pages excluded from allocation (see Reserved Regions). total =
 * reserved + free + allocated; a generator that cannot make those add up has
 * a bug in its reserved-region handling. */
uint64_t pmm_reserved_count(void);

/* Mark a physical address range as used (for reserved regions).
 * Rounds start down and end up to frame boundaries — a reserved region that
 * begins mid-frame must reserve the whole frame, or the other half is handed
 * out and the region is corrupted. */
void pmm_mark_used(uint64_t phys_start, uint64_t size);

/* Physically contiguous allocation with caller-specified alignment, for DMA.
 *
 * PRESERVED CONTRACT. The retired tree's lib/phys.c provided this as a bump
 * allocator with no free, and every driver plus the neural backend calls it.
 * The replacement must keep both guarantees — physical contiguity and the
 * requested alignment — because a generated allocator that silently returns
 * unaligned or discontiguous memory to a DMA caller produces corruption that
 * presents as a driver bug, far from its cause.
 *
 * `align` must be a power of two and at least 8. Returns NULL on failure;
 * never returns a partially-satisfying block. */
void *dma_alloc(unsigned long size, unsigned long align);

/* Release a dma_alloc block. `dma_free(NULL)` is a no-op. */
void dma_free(void *ptr);
```

### Reserved Regions (REQUIRED)

A frame in any of these must never be returned by `pmm_alloc_page`,
`pmm_alloc_contiguous` or `dma_alloc`. The PMM marks them before it satisfies a
single request.

| Region | Source | Why |
|---|---|---|
| Frame 0 | fixed | A NULL return must be distinguishable from a valid allocation |
| Kernel image | linker symbols `__kernel_start` / `__kernel_end` | Handing out the running code is immediate |
| The bitmap itself | placed by `pmm_init` | See below |
| **Boot modules** | Multiboot2 tag type 3, each `mod_start`..`mod_end` | **The model runs in place from its module.** It is never copied — that is the whole point of the flat format. A PMM that hands this memory out corrupts the running model, and the symptom is degenerate output much later, which looks like a bad model rather than an allocator bug |
| Firmware-reserved | Multiboot2 memory-map entries with `type != 1` | Not RAM, or claimed by ACPI/firmware |
| SLM pool | `slm_pool_init` | Contiguous by construction, reserved early (see SLM Memory Pool) |

Boot modules are the one a generator is most likely to miss: the memory map
reports them as available RAM, because from the firmware's point of view they
are. Only the module tags say otherwise.

### Bitmap Placement (REQUIRED)

The bitmap needs `total_frames / 8` bytes, and it cannot allocate them — it is
what allocation depends on. `pmm_init` therefore:

1. Computes `total_frames` from the memory map.
2. Chooses the lowest available region large enough to hold the bitmap that does
   not overlap the kernel image or any boot module.
3. Places the bitmap there, zeroes it, then marks every reserved region used —
   **including the frames the bitmap now occupies**.

Step 3's last clause is the subtle one. A bitmap that does not mark itself is
handed out on the first allocation that reaches it, and every allocation
afterwards reads corrupted state.

### Reporting (REQUIRED)

`pmm_init` ends by printing exactly:

```
[MM] PMM initialized: <total> pages total, <reserved> reserved, <free> free
```

The three numbers must satisfy `total == reserved + free` at init. The previous
format reported only a free count, which nothing could verify — any number at
all satisfied `\[MM\] PMM initialized: \d+ pages free`, including a wrong one.


### Virtual Memory Manager (`kernel/include/mm.h`)

```c
/* Initialize VMM: calls arch_mmu_init() to set up root page table,
 * map kernel higher-half, identity map critical regions.
 * Must be called after pmm_init(). */
void vmm_init(void);

/* Map a single virtual page to a physical frame with given flags.
 * Calls arch_map_page() which allocates intermediate page tables as needed.
 * Returns 0 on success, -1 on failure (out of memory for page tables). */
int vmm_map_page(uint64_t virt, uint64_t phys, uint64_t flags);

/* Map a contiguous range of virtual pages to physical frames.
 * Convenience wrapper over vmm_map_page for multi-page mappings. */
int vmm_map_range(uint64_t virt_start, uint64_t phys_start,
                  uint64_t size, uint64_t flags);

/* Unmap a virtual page. Invalidates TLB entry via arch_flush_tlb().
 * Does NOT free the physical page (caller must do that separately). */
void vmm_unmap_page(uint64_t virt);

/* Translate virtual address to physical address.
 * Walks page tables. Returns 0 if not mapped. */
uint64_t vmm_get_physical(uint64_t virt);

/* Create a new address space via arch_create_address_space().
 * Copies kernel mappings into new root table. Returns physical address. */
uint64_t vmm_create_address_space(void);

/* Switch to a different address space via arch_switch_address_space(). */
void vmm_switch_address_space(uint64_t root_table_phys);

/* Destroy an address space via arch_destroy_address_space(). */
void vmm_destroy_address_space(uint64_t root_table_phys);

/* Change a mapped page's flags, keeping its frame. Splits a covering 2 MiB
 * mapping first. Returns 0, or -1 if the page is not mapped. */
int vmm_protect(uint64_t virt, uint64_t flags);
```

The VMM reaches memory, the TLB and the boot tables only through the PMM and the HAL:
`pmm_alloc_page`/`pmm_free_page`, `phys_to_virt`, `arch_invlpg`, `arch_read_root` (CR3 on
x86-64), `arch_nx_supported`. Those are exactly the hooks `tests/kernel/vmm_reference/include/
vmm_host.h` declares, so a generated `vmm.c` is tested against what it will call.

### Boot Handover (REQUIRED)

`vmm_init` **adopts** the page tables the boot code built, read with `arch_read_root()`, and
allocates nothing to do so. On x86-64 that is `boot.S`'s identity map of the low 4 GiB in
**2 MiB pages**. Rebuilding a fresh set of tables at init would have to reproduce every mapping
the boot code made, including the ones the kernel is executing from, and a mistake there is a
triple fault with no diagnostic.

### Huge-Page Split (REQUIRED)

Any 4 KiB operation (`vmm_map_page`, `vmm_protect`) on an address covered by a 2 MiB mapping
first **splits** it: allocate one page table; fill its 512 entries with the huge page's frame +
`i × 4 KiB`, carrying the huge entry's P, RW, US, PCD and XD bits; point the directory entry at
the table; invalidate the old 2 MiB translation.

| Rule | Why | Failure if broken |
|---|---|---|
| Do **not** copy bit 7 into the PTEs | bit 7 is PS in a PDE and **PAT** in a PTE | every split page silently changes memory type |
| Preserve every neighbour's flags | only the target page's permissions are changing | 511 pages turn read-only; the next write to one faults somewhere unrelated |
| Invalidate the 2 MiB translation | the TLB may hold the large entry | the old permissions stay in force until an unrelated flush |

### Permission Change (REQUIRED)

`vmm_protect(virt, flags)` replaces the page's flags, keeps its frame, and calls
`arch_invlpg(virt)`. The first consumer is `mitigations/f00f-idt-remap.md`, which needs the page
holding IDT entries 0–6 **read-only** while the kernel keeps running from the same 2 MiB region.

### Intermediate Tables and Out-of-Memory (REQUIRED)

Intermediate tables come from `pmm_alloc_page()` and are zeroed before they are linked. If an
allocation fails partway down a walk, every table allocated **by that call** is unlinked and
freed before `-1` is returned. A failed map must leave the tree exactly as it found it. A
half-built path makes later walks follow a pointer to a freed frame.

### TLB Invalidation (REQUIRED)

| Operation | Invalidates |
|---|---|
| map over a present page | that page |
| unmap | that page |
| protect | that page |
| split | the 2 MiB region's translation |
| map into a previously absent entry | nothing (an absent entry is never cached) |

A VMM that forgets the TLB passes every translation test and is wrong on hardware. The host suite
therefore asserts *which* addresses were invalidated, not just the resulting tables.

### No-Execute

`VMM_FLAG_NO_EXECUTE` sets bit 63 (XD) **only** when `arch_nx_supported()` reports EFER.NXE
enabled. Without it bit 63 is reserved, and setting it faults every access through that entry. The
flag is then ignored and the mapping made without it.

### Verification

`tests/kernel/run_vmm_test.sh --self-test` proves the suite against `vmm_reference/` under
ASan/UBSan. `KERNEL_TREE=<dir> tests/kernel/run_vmm_test.sh` gates a generated `kernel/mm/vmm.c`:
exit 2 means not generated, exit 1 means generated wrong. Five injected bugs (a forgotten
invalidation, PS copied as PAT, a split dropping the neighbours' RW, OOM leaking a table,
translation dropping the page offset) are each caught.


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
 * Determines size class from slab metadata.
 *
 * kfree(NULL) is LEGAL and is a no-op. Every error path in the kernel ends in
 * a cleanup that frees whatever it got, and making NULL illegal turns each of
 * those into a branch a generator will eventually forget. */
void kfree(void *ptr);

/* Print slab allocator statistics to serial (debug). */
void slab_dump_stats(void);
```

### General vs DMA allocation (REQUIRED)

Two allocators, and a generator must not conflate them:

| | `kmalloc` | `dma_alloc` |
|---|---|---|
| Returns | virtual address | physical address, identity-mapped |
| Contiguity | virtual only | **physically contiguous** |
| Alignment | `sizeof(void *)`, or the size class where larger | **caller-specified**, power of two |
| Use | kernel objects, buffers, strings | descriptor rings, packet buffers, model weights |
| On failure | NULL | NULL |

`kmalloc` is the default. `dma_alloc` exists only because hardware reads the
memory without going through the MMU, so a driver that takes a `kmalloc` pointer
and hands it to a NIC gets whatever physical pages happened to back it.

### kmalloc semantics (REQUIRED)

- `kmalloc(0)` returns NULL. A unique non-NULL pointer would be defensible in
  userspace; in a kernel it is one more thing to free correctly for no benefit.
- Returned memory is **not** zeroed. `kzalloc` is the zeroing form, and a
  generator that zeroes in `kmalloc` makes every caller pay for it silently.
- A failed `kmalloc` returns NULL and allocates nothing. Partial success is not
  a state any caller is written to handle.
- Double-free is a bug the allocator must detect, not absorb: `kfree` on a
  pointer whose slab metadata says free panics with the address. Absorbing it
  hides a use-after-free that will corrupt unrelated memory later.
- `kfree` on a pointer the allocator never returned panics. Silently ignoring it
  turns a pointer-arithmetic bug into a leak plus corruption.

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

Page table walking is architecture-specific and handled by the MMU HAL. The portable VMM calls `arch_map_page(virt, phys, flags)` which:

1. Walks the architecture's page table hierarchy (e.g., PML4→PDPT→PD→PT on x86_64, or L0→L1→L2→L3 on AArch64)
2. Allocates intermediate page tables as needed (via `pmm_alloc_page()`)
3. Sets the leaf entry with the physical address and translated flags
4. Flushes the TLB for the address via `arch_flush_tlb(virt)`

See `arch/<arch>.md` for the specific page table format and virtual address layout.

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
- **Double free**: `pmm_free_page()` panics with diagnostic (address, caller return address)
- **Page table allocation failure during mapping**: `vmm_map_page()` returns -1
- **Slab large allocation**: sizes > 2048 bytes bypass slab, use direct page allocation
- **SLM pool exhaustion**: `slm_pool_alloc()` returns NULL; SLM falls back to simpler inference or reports error
- **SLM pool too small for neural backend**: SLM runtime detects this and falls back to rule engine

## Files

| File | Purpose |
|------|---------|
| `kernel/mm/pmm.c`       | Physical memory manager (bitmap allocator) |
| `kernel/mm/vmm.c`       | Virtual memory manager (portable, calls MMU HAL) |
| `kernel/mm/slab.c`      | Slab allocator (kmalloc/kfree) |
| `kernel/mm/slm_pool.c`  | SLM dedicated memory pool |
| `kernel/include/mm.h`   | All memory management interfaces |

## Dependencies

- **boot**: provides `boot_mmap_t` (parsed from architecture boot protocol)
- **boot**: provides kernel physical address range (linker symbols)
- **arch/mm**: MMU HAL functions (`arch_map_page`, `arch_flush_tlb`, `arch_create_address_space`, etc.)
- PMM has no dependencies (first subsystem initialized after serial)
- VMM depends on PMM (needs pages for page tables)
- Slab depends on PMM + VMM
- SLM pool depends on PMM + VMM

## Acceptance Criteria

1. PMM correctly parses boot memory map; `pmm_total_count()` matches expected RAM
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
