/* Interrupt entry stubs. Each saves the caller-saved registers, aligns the
 * stack for the System V ABI, calls a C handler, restores, and iretq. */

.section .text

/* Common prologue/epilogue via macros. */
.macro IRQ_ENTER
	push	%rax
	push	%rcx
	push	%rdx
	push	%rsi
	push	%rdi
	push	%r8
	push	%r9
	push	%r10
	push	%r11
	push	%rbp
	mov	%rsp, %rbp
	and	$-16, %rsp          /* 16-byte align for the call */
.endm

.macro IRQ_LEAVE
	mov	%rbp, %rsp
	pop	%rbp
	pop	%r11
	pop	%r10
	pop	%r9
	pop	%r8
	pop	%rdi
	pop	%rsi
	pop	%rdx
	pop	%rcx
	pop	%rax
	iretq
.endm

/* Timer (IRQ0) — wakes hlt and EOIs. */
.global irq0_stub
irq0_stub:
	IRQ_ENTER
	call	irq_timer
	IRQ_LEAVE

/* Any other hardware IRQ — EOI only. */
.global irq_default
irq_default:
	IRQ_ENTER
	call	irq_eoi_only
	IRQ_LEAVE

/* CPU exceptions (vectors 0-31) — report and halt; never returns. */
.global isr_default
isr_default:
	cli
	call	exception_handler
1:	hlt
	jmp	1b

.section .note.GNU-stack, "", @progbits
