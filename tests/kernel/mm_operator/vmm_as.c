/* Address-space management (operator-authored R1 fallback tree). A new space shares the boot
 * identity map: it starts as a copy of the current root's top level. */
#include <stdint.h>
#include "mm.h"
#include "kernel.h"

uint64_t vmm_create_address_space(void)
{
	void *phys = pmm_alloc_page();
	if (!phys)
		return 0;
	kmemcpy(phys_to_virt((uint64_t)(uintptr_t)phys),
	        phys_to_virt(arch_read_root() & 0x000FFFFFFFFFF000ULL), PAGE_SIZE);
	return (uint64_t)(uintptr_t)phys;
}

void vmm_switch_address_space(uint64_t root_table_phys)
{
	arch_write_root(root_table_phys);
}

/* Frees the top-level table only: the lower levels are shared with the boot map. */
void vmm_destroy_address_space(uint64_t root_table_phys)
{
	if (root_table_phys)
		pmm_free_page((void *)(uintptr_t)root_table_phys);
}
