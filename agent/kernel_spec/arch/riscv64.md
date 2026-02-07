# RISC-V 64-bit Architecture Specification

## Overview

This document is the complete architecture reference for agents building the RISC-V 64-bit HAL implementation of the AUTON kernel. It covers boot protocol, toolchain, register set, page table format, memory layout, I/O mechanisms, core hardware on the QEMU `virt` machine, firmware interfaces, context switching, initial page table setup, and acceptance criteria.

All RISC-V HAL code lives under `kernel/arch/riscv64/`. Portable kernel code calls the HAL interfaces defined in `arch/hal.md` -- this document specifies how those interfaces map to RISC-V hardware.

---

## Boot Protocol

### Firmware: OpenSBI

The RISC-V boot chain uses OpenSBI (Open Supervisor Binary Interface) as the M-mode firmware. OpenSBI initializes the platform in Machine mode (M-mode), then jumps to the kernel payload in Supervisor mode (S-mode). The kernel never executes in M-mode.

Boot chain: **Power-on -> OpenSBI (M-mode) -> Kernel (S-mode)**

### Entry Conditions

When OpenSBI transfers control to `_start`, the CPU state is:

| Register | Value |
|----------|-------|
| `a0` (x10) | Hart ID (hardware thread identifier) |
| `a1` (x11) | Physical address of the Device Tree Blob (DTB) |
| `pc` | Kernel load address (0x80200000 on QEMU `virt`) |
| Mode | Supervisor mode (S-mode) |
| `sstatus.SIE` | 0 (interrupts disabled) |
| `satp` | 0 (paging disabled, bare mode) |

### Trap Vector Setup

The S-mode trap vector base address is configured via the `stvec` CSR:

- **Direct mode** (`stvec[1:0] = 0b00`): All traps jump to the address in `stvec[63:2] << 2`.
- **Vectored mode** (`stvec[1:0] = 0b01`): Exceptions jump to BASE, interrupts jump to `BASE + 4 * cause`.

Use direct mode for simplicity. Set `stvec` to point at the trap handler before enabling interrupts.

```c
/* Write the trap handler address to stvec (direct mode) */
asm volatile("csrw stvec, %0" : : "r"(trap_entry));
```

### SBI Early Console

Before the NS16550A UART driver is initialized, use the legacy SBI console extension for output:

```c
/* SBI legacy console putchar: extension 0x01, a0 = character */
static inline void sbi_console_putchar(int ch)
{
    register long a0 asm("a0") = ch;
    register long a7 asm("a7") = 0x01;  /* legacy extension ID */
    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a7)
                 : "memory");
}
```

This implements the `arch_serial_putchar()` HAL function during early boot.

### Assembly Syntax

All RISC-V assembly uses **GNU AS** (GAS) syntax. Files use the `.S` extension (uppercase, for C preprocessor support).

### Skeleton `boot.S`

```asm
/* kernel/arch/riscv64/boot/boot.S */

.section .text.init
.global _start

_start:
    /* a0 = hartid, a1 = DTB physical address */

    /* ---- Park non-boot harts ---- */
    /* Hart 0 is the boot hart; all others spin in a WFI loop */
    bnez    a0, .park_hart

    /* ---- Set global pointer (linker-relaxation support) ---- */
.option push
.option norelax
    la      gp, __global_pointer$
.option pop

    /* ---- Clear BSS ---- */
    la      t0, __bss_start
    la      t1, __bss_end
.bss_clear:
    beq     t0, t1, .bss_done
    sd      zero, 0(t0)
    addi    t0, t0, 8
    j       .bss_clear
.bss_done:

    /* ---- Set up boot stack ---- */
    la      sp, __boot_stack_top

    /* ---- Set trap vector (direct mode) ---- */
    la      t0, trap_entry
    csrw    stvec, t0

    /* ---- Save DTB pointer for later use ---- */
    /* a0 = hartid (still 0), a1 = dtb pointer */
    /* Pass both to kernel_main(hartid, dtb) */
    call    kernel_main

    /* Should not return; halt if it does */
.halt:
    wfi
    j       .halt

    /* ---- Non-boot hart parking loop ---- */
.park_hart:
    wfi
    j       .park_hart

/* ---- Boot stack ---- */
.section .bss
.align 12
__boot_stack_bottom:
    .space  16384       /* 16 KB boot stack */
__boot_stack_top:
```

The linker script must place `.text.init` at `0x80200000` (the OpenSBI payload address on QEMU `virt`).

---

## Toolchain

### Compiler and Tools

| Tool | Binary | Notes |
|------|--------|-------|
| C Compiler | `riscv64-elf-gcc` or `riscv64-unknown-elf-gcc` | Bare-metal cross-compiler |
| Assembler | `riscv64-elf-as` | GNU AS, invoked via gcc for `.S` files |
| Linker | `riscv64-elf-ld` | GNU ld |
| Object Copy | `riscv64-elf-objcopy` | For binary extraction |
| Object Dump | `riscv64-elf-objdump` | For disassembly |

### Compiler Flags

```makefile
# kernel/arch/riscv64/toolchain.mk

ARCH       = riscv64
CC         = riscv64-elf-gcc
AS         = riscv64-elf-as
LD         = riscv64-elf-ld
OBJCOPY    = riscv64-elf-objcopy

CFLAGS     = -ffreestanding      \
             -fno-exceptions     \
             -march=rv64gc       \
             -mabi=lp64d         \
             -mcmodel=medany     \
             -Wall -Wextra       \
             -std=c11            \
             -nostdinc            \
             -fno-stack-protector \
             -fno-pie -no-pie

ASFLAGS    = -march=rv64gc       \
             -mabi=lp64d

LDFLAGS    = -T kernel/arch/riscv64/linker.ld \
             -nostdlib            \
             -static
```

### Flag Explanations

| Flag | Purpose |
|------|---------|
| `-ffreestanding` | No hosted environment; no standard library assumptions |
| `-fno-exceptions` | Disable C++ exception tables (kernel is C11) |
| `-march=rv64gc` | RV64I base + M (multiply) + A (atomic) + F (single-float) + D (double-float) + C (compressed) |
| `-mabi=lp64d` | LP64 ABI with hardware double-precision float passing |
| `-mcmodel=medany` | Code and data can be anywhere in address space; uses PC-relative addressing. Required for higher-half kernels |
| `-nostdinc` | Do not search standard include paths |
| `-fno-stack-protector` | No stack canary (no libc to provide `__stack_chk_fail`) |

---

## Register Set

### General-Purpose Registers

All 32 registers are 64 bits wide on RV64.

| Register | ABI Name | Usage | Saved By |
|----------|----------|-------|----------|
| `x0` | `zero` | Hardwired zero | N/A |
| `x1` | `ra` | Return address | Caller |
| `x2` | `sp` | Stack pointer | Callee |
| `x3` | `gp` | Global pointer | N/A (set once) |
| `x4` | `tp` | Thread pointer | N/A (per-hart) |
| `x5` | `t0` | Temporary | Caller |
| `x6` | `t1` | Temporary | Caller |
| `x7` | `t2` | Temporary | Caller |
| `x8` | `s0` / `fp` | Saved / frame pointer | Callee |
| `x9` | `s1` | Saved | Callee |
| `x10` | `a0` | Argument 0 / return value 0 | Caller |
| `x11` | `a1` | Argument 1 / return value 1 | Caller |
| `x12` | `a2` | Argument 2 | Caller |
| `x13` | `a3` | Argument 3 | Caller |
| `x14` | `a4` | Argument 4 | Caller |
| `x15` | `a5` | Argument 5 | Caller |
| `x16` | `a6` | Argument 6 | Caller |
| `x17` | `a7` | Argument 7 / ecall function ID | Caller |
| `x18` | `s2` | Saved | Callee |
| `x19` | `s3` | Saved | Callee |
| `x20` | `s4` | Saved | Callee |
| `x21` | `s5` | Saved | Callee |
| `x22` | `s6` | Saved | Callee |
| `x23` | `s7` | Saved | Callee |
| `x24` | `s8` | Saved | Callee |
| `x25` | `s9` | Saved | Callee |
| `x26` | `s10` | Saved | Callee |
| `x27` | `s11` | Saved | Callee |
| `x28` | `t3` | Temporary | Caller |
| `x29` | `t4` | Temporary | Caller |
| `x30` | `t5` | Temporary | Caller |
| `x31` | `t6` | Temporary | Caller |

### Calling Convention

RISC-V uses the standard calling convention defined in the RISC-V ELF psABI:

- **Arguments**: `a0`-`a7` (x10-x17). Additional arguments go on the stack.
- **Return values**: `a0` (x10) for the primary return value, `a1` (x11) for a second return value (128-bit returns).
- **Callee-saved**: `s0`-`s11` (x8-x9, x18-x27), `sp` (x2), `ra` (x1) must be preserved across calls by the callee.
- **Caller-saved**: `t0`-`t6` (x5-x7, x28-x31), `a0`-`a7` (x10-x17) may be clobbered by the callee.
- **Stack alignment**: 16-byte aligned at function entry.
- **No flags register**: RISC-V has no condition flags register (no EFLAGS/PSR equivalent). Comparisons use branch instructions directly: `beq`, `bne`, `blt`, `bge`, `bltu`, `bgeu`.

### Key CSRs (Supervisor Mode)

These are the CSRs the kernel reads and writes in S-mode:

| CSR | Address | Description |
|-----|---------|-------------|
| `sstatus` | 0x100 | Supervisor status: SIE (interrupt enable, bit 1), SPIE (previous IE, bit 5), SPP (previous privilege, bit 8) |
| `sie` | 0x104 | Supervisor interrupt enable: SSIE (software, bit 1), STIE (timer, bit 5), SEIE (external, bit 9) |
| `stvec` | 0x105 | Supervisor trap vector base address + mode (bits 1:0) |
| `sscratch` | 0x140 | Supervisor scratch register (used for trap handler temporary storage) |
| `sepc` | 0x141 | Supervisor exception PC (address of instruction that caused the trap) |
| `scause` | 0x142 | Supervisor trap cause: bit 63 = interrupt flag, bits 62:0 = exception/interrupt code |
| `stval` | 0x143 | Supervisor trap value (faulting address for page faults, faulting instruction for illegal insn) |
| `sip` | 0x144 | Supervisor interrupt pending: SSIP (bit 1), STIP (bit 5), SEIP (bit 9) |
| `satp` | 0x180 | Supervisor address translation and protection: MODE (bits 63:60), ASID (bits 59:44), PPN (bits 43:0) |
| `scounteren` | 0x106 | Supervisor counter enable (controls U-mode access to cycle/time/instret) |

### `scause` Values

**Exceptions (bit 63 = 0):**

| Code | Name |
|------|------|
| 0 | Instruction address misaligned |
| 1 | Instruction access fault |
| 2 | Illegal instruction |
| 3 | Breakpoint |
| 4 | Load address misaligned |
| 5 | Load access fault |
| 6 | Store/AMO address misaligned |
| 7 | Store/AMO access fault |
| 8 | Environment call from U-mode |
| 9 | Environment call from S-mode |
| 12 | Instruction page fault |
| 13 | Load page fault |
| 15 | Store/AMO page fault |

**Interrupts (bit 63 = 1):**

| Code | Name |
|------|------|
| 1 | Supervisor software interrupt |
| 5 | Supervisor timer interrupt |
| 9 | Supervisor external interrupt |

---

## Page Table Format

### Sv39 (Default)

The AUTON kernel uses **Sv39** paging by default: 3-level page tables with 39-bit virtual addresses.

```
Virtual Address (39 bits, sign-extended to 64 bits):
  63      39 38    30 29    21 20    12 11       0
 [sign-ext] [VPN[2]] [VPN[1]] [VPN[0]] [ offset ]
             9 bits   9 bits   9 bits   12 bits
```

- Each page table contains **512 entries** (2^9).
- Each page table entry (PTE) is **8 bytes**.
- Each page table occupies exactly **one 4KB page** (512 * 8 = 4096).
- Virtual addresses are **sign-extended** from bit 38 to bit 63. Valid addresses are either `0x0000_0000_0000_0000`-`0x0000_003F_FFFF_FFFF` (user) or `0xFFFF_FFC0_0000_0000`-`0xFFFF_FFFF_FFFF_FFFF` (kernel).

### Page Sizes

| Level | Page Size | Name | VPN bits used |
|-------|-----------|------|---------------|
| 0 (leaf) | 4 KB | Base page | VPN[2] + VPN[1] + VPN[0] |
| 1 (leaf) | 2 MB | Megapage | VPN[2] + VPN[1] |
| 2 (leaf) | 1 GB | Gigapage | VPN[2] |

Megapages and gigapages are created by setting R, W, or X bits on a non-leaf-level PTE. When a level-1 PTE has R/W/X bits set, it maps a contiguous 2MB region. When a level-2 PTE has them set, it maps 1GB.

### PTE Format

```
  63  54 53       10  9  8  7  6  5  4  3  2  1  0
 [rsvd] [  PPN[2]  ] [PPN[1]] [PPN[0]] [RSW] [D][A][G][U][X][W][R][V]
 10 bits  26 bits     9 bits   9 bits  2 bits
```

| Bit(s) | Field | Description |
|--------|-------|-------------|
| 0 | V (Valid) | Entry is valid |
| 1 | R (Read) | Page is readable |
| 2 | W (Write) | Page is writable |
| 3 | X (Execute) | Page is executable |
| 4 | U (User) | Page accessible in U-mode |
| 5 | G (Global) | Global mapping (not flushed on ASID change) |
| 6 | A (Accessed) | Page has been accessed (set by hardware or software) |
| 7 | D (Dirty) | Page has been written (set by hardware or software) |
| 8:9 | RSW | Reserved for software use |
| 10:53 | PPN | Physical page number (44 bits) |
| 54:63 | Reserved | Must be zero |

**Leaf vs. non-leaf determination**: If any of R, W, X bits are set, the PTE is a leaf (maps a page). If R=W=X=0 and V=1, the PTE points to the next level page table.

### PTE Helper Macros

```c
#define PTE_V   (1UL << 0)
#define PTE_R   (1UL << 1)
#define PTE_W   (1UL << 2)
#define PTE_X   (1UL << 3)
#define PTE_U   (1UL << 4)
#define PTE_G   (1UL << 5)
#define PTE_A   (1UL << 6)
#define PTE_D   (1UL << 7)

/* Extract physical address from PTE */
#define PTE_TO_PA(pte)   (((pte) >> 10) << 12)

/* Create PTE from physical address and flags */
#define PA_TO_PTE(pa)    (((uint64_t)(pa) >> 12) << 10)

/* VPN extraction from virtual address */
#define VPN2(va)  (((va) >> 30) & 0x1FF)
#define VPN1(va)  (((va) >> 21) & 0x1FF)
#define VPN0(va)  (((va) >> 12) & 0x1FF)
```

### `satp` CSR Format

```
  63  60 59      44 43          0
 [MODE ] [ ASID  ] [    PPN    ]
 4 bits   16 bits    44 bits
```

| MODE Value | Name | Description |
|------------|------|-------------|
| 0 | Bare | No translation (physical addressing) |
| 8 | Sv39 | 39-bit virtual addressing, 3-level page table |
| 9 | Sv48 | 48-bit virtual addressing, 4-level page table |

```c
#define SATP_SV39    (8UL << 60)
#define SATP_SV48    (9UL << 60)

/* Build satp value for Sv39 */
#define MAKE_SATP(root_ppn, asid) \
    (SATP_SV39 | ((uint64_t)(asid) << 44) | (root_ppn))
```

### TLB Management

```c
/* Flush all TLB entries */
static inline void tlb_flush_all(void)
{
    asm volatile("sfence.vma zero, zero" ::: "memory");
}

/* Flush TLB entry for a specific virtual address */
static inline void tlb_flush_addr(uint64_t vaddr)
{
    asm volatile("sfence.vma %0, zero" : : "r"(vaddr) : "memory");
}

/* Flush all TLB entries for a specific ASID */
static inline void tlb_flush_asid(uint64_t asid)
{
    asm volatile("sfence.vma zero, %0" : : "r"(asid) : "memory");
}
```

### Address Space Switch

```c
/* Switch to a new address space (implements arch_switch_address_space) */
static inline void switch_address_space(uint64_t root_table_phys)
{
    uint64_t ppn = root_table_phys >> 12;
    uint64_t satp_val = SATP_SV39 | ppn;
    asm volatile("csrw satp, %0" : : "r"(satp_val));
    asm volatile("sfence.vma zero, zero" ::: "memory");
}
```

### Sv48 (Optional)

Sv48 adds a fourth page table level for 48-bit virtual addresses (256 TB address space). The structure is identical to Sv39 but with an additional VPN[3] level. Use `satp.MODE = 9` to enable Sv48. The AUTON kernel uses Sv39 by default for simplicity.

---

## Memory Layout (Sv39)

### Virtual Address Space

```
0x0000_0000_0000_0000 +-----------------------+
                      |                       |
                      |     User Space        |
                      |     (256 GB)          |
                      |                       |
0x0000_003F_FFFF_FFFF +-----------------------+
                      |                       |
                      |  Non-canonical hole   |
                      |  (invalid addresses)  |
                      |                       |
0xFFFF_FFC0_0000_0000 +-----------------------+  <-- KERNEL_VBASE
                      |                       |
                      |    Kernel Space       |
                      |    (256 GB)           |
                      |                       |
0xFFFF_FFFF_FFFF_FFFF +-----------------------+
```

### Architecture Constants

```c
/* kernel/arch/riscv64/include/arch_memory.h */

#define ARCH_PAGE_SIZE       4096
#define ARCH_PT_LEVELS       3

#define ARCH_KERNEL_VBASE    0xFFFFFFC000000000UL
#define ARCH_KERNEL_LOAD     0x80200000UL           /* Physical load address (QEMU virt) */
#define ARCH_USER_VBASE      0x0000000000000000UL
#define ARCH_USER_VTOP       0x0000003FFFFFFFFFUL

#define ARCH_STACK_SIZE      16384                   /* 16 KB kernel stack per process */
```

### Physical Memory Map (QEMU `virt` Machine)

| Address Range | Size | Device / Region |
|---------------|------|-----------------|
| `0x0000_0000` - `0x0000_0FFF` | 4 KB | Debug region |
| `0x0010_0000` - `0x0010_0FFF` | 4 KB | QEMU test device |
| `0x0010_1000` - `0x0010_1FFF` | 4 KB | RTC (Goldfish) |
| `0x0200_0000` - `0x0200_FFFF` | 64 KB | CLINT (Core Local Interruptor) |
| `0x0C00_0000` - `0x0FFF_FFFF` | 64 MB | PLIC (Platform-Level Interrupt Controller) |
| `0x1000_0000` - `0x1000_0FFF` | 4 KB | NS16550A UART |
| `0x1000_1000` - `0x1000_8FFF` | 32 KB | virtio-mmio devices (8 slots) |
| `0x3000_0000` - `0x3FFF_FFFF` | 256 MB | PCIe ECAM configuration space |
| `0x4000_0000` - `0x7FFF_FFFF` | 1 GB | PCIe MMIO region |
| `0x8000_0000` - end of RAM | Variable | DRAM (RAM starts at 0x80000000) |

OpenSBI occupies `0x8000_0000` - `0x801F_FFFF`. The kernel loads at `0x8020_0000`.

---

## I/O Mechanism

### No Port I/O

RISC-V has **no port I/O instructions** (no equivalent of x86 `inb`/`outb`). All hardware registers are accessed via Memory-Mapped I/O (MMIO). Every device register is at a physical address and accessed through volatile pointer dereferences.

### MMIO Access Functions

```c
/* kernel/arch/riscv64/io/io.c */

/* Implements arch_io_read8 / arch_io_write8 etc. from the HAL */

static inline uint8_t mmio_read8(uint64_t addr)
{
    return *(volatile uint8_t *)addr;
}

static inline void mmio_write8(uint64_t addr, uint8_t val)
{
    *(volatile uint8_t *)addr = val;
}

static inline uint16_t mmio_read16(uint64_t addr)
{
    return *(volatile uint16_t *)addr;
}

static inline void mmio_write16(uint64_t addr, uint16_t val)
{
    *(volatile uint16_t *)addr = val;
}

static inline uint32_t mmio_read32(uint64_t addr)
{
    return *(volatile uint32_t *)addr;
}

static inline void mmio_write32(uint64_t addr, uint32_t val)
{
    *(volatile uint32_t *)addr = val;
}

static inline uint64_t mmio_read64(uint64_t addr)
{
    return *(volatile uint64_t *)addr;
}

static inline void mmio_write64(uint64_t addr, uint64_t val)
{
    *(volatile uint64_t *)addr = val;
}
```

The HAL `arch_io_read*` / `arch_io_write*` functions map directly to these MMIO accessors. The `addr` parameter is always a physical or mapped virtual address of a device register.

### Memory Ordering

RISC-V uses a relaxed memory model (RVWMO). Use `fence` instructions when device register access ordering matters:

```c
/* Full memory barrier */
static inline void mb(void)
{
    asm volatile("fence iorw, iorw" ::: "memory");
}

/* Read barrier (loads only) */
static inline void rmb(void)
{
    asm volatile("fence ir, ir" ::: "memory");
}

/* Write barrier (stores only) */
static inline void wmb(void)
{
    asm volatile("fence ow, ow" ::: "memory");
}
```

### PCI Configuration Space

PCI configuration is accessed via ECAM (Enhanced Configuration Access Mechanism) through MMIO. The ECAM base address is discovered from the DTB (`pci` node, `reg` property). On QEMU `virt`, the ECAM base is `0x30000000`.

```c
/* PCI ECAM address calculation */
#define ECAM_ADDR(base, bus, dev, func, offset) \
    ((base) + ((uint64_t)(bus) << 20) | ((dev) << 15) | ((func) << 12) | (offset))

uint32_t arch_pci_config_read32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset)
{
    uint64_t addr = ECAM_ADDR(pci_ecam_base, bus, dev, func, offset);
    return mmio_read32(addr);
}
```

---

## Core Hardware (QEMU `virt` Machine)

### PLIC (Platform-Level Interrupt Controller)

The PLIC manages external interrupts from devices. MMIO base: `0x0C000000`.

**Register Map:**

| Offset | Register | Description |
|--------|----------|-------------|
| `0x000000 + 4*id` | Priority[id] | Interrupt source priority (0 = disabled, 1-7 = priority) |
| `0x001000 + 4*(id/32)` | Pending[id/32] | Interrupt pending bits (read-only) |
| `0x002000 + 0x80*ctx + 4*(id/32)` | Enable[ctx][id/32] | Interrupt enable bits per context |
| `0x200000 + 0x1000*ctx` | Threshold[ctx] | Priority threshold per context |
| `0x200004 + 0x1000*ctx` | Claim/Complete[ctx] | Claim (read) / complete (write) per context |

**Context mapping**: Each hart has two contexts: M-mode context (2*hartid) and S-mode context (2*hartid + 1). The kernel uses the S-mode context.

```c
#define PLIC_BASE            0x0C000000UL
#define PLIC_PRIORITY(id)    (PLIC_BASE + 4 * (id))
#define PLIC_PENDING(id)     (PLIC_BASE + 0x1000 + 4 * ((id) / 32))

/* S-mode context for hart 0 = context 1 */
#define PLIC_SENABLE(ctx, id)    (PLIC_BASE + 0x2000 + 0x80 * (ctx) + 4 * ((id) / 32))
#define PLIC_STHRESHOLD(ctx)     (PLIC_BASE + 0x200000 + 0x1000 * (ctx))
#define PLIC_SCLAIM(ctx)         (PLIC_BASE + 0x200004 + 0x1000 * (ctx))

/* Enable an interrupt source for S-mode on hart 0 */
void plic_enable(uint32_t irq_id)
{
    uint32_t ctx = 1;  /* S-mode context for hart 0 */
    uint64_t addr = PLIC_SENABLE(ctx, irq_id);
    uint32_t val = mmio_read32(addr);
    val |= (1U << (irq_id % 32));
    mmio_write32(addr, val);
}

/* Set priority for an interrupt source */
void plic_set_priority(uint32_t irq_id, uint32_t priority)
{
    mmio_write32(PLIC_PRIORITY(irq_id), priority);
}

/* Set threshold (0 = accept all priorities > 0) */
void plic_set_threshold(uint32_t threshold)
{
    uint32_t ctx = 1;
    mmio_write32(PLIC_STHRESHOLD(ctx), threshold);
}

/* Claim the highest-priority pending interrupt (returns IRQ id, 0 = none) */
uint32_t plic_claim(void)
{
    uint32_t ctx = 1;
    return mmio_read32(PLIC_SCLAIM(ctx));
}

/* Complete an interrupt (write back the IRQ id) */
void plic_complete(uint32_t irq_id)
{
    uint32_t ctx = 1;
    mmio_write32(PLIC_SCLAIM(ctx), irq_id);
}
```

**QEMU `virt` interrupt source IDs:**

| IRQ ID | Device |
|--------|--------|
| 10 | NS16550A UART |
| 1-8 | virtio-mmio devices |

### CLINT (Core Local Interruptor)

The CLINT provides timer and software interrupts per hart. MMIO base: `0x02000000`.

**Register Map:**

| Offset | Register | Width | Description |
|--------|----------|-------|-------------|
| `0x0000 + 4*hartid` | `msip[hartid]` | 32-bit | Machine software interrupt pending |
| `0x4000 + 8*hartid` | `mtimecmp[hartid]` | 64-bit | Timer compare value per hart |
| `0xBFF8` | `mtime` | 64-bit | Machine timer (global, monotonic) |

The CLINT registers are M-mode. In S-mode, the kernel accesses timer functionality through SBI calls:

```c
#define CLINT_BASE       0x02000000UL
#define CLINT_MTIME      (CLINT_BASE + 0xBFF8)
#define CLINT_MTIMECMP(hart) (CLINT_BASE + 0x4000 + 8 * (hart))

/* Read mtime (if mapped and accessible from S-mode) */
uint64_t timer_read_mtime(void)
{
    return mmio_read64(CLINT_MTIME);
}

/* Set timer via SBI (preferred from S-mode) */
void sbi_set_timer(uint64_t stime_value)
{
    register long a0 asm("a0") = (long)stime_value;
    register long a6 asm("a6") = 0;              /* function ID */
    register long a7 asm("a7") = 0x54494D45;     /* SBI Timer extension EID */
    asm volatile("ecall"
                 : "+r"(a0)
                 : "r"(a6), "r"(a7)
                 : "memory");
}
```

Timer interrupts are handled by:
1. The SBI `set_timer` call programs `mtimecmp` from M-mode.
2. When `mtime >= mtimecmp`, a timer interrupt fires and is delegated to S-mode.
3. The kernel's trap handler reads `scause` (bit 63 set, code 5 = supervisor timer interrupt).
4. The handler calls `sbi_set_timer()` with the next deadline and clears `sip.STIP`.

```c
/* Enable supervisor timer interrupts */
static inline void enable_timer_interrupt(void)
{
    uint64_t sie;
    asm volatile("csrr %0, sie" : "=r"(sie));
    sie |= (1UL << 5);  /* STIE bit */
    asm volatile("csrw sie, %0" : : "r"(sie));
}
```

### NS16550A UART

MMIO base: `0x10000000`. The register layout is identical to the standard 16550A UART used on x86, but accessed via MMIO instead of port I/O.

| Offset | Register | Read/Write | Description |
|--------|----------|------------|-------------|
| 0x00 | RBR / THR | R / W | Receive Buffer / Transmit Holding |
| 0x01 | IER | R/W | Interrupt Enable Register |
| 0x02 | IIR / FCR | R / W | Interrupt Ident / FIFO Control |
| 0x03 | LCR | R/W | Line Control Register |
| 0x04 | MCR | R/W | Modem Control Register |
| 0x05 | LSR | R | Line Status Register |
| 0x06 | MSR | R | Modem Status Register |
| 0x07 | SCR | R/W | Scratch Register |

**Note**: On QEMU `virt`, registers are at **byte offsets** (not shifted). Some real hardware uses 4-byte register spacing.

```c
#define UART_BASE   0x10000000UL

#define UART_RBR    (UART_BASE + 0x00)  /* Receive Buffer Register (read) */
#define UART_THR    (UART_BASE + 0x00)  /* Transmit Holding Register (write) */
#define UART_IER    (UART_BASE + 0x01)  /* Interrupt Enable */
#define UART_FCR    (UART_BASE + 0x02)  /* FIFO Control (write) */
#define UART_LCR    (UART_BASE + 0x03)  /* Line Control */
#define UART_LSR    (UART_BASE + 0x05)  /* Line Status */

#define LSR_TX_EMPTY  (1 << 5)  /* THR empty */
#define LSR_RX_READY  (1 << 0)  /* Data ready */

void uart_init(void)
{
    /* Disable interrupts */
    mmio_write8(UART_IER, 0x00);
    /* Enable DLAB (set baud rate divisor) */
    mmio_write8(UART_LCR, 0x80);
    /* Set divisor to 1 (115200 baud with 1.8432 MHz clock) */
    mmio_write8(UART_BASE + 0x00, 0x01);  /* DLL */
    mmio_write8(UART_BASE + 0x01, 0x00);  /* DLM */
    /* 8 bits, no parity, one stop bit (8N1), clear DLAB */
    mmio_write8(UART_LCR, 0x03);
    /* Enable FIFO, clear them, 14-byte threshold */
    mmio_write8(UART_FCR, 0xC7);
    /* Enable receive interrupts */
    mmio_write8(UART_IER, 0x01);
}

void uart_putchar(char c)
{
    /* Wait for transmit holding register to be empty */
    while ((mmio_read8(UART_LSR) & LSR_TX_EMPTY) == 0)
        ;
    mmio_write8(UART_THR, c);
}

int uart_getchar(void)
{
    if (mmio_read8(UART_LSR) & LSR_RX_READY)
        return mmio_read8(UART_RBR);
    return -1;
}
```

### virtio-mmio Devices

virtio MMIO transport devices are at `0x10001000` through `0x10008000`, each occupying 0x1000 bytes. The specific virtio device types are configured when QEMU is launched (e.g., `-device virtio-blk-device`, `-device virtio-net-device`).

### Devices NOT Present

Unlike x86, the RISC-V QEMU `virt` machine does **not** have:

- VGA text mode framebuffer (no 0xB8000)
- PIT (8254 Programmable Interval Timer)
- PS/2 keyboard/mouse controller
- PIC (8259A Programmable Interrupt Controller)
- APIC / IO-APIC
- ISA bus

---

## Firmware

### Device Tree Blob (DTB)

RISC-V uses the Flattened Device Tree (FDT) format -- the same format used on ARM platforms. The DTB pointer is passed in register `a1` at kernel entry.

The DTB describes:
- Memory regions (size and location of RAM)
- CPU topology (number of harts, ISA extensions)
- Interrupt controller configuration (PLIC, CLINT addresses)
- UART, virtio, and PCIe device addresses and interrupt mappings
- Chosen node (boot arguments, stdout-path)

```c
/* Validate the DTB magic number */
#define FDT_MAGIC   0xD00DFEED

int dtb_validate(void *dtb)
{
    uint32_t magic = __builtin_bswap32(*(uint32_t *)dtb);
    return (magic == FDT_MAGIC) ? 0 : -1;
}
```

The DTB uses big-endian encoding regardless of the CPU endianness. Use byte-swap functions when reading DTB fields.

The kernel must implement `arch_firmware_parse()` to traverse the FDT and extract:
- Memory regions (for the PMM)
- Interrupt controller base addresses (PLIC, CLINT)
- UART base address
- PCI ECAM base address
- Boot command line (`/chosen/bootargs`)

### SBI (Supervisor Binary Interface)

SBI provides an `ecall`-based interface from S-mode to M-mode (implemented by OpenSBI). The kernel uses SBI for operations that require M-mode privilege.

**SBI Calling Convention:**

| Register | Purpose |
|----------|---------|
| `a7` | Extension ID (EID) |
| `a6` | Function ID (FID) |
| `a0`-`a5` | Arguments |
| `a0` | Return error code |
| `a1` | Return value |

**SBI Extensions:**

| Extension | EID | Functions | Description |
|-----------|-----|-----------|-------------|
| Legacy Console | `0x01` | putchar | Early console output (deprecated but widely supported) |
| Timer | `0x54494D45` ("TIME") | set_timer (FID 0) | Program the timer interrupt |
| IPI | `0x735049` ("sPI") | send_ipi (FID 0) | Send inter-processor interrupt |
| RFENCE | `0x52464E43` ("RFNC") | remote_sfence_vma (FID 0), etc. | Remote TLB flush |
| HSM | `0x48534D` ("HSM") | hart_start (FID 0), hart_stop (FID 1), hart_get_status (FID 2) | Hart State Management |
| SRST | `0x53525354` ("SRST") | system_reset (FID 0) | System reset/shutdown |
| Base | `0x10` | get_sbi_spec_version (FID 0), get_sbi_impl_id (FID 1), etc. | Query SBI version/capabilities |

**Generic SBI call wrapper:**

```c
struct sbiret {
    long error;
    long value;
};

static inline struct sbiret sbi_ecall(long eid, long fid,
                                       long a0, long a1, long a2,
                                       long a3, long a4, long a5)
{
    register long r_a0 asm("a0") = a0;
    register long r_a1 asm("a1") = a1;
    register long r_a2 asm("a2") = a2;
    register long r_a3 asm("a3") = a3;
    register long r_a4 asm("a4") = a4;
    register long r_a5 asm("a5") = a5;
    register long r_a6 asm("a6") = fid;
    register long r_a7 asm("a7") = eid;

    asm volatile("ecall"
                 : "+r"(r_a0), "+r"(r_a1)
                 : "r"(r_a2), "r"(r_a3), "r"(r_a4),
                   "r"(r_a5), "r"(r_a6), "r"(r_a7)
                 : "memory");

    struct sbiret ret = { .error = r_a0, .value = r_a1 };
    return ret;
}

/* SBI error codes */
#define SBI_SUCCESS               0
#define SBI_ERR_FAILED           -1
#define SBI_ERR_NOT_SUPPORTED    -2
#define SBI_ERR_INVALID_PARAM    -3
#define SBI_ERR_DENIED           -4
#define SBI_ERR_INVALID_ADDRESS  -5
#define SBI_ERR_ALREADY_AVAILABLE -6
```

---

## Context Switch Assembly

The context switch saves and restores only the **callee-saved registers** (s0-s11, ra, sp). Caller-saved registers are already saved on the stack by the C calling convention before `arch_context_switch()` is called.

```asm
/* kernel/arch/riscv64/sched/context_switch.S
 *
 * void arch_context_switch(uint64_t *old_sp_ptr, uint64_t new_sp);
 *   a0 = pointer to old process's saved SP location
 *   a1 = new process's saved SP value
 */

.global arch_context_switch
arch_context_switch:
    /* ---- Save callee-saved registers onto the current (old) stack ---- */
    addi    sp, sp, -112        /* Allocate 14 * 8 = 112 bytes */

    sd      ra,  0(sp)
    sd      s0,  8(sp)
    sd      s1, 16(sp)
    sd      s2, 24(sp)
    sd      s3, 32(sp)
    sd      s4, 40(sp)
    sd      s5, 48(sp)
    sd      s6, 56(sp)
    sd      s7, 64(sp)
    sd      s8, 72(sp)
    sd      s9, 80(sp)
    sd      s10, 88(sp)
    sd      s11, 96(sp)

    /* Save sstatus (for interrupt enable state across switch) */
    csrr    t0, sstatus
    sd      t0, 104(sp)

    /* ---- Store current SP into *old_sp_ptr ---- */
    sd      sp, 0(a0)

    /* ---- Switch to new stack ---- */
    mv      sp, a1

    /* ---- Restore callee-saved registers from the new stack ---- */
    ld      t0, 104(sp)
    csrw    sstatus, t0

    ld      ra,  0(sp)
    ld      s0,  8(sp)
    ld      s1, 16(sp)
    ld      s2, 24(sp)
    ld      s3, 32(sp)
    ld      s4, 40(sp)
    ld      s5, 48(sp)
    ld      s6, 56(sp)
    ld      s7, 64(sp)
    ld      s8, 72(sp)
    ld      s9, 80(sp)
    ld      s10, 88(sp)
    ld      s11, 96(sp)

    addi    sp, sp, 112         /* Deallocate frame */

    ret                         /* Jump to restored ra */
```

### Initial Context Setup

When creating a new process, `arch_setup_initial_context()` builds a fake stack frame so that the first `arch_context_switch()` to this process will "restore" the constructed state and jump to the entry function:

```c
void arch_setup_initial_context(struct process *proc, void (*entry)(void))
{
    uint64_t *sp = (uint64_t *)(proc->kernel_stack + ARCH_STACK_SIZE);

    /* Build the frame that arch_context_switch will "restore" */
    sp -= 14;  /* 14 slots: ra, s0-s11, sstatus */

    sp[0]  = (uint64_t)entry;   /* ra = entry point */
    sp[1]  = 0;                 /* s0 */
    sp[2]  = 0;                 /* s1 */
    sp[3]  = 0;                 /* s2 */
    sp[4]  = 0;                 /* s3 */
    sp[5]  = 0;                 /* s4 */
    sp[6]  = 0;                 /* s5 */
    sp[7]  = 0;                 /* s6 */
    sp[8]  = 0;                 /* s7 */
    sp[9]  = 0;                 /* s8 */
    sp[10] = 0;                 /* s9 */
    sp[11] = 0;                 /* s10 */
    sp[12] = 0;                 /* s11 */
    sp[13] = (1UL << 8);       /* sstatus: SPP=1 (return to S-mode), SIE=0 */

    proc->saved_sp = (uint64_t)sp;
}
```

---

## Trap Handler

All traps (exceptions and interrupts) in S-mode vector through the address in `stvec`. The trap entry code must save all caller-saved registers (the C trap handler may clobber them), read `scause` and `stval`, and dispatch to the appropriate handler.

```asm
/* kernel/arch/riscv64/cpu/trap_entry.S */

.global trap_entry
.align 4
trap_entry:
    /* Save all general-purpose registers onto the kernel stack.
     * sscratch is used to hold the kernel SP when trapping from U-mode. */

    /* Swap sp and sscratch if coming from U-mode */
    csrrw   sp, sscratch, sp

    /* Allocate trap frame (32 regs * 8 bytes + sepc + sstatus + stval = 280 bytes) */
    addi    sp, sp, -280

    /* Save x1-x31 (x0 is always zero, no need to save) */
    sd      x1,   0(sp)
    sd      x2,   8(sp)    /* original sp (or sscratch value) */
    sd      x3,  16(sp)
    sd      x4,  24(sp)
    sd      x5,  32(sp)
    sd      x6,  40(sp)
    sd      x7,  48(sp)
    sd      x8,  56(sp)
    sd      x9,  64(sp)
    sd      x10, 72(sp)
    sd      x11, 80(sp)
    sd      x12, 88(sp)
    sd      x13, 96(sp)
    sd      x14, 104(sp)
    sd      x15, 112(sp)
    sd      x16, 120(sp)
    sd      x17, 128(sp)
    sd      x18, 136(sp)
    sd      x19, 144(sp)
    sd      x20, 152(sp)
    sd      x21, 160(sp)
    sd      x22, 168(sp)
    sd      x23, 176(sp)
    sd      x24, 184(sp)
    sd      x25, 192(sp)
    sd      x26, 200(sp)
    sd      x27, 208(sp)
    sd      x28, 216(sp)
    sd      x29, 224(sp)
    sd      x30, 232(sp)
    sd      x31, 240(sp)

    /* Save CSRs */
    csrr    t0, sepc
    sd      t0, 248(sp)
    csrr    t0, sstatus
    sd      t0, 256(sp)
    csrr    t0, stval
    sd      t0, 264(sp)
    csrr    t0, scause
    sd      t0, 272(sp)

    /* Call C handler: trap_dispatch(scause, stval, sepc, trap_frame *) */
    csrr    a0, scause
    csrr    a1, stval
    csrr    a2, sepc
    mv      a3, sp          /* pointer to trap frame */
    call    trap_dispatch

    /* Restore CSRs */
    ld      t0, 248(sp)
    csrw    sepc, t0
    ld      t0, 256(sp)
    csrw    sstatus, t0

    /* Restore general-purpose registers */
    ld      x1,   0(sp)
    ld      x3,  16(sp)
    ld      x4,  24(sp)
    ld      x5,  32(sp)
    ld      x6,  40(sp)
    ld      x7,  48(sp)
    ld      x8,  56(sp)
    ld      x9,  64(sp)
    ld      x10, 72(sp)
    ld      x11, 80(sp)
    ld      x12, 88(sp)
    ld      x13, 96(sp)
    ld      x14, 104(sp)
    ld      x15, 112(sp)
    ld      x16, 120(sp)
    ld      x17, 128(sp)
    ld      x18, 136(sp)
    ld      x19, 144(sp)
    ld      x20, 152(sp)
    ld      x21, 160(sp)
    ld      x22, 168(sp)
    ld      x23, 176(sp)
    ld      x24, 184(sp)
    ld      x25, 192(sp)
    ld      x26, 200(sp)
    ld      x27, 208(sp)
    ld      x28, 216(sp)
    ld      x29, 224(sp)
    ld      x30, 232(sp)
    ld      x31, 240(sp)

    addi    sp, sp, 280

    /* Swap back sp and sscratch for U-mode return */
    csrrw   sp, sscratch, sp

    sret
```

### C Trap Dispatcher

```c
/* kernel/arch/riscv64/cpu/trap.c */

void trap_dispatch(uint64_t scause, uint64_t stval,
                   uint64_t sepc, void *frame)
{
    int is_interrupt = (scause >> 63) & 1;
    uint64_t code = scause & 0x7FFFFFFFFFFFFFFFUL;

    if (is_interrupt) {
        switch (code) {
        case 1:  /* Supervisor software interrupt */
            handle_software_interrupt();
            break;
        case 5:  /* Supervisor timer interrupt */
            handle_timer_interrupt();
            break;
        case 9:  /* Supervisor external interrupt */
            handle_external_interrupt();  /* Calls plic_claim/complete */
            break;
        default:
            panic("Unknown interrupt: %lu", code);
        }
    } else {
        switch (code) {
        case 8:  /* Environment call from U-mode (syscall) */
            handle_syscall(frame);
            break;
        case 12: /* Instruction page fault */
        case 13: /* Load page fault */
        case 15: /* Store/AMO page fault */
            handle_page_fault(scause, stval, sepc);
            break;
        case 2:  /* Illegal instruction */
            handle_illegal_instruction(stval, sepc);
            break;
        default:
            panic("Unhandled exception: cause=%lu stval=0x%lx sepc=0x%lx",
                  code, stval, sepc);
        }
    }
}
```

---

## Initial Page Table Setup

At boot, paging is disabled (`satp.MODE = 0`, bare mode). The kernel must set up initial Sv39 page tables before jumping to higher-half addresses.

### Strategy

Use **1GB gigapages** (level-2 leaf PTEs) for the initial mapping. This requires only a single root page table (level 2) -- no level 1 or level 0 tables needed.

Two mappings are required:

1. **Identity map**: Physical address `0x80000000` maps to virtual address `0x80000000` (so the kernel can continue executing after enabling paging).
2. **Higher-half map**: Physical address `0x80000000` maps to virtual address `KERNEL_VBASE` (`0xFFFFFFC000000000`).

### Implementation

```c
/* kernel/arch/riscv64/mm/early_paging.c */

/* Root page table -- must be page-aligned */
__attribute__((aligned(4096)))
uint64_t boot_page_table[512];

void setup_early_paging(void)
{
    /* Clear the root page table */
    for (int i = 0; i < 512; i++)
        boot_page_table[i] = 0;

    /*
     * Identity map: VA 0x80000000 -> PA 0x80000000 (1GB gigapage)
     *
     * VA 0x80000000:
     *   VPN[2] = (0x80000000 >> 30) & 0x1FF = 2
     *
     * PTE = PA_TO_PTE(0x80000000) | PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D
     */
    boot_page_table[2] = PA_TO_PTE(0x80000000UL)
                        | PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;

    /*
     * Higher-half map: VA 0xFFFFFFC000000000 -> PA 0x80000000 (1GB gigapage)
     *
     * VA 0xFFFFFFC000000000:
     *   VPN[2] = (0xFFFFFFC000000000 >> 30) & 0x1FF = 256
     *
     * Note: For Sv39, bits 63:39 are sign-extension of bit 38.
     * 0xFFFFFFC000000000 has bit 38 = 1, so VPN[2] = 0x100 = 256.
     */
    boot_page_table[256] = PA_TO_PTE(0x80000000UL)
                         | PTE_V | PTE_R | PTE_W | PTE_X | PTE_A | PTE_D;

    /*
     * Activate Sv39 paging:
     *   satp = SATP_SV39 | (root_table_phys >> 12)
     */
    uint64_t root_ppn = (uint64_t)boot_page_table >> 12;
    uint64_t satp_val = SATP_SV39 | root_ppn;

    asm volatile("csrw satp, %0" : : "r"(satp_val));
    asm volatile("sfence.vma zero, zero" ::: "memory");
}
```

After paging is enabled, the identity map keeps the currently executing code valid. Once the kernel relocates its program counter to the higher-half virtual addresses, the identity map entry can be removed.

### Linker Script Excerpt

```ld
/* kernel/arch/riscv64/linker.ld */

ENTRY(_start)

KERNEL_VBASE = 0xFFFFFFC000000000;
KERNEL_PHYS  = 0x80200000;
KERNEL_OFFSET = KERNEL_VBASE - 0x80000000;

SECTIONS
{
    . = KERNEL_PHYS;

    .text.init : AT(KERNEL_PHYS)
    {
        *(.text.init)
    }

    . = KERNEL_VBASE + (. - KERNEL_PHYS);

    .text : AT(ADDR(.text) - KERNEL_OFFSET)
    {
        *(.text .text.*)
    }

    .rodata : AT(ADDR(.rodata) - KERNEL_OFFSET)
    {
        *(.rodata .rodata.*)
    }

    .data : AT(ADDR(.data) - KERNEL_OFFSET)
    {
        *(.data .data.*)
    }

    . = ALIGN(8);
    PROVIDE(__global_pointer$ = . + 0x800);

    .sdata : AT(ADDR(.sdata) - KERNEL_OFFSET)
    {
        *(.sdata .sdata.*)
    }

    . = ALIGN(4096);
    PROVIDE(__bss_start = .);
    .bss : AT(ADDR(.bss) - KERNEL_OFFSET)
    {
        *(.bss .bss.*)
        *(COMMON)
    }
    . = ALIGN(4096);
    PROVIDE(__bss_end = .);

    PROVIDE(__kernel_end = .);
}
```

---

## QEMU Test Command

```bash
qemu-system-riscv64 \
    -machine virt \
    -bios default \
    -kernel kernel.bin \
    -serial stdio \
    -display none \
    -no-reboot \
    -m 128M \
    -nographic
```

**Flag explanations:**

| Flag | Purpose |
|------|---------|
| `-machine virt` | QEMU RISC-V virtual platform |
| `-bios default` | Use bundled OpenSBI firmware (boots kernel in S-mode) |
| `-kernel kernel.bin` | Kernel binary loaded at 0x80200000 |
| `-serial stdio` | Route UART to terminal stdin/stdout |
| `-display none` | No graphical display (no VGA on RISC-V virt) |
| `-no-reboot` | Stop on triple fault instead of rebooting |
| `-m 128M` | 128 MB of RAM |
| `-nographic` | Disable graphical output, combine with `-serial stdio` |

**Debug variant (with GDB stub):**

```bash
qemu-system-riscv64 \
    -machine virt \
    -bios default \
    -kernel kernel.bin \
    -serial stdio \
    -display none \
    -no-reboot \
    -m 128M \
    -nographic \
    -s -S
```

Then connect with: `riscv64-elf-gdb kernel.elf -ex "target remote :1234"`

**Multi-hart variant:**

```bash
qemu-system-riscv64 \
    -machine virt \
    -bios default \
    -kernel kernel.bin \
    -serial stdio \
    -display none \
    -no-reboot \
    -m 128M \
    -nographic \
    -smp 4
```

---

## Interrupt Enable / Disable

```c
/* Implements arch_enable_interrupts */
static inline void arch_enable_interrupts(void)
{
    asm volatile("csrsi sstatus, 0x2");  /* Set SIE bit (bit 1) */
}

/* Implements arch_disable_interrupts */
static inline void arch_disable_interrupts(void)
{
    asm volatile("csrci sstatus, 0x2");  /* Clear SIE bit (bit 1) */
}

/* Implements arch_save_irq_state */
static inline uint64_t arch_save_irq_state(void)
{
    uint64_t sstatus;
    asm volatile("csrr %0, sstatus" : "=r"(sstatus));
    asm volatile("csrci sstatus, 0x2");
    return sstatus & 0x2;  /* Return just the SIE bit */
}

/* Implements arch_restore_irq_state */
static inline void arch_restore_irq_state(uint64_t state)
{
    if (state & 0x2)
        asm volatile("csrsi sstatus, 0x2");
}

/* Implements arch_halt */
static inline void arch_halt(void)
{
    asm volatile("wfi");
}
```

---

## CSR Access Helpers

```c
/* Generic CSR read/write macros using GNU C statement expressions */

#define csr_read(csr)                                   \
({                                                      \
    uint64_t __val;                                     \
    asm volatile("csrr %0, " #csr : "=r"(__val));      \
    __val;                                              \
})

#define csr_write(csr, val)                             \
({                                                      \
    asm volatile("csrw " #csr ", %0" : : "r"(val));    \
})

#define csr_set(csr, bits)                              \
({                                                      \
    asm volatile("csrs " #csr ", %0" : : "r"(bits));   \
})

#define csr_clear(csr, bits)                            \
({                                                      \
    asm volatile("csrc " #csr ", %0" : : "r"(bits));   \
})
```

---

## HAL Function Mapping Summary

This table maps each HAL contract function to its RISC-V implementation mechanism:

| HAL Function | RISC-V Implementation |
|---|---|
| `arch_boot_init()` | `boot.S` -> `kernel_main(hartid, dtb)` |
| `arch_serial_early_init()` | No-op (SBI console available immediately) |
| `arch_serial_putchar()` | SBI legacy `ecall` (extension 0x01), then UART after init |
| `arch_parse_memory_map()` | Parse DTB `/memory` node |
| `arch_parse_modules()` | Parse DTB `/chosen` node |
| `arch_get_hw_summary()` | Build from DTB data |
| `arch_cpu_init()` | Read hart capabilities, configure `sstatus` |
| `arch_interrupt_init()` | Set `stvec`, init PLIC, enable `sie` bits |
| `arch_set_interrupt_handler()` | Register in handler table, enable in PLIC |
| `arch_enable_interrupts()` | `csrsi sstatus, 0x2` |
| `arch_disable_interrupts()` | `csrci sstatus, 0x2` |
| `arch_save_irq_state()` | `csrr sstatus`, then clear SIE |
| `arch_restore_irq_state()` | Conditionally `csrsi sstatus, 0x2` |
| `arch_halt()` | `wfi` instruction |
| `arch_mmu_init()` | Set up Sv39 page tables, write `satp` |
| `arch_map_page()` | Walk/allocate Sv39 page tables, set PTE |
| `arch_unmap_page()` | Clear PTE, `sfence.vma` |
| `arch_flush_tlb()` | `sfence.vma addr, zero` |
| `arch_flush_tlb_all()` | `sfence.vma zero, zero` |
| `arch_create_address_space()` | Allocate root page table page |
| `arch_switch_address_space()` | Write `satp` CSR + `sfence.vma` |
| `arch_context_switch()` | Save/restore s0-s11, ra, sp (assembly) |
| `arch_setup_initial_context()` | Build fake stack frame with entry in ra slot |
| `arch_set_kernel_stack()` | Store in per-hart `sscratch` (for U->S traps) |
| `arch_default_user_flags()` | `sstatus` with SPP=0 (U-mode), SPIE=1 |
| `arch_timer_init()` | SBI set_timer, enable STIE in `sie` |
| `arch_timer_get_ticks()` | Read `mtime` via CLINT MMIO or `rdtime` instruction |
| `arch_timer_get_frequency()` | Parse `timebase-frequency` from DTB `/cpus` node |
| `arch_io_read8/16/32()` | Volatile MMIO pointer dereference |
| `arch_io_write8/16/32()` | Volatile MMIO pointer dereference |
| `arch_get_firmware_type()` | Return `FIRMWARE_DEVICE_TREE` |
| `arch_pci_config_read32()` | ECAM MMIO read (base from DTB) |
| `arch_firmware_parse()` | FDT traversal |

---

## Acceptance Criteria

The RISC-V HAL implementation is complete when all of the following tests pass on `qemu-system-riscv64 -machine virt`:

### Boot Tests

1. **S-mode active**: Kernel entry code reads `sstatus.SPP` and confirms execution in S-mode. Attempting a privileged M-mode instruction (e.g., `csrr mstatus`) triggers an illegal instruction exception, confirming S-mode.

2. **Hart parking**: With `-smp 4`, only hart 0 reaches `kernel_main()`. Harts 1-3 remain in the `wfi` parking loop and do not corrupt shared state.

3. **BSS cleared**: All variables in `.bss` read as zero after boot. A test variable initialized to a non-zero value before BSS clear must read zero after.

4. **DTB parsed**: The DTB magic (`0xD00DFEED`) is validated. Memory size reported from DTB `/memory` node matches QEMU `-m` parameter. At least one memory region is extracted.

5. **Boot banner**: `"AUTON Kernel booting..."` is printed to serial (first via SBI putchar, then via UART after driver init).

### Interrupt and Trap Tests

6. **Trap vectors set**: `stvec` CSR contains the address of `trap_entry`. An `ecall` from S-mode triggers the trap handler and returns correctly.

7. **PLIC initialized**: PLIC threshold set to 0, UART interrupt (IRQ 10) enabled. Writing to the UART triggers an external interrupt that is claimed and completed through the PLIC.

8. **Timer working**: SBI `set_timer` programs a timer interrupt. The supervisor timer interrupt fires (scause = 0x8000000000000005), and the handler successfully reprograms the next tick.

9. **Page fault handling**: Accessing an unmapped virtual address triggers a load/store page fault (scause 13 or 15). The handler receives the correct faulting address in `stval` and the faulting instruction address in `sepc`.

### Memory Management Tests

10. **Sv39 paging active**: `satp.MODE` reads 8 (Sv39). Virtual address translation is working: kernel code executes from higher-half addresses (`>= 0xFFFFFFC000000000`).

11. **Page mapping**: `arch_map_page()` creates a valid Sv39 PTE. `arch_get_physical()` returns the correct physical address for the mapped virtual address.

12. **TLB flush**: After unmapping a page and calling `sfence.vma`, accessing the unmapped address triggers a page fault (not a stale TLB hit).

### I/O Tests

13. **UART output**: `uart_putchar()` writes characters to the NS16550A at `0x10000000`. Characters appear on the QEMU serial console.

14. **UART input**: `uart_getchar()` reads characters typed into the QEMU serial console. The UART receive interrupt fires through the PLIC.

### Context Switch Tests

15. **Context switch**: Two kernel threads are created with `arch_setup_initial_context()`. `arch_context_switch()` successfully switches between them. Each thread maintains its own stack and register state. The `s0`-`s11` registers are preserved across the switch.

### SBI Tests

16. **SBI functional**: `sbi_ecall()` with the Base extension (EID 0x10, FID 0) returns a valid SBI specification version. Legacy console putchar (EID 0x01) outputs a character.
