/* The kernel environment an allocator links against, for the host suite.
 *
 * mm.md REQUIRES the PMM to report a [MM] line (kprintf) and to reserve the
 * kernel image from the linker symbols __kernel_start / __kernel_end. The
 * suite supplied neither, so every allocator that followed the spec failed to
 * link and scored "generated wrong" (w18 R1, stop rule 5: the tftp_stub class,
 * a gate requiring what lies outside the scope it verifies). The reference
 * passed only because it skipped both requirements.
 *
 * Everything here is weak: a tree that ships its own definition (its libk in
 * the sources, say) wins. None of it is under test — the allocator is.
 */
#include <stdarg.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define WEAK __attribute__((weak))

WEAK void kprintf(const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);
	vprintf(fmt, ap);
	va_end(ap);
}

WEAK void *kmemset(void *dst, int c, size_t n) { return memset(dst, c, n); }
WEAK void *kmemcpy(void *dst, const void *src, size_t n) { return memcpy(dst, src, n); }
WEAK size_t kstrlen(const char *s) { return strlen(s); }
WEAK int kstrcmp(const char *a, const char *b) { return strcmp(a, b); }

/* The slab sits on the PMM; an allocator that initialises it links these. */
/* The boot layer's accessors, which kernel-base-v5's boot.h declares and a PMM may call to learn
 * where the boot modules are (w24: R1's allocator did, and failed to link). A host has no
 * modules; the suite reserves its own with pmm_mark_used. Typed loosely on purpose: this file
 * includes no kernel header, so the stub cannot disagree with the tree's declaration. */
static unsigned char host_boot_info[4096];
WEAK const void *boot_get_info(void) { return host_boot_info; }
WEAK int boot_module_reserved_range(const void *info, uint32_t i, uint64_t *start, uint64_t *end)
{ (void)info; (void)i; (void)start; (void)end; return -1; }

WEAK void slab_init(void) {}
WEAK void *kmalloc(size_t n) { return malloc(n); }
WEAK void *kzalloc(size_t n) { return calloc(1, n); }
WEAK void kfree(void *p) { free(p); }

/* The kernel image where mm_test.c places it (KERNEL_BASE, KERNEL_LEN):
 * absolute symbols, so &__kernel_start is that physical address, exactly as
 * the linker script makes it on the target. The suite marks the same range
 * itself, so an allocator that reserves it again is consistent. */
#if defined(__APPLE__)
__asm__(".globl ___kernel_start\n.set ___kernel_start, 0x100000\n"
        ".globl ___kernel_end\n.set ___kernel_end, 0x300000\n");
#else
__asm__(".globl __kernel_start\n.set __kernel_start, 0x100000\n"
        ".globl __kernel_end\n.set __kernel_end, 0x300000\n");
#endif

/* mm.md: the PMM places its bitmap in RAM and reaches it through the
 * phys_to_virt hook (the VMM suite supplies the same hook). Here "RAM" is host
 * memory the size of mm_test.c's map, so a self-placed bitmap lands somewhere
 * real. A tree that defines phys_to_virt inline in a header never reaches
 * this, and cannot be tested by substitution — that is its own defect. */
#define HOST_RAM_BYTES (64u * 1024 * 1024)     /* mm_test.c's MEM_BYTES */
WEAK void *phys_to_virt(uint64_t phys)
{
	static uint8_t *ram;
	if (!ram)
		ram = calloc(1, HOST_RAM_BYTES);
	if (!ram || phys >= HOST_RAM_BYTES) {
		fprintf(stderr, "phys_to_virt(0x%llx): outside the test's RAM\n",
			(unsigned long long)phys);
		abort();
	}
	return ram + phys;
}

/* The CPU HAL's halt (architecture.md: "CPU idle via arch_halt()"): what a
 * portable PMM calls after a panic message. In a test process, a panic ends it. */
WEAK void arch_halt(void) { abort(); }
