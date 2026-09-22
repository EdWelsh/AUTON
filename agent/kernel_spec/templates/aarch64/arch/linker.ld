/* AUTON aarch64 seed kernel linker script.
 *
 * QEMU's `virt` machine loads a 64-bit ELF with -kernel at the base of RAM,
 * which is 0x40000000 (confirmed by the memory node of a real dumped device
 * tree: tests/kernel/dtb_fixtures/virt.dtb). There is no bootloader and no
 * Multiboot header: the firmware jumps to the entry point with the DTB's
 * address in X0.
 */

ENTRY(_start)

SECTIONS
{
	. = 0x40080000;          /* 512 KiB above RAM base, the Linux convention:
	                            leaves room for the DTB the firmware placed low */

	.text : ALIGN(4K)
	{
		KEEP(*(.text.boot))   /* _start must be first: the firmware jumps here */
		*(.text .text.*)
	}

	.rodata : ALIGN(4K)
	{
		*(.rodata .rodata.*)
	}

	.data : ALIGN(4K)
	{
		*(.data .data.*)
	}

	/* The stack lives in .bss so the image on disk stays small; boot.S sets
	 * SP to __stack_top before calling into C. */
	.bss : ALIGN(4K)
	{
		__bss_start = .;
		*(COMMON)
		*(.bss .bss.*)
		. = ALIGN(16);
		__stack_bottom = .;
		. += 64K;
		__stack_top = .;
		__bss_end = .;
	}

	/DISCARD/ : { *(.comment) *(.note .note.*) *(.eh_frame) }
}
