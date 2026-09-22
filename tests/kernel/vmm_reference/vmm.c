/* Reference x86-64 VMM, implementing agent/kernel_spec/subsystems/mm.md.
 *
 * NOT kernel code and not shipped. It exists so vmm_test.c can be proved
 * against a known-good implementation, and it pins the spec: the REQUIRED
 * sections in mm.md were written alongside it. It touches memory only through
 * vmm_host.h, which is what a generated vmm.c gets from the PMM and the HAL.
 *
 * Page-table format: Intel SDM Vol. 3A §4.5 (4-level paging).
 */
#include <stdint.h>
#include <stddef.h>
#include "mm.h"
#include "vmm_host.h"

#define PTE_P    (1ULL << 0)
#define PTE_RW   (1ULL << 1)
#define PTE_US   (1ULL << 2)
#define PTE_PCD  (1ULL << 4)
#define PTE_PS   (1ULL << 7)    /* in a PDE/PDPTE: large page. In a PTE: PAT. */
#define PTE_XD   (1ULL << 63)
#define PTE_ADDR 0x000FFFFFFFFFF000ULL
/* Flags a split copies from the 2 MiB entry into each PTE. PS is not among
 * them: bit 7 of a PTE is PAT, so copying it changes the memory type. */
#define SPLIT_KEEP (PTE_P | PTE_RW | PTE_US | PTE_PCD | PTE_XD)

static uint64_t root;

static uint64_t *tbl(uint64_t entry) { return (uint64_t *)phys_to_virt(entry & PTE_ADDR); }
static unsigned idx(uint64_t va, int level) { return (unsigned)(va >> (12 + 9 * level)) & 511; }

static uint64_t native(uint64_t flags)
{
	uint64_t e = 0;
	if (flags & VMM_FLAG_PRESENT)  e |= PTE_P;
	if (flags & VMM_FLAG_WRITABLE) e |= PTE_RW;
	if (flags & VMM_FLAG_USER)     e |= PTE_US;
	if (flags & VMM_FLAG_NOCACHE)  e |= PTE_PCD;
	/* XD is reserved without EFER.NXE; setting it would fault every access. */
	if ((flags & VMM_FLAG_NO_EXECUTE) && arch_nx_supported()) e |= PTE_XD;
	return e;
}

void vmm_init(void)
{
	/* Adopt the boot page tables (boot.S: 4 GiB identity, 2 MiB pages). */
	root = arch_read_root() & PTE_ADDR;
}

/* Split the 2 MiB entry *pde into a page table mapping the same frames. */
static int split(uint64_t *pde, uint64_t va)
{
	void *pt_phys = pmm_alloc_page();
	if (!pt_phys)
		return -1;
	uint64_t *pt = (uint64_t *)phys_to_virt((uint64_t)(uintptr_t)pt_phys);
	uint64_t base = *pde & 0x000FFFFFFFE00000ULL;
	uint64_t keep = *pde & SPLIT_KEEP;
	for (int i = 0; i < 512; i++)
		pt[i] = (base + (uint64_t)i * PAGE_SIZE) | keep;
	/* The directory entry itself stays maximally permissive; the PTEs decide. */
	*pde = (uint64_t)(uintptr_t)pt_phys | PTE_P | PTE_RW | (*pde & PTE_US);
	arch_invlpg(va & ~(HUGE_PAGE_SIZE - 1));
	return 0;
}

/* The PTE for va, creating tables (and splitting a 2 MiB page) when create is
 * set. Returns 0 if absent, or on allocation failure after unwinding. */
static uint64_t *walk(uint64_t va, int create)
{
	uint64_t *made[3];
	uint64_t *made_at[3];
	int nmade = 0;
	uint64_t *t = (uint64_t *)phys_to_virt(root);

	for (int level = 3; level >= 1; level--) {
		uint64_t *e = &t[idx(va, level)];
		if (level == 1 && (*e & PTE_P) && (*e & PTE_PS)) {
			if (!create || split(e, va) != 0)
				return 0;
		} else if (!(*e & PTE_P)) {
			if (!create)
				return 0;
			void *p = pmm_alloc_page();
			if (!p) {
				/* Unwind: free what this call allocated, newest first, and
				 * unlink it, so a failed map leaves no half-built path. */
				while (nmade--) {
					*made_at[nmade] = 0;
					pmm_free_page(made[nmade]);
				}
				return 0;
			}
			*e = (uint64_t)(uintptr_t)p | PTE_P | PTE_RW | PTE_US;
			made[nmade] = (uint64_t *)p;
			made_at[nmade] = e;
			nmade++;
		}
		t = tbl(*e);
	}
	return &t[idx(va, 0)];
}

int vmm_map_page(uint64_t virt, uint64_t phys, uint64_t flags)
{
	if ((virt | phys) & (PAGE_SIZE - 1))
		return -1;
	uint64_t *pte = walk(virt, 1);
	if (!pte)
		return -1;
	int was_present = (*pte & PTE_P) != 0;
	*pte = phys | native(flags);
	if (was_present)
		arch_invlpg(virt);
	return 0;
}

int vmm_map_range(uint64_t virt_start, uint64_t phys_start, uint64_t size, uint64_t flags)
{
	for (uint64_t off = 0; off < size; off += PAGE_SIZE)
		if (vmm_map_page(virt_start + off, phys_start + off, flags) != 0)
			return -1;
	return 0;
}

void vmm_unmap_page(uint64_t virt)
{
	uint64_t *pte = walk(virt & ~(PAGE_SIZE - 1), 0);
	if (!pte || !(*pte & PTE_P))
		return;
	*pte = 0;
	arch_invlpg(virt & ~(PAGE_SIZE - 1));
}

uint64_t vmm_get_physical(uint64_t virt)
{
	uint64_t *t = (uint64_t *)phys_to_virt(root);
	for (int level = 3; level >= 1; level--) {
		uint64_t e = t[idx(virt, level)];
		if (!(e & PTE_P))
			return 0;
		if (level == 1 && (e & PTE_PS))
			return (e & 0x000FFFFFFFE00000ULL) | (virt & (HUGE_PAGE_SIZE - 1));
		t = tbl(e);
	}
	uint64_t pte = t[idx(virt, 0)];
	if (!(pte & PTE_P))
		return 0;
	return (pte & PTE_ADDR) | (virt & (PAGE_SIZE - 1));
}

/* Whether va is mapped at all. vmm_get_physical cannot say: it returns 0 for
 * "unmapped" and for "mapped to frame 0" alike (mm.md's interface). */
static int present(uint64_t va)
{
	uint64_t *t = (uint64_t *)phys_to_virt(root);
	for (int level = 3; level >= 1; level--) {
		uint64_t e = t[idx(va, level)];
		if (!(e & PTE_P))
			return 0;
		if (level == 1 && (e & PTE_PS))
			return 1;
		t = tbl(e);
	}
	return (t[idx(va, 0)] & PTE_P) != 0;
}

int vmm_protect(uint64_t virt, uint64_t flags)
{
	virt &= ~(PAGE_SIZE - 1);
	if (!present(virt))
		return -1;
	uint64_t *pte = walk(virt, 1);   /* splits a covering 2 MiB page */
	if (!pte || !(*pte & PTE_P))
		return -1;
	*pte = (*pte & PTE_ADDR) | native(flags);
	arch_invlpg(virt);
	return 0;
}
