# AArch64 (ARM64) Architecture Specification

## Overview

This document is the authoritative reference for agents implementing the AArch64 HAL for the AUTON kernel. It covers every architecture-specific detail needed to produce a working `kernel/arch/aarch64/` implementation: boot protocol, toolchain, registers, page tables, memory layout, I/O, interrupt controller, timer, UART, firmware parsing, context switching, and initial MMU setup.

AArch64 differs fundamentally from x86_64. There is no BIOS, no port I/O, no GDT/IDT, no PIC/PIT, and no VGA text mode. Privilege is managed through Exception Levels (EL0-EL3), all devices are accessed via MMIO, interrupts are routed through a GIC, and hardware description comes from a Device Tree Blob rather than ACPI.

---

## Boot Protocol

### Firmware Handoff

On the QEMU `virt` machine, firmware (or QEMU's built-in bootloader with `-kernel`) passes control to the kernel image at its load address with:

- **X0** = physical address of the Device Tree Blob (DTB)
- **X1, X2, X3** = reserved (zero)
- CPU may be in **EL2** (hypervisor) or **EL1** (kernel) depending on firmware

The kernel entry point `_start` must handle both cases.

### Exception Levels

AArch64 uses Exception Levels instead of x86 rings:

| Level | Name | Purpose |
|-------|------|---------|
| EL0 | User | Unprivileged application code |
| EL1 | Kernel | OS kernel, full hardware access |
| EL2 | Hypervisor | Virtualization host |
| EL3 | Secure Monitor | TrustZone secure world |

AUTON runs at **EL1**. If entered at EL2, the boot code must drop to EL1.

### EL2 to EL1 Transition

To drop from EL2 to EL1:

1. Configure `HCR_EL2` to route exceptions to EL1 (set `HCR_EL2.RW = 1` for AArch64 at EL1)
2. Set `SPSR_EL2` to `0x3C5` (EL1h mode, all exceptions masked: DAIF)
3. Load the EL1 entry address into `ELR_EL2`
4. Execute `eret` to return to EL1 at the address in `ELR_EL2`

### Exception Vector Table (VBAR_EL1)

The AArch64 exception vector table is 2048 bytes, aligned to 2048 bytes. It contains 4 groups of 4 vectors, each vector entry is 128 bytes (32 instructions):

| Offset | Source | Type |
|--------|--------|------|
| 0x000 | Current EL with SP_EL0 | Synchronous |
| 0x080 | Current EL with SP_EL0 | IRQ |
| 0x100 | Current EL with SP_EL0 | FIQ |
| 0x180 | Current EL with SP_EL0 | SError |
| 0x200 | Current EL with SP_ELx | Synchronous |
| 0x280 | Current EL with SP_ELx | IRQ |
| 0x300 | Current EL with SP_ELx | FIQ |
| 0x380 | Current EL with SP_ELx | SError |
| 0x400 | Lower EL (AArch64) | Synchronous |
| 0x480 | Lower EL (AArch64) | IRQ |
| 0x500 | Lower EL (AArch64) | FIQ |
| 0x580 | Lower EL (AArch64) | SError |
| 0x600 | Lower EL (AArch32) | Synchronous |
| 0x680 | Lower EL (AArch32) | IRQ |
| 0x700 | Lower EL (AArch32) | FIQ |
| 0x780 | Lower EL (AArch32) | SError |

The kernel uses the "Current EL with SP_ELx" group (offsets 0x200-0x380) for kernel exceptions, and the "Lower EL (AArch64)" group (offsets 0x400-0x580) for exceptions from user space.

Set the vector base address: `msr VBAR_EL1, x0`.

### No GDT/IDT Equivalent

AArch64 has no Global Descriptor Table, Interrupt Descriptor Table, or Task State Segment. Privilege is entirely controlled by Exception Levels. Interrupt dispatch is handled by the exception vector table (VBAR_EL1) plus the GIC.

### Assembly Syntax

All AArch64 assembly uses **GNU AS** syntax (`.S` files, preprocessed by GCC). There is no NASM equivalent for AArch64.

### Skeleton boot.S

```asm
/* kernel/arch/aarch64/boot/boot.S */

.section ".text.boot"
.globl _start

_start:
    /* X0 = DTB physical address (preserve it) */
    mov     x19, x0

    /* Determine current Exception Level */
    mrs     x1, CurrentEL
    and     x1, x1, #0x0C          /* bits [3:2] encode EL */
    cmp     x1, #0x08              /* EL2 = 0b1000 */
    b.eq    .Lel2_to_el1
    cmp     x1, #0x04              /* EL1 = 0b0100 */
    b.eq    .Lat_el1
    /* EL3 or EL0: should not happen; spin forever */
    b       .Lhang

.Lel2_to_el1:
    /* Configure HCR_EL2: set RW bit (bit 31) for AArch64 at EL1 */
    mov     x0, #(1 << 31)
    msr     hcr_el2, x0

    /* Set SPSR_EL2: return to EL1h with DAIF masked */
    mov     x0, #0x3C5
    msr     spsr_el2, x0

    /* Set ELR_EL2: address to return to in EL1 */
    adr     x0, .Lat_el1
    msr     elr_el2, x0

    /* Drop to EL1 */
    eret

.Lat_el1:
    /* ---- Now running at EL1 ---- */

    /* Set up exception vectors */
    ldr     x0, =exception_vectors
    msr     vbar_el1, x0

    /* Disable MMU and caches initially in SCTLR_EL1 */
    mrs     x0, sctlr_el1
    bic     x0, x0, #(1 << 0)      /* M: MMU disable */
    bic     x0, x0, #(1 << 2)      /* C: data cache disable */
    bic     x0, x0, #(1 << 12)     /* I: instruction cache disable */
    msr     sctlr_el1, x0
    isb

    /* Clear BSS */
    ldr     x0, =__bss_start
    ldr     x1, =__bss_end
.Lbss_loop:
    cmp     x0, x1
    b.ge    .Lbss_done
    str     xzr, [x0], #8
    b       .Lbss_loop
.Lbss_done:

    /* Set up the kernel stack (grows downward) */
    ldr     x0, =__stack_top
    mov     sp, x0

    /* Restore DTB pointer into X0 (first argument to kernel_main) */
    mov     x0, x19

    /* Branch to C kernel entry point */
    bl      kernel_main

    /* If kernel_main returns, hang */
.Lhang:
    wfe
    b       .Lhang
```

### Linker Script Requirements

The linker script (`linker.ld`) must define:

- `__bss_start` and `__bss_end` symbols for BSS clearing
- `__stack_top` pointing to the top of the initial kernel stack (at least 16KB)
- `.text.boot` section placed first at the kernel load address
- All sections page-aligned (4KB)

```ld
/* kernel/arch/aarch64/linker.ld */
ENTRY(_start)

KERNEL_PHYS = 0x40080000;

SECTIONS {
    . = KERNEL_PHYS;

    .text.boot : {
        *(.text.boot)
    }

    .text : ALIGN(4096) {
        *(.text .text.*)
    }

    .rodata : ALIGN(4096) {
        *(.rodata .rodata.*)
    }

    .data : ALIGN(4096) {
        *(.data .data.*)
    }

    .bss : ALIGN(4096) {
        __bss_start = .;
        *(.bss .bss.*)
        *(COMMON)
        __bss_end = .;
    }

    . = ALIGN(4096);
    . = . + 16384;
    __stack_top = .;

    _kernel_start = KERNEL_PHYS;
    _kernel_end = .;
}
```

---

## Toolchain

| Tool | Binary | Notes |
|------|--------|-------|
| C Compiler | `aarch64-elf-gcc` or `aarch64-none-elf-gcc` | Bare-metal cross compiler |
| Assembler | `aarch64-elf-as` | GNU AS, ARM syntax |
| Linker | `aarch64-elf-ld` | |
| Objcopy | `aarch64-elf-objcopy` | For producing flat binary |

### Compiler Flags

```makefile
CC      = aarch64-elf-gcc
AS      = aarch64-elf-as
LD      = aarch64-elf-ld
OBJCOPY = aarch64-elf-objcopy

CFLAGS  = -ffreestanding -mgeneral-regs-only -fno-exceptions -Wall -Wextra -std=c11
ASFLAGS =
LDFLAGS = -T linker.ld -nostdlib
```

Flag rationale:
- `-ffreestanding`: no hosted C library assumptions
- `-mgeneral-regs-only`: forbids SIMD/FP register use in kernel code (avoids saving NEON/FP state on every exception)
- `-fno-exceptions`: no C++ exception unwinding
- `-Wall -Wextra`: strict warnings
- `-std=c11`: C11 standard
- `-nostdlib`: no standard library linking

### Assembly Files

All assembly files use the `.S` extension (uppercase S) so GCC preprocesses them, enabling `#include`, `#define`, and conditional compilation. There is no NASM for AArch64.

### Build Targets

```makefile
kernel.bin: kernel.elf
	$(OBJCOPY) -O binary kernel.elf kernel.bin

kernel.elf: boot.o vectors.o context_switch.o kernel.o mm.o ...
	$(LD) $(LDFLAGS) -o $@ $^

boot.o: boot.S
	$(CC) $(CFLAGS) -c $< -o $@
```

---

## Register Set

### General-Purpose Registers

| Register | Width | Purpose |
|----------|-------|---------|
| X0-X7 | 64-bit | Function arguments and return values |
| X8 | 64-bit | Indirect result location register |
| X9-X15 | 64-bit | Caller-saved temporaries |
| X16 (IP0) | 64-bit | Intra-procedure scratch (linker veneer) |
| X17 (IP1) | 64-bit | Intra-procedure scratch (linker veneer) |
| X18 | 64-bit | Platform register (reserved, do not use) |
| X19-X28 | 64-bit | Callee-saved registers |
| X29 (FP) | 64-bit | Frame pointer |
| X30 (LR) | 64-bit | Link register (return address) |
| SP | 64-bit | Stack pointer (selected by SPSel) |
| XZR | 64-bit | Zero register (reads as 0, writes discarded) |
| WZR | 32-bit | Zero register (32-bit alias) |
| W0-W30 | 32-bit | Lower 32 bits of X0-X30 |

The program counter (PC) is not directly accessible as a general register. Use `adr` or `adrp` instructions to get the current address.

### Key System Registers

| Register | Purpose |
|----------|---------|
| `SCTLR_EL1` | System Control: MMU enable (bit 0), cache enable (bit 2), instruction cache (bit 12) |
| `TTBR0_EL1` | Translation Table Base Register 0: user-space page table base |
| `TTBR1_EL1` | Translation Table Base Register 1: kernel-space page table base |
| `TCR_EL1` | Translation Control Register: granule size, address space size (T0SZ, T1SZ) |
| `MAIR_EL1` | Memory Attribute Indirection Register: memory type definitions |
| `VBAR_EL1` | Vector Base Address Register: exception vector table base |
| `ESR_EL1` | Exception Syndrome Register: exception class, ISS (Instruction Specific Syndrome) |
| `FAR_EL1` | Fault Address Register: faulting virtual address |
| `ELR_EL1` | Exception Link Register: return address after exception |
| `SPSR_EL1` | Saved Program Status Register: saved PSTATE on exception entry |
| `CurrentEL` | Current Exception Level (read-only, bits [3:2]) |
| `DAIF` | Interrupt mask flags: D(ebug), A(SError), I(RQ), F(IQ) |
| `SP_EL0` | EL0 stack pointer (accessible from EL1) |
| `SP_EL1` | EL1 stack pointer |
| `HCR_EL2` | Hypervisor Configuration Register |
| `CNTP_TVAL_EL0` | Physical timer value (countdown) |
| `CNTP_CTL_EL0` | Physical timer control |
| `CNTFRQ_EL0` | Counter frequency (Hz) |

### Calling Convention (AAPCS64)

- **Arguments**: X0-X7 (up to 8 integer/pointer arguments)
- **Return value**: X0 (X1 for 128-bit returns)
- **Indirect result**: X8 (pointer to memory for large struct returns)
- **Caller-saved** (volatile): X0-X15, X16-X17 (scratch), X18 (platform)
- **Callee-saved** (non-volatile): X19-X28, FP (X29), LR (X30)
- **Stack alignment**: 16-byte alignment required at all public function call boundaries
- **Frame pointer**: X29 must point to the previous frame record (FP, LR pair) if used

---

## Page Table Format

### Translation Granule and Levels

AArch64 supports three granule sizes. AUTON uses the **4KB granule** for simplicity and compatibility:

| Granule | Levels | Bits per Level | Entries per Table |
|---------|--------|----------------|-------------------|
| 4KB | 4 (L0-L3) | 9 | 512 |
| 16KB | 4 | 11 | 2048 |
| 64KB | 3 | 13 | 8192 |

With 4KB granule and 48-bit virtual addresses:

```
Virtual Address (48-bit):
[47:39] L0 index (9 bits) -> L0 table (512 entries)
[38:30] L1 index (9 bits) -> L1 table (512 entries)
[29:21] L2 index (9 bits) -> L2 table (512 entries)
[20:12] L3 index (9 bits) -> L3 table (512 entries)
[11: 0] Page offset (12 bits)
```

### Page and Block Sizes

| Level | Descriptor Type | Mapped Size |
|-------|-----------------|-------------|
| L0 | Table only | (points to L1) |
| L1 | Block | 1 GB |
| L1 | Table | (points to L2) |
| L2 | Block | 2 MB |
| L2 | Table | (points to L3) |
| L3 | Page | 4 KB |

### Descriptor Format (8 bytes per entry)

```
Bits    Field           Values / Meaning
------  --------------  -----------------------------------------------
[0]     Valid           0 = invalid (fault), 1 = valid
[1]     Type            At L0/L1/L2: 0 = Block, 1 = Table
                        At L3: must be 1 (Page descriptor)
[4:2]   AttrIndx        Index into MAIR_EL1 (memory attributes)
[5]     NS              Non-Secure (ignored if not using TrustZone)
[7:6]   AP              Access Permissions:
                          00 = EL1 RW, EL0 none
                          01 = EL1 RW, EL0 RW
                          10 = EL1 RO, EL0 none
                          11 = EL1 RO, EL0 RO
[9:8]   SH              Shareability:
                          00 = Non-shareable
                          10 = Outer Shareable
                          11 = Inner Shareable
[10]    AF              Access Flag (must set to 1, or hardware fault on first access)
[11]    nG              not Global (0 = global, 1 = process-specific ASID match)
[47:12] Address         Physical address of next-level table, block, or page
                        (aligned to granule size)
[53]    PXN             Privileged Execute-Never
[54]    UXN/XN          Unprivileged Execute-Never (or Execute-Never for blocks)
```

### Descriptor Type Summary

| Bits [1:0] | Level | Meaning |
|------------|-------|---------|
| `00` | Any | Invalid (translation fault) |
| `01` | L1, L2 | Block descriptor (maps 1GB or 2MB) |
| `11` | L0, L1, L2 | Table descriptor (points to next-level table) |
| `11` | L3 | Page descriptor (maps 4KB) |

Note: At L3, bit [1] = 1 indicates a valid page (combined with bit [0] = 1). A L3 entry with bits [1:0] = `01` is **reserved/invalid**.

### C Definitions

```c
/* Page table constants */
#define PAGE_SIZE           4096
#define PAGE_SHIFT          12
#define PT_ENTRIES          512
#define PT_LEVELS           4

/* Descriptor bits */
#define PTE_VALID           (1ULL << 0)
#define PTE_TABLE           (1ULL << 1)  /* L0/L1/L2: table descriptor */
#define PTE_PAGE            (1ULL << 1)  /* L3: page descriptor */
#define PTE_BLOCK           (0ULL << 1)  /* L1/L2: block descriptor (bit 1 = 0) */

#define PTE_ATTR_IDX(n)     (((uint64_t)(n)) << 2)  /* AttrIndx [4:2] */
#define PTE_NS              (1ULL << 5)

#define PTE_AP_RW_EL1       (0ULL << 6)  /* EL1 RW, EL0 none */
#define PTE_AP_RW_ALL       (1ULL << 6)  /* EL1 RW, EL0 RW */
#define PTE_AP_RO_EL1       (2ULL << 6)  /* EL1 RO, EL0 none */
#define PTE_AP_RO_ALL       (3ULL << 6)  /* EL1 RO, EL0 RO */

#define PTE_SH_NONE         (0ULL << 8)
#define PTE_SH_OUTER        (2ULL << 8)
#define PTE_SH_INNER        (3ULL << 8)

#define PTE_AF              (1ULL << 10)  /* Access Flag */
#define PTE_NG              (1ULL << 11)  /* not Global */
#define PTE_PXN             (1ULL << 53)  /* Privileged Execute-Never */
#define PTE_UXN             (1ULL << 54)  /* Unprivileged Execute-Never */

/* Address mask for extracting physical address from descriptor */
#define PTE_ADDR_MASK       0x0000FFFFFFFFF000ULL

/* Commonly used combined flags */
#define PTE_KERNEL_CODE     (PTE_VALID | PTE_AF | PTE_SH_INNER | PTE_ATTR_IDX(0) | PTE_UXN)
#define PTE_KERNEL_DATA     (PTE_VALID | PTE_AF | PTE_SH_INNER | PTE_ATTR_IDX(0) | PTE_UXN | PTE_PXN)
#define PTE_KERNEL_RODATA   (PTE_VALID | PTE_AF | PTE_SH_INNER | PTE_ATTR_IDX(0) | PTE_AP_RO_EL1 | PTE_UXN | PTE_PXN)
#define PTE_DEVICE_MMIO     (PTE_VALID | PTE_AF | PTE_SH_NONE  | PTE_ATTR_IDX(1) | PTE_UXN | PTE_PXN)
#define PTE_USER_CODE       (PTE_VALID | PTE_AF | PTE_SH_INNER | PTE_ATTR_IDX(0) | PTE_AP_RO_ALL | PTE_PXN | PTE_NG)
#define PTE_USER_DATA       (PTE_VALID | PTE_AF | PTE_SH_INNER | PTE_ATTR_IDX(0) | PTE_AP_RW_ALL | PTE_UXN | PTE_PXN | PTE_NG)
```

### Two Translation Table Base Registers

AArch64 splits the virtual address space with two page table roots:

- **TTBR0_EL1**: translates addresses starting with `0x0000...` (user space). Upper bits are zero.
- **TTBR1_EL1**: translates addresses starting with `0xFFFF...` (kernel space). Upper bits are one.

The split point is configured by `TCR_EL1.T0SZ` and `TCR_EL1.T1SZ`:
- `T0SZ = 16` means TTBR0 covers 48 bits of address space: `0x0000_0000_0000_0000` to `0x0000_FFFF_FFFF_FFFF`
- `T1SZ = 16` means TTBR1 covers 48 bits of address space: `0xFFFF_0000_0000_0000` to `0xFFFF_FFFF_FFFF_FFFF`

### TCR_EL1 Configuration

```c
/*
 * TCR_EL1 for 4KB granule, 48-bit VA for both TTBR0 and TTBR1:
 *
 * T0SZ  = 16  (bits [5:0])    -> 48-bit TTBR0 range
 * T1SZ  = 16  (bits [21:16])  -> 48-bit TTBR1 range
 * TG0   = 0b00 (bits [15:14]) -> 4KB granule for TTBR0
 * TG1   = 0b10 (bits [31:30]) -> 4KB granule for TTBR1
 * SH0   = 0b11 (bits [13:12]) -> Inner Shareable for TTBR0
 * SH1   = 0b11 (bits [29:28]) -> Inner Shareable for TTBR1
 * ORGN0 = 0b01 (bits [11:10]) -> Write-Back Write-Allocate cacheable for TTBR0
 * IRGN0 = 0b01 (bits [9:8])   -> Write-Back Write-Allocate cacheable for TTBR0
 * ORGN1 = 0b01 (bits [27:26]) -> Write-Back Write-Allocate cacheable for TTBR1
 * IRGN1 = 0b01 (bits [25:24]) -> Write-Back Write-Allocate cacheable for TTBR1
 * IPS   = 0b101 (bits [34:32])-> 48-bit physical address space (256TB)
 */
#define TCR_T0SZ        (16ULL << 0)
#define TCR_T1SZ        (16ULL << 16)
#define TCR_TG0_4KB     (0ULL << 14)
#define TCR_TG1_4KB     (2ULL << 30)
#define TCR_SH0_INNER   (3ULL << 12)
#define TCR_SH1_INNER   (3ULL << 28)
#define TCR_ORGN0_WBWA  (1ULL << 10)
#define TCR_IRGN0_WBWA  (1ULL << 8)
#define TCR_ORGN1_WBWA  (1ULL << 26)
#define TCR_IRGN1_WBWA  (1ULL << 24)
#define TCR_IPS_48BIT   (5ULL << 32)

#define TCR_VALUE       (TCR_T0SZ | TCR_T1SZ | TCR_TG0_4KB | TCR_TG1_4KB | \
                         TCR_SH0_INNER | TCR_SH1_INNER | \
                         TCR_ORGN0_WBWA | TCR_IRGN0_WBWA | \
                         TCR_ORGN1_WBWA | TCR_IRGN1_WBWA | \
                         TCR_IPS_48BIT)
```

### MAIR_EL1 Configuration

```c
/*
 * MAIR_EL1: Memory Attribute Indirection Register
 *
 * Attr0 = 0xFF -> Normal memory, Write-Back cacheable (inner + outer)
 * Attr1 = 0x00 -> Device-nGnRnE (strictly ordered device memory)
 * Attr2 = 0x44 -> Normal memory, Non-Cacheable (inner + outer)
 */
#define MAIR_ATTR0_NORMAL_WB   (0xFFULL << 0)   /* AttrIndx = 0 */
#define MAIR_ATTR1_DEVICE      (0x00ULL << 8)    /* AttrIndx = 1 */
#define MAIR_ATTR2_NORMAL_NC   (0x44ULL << 16)   /* AttrIndx = 2 */

#define MAIR_VALUE  (MAIR_ATTR0_NORMAL_WB | MAIR_ATTR1_DEVICE | MAIR_ATTR2_NORMAL_NC)
```

### TLB Maintenance

AArch64 uses `TLBI` instructions for TLB invalidation:

```asm
/* Invalidate all TLB entries at EL1 */
tlbi    vmalle1
dsb     sy
isb

/* Invalidate TLB entry for a specific virtual address */
/* X0 = virtual address >> 12 (page-aligned, shifted right by 12) */
lsr     x0, x0, #12
tlbi    vae1, x0
dsb     sy
isb
```

In C (using inline assembly):

```c
static inline void arch_flush_tlb_all(void)
{
    asm volatile("tlbi vmalle1\n\t"
                 "dsb sy\n\t"
                 "isb" ::: "memory");
}

static inline void arch_flush_tlb(uint64_t virt)
{
    uint64_t page = virt >> 12;
    asm volatile("tlbi vae1, %0\n\t"
                 "dsb sy\n\t"
                 "isb" :: "r"(page) : "memory");
}
```

---

## Memory Layout

### Virtual Address Space

```
User space (TTBR0_EL1):
0x0000_0000_0000_0000 - 0x0000_FFFF_FFFF_FFFF   (256 TB)

--- unmapped gap (addresses with mixed upper bits cause translation fault) ---

Kernel space (TTBR1_EL1):
0xFFFF_0000_0000_0000 - 0xFFFF_FFFF_FFFF_FFFF   (256 TB)
```

### Kernel Virtual Layout

```
0xFFFF_0000_0000_0000  KERNEL_VBASE (start of kernel virtual space)
0xFFFF_0000_0008_0000  Kernel code (.text) mapped here (offset from physical load)
0xFFFF_0000_4000_0000  Kernel heap start (1 GB offset)
0xFFFF_0000_8000_0000  SLM runtime memory pool (2 GB offset)
0xFFFF_FFFF_0000_0000  MMIO device mappings region
0xFFFF_FFFF_FFFF_FFFF  Top of kernel virtual space
```

### Physical Layout (QEMU virt machine)

```
0x0000_0000 - 0x07FF_FFFF  Flash memory (128MB, firmware)
0x0800_0000 - 0x0800_FFFF  GICv2 Distributor (GICD)
0x0801_0000 - 0x0801_FFFF  GICv2 CPU interface (GICC)
0x0900_0000 - 0x0900_0FFF  PL011 UART
0x0901_0000               RTC (PL031)
0x0A00_0000 - 0x0A00_0FFF  virtio-mmio device 0
0x0A00_1000 - 0x0A00_1FFF  virtio-mmio device 1
  ...                       (more virtio-mmio at 0x1000 intervals)
0x0C00_0000               Platform bus
0x1000_0000 - 0x1FFF_FFFF  PCIe ECAM configuration space (256MB)
0x4000_0000 - 0x7FFF_FFFF  RAM start (QEMU virt default, 1GB window)
0x4008_0000               Kernel load address (-kernel flag loads here)
```

### Architecture Constants

```c
#define ARCH_KERNEL_VBASE       0xFFFF000000000000ULL
#define ARCH_USER_VBASE         0x0000000000400000ULL
#define ARCH_USER_VTOP          0x0000FFFFFFFFFFFFULL
#define ARCH_KERNEL_LOAD        0x40080000ULL
#define ARCH_PAGE_SIZE          4096
#define ARCH_PT_LEVELS          4
#define ARCH_STACK_SIZE         16384   /* 16KB kernel stack per process */
```

---

## I/O Mechanism

### No Port I/O

AArch64 has **no port I/O** instructions (`in`/`out` do not exist). All hardware registers are accessed via **Memory-Mapped I/O (MMIO)**: the device's control/status/data registers are mapped to physical addresses, and the CPU reads/writes them as normal memory locations.

### MMIO Access Functions

All MMIO accesses must be volatile to prevent compiler optimization, and use appropriate barrier instructions for device memory:

```c
#include <stdint.h>

static inline void mmio_write32(uint64_t addr, uint32_t value)
{
    *(volatile uint32_t *)addr = value;
}

static inline uint32_t mmio_read32(uint64_t addr)
{
    return *(volatile uint32_t *)addr;
}

static inline void mmio_write16(uint64_t addr, uint16_t value)
{
    *(volatile uint16_t *)addr = value;
}

static inline uint16_t mmio_read16(uint64_t addr)
{
    return *(volatile uint16_t *)addr;
}

static inline void mmio_write8(uint64_t addr, uint8_t value)
{
    *(volatile uint8_t *)addr = value;
}

static inline uint8_t mmio_read8(uint64_t addr)
{
    return *(volatile uint8_t *)addr;
}
```

### HAL I/O Implementation

The `arch_io_read*` / `arch_io_write*` HAL functions are direct MMIO operations on AArch64:

```c
uint8_t arch_io_read8(uint64_t addr)   { return mmio_read8(addr); }
uint16_t arch_io_read16(uint64_t addr) { return mmio_read16(addr); }
uint32_t arch_io_read32(uint64_t addr) { return mmio_read32(addr); }

void arch_io_write8(uint64_t addr, uint8_t val)   { mmio_write8(addr, val); }
void arch_io_write16(uint64_t addr, uint16_t val)  { mmio_write16(addr, val); }
void arch_io_write32(uint64_t addr, uint32_t val)  { mmio_write32(addr, val); }
```

### PCI Configuration Access

On ARM platforms, PCI configuration space is accessed via **ECAM** (Enhanced Configuration Access Mechanism), which maps PCI config space into a contiguous MMIO region. The ECAM base address is obtained from the Device Tree (`pcie@10000000` node on QEMU virt).

```c
/*
 * ECAM address calculation:
 * offset = (bus << 20) | (device << 15) | (function << 12) | register
 * Physical address = ecam_base + offset
 */
#define ECAM_ADDR(base, bus, dev, func, reg) \
    ((base) + ((uint64_t)(bus) << 20) | ((uint64_t)(dev) << 15) | \
     ((uint64_t)(func) << 12) | ((uint64_t)(reg)))

uint32_t arch_pci_config_read32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset)
{
    uint64_t addr = ECAM_ADDR(ecam_base, bus, dev, func, offset);
    return mmio_read32(addr);
}

void arch_pci_config_write32(uint8_t bus, uint8_t dev, uint8_t func,
                             uint8_t offset, uint32_t val)
{
    uint64_t addr = ECAM_ADDR(ecam_base, bus, dev, func, offset);
    mmio_write32(addr, val);
}
```

---

## Core Hardware (QEMU virt machine)

### GICv2 (Generic Interrupt Controller)

The GICv2 is the interrupt controller on the QEMU `virt` machine. It replaces the x86 8259 PIC and APIC.

**Base Addresses (QEMU virt):**

| Component | Base Address | Size |
|-----------|-------------|------|
| GICD (Distributor) | `0x08000000` | 64 KB |
| GICC (CPU Interface) | `0x08010000` | 64 KB |

**Interrupt Types:**

| Type | Range | Description |
|------|-------|-------------|
| SGI (Software Generated Interrupt) | 0-15 | Inter-processor interrupts |
| PPI (Private Peripheral Interrupt) | 16-31 | Per-CPU private (e.g., timer = INTID 30) |
| SPI (Shared Peripheral Interrupt) | 32-1019 | Shared hardware interrupts (e.g., UART = SPI 33 = INTID 33) |

**Key GICD Registers (Distributor):**

| Register | Offset | Description |
|----------|--------|-------------|
| `GICD_CTLR` | 0x000 | Distributor Control (bit 0: enable) |
| `GICD_TYPER` | 0x004 | Interrupt Controller Type (number of IRQ lines) |
| `GICD_ISENABLER[n]` | 0x100 + 4*n | Interrupt Set-Enable (write 1 to enable) |
| `GICD_ICENABLER[n]` | 0x180 + 4*n | Interrupt Clear-Enable (write 1 to disable) |
| `GICD_ISPENDR[n]` | 0x200 + 4*n | Interrupt Set-Pending |
| `GICD_ICPENDR[n]` | 0x280 + 4*n | Interrupt Clear-Pending |
| `GICD_IPRIORITYR[n]` | 0x400 + 4*n | Interrupt Priority (8 bits per interrupt, lower = higher priority) |
| `GICD_ITARGETSR[n]` | 0x800 + 4*n | Interrupt Processor Targets (8 bits per interrupt, bitmask of CPUs) |
| `GICD_ICFGR[n]` | 0xC00 + 4*n | Interrupt Configuration (edge/level) |

**Key GICC Registers (CPU Interface):**

| Register | Offset | Description |
|----------|--------|-------------|
| `GICC_CTLR` | 0x000 | CPU Interface Control (bit 0: enable) |
| `GICC_PMR` | 0x004 | Priority Mask (interrupts below this priority are masked) |
| `GICC_IAR` | 0x00C | Interrupt Acknowledge (read to get INTID of pending interrupt) |
| `GICC_EOIR` | 0x010 | End of Interrupt (write INTID to signal completion) |

**GIC Initialization Sequence:**

```c
#define GICD_BASE   0x08000000ULL
#define GICC_BASE   0x08010000ULL

void gic_init(void)
{
    /* Disable distributor */
    mmio_write32(GICD_BASE + 0x000, 0);

    /* Determine number of interrupt lines */
    uint32_t typer = mmio_read32(GICD_BASE + 0x004);
    uint32_t num_irqs = ((typer & 0x1F) + 1) * 32;

    /* Set all SPIs to: lowest priority, target CPU 0, level-triggered */
    for (uint32_t i = 32; i < num_irqs; i += 4) {
        mmio_write32(GICD_BASE + 0x400 + (i / 4) * 4, 0xA0A0A0A0);  /* priority */
        mmio_write32(GICD_BASE + 0x800 + (i / 4) * 4, 0x01010101);  /* target CPU 0 */
    }

    /* Disable all interrupts initially */
    for (uint32_t i = 0; i < num_irqs / 32; i++) {
        mmio_write32(GICD_BASE + 0x180 + i * 4, 0xFFFFFFFF);
    }

    /* Enable distributor */
    mmio_write32(GICD_BASE + 0x000, 1);

    /* CPU interface: set priority mask to accept all, enable interface */
    mmio_write32(GICC_BASE + 0x004, 0xFF);  /* PMR: accept all priorities */
    mmio_write32(GICC_BASE + 0x000, 1);     /* Enable CPU interface */
}

void gic_enable_irq(uint32_t intid)
{
    uint32_t reg = intid / 32;
    uint32_t bit = intid % 32;
    mmio_write32(GICD_BASE + 0x100 + reg * 4, (1 << bit));
}

uint32_t gic_acknowledge(void)
{
    return mmio_read32(GICC_BASE + 0x00C);  /* Read IAR */
}

void gic_end_of_interrupt(uint32_t intid)
{
    mmio_write32(GICC_BASE + 0x010, intid);  /* Write EOIR */
}
```

### PL011 UART

The PL011 is the serial UART on the QEMU `virt` machine. It replaces the x86 16550A COM port.

**Base Address:** `0x09000000` (QEMU virt)
**Interrupt:** SPI 1 (INTID 33)

**Registers:**

| Register | Offset | Description |
|----------|--------|-------------|
| `UARTDR` | 0x000 | Data Register (read: receive, write: transmit) |
| `UARTRSR` | 0x004 | Receive Status / Error Clear |
| `UARTFR` | 0x018 | Flag Register (status flags) |
| `UARTILPR` | 0x020 | IrDA Low-Power Counter |
| `UARTIBRD` | 0x024 | Integer Baud Rate Divisor |
| `UARTFBRD` | 0x028 | Fractional Baud Rate Divisor |
| `UARTLCR_H` | 0x02C | Line Control Register (word length, FIFO enable, parity) |
| `UARTCR` | 0x030 | Control Register (UART enable, TX/RX enable) |
| `UARTIFLS` | 0x034 | Interrupt FIFO Level Select |
| `UARTIMSC` | 0x038 | Interrupt Mask Set/Clear |
| `UARTRIS` | 0x03C | Raw Interrupt Status |
| `UARTMIS` | 0x040 | Masked Interrupt Status |
| `UARTICR` | 0x044 | Interrupt Clear Register |

**Flag Register (UARTFR) Bits:**

| Bit | Name | Description |
|-----|------|-------------|
| 0 | CTS | Clear to Send |
| 3 | BUSY | UART is transmitting data |
| 4 | RXFE | Receive FIFO empty |
| 5 | TXFF | Transmit FIFO full |
| 6 | RXFF | Receive FIFO full |
| 7 | TXFE | Transmit FIFO empty |

**Minimal UART Implementation:**

```c
#define UART_BASE   0x09000000ULL
#define UART_DR     (UART_BASE + 0x000)
#define UART_FR     (UART_BASE + 0x018)
#define UART_IBRD   (UART_BASE + 0x024)
#define UART_FBRD   (UART_BASE + 0x028)
#define UART_LCR_H  (UART_BASE + 0x02C)
#define UART_CR     (UART_BASE + 0x030)
#define UART_IMSC   (UART_BASE + 0x038)
#define UART_ICR    (UART_BASE + 0x044)

#define FR_TXFF     (1 << 5)   /* Transmit FIFO full */
#define FR_RXFE     (1 << 4)   /* Receive FIFO empty */
#define FR_BUSY     (1 << 3)   /* UART busy */

void uart_init(void)
{
    /* Disable UART */
    mmio_write32(UART_CR, 0);

    /* Clear pending interrupts */
    mmio_write32(UART_ICR, 0x7FF);

    /*
     * Set baud rate: QEMU does not care about actual baud rate,
     * but set to 115200 for correctness.
     * Assuming 24MHz UART clock: divisor = 24000000 / (16 * 115200) = 13.0208
     * IBRD = 13, FBRD = round(0.0208 * 64) = 1
     */
    mmio_write32(UART_IBRD, 13);
    mmio_write32(UART_FBRD, 1);

    /* 8 bits, no parity, 1 stop bit, FIFO enabled */
    mmio_write32(UART_LCR_H, (3 << 5) | (1 << 4));  /* WLEN=8bit, FEN=1 */

    /* Mask all interrupts (unmask selectively later if needed) */
    mmio_write32(UART_IMSC, 0);

    /* Enable UART, TX, and RX */
    mmio_write32(UART_CR, (1 << 0) | (1 << 8) | (1 << 9));  /* UARTEN, TXE, RXE */
}

void uart_putchar(char c)
{
    /* Wait for transmit FIFO to have space */
    while (mmio_read32(UART_FR) & FR_TXFF)
        ;
    mmio_write32(UART_DR, (uint32_t)c);
}

char uart_getchar(void)
{
    /* Wait for receive FIFO to have data */
    while (mmio_read32(UART_FR) & FR_RXFE)
        ;
    return (char)(mmio_read32(UART_DR) & 0xFF);
}

void uart_puts(const char *s)
{
    while (*s) {
        if (*s == '\n')
            uart_putchar('\r');
        uart_putchar(*s++);
    }
}
```

### ARM Architected Timer

AArch64 has a built-in architectural timer accessed via system registers. It replaces the x86 PIT (8254) and APIC timer.

**System Registers:**

| Register | Purpose |
|----------|---------|
| `CNTFRQ_EL0` | Counter frequency in Hz (set by firmware, typically 62.5 MHz on QEMU) |
| `CNTPCT_EL0` | Physical counter value (monotonically increasing) |
| `CNTP_TVAL_EL0` | Physical timer value: countdown from loaded value to zero |
| `CNTP_CTL_EL0` | Physical timer control: enable (bit 0), IMASK (bit 1), ISTATUS (bit 2) |
| `CNTP_CVAL_EL0` | Physical timer compare value (fire when counter >= compare) |

**Timer Interrupt:** PPI 14 (INTID 30) — `EL1 Physical Timer`

**Timer Implementation:**

```c
static uint32_t timer_freq;
static uint32_t timer_interval;

void timer_init(uint32_t frequency_hz)
{
    /* Read the hardware counter frequency */
    asm volatile("mrs %0, cntfrq_el0" : "=r"(timer_freq));

    /* Calculate ticks per scheduler interval */
    timer_interval = timer_freq / frequency_hz;

    /* Load the countdown timer */
    asm volatile("msr cntp_tval_el0, %0" :: "r"(timer_interval));

    /* Enable the timer, unmask interrupt */
    uint64_t ctl = 1;  /* ENABLE = 1, IMASK = 0 */
    asm volatile("msr cntp_ctl_el0, %0" :: "r"(ctl));

    /* Enable the timer interrupt in the GIC (PPI 14, INTID 30) */
    gic_enable_irq(30);
}

void timer_irq_handler(void)
{
    /* Reload the countdown timer for next tick */
    asm volatile("msr cntp_tval_el0, %0" :: "r"(timer_interval));

    /* Call portable scheduler tick */
    sched_tick();
}

uint64_t timer_get_ticks(void)
{
    uint64_t val;
    asm volatile("mrs %0, cntpct_el0" : "=r"(val));
    return val;
}

uint32_t timer_get_frequency(void)
{
    return timer_freq;
}
```

### virtio-mmio Devices

QEMU's `virt` machine places virtio-mmio devices at addresses starting from `0x0A000000`, each device occupying a 0x1000 (4KB) region:

| Device | Base Address | SPI | INTID |
|--------|-------------|-----|-------|
| virtio-mmio #0 | `0x0A000000` | SPI 16 | 48 |
| virtio-mmio #1 | `0x0A000200` | SPI 17 | 49 |
| ... | +0x200 each | ... | ... |

Note: Exact addresses and interrupt mappings should be obtained from the DTB, not hard-coded.

### What Does NOT Exist on AArch64

These x86-specific devices have **no equivalent** on the QEMU `virt` machine:

| x86 Device | AArch64 Replacement |
|------------|-------------------|
| VGA text mode (0xB8000) | PL011 UART serial console (or framebuffer via virtio-gpu) |
| PIT 8254 timer | ARM Architected Timer (system registers) |
| PS/2 keyboard controller | virtio-input or no keyboard (serial console) |
| 8259 PIC | GICv2 (or GICv3 on newer platforms) |
| I/O ports (inb/outb) | All MMIO |
| BIOS / legacy boot | Device Tree / UEFI |
| PCI config via 0xCF8/0xCFC | PCIe ECAM (MMIO) |
| CMOS RTC (port 0x70/0x71) | PL031 RTC (MMIO at 0x09010000) |

---

## Firmware

### Device Tree Blob (DTB)

On AArch64, the firmware passes a **Flattened Device Tree (FDT)** in memory. The physical address of the DTB is provided in register **X0** at kernel entry.

The DTB replaces ACPI tables for hardware description on QEMU `virt`. It provides:

- Memory regions and sizes (`/memory` node)
- Device base addresses and register sizes (`reg` properties)
- Interrupt mappings (`interrupts` properties)
- Compatible strings for driver matching (`compatible` properties)
- Chosen node (`/chosen`) for boot arguments and initrd location

### FDT Binary Format

**Header (40 bytes):**

```c
typedef struct fdt_header {
    uint32_t magic;             /* 0xD00DFEED (big-endian!) */
    uint32_t totalsize;         /* total size of DTB */
    uint32_t off_dt_struct;     /* offset to structure block */
    uint32_t off_dt_strings;    /* offset to strings block */
    uint32_t off_mem_rsvmap;    /* offset to memory reservation block */
    uint32_t version;           /* DTB format version (17) */
    uint32_t last_comp_version; /* last compatible version (16) */
    uint32_t boot_cpuid_phys;   /* physical ID of boot CPU */
    uint32_t size_dt_strings;   /* size of strings block */
    uint32_t size_dt_struct;    /* size of structure block */
} fdt_header_t;
```

**Important:** All multi-byte values in the DTB are **big-endian**. The parser must byte-swap on little-endian AArch64:

```c
static inline uint32_t fdt_be32(uint32_t val)
{
    return __builtin_bswap32(val);
}

static inline uint64_t fdt_be64(uint64_t val)
{
    return __builtin_bswap64(val);
}
```

**FDT Tokens (structure block):**

| Token | Value | Description |
|-------|-------|-------------|
| `FDT_BEGIN_NODE` | 0x00000001 | Start of a node (followed by null-terminated name, padded to 4 bytes) |
| `FDT_END_NODE` | 0x00000002 | End of a node |
| `FDT_PROP` | 0x00000003 | Property (followed by length, nameoff, then value padded to 4 bytes) |
| `FDT_NOP` | 0x00000004 | No operation (skip) |
| `FDT_END` | 0x00000009 | End of structure block |

**Property Structure:**

```c
typedef struct fdt_prop {
    uint32_t len;       /* length of value in bytes */
    uint32_t nameoff;   /* offset into strings block for property name */
    /* followed by `len` bytes of value, padded to 4-byte alignment */
} fdt_prop_t;
```

### Key DTB Nodes (QEMU virt)

```
/ {
    compatible = "linux,dummy-virt";
    #address-cells = <2>;
    #size-cells = <2>;

    chosen {
        bootargs = "...";
        linux,initrd-start = <...>;
        linux,initrd-end = <...>;
    };

    memory@40000000 {
        device_type = "memory";
        reg = <0x00 0x40000000 0x00 0x08000000>;  /* 128MB at 0x40000000 */
    };

    intc@8000000 {
        compatible = "arm,cortex-a15-gic";
        reg = <0x00 0x08000000 0x00 0x10000    /* GICD */
               0x00 0x08010000 0x00 0x10000>;  /* GICC */
        #interrupt-cells = <3>;
        interrupt-controller;
    };

    pl011@9000000 {
        compatible = "arm,pl011", "arm,primecell";
        reg = <0x00 0x09000000 0x00 0x1000>;
        interrupts = <0x00 0x01 0x04>;  /* SPI 1, level */
    };

    timer {
        compatible = "arm,armv8-timer";
        interrupts = <1 13 0xf08>,  /* Secure PPI 13 */
                     <1 14 0xf08>,  /* Non-secure PPI 14 */
                     <1 11 0xf08>,  /* Virtual PPI 11 */
                     <1 10 0xf08>;  /* Hypervisor PPI 10 */
    };

    pcie@10000000 {
        compatible = "pci-host-ecam-generic";
        reg = <0x00 0x3f000000 0x00 0x01000000>;  /* ECAM config space */
        ranges = <0x01000000 0x00 0x00000000  0x00 0x3eff0000  0x00 0x00010000>,
                 <0x02000000 0x00 0x10000000  0x00 0x10000000  0x00 0x2eff0000>;
    };

    virtio_mmio@a000000 {
        compatible = "virtio,mmio";
        reg = <0x00 0x0a000000 0x00 0x200>;
        interrupts = <0x00 0x10 0x01>;  /* SPI 16 */
    };
    /* ... more virtio_mmio nodes ... */
};
```

### Minimal DTB Parser

```c
#define FDT_MAGIC       0xD00DFEED
#define FDT_BEGIN_NODE  0x00000001
#define FDT_END_NODE    0x00000002
#define FDT_PROP        0x00000003
#define FDT_NOP         0x00000004
#define FDT_END         0x00000009

int fdt_validate(void *dtb)
{
    fdt_header_t *hdr = (fdt_header_t *)dtb;
    if (fdt_be32(hdr->magic) != FDT_MAGIC)
        return -1;
    if (fdt_be32(hdr->version) < 16)
        return -1;
    return 0;
}

/* Walk the structure block, calling callbacks for nodes and properties.
 * A full implementation finds /memory for RAM, /chosen for bootargs,
 * and device nodes for MMIO base addresses and interrupt mappings. */
```

### No ACPI on QEMU virt (Default)

The QEMU `virt` machine uses a Device Tree by default. ACPI tables are **not** provided unless explicitly enabled with `-machine virt,acpi=on`. The AUTON AArch64 HAL targets the DTB path.

---

## Context Switch Assembly

The context switch saves and restores callee-saved registers. On AArch64, these are X19-X28, FP (X29), and LR (X30). The C compiler preserves all other registers across function calls, so the context switch only needs to save the callee-saved set plus SP.

### Implementation

```asm
/* kernel/arch/aarch64/sched/context_switch.S
 *
 * void arch_context_switch(uint64_t *old_sp_ptr, uint64_t new_sp);
 *
 * X0 = pointer to old task's saved SP location
 * X1 = new task's saved SP value
 *
 * Saves callee-saved registers to old stack, switches SP, restores from new stack.
 */

.globl arch_context_switch
arch_context_switch:
    /* Save callee-saved registers to the current (old) stack */
    stp     x19, x20, [sp, #-16]!
    stp     x21, x22, [sp, #-16]!
    stp     x23, x24, [sp, #-16]!
    stp     x25, x26, [sp, #-16]!
    stp     x27, x28, [sp, #-16]!
    stp     x29, x30, [sp, #-16]!      /* FP and LR */

    /* Save current SP to *old_sp_ptr */
    mov     x2, sp
    str     x2, [x0]

    /* Load new SP */
    mov     sp, x1

    /* Restore callee-saved registers from the new stack */
    ldp     x29, x30, [sp], #16        /* FP and LR */
    ldp     x27, x28, [sp], #16
    ldp     x25, x26, [sp], #16
    ldp     x23, x24, [sp], #16
    ldp     x21, x22, [sp], #16
    ldp     x19, x20, [sp], #16

    /* Return to the new task (branches to address in LR / X30) */
    ret
```

### Initial Context Setup

When creating a new process, set up its kernel stack so that `arch_context_switch` into it will start executing the entry point:

```c
void arch_setup_initial_context(struct process *proc, void (*entry)(void))
{
    uint64_t *sp = (uint64_t *)(proc->kernel_stack_top);

    /* Build a fake stack frame matching what arch_context_switch expects.
     * The ldp sequence pops 6 pairs = 12 registers = 96 bytes. */

    /* Pair 6 (first popped): X29 (FP) and X30 (LR) */
    *(--sp) = (uint64_t)entry;   /* X30 / LR: ret will jump here */
    *(--sp) = 0;                 /* X29 / FP: null frame pointer */

    /* Pairs 5-1: X27/X28, X25/X26, X23/X24, X21/X22, X19/X20 */
    *(--sp) = 0;  /* X28 */
    *(--sp) = 0;  /* X27 */
    *(--sp) = 0;  /* X26 */
    *(--sp) = 0;  /* X25 */
    *(--sp) = 0;  /* X24 */
    *(--sp) = 0;  /* X23 */
    *(--sp) = 0;  /* X22 */
    *(--sp) = 0;  /* X21 */
    *(--sp) = 0;  /* X20 */
    *(--sp) = 0;  /* X19 */

    proc->saved_sp = (uint64_t)sp;
}
```

### Exception Entry/Exit (Full Context Save)

For exceptions and interrupts (unlike context switch), the **full** register set must be saved:

```asm
/* Save all general-purpose registers + ELR + SPSR on exception entry */
.macro save_all_regs
    sub     sp, sp, #272            /* 34 * 8 bytes */
    stp     x0,  x1,  [sp, #0]
    stp     x2,  x3,  [sp, #16]
    stp     x4,  x5,  [sp, #32]
    stp     x6,  x7,  [sp, #48]
    stp     x8,  x9,  [sp, #64]
    stp     x10, x11, [sp, #80]
    stp     x12, x13, [sp, #96]
    stp     x14, x15, [sp, #112]
    stp     x16, x17, [sp, #128]
    stp     x18, x19, [sp, #144]
    stp     x20, x21, [sp, #160]
    stp     x22, x23, [sp, #176]
    stp     x24, x25, [sp, #192]
    stp     x26, x27, [sp, #208]
    stp     x28, x29, [sp, #224]
    str     x30,      [sp, #240]

    mrs     x0, elr_el1
    mrs     x1, spsr_el1
    stp     x0, x1, [sp, #248]     /* ELR_EL1 and SPSR_EL1 */

    /* If from EL0, save user SP */
    mrs     x0, sp_el0
    str     x0, [sp, #264]
.endm

/* Restore all registers and return from exception */
.macro restore_all_regs
    ldr     x0, [sp, #264]
    msr     sp_el0, x0              /* Restore user SP */

    ldp     x0, x1, [sp, #248]
    msr     elr_el1, x0
    msr     spsr_el1, x1

    ldr     x30,      [sp, #240]
    ldp     x28, x29, [sp, #224]
    ldp     x26, x27, [sp, #208]
    ldp     x24, x25, [sp, #192]
    ldp     x22, x23, [sp, #176]
    ldp     x20, x21, [sp, #160]
    ldp     x18, x19, [sp, #144]
    ldp     x16, x17, [sp, #128]
    ldp     x14, x15, [sp, #112]
    ldp     x12, x13, [sp, #96]
    ldp     x10, x11, [sp, #80]
    ldp     x8,  x9,  [sp, #64]
    ldp     x6,  x7,  [sp, #48]
    ldp     x4,  x5,  [sp, #32]
    ldp     x2,  x3,  [sp, #16]
    ldp     x0,  x1,  [sp, #0]
    add     sp, sp, #272

    eret
.endm
```

---

## Initial Page Table Setup

Before jumping to C code that uses virtual addresses, the boot assembly must set up minimal page tables: an **identity map** of the kernel's physical address range (so current PC remains valid after MMU enable) and a **higher-half map** at `KERNEL_VBASE`.

### Strategy: L1 Block Descriptors (1GB Blocks)

For the initial boot map, use L1 block descriptors (1GB granularity) to keep the code simple. Only three page tables are needed: one L0 table, and two L1 tables (one for TTBR0, one for TTBR1).

### Assembly Implementation

```asm
/* kernel/arch/aarch64/boot/mmu_init.S
 *
 * Sets up initial identity + kernel page tables using 1GB block descriptors.
 * Called from boot.S before branching to kernel_main.
 */

.section ".text.boot"

/* Page table alignment: 4KB */
.balign 4096
boot_l0_ttbr0:  .space 4096    /* L0 table for TTBR0 (identity map) */
.balign 4096
boot_l1_ttbr0:  .space 4096    /* L1 table for TTBR0 */
.balign 4096
boot_l0_ttbr1:  .space 4096    /* L0 table for TTBR1 (kernel map) */
.balign 4096
boot_l1_ttbr1:  .space 4096    /* L1 table for TTBR1 */

/*
 * mmu_early_init:
 *   Sets up identity map (TTBR0) and kernel higher-half map (TTBR1).
 *   Uses 1GB block descriptors at L1 level.
 *
 *   Identity map: VA 0x40000000 -> PA 0x40000000 (1GB block covering RAM)
 *   Also map:     VA 0x00000000 -> PA 0x00000000 (1GB block covering MMIO devices)
 *   Kernel map:   VA 0xFFFF000000000000 -> PA 0x00000000 (first 1GB)
 *                 VA 0xFFFF000040000000 -> PA 0x40000000 (second 1GB, RAM)
 */
.globl mmu_early_init
mmu_early_init:
    /* Define block descriptor attributes */
    /* Normal memory: AttrIndx=0, AF=1, SH=Inner Shareable, valid block */
    mov     x2, #0x00000000000000401  /* Valid=1, Block(bit1=0), AttrIndx=0, AF, SH=Inner */
    movk    x2, #0x0000, lsl #48
    /* Precise encoding:
     * Bits [1:0] = 0b01 (valid block)
     * Bits [4:2] = 0b000 (AttrIndx = 0, normal WB memory)
     * Bits [9:8] = 0b11 (Inner Shareable)
     * Bit [10]   = 1 (AF)
     */
    ldr     x2, =0x0000000000000705   /* Valid(1) | Block(0) | AttrIdx0 | SH_Inner(3<<8) | AF(1<<10) */
    /* = 0x1 | (0 << 2) | (3 << 8) | (1 << 10) = 0x1 | 0x300 | 0x400 = 0x701
     * Actually let's compute exactly: */

    /* Normal memory block attributes */
    mov     x2, #0x0000000000000001  /* Valid */
                                      /* Bit 1 = 0: Block descriptor */
    orr     x2, x2, #(0 << 2)       /* AttrIndx = 0 (normal WB from MAIR) */
    orr     x2, x2, #(3 << 8)       /* SH = Inner Shareable */
    orr     x2, x2, #(1 << 10)      /* AF = 1 */

    /* Device memory block attributes (for MMIO region 0x00000000-0x3FFFFFFF) */
    mov     x3, #0x0000000000000001  /* Valid */
    orr     x3, x3, #(1 << 2)       /* AttrIndx = 1 (device memory from MAIR) */
    orr     x3, x3, #(1 << 10)      /* AF = 1 */
    /* Device memory is non-shareable, non-cacheable by MAIR definition */

    /* ---- TTBR0: Identity Map ---- */

    /* L0 table: entry 0 -> L1 table */
    ldr     x0, =boot_l0_ttbr0
    ldr     x1, =boot_l1_ttbr0
    orr     x4, x1, #0x3            /* Table descriptor: Valid(1) | Table(1) = 0x3 */
    str     x4, [x0, #0]            /* L0[0] -> L1 table */

    /* L1 table: entry 0 -> 0x00000000 (1GB device MMIO) */
    mov     x5, x3                   /* Device attributes + PA 0x00000000 */
    str     x5, [x1, #0]            /* L1[0] = 0x00000000 block (device) */

    /* L1 table: entry 1 -> 0x40000000 (1GB RAM) */
    mov     x5, #0x40000000
    orr     x5, x5, x2              /* Normal memory attributes + PA 0x40000000 */
    str     x5, [x1, #8]            /* L1[1] = 0x40000000 block (RAM) */

    /* ---- TTBR1: Kernel Higher-Half Map ---- */

    /* L0 table: entry 0 -> L1 table
     * For TTBR1, VA 0xFFFF_0000_0000_0000 has L0 index = 0
     * (because T1SZ=16 means bits [47:39] index L0, and those bits are 0
     *  for 0xFFFF_0000_0000_0000) */
    ldr     x0, =boot_l0_ttbr1
    ldr     x1, =boot_l1_ttbr1
    orr     x4, x1, #0x3            /* Table descriptor */
    str     x4, [x0, #0]            /* L0[0] -> L1 table */

    /* L1[0] -> PA 0x00000000 (device MMIO, 1GB) */
    mov     x5, x3
    str     x5, [x1, #0]

    /* L1[1] -> PA 0x40000000 (RAM, 1GB) */
    mov     x5, #0x40000000
    orr     x5, x5, x2
    str     x5, [x1, #8]

    /* ---- Configure TCR_EL1 ---- */
    ldr     x0, =0x00000005B5103510  /* TCR_VALUE (see TCR section above) */
    msr     tcr_el1, x0

    /* ---- Configure MAIR_EL1 ---- */
    ldr     x0, =0x000000000000FF44  /* Attr0=0xFF(normal WB), Attr1=0x00(device), Attr2=0x44(NC) */
    /* Actually: Attr0 at bits[7:0]=0xFF, Attr1 at bits[15:8]=0x00, Attr2 at bits[23:16]=0x44 */
    ldr     x0, =0x0000000000440044  /* Correct: */
    mov     x0, #0xFF               /* Attr0: Normal WB */
    movk    x0, #0x0044, lsl #16   /* Attr2: Normal NC at bits [23:16] */
    /* Attr1 at bits [15:8] = 0x00 (device) — already zero */
    msr     mair_el1, x0

    /* ---- Load TTBR0 and TTBR1 ---- */
    ldr     x0, =boot_l0_ttbr0
    msr     ttbr0_el1, x0
    ldr     x0, =boot_l0_ttbr1
    msr     ttbr1_el1, x0

    isb

    /* ---- Enable MMU ---- */
    mrs     x0, sctlr_el1
    orr     x0, x0, #(1 << 0)      /* M: Enable MMU */
    orr     x0, x0, #(1 << 2)      /* C: Enable data cache */
    orr     x0, x0, #(1 << 12)     /* I: Enable instruction cache */
    msr     sctlr_el1, x0

    isb

    ret
```

### Simplified C Description of the Above

```c
/*
 * Boot page table setup summary:
 *
 * 1. Allocate 4 page-aligned 4KB tables in .bss or .text.boot:
 *    - boot_l0_ttbr0 (L0 for identity map)
 *    - boot_l1_ttbr0 (L1 for identity map)
 *    - boot_l0_ttbr1 (L0 for kernel map)
 *    - boot_l1_ttbr1 (L1 for kernel map)
 *
 * 2. Identity map (TTBR0):
 *    L0[0] -> boot_l1_ttbr0 (table descriptor)
 *    boot_l1_ttbr0[0] = 0x00000000 | DEVICE_BLOCK  (first 1GB: MMIO)
 *    boot_l1_ttbr0[1] = 0x40000000 | NORMAL_BLOCK  (second 1GB: RAM)
 *
 * 3. Kernel map (TTBR1):
 *    L0[0] -> boot_l1_ttbr1 (table descriptor)
 *    boot_l1_ttbr1[0] = 0x00000000 | DEVICE_BLOCK  (MMIO at KERNEL_VBASE + 0)
 *    boot_l1_ttbr1[1] = 0x40000000 | NORMAL_BLOCK  (RAM at KERNEL_VBASE + 1GB)
 *
 * 4. Set MAIR_EL1: Attr0=WB normal, Attr1=device, Attr2=non-cacheable
 * 5. Set TCR_EL1: T0SZ=16, T1SZ=16, 4KB granule, Inner Shareable, WB cacheable walks
 * 6. Load TTBR0_EL1 and TTBR1_EL1
 * 7. Enable MMU in SCTLR_EL1 (set M, C, I bits)
 * 8. ISB to synchronize
 *
 * After this, the kernel runs with identity mapping (same PCs work)
 * AND higher-half mapping (kernel can reference KERNEL_VBASE addresses).
 * The VMM subsystem later replaces these coarse 1GB mappings with
 * fine-grained 4KB page mappings.
 */
```

---

## QEMU Test Command

```bash
qemu-system-aarch64 \
    -machine virt \
    -cpu cortex-a53 \
    -kernel kernel.bin \
    -serial stdio \
    -display none \
    -no-reboot \
    -m 128M \
    -nographic
```

**Flags explained:**

| Flag | Purpose |
|------|---------|
| `-machine virt` | ARM virtual machine (GICv2, PL011, virtio, PCIe) |
| `-cpu cortex-a53` | ARMv8-A CPU (64-bit, EL2 support) |
| `-kernel kernel.bin` | Load flat binary at 0x40080000 |
| `-serial stdio` | Route PL011 UART to host terminal stdin/stdout |
| `-display none` | No graphical display window |
| `-no-reboot` | Exit on guest triple fault instead of rebooting |
| `-m 128M` | 128 MB of RAM |
| `-nographic` | Combine `-serial stdio -display none` (redundant but explicit) |

**With DTB dump (for debugging):**

```bash
qemu-system-aarch64 -machine virt,dumpdtb=virt.dtb -cpu cortex-a53
dtc -I dtb -O dts virt.dtb > virt.dts   # decompile to readable source
```

**With initramfs module:**

```bash
qemu-system-aarch64 \
    -machine virt \
    -cpu cortex-a53 \
    -kernel kernel.bin \
    -initrd initramfs.cpio \
    -serial stdio \
    -nographic \
    -m 128M
```

**With GDB debugging:**

```bash
qemu-system-aarch64 \
    -machine virt \
    -cpu cortex-a53 \
    -kernel kernel.elf \
    -serial stdio \
    -nographic \
    -m 128M \
    -S -s
# In another terminal:
# aarch64-elf-gdb kernel.elf -ex "target remote :1234"
```

---

## Exception Handling

### Exception Syndrome Register (ESR_EL1)

When a synchronous exception occurs, `ESR_EL1` provides the cause:

```
Bits [31:26]: EC (Exception Class)
Bits [24:0]:  ISS (Instruction Specific Syndrome)
Bit  [25]:    IL (Instruction Length, 0=16-bit, 1=32-bit)
```

**Common EC Values:**

| EC (hex) | EC (binary) | Exception Class |
|----------|-------------|-----------------|
| 0x00 | 000000 | Unknown reason |
| 0x01 | 000001 | Trapped WFI/WFE |
| 0x15 | 010101 | SVC from AArch64 (system call) |
| 0x20 | 100000 | Instruction Abort from lower EL |
| 0x21 | 100001 | Instruction Abort from current EL |
| 0x24 | 100100 | Data Abort from lower EL |
| 0x25 | 100101 | Data Abort from current EL |
| 0x26 | 100110 | SP Alignment fault |
| 0x2C | 101100 | Trapped FP access |

**Synchronous Exception Handler:**

```c
void exception_sync_handler(uint64_t esr, uint64_t elr, uint64_t far)
{
    uint32_t ec = (esr >> 26) & 0x3F;

    switch (ec) {
    case 0x15:  /* SVC from AArch64 — system call */
        syscall_dispatch(esr & 0xFFFF);
        break;
    case 0x20:  /* Instruction abort (lower EL) */
    case 0x21:  /* Instruction abort (current EL) */
        page_fault_handler(far, elr, esr, /*is_write=*/0);
        break;
    case 0x24:  /* Data abort (lower EL) */
    case 0x25:  /* Data abort (current EL) */
        page_fault_handler(far, elr, esr, /*is_write=*/(esr >> 6) & 1);
        break;
    default:
        arch_panic("Unhandled synchronous exception");
    }
}
```

---

## Inline Assembly Helpers

Common system register access patterns used throughout the AArch64 HAL:

```c
/* Read a system register */
#define READ_SYSREG(reg) ({                     \
    uint64_t __val;                             \
    asm volatile("mrs %0, " #reg : "=r"(__val));\
    __val;                                      \
})

/* Write a system register */
#define WRITE_SYSREG(reg, val)                  \
    asm volatile("msr " #reg ", %0" :: "r"((uint64_t)(val)))

/* Instruction synchronization barrier */
static inline void isb(void)
{
    asm volatile("isb" ::: "memory");
}

/* Data synchronization barrier */
static inline void dsb(void)
{
    asm volatile("dsb sy" ::: "memory");
}

/* Data memory barrier */
static inline void dmb(void)
{
    asm volatile("dmb sy" ::: "memory");
}

/* Wait for event (low-power idle) */
static inline void wfe(void)
{
    asm volatile("wfe");
}

/* Wait for interrupt (low-power idle) */
static inline void wfi(void)
{
    asm volatile("wfi");
}

/* Enable IRQ (clear I bit in DAIF) */
static inline void arch_enable_interrupts(void)
{
    asm volatile("msr daifclr, #2" ::: "memory");
}

/* Disable IRQ (set I bit in DAIF) */
static inline void arch_disable_interrupts(void)
{
    asm volatile("msr daifset, #2" ::: "memory");
}

/* Save and return interrupt state (DAIF register) */
static inline uint64_t arch_save_irq_state(void)
{
    uint64_t flags;
    asm volatile("mrs %0, daif" : "=r"(flags));
    asm volatile("msr daifset, #2" ::: "memory");
    return flags;
}

/* Restore interrupt state */
static inline void arch_restore_irq_state(uint64_t flags)
{
    asm volatile("msr daif, %0" :: "r"(flags) : "memory");
}

/* Halt until interrupt (idle loop) */
static inline void arch_halt(void)
{
    asm volatile("wfi");
}
```

---

## Files

| File | Purpose |
|------|---------|
| `kernel/arch/aarch64/boot/boot.S` | Entry point `_start`, EL check, EL2-to-EL1 drop, BSS clear, stack setup, branch to `kernel_main` |
| `kernel/arch/aarch64/boot/mmu_init.S` | Early page table setup (1GB blocks), TCR/MAIR/TTBR config, MMU enable |
| `kernel/arch/aarch64/boot/main.c` | `kernel_main()`, DTB parsing, subsystem initialization ordering |
| `kernel/arch/aarch64/boot/linker.ld` | Linker script: sections, symbols, load address |
| `kernel/arch/aarch64/cpu/vectors.S` | Exception vector table, `save_all_regs`/`restore_all_regs`, dispatch to C handlers |
| `kernel/arch/aarch64/cpu/exception.c` | Synchronous exception handler, ESR decoding, page fault dispatch |
| `kernel/arch/aarch64/cpu/gic.c` | GICv2 initialization, IRQ enable/disable, acknowledge, EOI |
| `kernel/arch/aarch64/mm/mmu.c` | Full 4-level page table management, `arch_map_page`, `arch_flush_tlb` |
| `kernel/arch/aarch64/sched/context_switch.S` | `arch_context_switch` assembly routine |
| `kernel/arch/aarch64/sched/context.c` | `arch_setup_initial_context`, `arch_set_kernel_stack` |
| `kernel/arch/aarch64/timer/timer.c` | ARM architected timer init, IRQ handler, tick counter |
| `kernel/arch/aarch64/io/mmio.c` | `arch_io_read*` / `arch_io_write*` MMIO wrappers |
| `kernel/arch/aarch64/dev/fdt.c` | Flattened Device Tree parser |
| `kernel/arch/aarch64/dev/pci_ecam.c` | PCIe ECAM configuration space access |
| `kernel/arch/aarch64/include/arch_context.h` | `struct cpu_context` definition |
| `kernel/arch/aarch64/include/arch_memory.h` | `ARCH_KERNEL_VBASE`, `ARCH_PAGE_SIZE`, etc. |
| `kernel/arch/aarch64/toolchain.mk` | CC, AS, LD, CFLAGS, ASFLAGS, LDFLAGS definitions |

---

## Dependencies

- None (the AArch64 arch layer is the root; all portable subsystems depend on it via the HAL)
- QEMU `virt` machine provides the hardware environment
- DTB is provided by QEMU firmware (passed in X0)
- The arch layer calls into portable subsystems: `mm` (PMM/VMM init), `sched`, `ipc`, `dev`, `slm`, `drivers`

---

## Acceptance Criteria

1. **EL1 Active**: After boot, `CurrentEL` reads as `0x04` (EL1). If entered at EL2, the EL2-to-EL1 transition completes without hanging.

2. **DTB Parsed**: The DTB at the address passed in X0 is validated (magic = `0xD00DFEED`). The `/memory` node is parsed and total RAM matches QEMU's `-m` flag (128MB). The `/chosen` node bootargs are extracted if present.

3. **GICv2 Initialized**: The GIC distributor and CPU interface are enabled. `GICD_CTLR` bit 0 is set. `GICC_CTLR` bit 0 is set. `GICC_PMR` is set to `0xFF`. The PL011 UART interrupt (SPI 1, INTID 33) and timer interrupt (PPI 14, INTID 30) are enabled in `GICD_ISENABLER`.

4. **Exception Vectors Set**: `VBAR_EL1` is loaded with the address of the exception vector table. A deliberate `svc #0` from EL1 triggers the synchronous exception handler at `VBAR_EL1 + 0x200` and is dispatched correctly. An unhandled exception prints ESR, ELR, and FAR to the UART.

5. **PL011 UART Output**: `uart_init()` configures the PL011 at `0x09000000`. `uart_puts("AUTON Kernel booting...\n")` produces visible output on the QEMU serial console (`-serial stdio`). Characters are transmitted without corruption.

6. **Timer Ticking**: The ARM architected timer fires at the configured frequency. `CNTP_CTL_EL0` bit 0 is set (enabled). The timer IRQ (INTID 30) is acknowledged via `GICC_IAR` and completed via `GICC_EOIR`. `sched_tick()` is called on each timer interrupt.

7. **MMU Enabled**: After `mmu_early_init`, `SCTLR_EL1` bit 0 (M) is set. Identity-mapped addresses and higher-half addresses both resolve correctly. A page fault on an unmapped address triggers the data abort handler (EC = 0x25) with the correct FAR.

8. **Memory Map Accurate**: Physical memory from the DTB `/memory` node is passed to the portable PMM. `pmm_total_count()` reports page count consistent with 128MB RAM minus reserved regions.

9. **Context Switch Functional**: `arch_context_switch` correctly saves X19-X28, FP, LR, and SP for the old task, restores them for the new task, and execution continues at the new task's saved LR.

10. **Subsystem Init Complete**: The full initialization sequence completes without panic: DTB parse, serial init, GIC init, MMU init (coarse then fine), PMM init, VMM init, slab init, timer init, scheduler init, IPC init, device framework init, SLM runtime init. The final message `"AUTON Kernel booting..."` appears on the UART.

11. **Page Fault Diagnostic**: An intentional access to unmapped address `0xDEAD000000000000` triggers a data abort. The handler prints: ESR (EC=0x25), ELR (faulting instruction PC), FAR (`0xDEAD000000000000`), and the kernel does not crash (it either recovers or panics cleanly).

12. **No x86 Dependencies**: The AArch64 HAL contains zero references to x86-specific constructs: no `inb`/`outb`, no GDT/IDT, no PIT/PIC, no VGA, no Multiboot2, no NASM syntax, no CR3/CR4 registers, no `int` instructions.
