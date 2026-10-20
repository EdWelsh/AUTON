/* x86-64 hooks for the memory managers (operator-authored R1 fallback tree).
 * The seed runs identity-mapped, so a physical address is a pointer. */
#include <stdint.h>
#include "mm.h"

void *phys_to_virt(uint64_t phys) { return (void *)(uintptr_t)phys; }

void arch_invlpg(uint64_t virt)
{
	__asm__ volatile("invlpg (%0)" :: "r"(virt) : "memory");
}

uint64_t arch_read_root(void)
{
	uint64_t cr3;
	__asm__ volatile("mov %%cr3, %0" : "=r"(cr3));
	return cr3;
}

void arch_write_root(uint64_t root)
{
	__asm__ volatile("mov %0, %%cr3" :: "r"(root) : "memory");
}

/* A no-execute bit is valid only when the CPU has it and EFER.NXE is on. */
int arch_nx_supported(void)
{
	uint32_t eax = 0x80000000u, ebx, ecx, edx;
	__asm__ volatile("cpuid" : "+a"(eax), "=b"(ebx), "=c"(ecx), "=d"(edx));
	if (eax < 0x80000001u)
		return 0;
	eax = 0x80000001u;
	__asm__ volatile("cpuid" : "+a"(eax), "=b"(ebx), "=c"(ecx), "=d"(edx));
	if (!(edx & (1u << 20)))
		return 0;
	uint32_t lo, hi;
	__asm__ volatile("rdmsr" : "=a"(lo), "=d"(hi) : "c"(0xC0000080u));
	return (lo >> 11) & 1;
}
