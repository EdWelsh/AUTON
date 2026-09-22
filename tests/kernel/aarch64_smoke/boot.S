/* The smallest aarch64 image that can say it booted.
 *
 * NOT the kernel: `kernel/arch/aarch64/` is what the agents write against
 * arch/aarch64.md. This exists to prove the things that must be right before
 * any of that can be debugged — the linker script's base address, that QEMU's
 * virt machine loads the ELF with -kernel, that X0 really holds a device tree,
 * and that the PL011 is where the dumped tree says it is.
 *
 * A generation run that fails is then a failure in the generated code, not in
 * the scaffolding underneath it.
 */
	.section .text.boot, "ax"
	.global _start
_start:
	/* The firmware hands us the DTB in X0. Keep it: main() checks it. */
	mov	x19, x0

	/* Park every core but the first. virt starts one, but a kernel that
	 * assumes so on hardware that starts four is a kernel with four kernels. */
	mrs	x1, mpidr_el1
	and	x1, x1, #3
	cbz	x1, 1f
0:	wfe
	b	0b

1:	/* Zero .bss before C runs: the C compiler is entitled to assume it. */
	adrp	x1, __bss_start
	add	x1, x1, :lo12:__bss_start
	adrp	x2, __bss_end
	add	x2, x2, :lo12:__bss_end
2:	cmp	x1, x2
	b.hs	3f
	str	xzr, [x1], #8
	b	2b

3:	adrp	x1, __stack_top
	add	x1, x1, :lo12:__stack_top
	mov	sp, x1
	mov	x0, x19
	bl	smoke_main
4:	wfe
	b	4b
