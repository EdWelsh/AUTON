# Boot Subsystem Specification

## Overview

The boot subsystem initializes the hardware and transitions the CPU from real mode to 64-bit long mode, then jumps to the C kernel entry point.

## Boot Sequence

1. **GRUB/Multiboot2 loads kernel** at 0x100000 (1MB)
2. **Assembly entry point** (`_start`):
   - Validate Multiboot2 magic number
   - Save Multiboot2 info pointer
   - Set up minimal GDT for 64-bit mode
   - Enable PAE (Physical Address Extension)
   - Set up initial page tables (identity map first 4MB)
   - Enable long mode (set EFER.LME)
   - Enable paging (set CR0.PG)
   - Far jump to 64-bit code segment
3. **64-bit entry** (`_start64`):
   - Load 64-bit GDT
   - Set up kernel stack (16KB)
   - Clear BSS section
   - Call `kernel_main(multiboot_info_ptr)`

## Files

- `kernel/boot/boot.asm` - Multiboot2 header + entry point
- `kernel/boot/gdt.asm` - GDT setup
- `kernel/boot/idt.asm` - IDT setup
- `kernel/boot/gdt.c` - GDT management functions
- `kernel/boot/idt.c` - IDT management + exception handlers
- `kernel/boot/main.c` - `kernel_main()` entry point

## Multiboot2 Header

```nasm
section .multiboot2
align 8
mb2_header_start:
    dd 0xE85250D6              ; magic
    dd 0                       ; architecture (i386/x86_64)
    dd mb2_header_end - mb2_header_start  ; header length
    dd -(0xE85250D6 + 0 + (mb2_header_end - mb2_header_start))  ; checksum
    ; end tag
    dw 0    ; type
    dw 0    ; flags
    dd 8    ; size
mb2_header_end:
```

## GDT Layout

| Entry | Base | Limit | Access | Description |
|-------|------|-------|--------|-------------|
| 0     | 0    | 0     | 0      | Null descriptor |
| 1     | 0    | 0xFFFFF | 0x9A | Kernel code (64-bit) |
| 2     | 0    | 0xFFFFF | 0x92 | Kernel data |
| 3     | 0    | 0xFFFFF | 0xFA | User code (64-bit) |
| 4     | 0    | 0xFFFFF | 0xF2 | User data |
| 5     | TSS  | sizeof(TSS) | 0x89 | TSS |

## IDT

- Entries 0-31: CPU exceptions (divide error, page fault, GPF, etc.)
- Entry 32: Timer interrupt (PIT/APIC)
- Entry 33: Keyboard interrupt
- Entry 128 (0x80): System call (traditional)
- Entry 129 (0x81): NL syscall trigger

## Acceptance Criteria

- Kernel boots in QEMU: `qemu-system-x86_64 -kernel kernel.bin`
- Multiboot2 magic validated in entry code
- CPU transitions to 64-bit long mode
- `kernel_main()` is called and prints "AUTON Kernel booting..." to serial
- GDT and IDT are properly loaded
- Exception handlers catch and report CPU faults
