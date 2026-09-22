/* What the VMM needs from below it: the frame allocator, physical memory
 * access, the TLB, and the boot page tables. In a kernel these are the PMM and
 * the HAL (arch/hal.md); in the host tests they are supplied by vmm_test.c, so
 * a generated vmm.c is tested against exactly the hooks it will call. */
#ifndef AUTON_TEST_VMM_HOST_H
#define AUTON_TEST_VMM_HOST_H
#include <stdint.h>

void    *pmm_alloc_page(void);          /* physical address of a zeroed frame, or 0 */
void     pmm_free_page(void *phys);
void    *phys_to_virt(uint64_t phys);   /* where the kernel can touch a frame */
void     arch_invlpg(uint64_t virt);    /* invalidate one TLB entry */
uint64_t arch_read_root(void);          /* physical root of the boot page tables (CR3) */
int      arch_nx_supported(void);       /* EFER.NXE usable */

#endif
