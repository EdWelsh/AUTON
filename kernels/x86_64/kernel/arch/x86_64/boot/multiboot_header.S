/* Multiboot2 header. GRUB loads this ELF64 kernel and enters `_start` in
 * 32-bit protected mode (per the Multiboot2 spec), where boot.S sets up long
 * mode. We boot via a GRUB rescue ISO + `qemu -cdrom`, because QEMU's
 * `-kernel` multiboot loader is v1-only and rejects 64-bit ELF images. */

.set MB2_MAGIC,  0xE85250D6
.set MB2_ARCH,   0                      /* 0 = i386 protected mode */

.section .multiboot, "a"
.align 8
mb2_header_start:
	.long MB2_MAGIC
	.long MB2_ARCH
	.long mb2_header_end - mb2_header_start
	.long -(MB2_MAGIC + MB2_ARCH + (mb2_header_end - mb2_header_start))

	/* end tag: type=0, flags=0, size=8 */
	.align 8
	.short 0
	.short 0
	.long 8
mb2_header_end:

.section .note.GNU-stack, "", @progbits
