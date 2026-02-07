# Hardware Abstraction Layer (HAL) Contract

## Overview

The HAL is the boundary between portable kernel code and architecture-specific code. All kernel subsystems call HAL interfaces — never raw architecture instructions or registers directly. Each target architecture provides a complete HAL implementation in `kernel/arch/<arch>/`.

Adding a new architecture means implementing this contract. No portable kernel code needs to change.

## HAL Interface Categories

### 1. Boot HAL (`kernel/arch/<arch>/boot/`)

Entry from bootloader, early hardware setup, and handoff to portable `kernel_main()`.

```c
/* Called by bootloader/firmware. Sets up enough state to call kernel_main(). */
void arch_boot_init(void *boot_params);

/* Parse bootloader-provided memory map into portable format. */
int arch_parse_memory_map(boot_info_t *info, boot_mmap_entry_t *entries, uint32_t *count);

/* Parse boot modules (initramfs, etc.) */
int arch_parse_modules(boot_info_t *info, boot_module_t *modules, uint32_t *count);

/* Collect hardware summary for SLM consumption. */
void arch_get_hw_summary(hw_summary_t *summary);

/* Enable early serial output before full driver initialization. */
void arch_serial_early_init(void);
void arch_serial_putchar(char c);
```

The boot sequence: `arch_boot_init()` → early setup → `kernel_main(boot_info_t *info)`.

### 2. CPU HAL (`kernel/arch/<arch>/cpu/`)

CPU feature detection, interrupt management, and control.

```c
/* CPU feature detection and mode setup. */
void arch_cpu_init(void);

/* Set up interrupt/exception dispatch table. */
void arch_interrupt_init(void);

/* Register a handler for a specific interrupt vector. */
void arch_set_interrupt_handler(uint32_t vector, void (*handler)(void *), void *data);

/* Enable/disable hardware interrupts. */
void arch_enable_interrupts(void);
void arch_disable_interrupts(void);

/* Save and restore interrupt state (for nested critical sections). */
uint64_t arch_save_irq_state(void);
void arch_restore_irq_state(uint64_t state);

/* Halt CPU until next interrupt (used by idle process). */
void arch_halt(void);

/* Panic: halt all CPUs, print diagnostic. */
void arch_panic(const char *message) __attribute__((noreturn));
```

### 3. MMU HAL (`kernel/arch/<arch>/mm/`)

Page table management. Portable code (PMM, VMM) calls these to manipulate virtual memory.

```c
/* Initialize page tables and enable paging/MMU. */
void arch_mmu_init(void);

/* Map a virtual page to a physical frame. */
int arch_map_page(uint64_t virt, uint64_t phys, uint64_t flags);

/* Unmap a virtual page. */
void arch_unmap_page(uint64_t virt);

/* Translate virtual address to physical. Returns 0 on failure. */
uint64_t arch_get_physical(uint64_t virt);

/* Invalidate a single TLB entry. */
void arch_flush_tlb(uint64_t virt);

/* Invalidate all TLB entries. */
void arch_flush_tlb_all(void);

/* Create a new address space (allocate root page table). Returns physical address. */
uint64_t arch_create_address_space(void);

/* Switch to a different address space. */
void arch_switch_address_space(uint64_t root_table_phys);

/* Destroy an address space (free root page table). */
void arch_destroy_address_space(uint64_t root_table_phys);
```

Architecture-defined constants:
- `ARCH_PAGE_SIZE` — typically 4096
- `ARCH_KERNEL_VBASE` — kernel virtual base address
- `ARCH_USER_VBASE`, `ARCH_USER_VTOP` — user space boundaries
- `ARCH_PT_LEVELS` — number of page table levels

### 4. Context Switch HAL (`kernel/arch/<arch>/sched/`)

Save/restore CPU state for process switching.

```c
/* Architecture-specific CPU context. Defined per-arch in <arch/arch_context.h>. */
struct cpu_context;  /* opaque to portable code */

/* Switch from current process to next. Saves/restores full register set. */
void arch_context_switch(uint64_t *old_sp_ptr, uint64_t new_sp);

/* Set up initial context for a new process so it starts executing at entry(). */
void arch_setup_initial_context(struct process *proc, void (*entry)(void));

/* Set the kernel stack for privilege transitions (e.g., TSS on x86_64). */
void arch_set_kernel_stack(uint64_t stack_top);

/* Get default flags register value for new user processes. */
uint64_t arch_default_user_flags(void);
```

### 5. Timer HAL (`kernel/arch/<arch>/timer/`)

Periodic timer for scheduler preemption.

```c
/* Initialize the system timer at the given frequency. */
void arch_timer_init(uint32_t frequency_hz);

/* Get current tick count (monotonic). */
uint64_t arch_timer_get_ticks(void);

/* Get timer frequency in Hz. */
uint32_t arch_timer_get_frequency(void);
```

The timer interrupt handler calls the portable `sched_tick()`.

### 6. I/O HAL (`kernel/arch/<arch>/io/`)

Hardware I/O access. On x86, this wraps port I/O (inb/outb) and MMIO. On ARM and RISC-V, everything is MMIO.

```c
/* Read/write 8/16/32-bit values from hardware.
 * On x86: port I/O if addr < 0x10000, MMIO otherwise.
 * On ARM/RISC-V: always MMIO (volatile pointer dereference). */
uint8_t  arch_io_read8(uint64_t addr);
uint16_t arch_io_read16(uint64_t addr);
uint32_t arch_io_read32(uint64_t addr);

void arch_io_write8(uint64_t addr, uint8_t value);
void arch_io_write16(uint64_t addr, uint16_t value);
void arch_io_write32(uint64_t addr, uint32_t value);
```

### 7. Device Discovery HAL (`kernel/arch/<arch>/dev/`)

Firmware and bus access for device enumeration.

```c
/* Firmware type this architecture uses. */
typedef enum {
    FIRMWARE_ACPI,         /* x86, some ARM servers */
    FIRMWARE_DEVICE_TREE,  /* ARM, RISC-V */
    FIRMWARE_NONE,         /* minimal/embedded */
} firmware_type_t;

firmware_type_t arch_get_firmware_type(void);

/* PCI configuration space access (mechanism varies by architecture). */
uint32_t arch_pci_config_read32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset);
void arch_pci_config_write32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset, uint32_t val);

/* Parse firmware tables to discover devices.
 * On x86: ACPI RSDP -> RSDT/XSDT -> MADT, MCFG, etc.
 * On ARM/RISC-V: FDT (Flattened Device Tree) traversal. */
int arch_firmware_parse(void *boot_firmware_data);
```

## Memory Layout Contract

Each architecture defines in `kernel/arch/<arch>/include/arch_memory.h`:

```c
#define ARCH_KERNEL_VBASE    /* Virtual base of kernel space */
#define ARCH_USER_VBASE      /* Start of user space (usually 0) */
#define ARCH_USER_VTOP       /* End of user space */
#define ARCH_KERNEL_LOAD     /* Physical load address */
#define ARCH_PAGE_SIZE       /* Page size (typically 4096) */
#define ARCH_PT_LEVELS       /* Number of page table levels */
#define ARCH_STACK_SIZE      /* Default kernel stack size per process */
```

## Calling Convention Contract

Each architecture follows its platform ABI:
- x86_64: System V AMD64 ABI (RDI, RSI, RDX, RCX, R8, R9)
- AArch64: AAPCS64 (X0-X7)
- RISC-V: Standard RISC-V calling convention (a0-a7)

Portable kernel code does not need to know the calling convention — the C compiler handles it.

## Directory Structure

```
kernel/
├── arch/
│   ├── x86_64/
│   │   ├── boot/        # Multiboot2 entry, GDT, IDT, long mode
│   │   ├── cpu/         # CPUID, PIC/APIC, MSRs
│   │   ├── mm/          # PML4 page tables, CR3, invlpg
│   │   ├── sched/       # Context switch (push/pop x86_64 regs)
│   │   ├── timer/       # PIT 8254
│   │   ├── io/          # Port I/O (inb/outb) + MMIO
│   │   ├── dev/         # ACPI parsing, PCI config via 0xCF8/0xCFC
│   │   ├── include/     # arch_context.h, arch_memory.h
│   │   └── toolchain.mk
│   ├── aarch64/
│   │   ├── boot/        # DTB/UEFI, EL2→EL1 transition
│   │   ├── cpu/         # GIC, exception vectors (VBAR_EL1)
│   │   ├── mm/          # Translation tables, TTBR0/TTBR1
│   │   ├── sched/       # Context switch (X19-X30, SP)
│   │   ├── timer/       # ARM architected timer
│   │   ├── io/          # MMIO wrappers
│   │   ├── dev/         # FDT parsing, ECAM PCI
│   │   ├── include/     # arch_context.h, arch_memory.h
│   │   └── toolchain.mk
│   └── riscv64/
│       ├── boot/        # SBI+DTB, S-mode entry
│       ├── cpu/         # PLIC, trap vectors (stvec)
│       ├── mm/          # Sv39 page tables, satp CSR
│       ├── sched/       # Context switch (s0-s11, ra, sp)
│       ├── timer/       # CLINT timer
│       ├── io/          # MMIO wrappers
│       ├── dev/         # FDT parsing, ECAM PCI
│       ├── include/     # arch_context.h, arch_memory.h
│       └── toolchain.mk
├── boot/           # Portable boot coordination (calls arch_boot_init)
├── mm/             # Portable PMM, slab (calls arch MMU HAL)
├── sched/          # Portable scheduler (calls arch_context_switch)
├── ipc/            # Fully portable
├── dev/            # Portable device framework (calls arch discovery HAL)
├── slm/            # Fully portable
├── drivers/
│   ├── common/     # Portable: PCI bus driver, AHCI, NVMe, virtio, e1000
│   └── arch/       # Arch-specific: 16550/PL011, PIT/ARM timer, VGA, PS/2
├── fs/             # Fully portable
├── net/            # Fully portable
├── pkg/            # Fully portable
├── sys/            # Fully portable
├── include/
│   └── arch/       # HAL headers (arch_boot.h, arch_cpu.h, arch_mmu.h, etc.)
├── lib/            # Portable utilities
├── Makefile        # Top-level: includes arch/$(ARCH)/toolchain.mk
└── linker.ld       # May need per-arch variants
```

## Adding a New Architecture

To add support for a new architecture (e.g., `mips64`):

1. Create `kernel/arch/mips64/` with all HAL subdirectories
2. Implement every function declared in this HAL contract
3. Create `arch/mips64.md` in the kernel spec with architecture details
4. Add an `ArchProfile` entry in `orchestrator/arch_registry.py`
5. Set `arch = "mips64"` in `auton.toml`

No changes needed to portable kernel code, agent prompts, or the orchestration framework.
