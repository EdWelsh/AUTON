/* AUTON x86_64 seed kernel linker script.
 * Loaded by QEMU -kernel (Multiboot v1) at physical 1 MiB. The kernel runs
 * identity-mapped in low memory (small code model), so no higher-half offset. */

ENTRY(_start)

SECTIONS
{
	. = 1M;

	/* Multiboot header must be early in the image (first 8 KiB). */
	.boot : ALIGN(4)
	{
		KEEP(*(.multiboot))
	}

	.text : ALIGN(4K)
	{
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

	.bss : ALIGN(4K)
	{
		*(COMMON)
		*(.bss .bss.*)
	}

	/DISCARD/ : { *(.comment) *(.note .note.*) *(.eh_frame) }
}
