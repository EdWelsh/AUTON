/* AUTON x86_64 boot trampoline.
 *
 * QEMU -kernel loads this ELF64 and enters `_start` in 32-bit protected mode
 * with EAX = multiboot magic (0x2BADB002) and EBX = pointer to the multiboot
 * info struct. We identity-map the low 4 GiB with 2 MiB pages, switch to 64-bit
 * long mode, then call the portable C entry point `kernel_main(mb_info, magic)`.
 *
 * 4 GiB (not 1) so device MMIO below 4 GiB — notably the e1000 NIC BAR near
 * ~0xFEBCxxxx — is addressable without faulting.
 */

.section .text

/* ---- 32-bit entry --------------------------------------------------------- */
.code32
.global _start
.extern kernel_main

_start:
	cli
	movl	$stack_top, %esp

	/* Stash the multiboot magic + info pointer; registers get clobbered. */
	movl	%eax, mb_magic
	movl	%ebx, mb_info

	call	setup_page_tables
	call	enable_long_mode

	lgdt	gdt64_pointer
	ljmp	$0x08, $long_mode_start

/* Identity-map the first 4 GiB using 2 MiB pages (4 PDs of 512 entries). */
setup_page_tables:
	/* PML4[0] -> PDPT */
	movl	$pdpt, %eax
	orl	$0x3, %eax              /* present | writable */
	movl	%eax, pml4

	/* PDPT[0..3] -> pd + 0/4096/8192/12288 (one PD = 1 GiB). */
	movl	$pdpt, %edi
	movl	$pd, %eax
	orl	$0x3, %eax
	movl	$0, %ecx
.fill_pdpt:
	movl	%eax, (%edi)
	movl	$0, 4(%edi)
	addl	$4096, %eax            /* next PD (4 KiB further) */
	addl	$8, %edi
	incl	%ecx
	cmpl	$4, %ecx
	jne	.fill_pdpt

	/* PD[i] = (i << 21) | present | writable | page-size(2MiB), i in 0..2047.
	 * i<<21 for i<=2047 is 0xFFE00000 — still 32-bit, so the high dword is 0. */
	movl	$pd, %edi
	xorl	%ecx, %ecx
.fill_pd:
	movl	%ecx, %eax
	shll	$21, %eax               /* i * 2 MiB */
	orl	$0x83, %eax
	movl	%eax, (%edi)
	movl	$0, 4(%edi)             /* high dword: 0 across the first 4 GiB */
	addl	$8, %edi
	incl	%ecx
	cmpl	$2048, %ecx
	jne	.fill_pd
	ret

enable_long_mode:
	/* CR3 = PML4 */
	movl	$pml4, %eax
	movl	%eax, %cr3

	/* CR4.PAE = 1 */
	movl	%cr4, %eax
	orl	$0x20, %eax
	movl	%eax, %cr4

	/* EFER.LME = 1 */
	movl	$0xC0000080, %ecx
	rdmsr
	orl	$0x100, %eax
	wrmsr

	/* CR0: enable paging (PG) and protection (PE) */
	movl	%cr0, %eax
	orl	$0x80000001, %eax
	movl	%eax, %cr0
	ret

/* ---- 64-bit entry --------------------------------------------------------- */
.code64
long_mode_start:
	xorw	%ax, %ax
	movw	%ax, %ds
	movw	%ax, %es
	movw	%ax, %ss
	movw	%ax, %fs
	movw	%ax, %gs

	/* kernel_main(uint32_t mb_info_ptr, uint32_t magic) -> rdi, rsi */
	movl	mb_info(%rip), %edi
	movl	mb_magic(%rip), %esi
	call	kernel_main

.hang:
	cli
	hlt
	jmp	.hang

/* ---- GDT (64-bit) --------------------------------------------------------- */
.section .rodata
.align 8
gdt64:
	.quad	0x0000000000000000      /* null */
	.quad	0x00AF9A000000FFFF      /* 0x08: 64-bit code (present, exec, L=1) */
	.quad	0x00AF92000000FFFF      /* 0x10: data (present, writable) */
gdt64_pointer:
	.word	gdt64_pointer - gdt64 - 1
	.quad	gdt64

/* ---- scratch storage ------------------------------------------------------ */
.section .data
mb_magic:	.long 0
mb_info:	.long 0

.section .bss
.align 4096
pml4:	.skip 4096
pdpt:	.skip 4096
pd:	.skip 16384                     /* 4 PDs -> 4 GiB identity map */
.align 16
stack_bottom:
	.skip 16384
stack_top:

/* Mark the stack non-executable (silences the linker exec-stack warning). */
.section .note.GNU-stack, "", @progbits
