/* Host tests for the virtual memory manager in agent/kernel_spec/subsystems/mm.md.
 *
 * The VMM is specified and not implemented: no tree has kernel/mm/vmm.c, and
 * the seed identity-maps 4 GiB with 2 MiB pages from boot.S. These tests are
 * the deliverable for a VMM that does not exist yet (`--self-test` runs them
 * against tests/kernel/vmm_reference/), and the gate a generated one must pass.
 *
 * Physical memory is a host arena; the frame allocator, invlpg and the boot
 * root are hooks this file provides (vmm_host.h). The invlpg log matters most:
 * a VMM that forgets the TLB passes every translation test and is wrong on
 * hardware, so the tests assert which addresses were invalidated.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "mm.h"
#include "vmm_host.h"

static int fails;
static void ok(const char *name, int cond, const char *detail)
{
	if (cond) {
		printf("PASS  %-58s\n", name);
	} else {
		printf("FAIL  %-58s  %s\n", name, detail ? detail : "");
		fails++;
	}
}

/* --- the machine under the VMM ------------------------------------------- */
#define ARENA_BYTES (8u * 1024 * 1024)  /* frames for page tables live here */
#define ARENA_PHYS  0x10000000ULL       /* where the arena sits in "physical" space */
static uint8_t arena[ARENA_BYTES] __attribute__((aligned(4096)));
static uint64_t next_frame;
static int allocs, frees, fail_after = -1;

void *phys_to_virt(uint64_t phys)
{
	if (phys < ARENA_PHYS || phys >= ARENA_PHYS + ARENA_BYTES)
		return 0;   /* only page-table frames are ever touched */
	return arena + (phys - ARENA_PHYS);
}

void *pmm_alloc_page(void)
{
	if (fail_after == 0)
		return 0;
	if (fail_after > 0)
		fail_after--;
	if (next_frame + PAGE_SIZE > ARENA_BYTES)
		return 0;
	uint64_t p = ARENA_PHYS + next_frame;
	next_frame += PAGE_SIZE;
	memset(phys_to_virt(p), 0, PAGE_SIZE);
	allocs++;
	return (void *)(uintptr_t)p;
}

void pmm_free_page(void *phys) { (void)phys; frees++; }

#define LOG_MAX 4096
static uint64_t inval[LOG_MAX];
static int ninval;
void arch_invlpg(uint64_t virt) { if (ninval < LOG_MAX) inval[ninval++] = virt; }

static int nx = 1;
int arch_nx_supported(void) { return nx; }

static uint64_t boot_root;
uint64_t arch_read_root(void) { return boot_root; }

/* --- building the boot map the way boot.S does ---------------------------- */
#define P  (1ULL << 0)
#define RW (1ULL << 1)
#define US (1ULL << 2)
#define PS (1ULL << 7)
#define XD (1ULL << 63)
#define ADDR 0x000FFFFFFFFFF000ULL

static uint64_t *table(uint64_t phys) { return (uint64_t *)phys_to_virt(phys & ADDR); }

/* Identity-map [0, 64 MiB) with 2 MiB pages under PML4[0]/PDPT[0]. */
static void fresh_machine(void)
{
	memset(arena, 0, sizeof arena);
	next_frame = 0; allocs = frees = 0; fail_after = -1; ninval = 0; nx = 1;
	uint64_t pml4 = (uint64_t)(uintptr_t)pmm_alloc_page();
	uint64_t pdpt = (uint64_t)(uintptr_t)pmm_alloc_page();
	uint64_t pd   = (uint64_t)(uintptr_t)pmm_alloc_page();
	table(pml4)[0] = pdpt | P | RW;
	table(pdpt)[0] = pd | P | RW;
	for (int i = 0; i < 32; i++)
		table(pd)[i] = ((uint64_t)i << 21) | P | RW | PS;
	boot_root = pml4;
	allocs = 0;
	vmm_init();
}

static uint64_t *pde_for(uint64_t va)
{
	uint64_t *l4 = table(boot_root);
	uint64_t *l3 = table(l4[(va >> 39) & 511]);
	uint64_t *l2 = table(l3[(va >> 30) & 511]);
	return &l2[(va >> 21) & 511];
}

static int invalidated_in(uint64_t lo, uint64_t hi)
{
	for (int i = 0; i < ninval; i++)
		if (inval[i] >= lo && inval[i] < hi)
			return 1;
	return 0;
}

int main(void)
{
	char why[160];

	/* --- boot handover (REQUIRED) ---------------------------------------- */
	fresh_machine();
	ok("vmm_init adopts the boot identity map",
	   vmm_get_physical(0x345678) == 0x345678, NULL);
	ok("vmm_init allocates nothing to adopt it", allocs == 0, NULL);
	ok("an address past the boot map is unmapped", vmm_get_physical(0x8000000) == 0, NULL);

	/* --- mapping and translation ----------------------------------------- */
	fresh_machine();
	uint64_t far = 0x8000000000ULL;   /* PML4[1]: needs PDPT, PD and PT */
	int r = vmm_map_page(far, 0x1234000, VMM_FLAG_PRESENT | VMM_FLAG_WRITABLE);
	ok("mapping into an empty PML4 slot succeeds", r == 0, NULL);
	snprintf(why, sizeof why, "allocated %d tables", allocs);
	ok("it allocates exactly three intermediate tables", allocs == 3, why);
	ok("translation keeps the page offset",
	   vmm_get_physical(far + 0x123) == 0x1234123, NULL);
	r = vmm_map_page(far + PAGE_SIZE, 0x5000, VMM_FLAG_PRESENT);
	snprintf(why, sizeof why, "allocated %d tables in total", allocs);
	ok("a neighbour in the same table allocates nothing new", r == 0 && allocs == 3, why);
	ok("an unaligned physical address is refused",
	   vmm_map_page(far + 2 * PAGE_SIZE, 0x5001, VMM_FLAG_PRESENT) == -1, NULL);

	/* --- replace and unmap ------------------------------------------------ */
	ninval = 0;
	vmm_map_page(far, 0x7777000, VMM_FLAG_PRESENT);
	ok("remapping an existing page replaces it", vmm_get_physical(far) == 0x7777000, NULL);
	ok("remapping invalidates that page", invalidated_in(far, far + PAGE_SIZE), NULL);
	ninval = 0;
	vmm_unmap_page(far);
	ok("unmap leaves the page untranslated", vmm_get_physical(far) == 0, NULL);
	ok("unmap invalidates that page", invalidated_in(far, far + PAGE_SIZE), NULL);
	ok("unmap does not free the physical frame (the caller owns it)", frees == 0, NULL);

	/* --- out of memory unwinds (REQUIRED) -------------------------------- */
	fresh_machine();
	fail_after = 1;               /* the PDPT succeeds, the PD fails */
	r = vmm_map_page(0x10000000000ULL, 0x9000, VMM_FLAG_PRESENT);
	ok("a failed intermediate allocation returns -1", r == -1, NULL);
	snprintf(why, sizeof why, "%d allocated, %d freed", allocs, frees);
	ok("the table already allocated is freed", allocs == 1 && frees == 1, why);
	ok("nothing is left linked to the freed table",
	   table(boot_root)[(0x10000000000ULL >> 39) & 511] == 0, NULL);

	/* --- huge-page split and permission change (REQUIRED) ---------------- */
	fresh_machine();
	uint64_t target = 0x200000 + 3 * PAGE_SIZE;   /* inside the 2nd 2 MiB page */
	ninval = 0;
	r = vmm_protect(target, VMM_FLAG_PRESENT);    /* read-only */
	uint64_t *pde = pde_for(target);
	ok("protect inside a 2 MiB page succeeds", r == 0, NULL);
	ok("the 2 MiB mapping is split into a page table", !(*pde & PS) && (*pde & P), NULL);
	uint64_t *pt = table(*pde);
	int frames_ok = 1, pat_clear = 1, rw_ok = 1;
	for (int i = 0; i < 512; i++) {
		if ((pt[i] & ADDR) != 0x200000 + (uint64_t)i * PAGE_SIZE) frames_ok = 0;
		if (pt[i] & PS) pat_clear = 0;   /* bit 7 in a PTE is PAT, not "huge" */
		int want_rw = (i != 3);
		if (!!(pt[i] & RW) != want_rw) rw_ok = 0;
	}
	ok("the split maps the same 512 frames in order", frames_ok, NULL);
	ok("no split PTE carries bit 7 (PAT) copied from PS", pat_clear, NULL);
	ok("only the target page lost write; its 511 neighbours kept it", rw_ok, NULL);
	ok("the old 2 MiB translation is invalidated",
	   invalidated_in(0x200000, 0x400000), NULL);
	ok("translation is unchanged by the split",
	   vmm_get_physical(target + 5) == target + 5, NULL);
	ok("protecting an unmapped page returns -1",
	   vmm_protect(0x9000000000ULL, VMM_FLAG_PRESENT) == -1, NULL);

	/* --- a 4 KiB map inside a 2 MiB page splits first -------------------- */
	fresh_machine();
	r = vmm_map_page(0x400000, 0x9000000, VMM_FLAG_PRESENT | VMM_FLAG_WRITABLE);
	ok("mapping 4 KiB inside a 2 MiB page succeeds", r == 0, NULL);
	ok("the page now points elsewhere", vmm_get_physical(0x400000) == 0x9000000, NULL);
	ok("its neighbours keep the identity map",
	   vmm_get_physical(0x401000) == 0x401000 && vmm_get_physical(0x5FF000) == 0x5FF000, NULL);

	/* --- NX (REQUIRED: only when the HAL says it is usable) --------------- */
	fresh_machine();
	vmm_map_page(far, 0x3000, VMM_FLAG_PRESENT | VMM_FLAG_NO_EXECUTE);
	uint64_t *l4 = table(boot_root);
	uint64_t *pte = &table(table(table(l4[1])[0])[0])[0];
	ok("NO_EXECUTE sets bit 63 when NX is supported", (*pte & XD) != 0, NULL);
	vmm_protect(far, VMM_FLAG_PRESENT);
	ok("clearing NO_EXECUTE clears bit 63", (*pte & XD) == 0, NULL);
	fresh_machine();
	nx = 0;
	vmm_map_page(far, 0x3000, VMM_FLAG_PRESENT | VMM_FLAG_NO_EXECUTE);
	l4 = table(boot_root);
	pte = &table(table(table(l4[1])[0])[0])[0];
	ok("without NX support bit 63 is never set (it would be reserved)",
	   (*pte & XD) == 0 && vmm_get_physical(far) == 0x3000, NULL);

	/* --- ranges ---------------------------------------------------------- */
	fresh_machine();
	r = vmm_map_range(far, 0x100000, 3 * PAGE_SIZE + 1, VMM_FLAG_PRESENT);
	ok("map_range covers a partial last page",
	   r == 0 && vmm_get_physical(far + 3 * PAGE_SIZE) == 0x103000, NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails;
}
