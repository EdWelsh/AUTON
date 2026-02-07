# Boot Subsystem Specification

## Overview

The boot subsystem handles architecture-specific early initialization (via the Boot HAL), parses boot information into portable structures, and hands control to the C kernel entry point. After basic kernel initialization, the boot subsystem enumerates hardware and passes a structured hardware report to the SLM runtime for intelligent driver loading and system configuration.

Architecture-specific boot details (boot protocol, descriptor tables, mode transitions, assembly entry points) are defined in `arch/<arch>.md` and implemented in `kernel/arch/<arch>/boot/`. This spec covers the **portable** boot contract.

## Data Structures

### Portable Boot Information

These structures are architecture-independent. The architecture's boot HAL (`arch_parse_memory_map()`, `arch_parse_modules()`) fills them from whatever boot protocol the architecture uses (Multiboot2 on x86, Device Tree on ARM/RISC-V, etc.).

```c
/* Portable memory map entry (filled by arch_parse_memory_map) */
typedef struct boot_mmap_entry {
    uint64_t base_addr;
    uint64_t length;
    uint32_t type;          /* 1=available, 2=reserved, 3=firmware reclaimable */
    uint32_t reserved;
} __attribute__((packed)) boot_mmap_entry_t;

/* Parsed memory map for kernel use */
typedef struct boot_mmap {
    boot_mmap_entry_t entries[128];
    uint32_t          count;
    uint64_t          total_available;   /* total usable bytes */
    uint64_t          highest_address;   /* highest usable address */
} boot_mmap_t;

/* Module loaded by bootloader (e.g., initramfs, SLM weights) */
typedef struct boot_module {
    uint64_t start;         /* physical start address */
    uint64_t end;           /* physical end address */
    char     cmdline[256];  /* module command line string */
} boot_module_t;

/* Firmware data pointer (ACPI RSDP on x86, DTB on ARM/RISC-V) */
typedef struct boot_firmware {
    uint64_t data_address;  /* physical address of firmware data */
    int      type;          /* 0=none, 1=ACPI 1.0, 2=ACPI 2.0+, 3=Device Tree */
} boot_firmware_t;

/* Master boot information structure passed to kernel_main() */
typedef struct boot_info {
    boot_mmap_t      mmap;
    boot_module_t    modules[16];
    uint32_t         module_count;
    boot_firmware_t  firmware;           /* firmware data (ACPI or DTB) */
    char             cmdline[512];       /* kernel command line */
    uint64_t         framebuffer_addr;   /* linear framebuffer if available */
    uint32_t         fb_width;
    uint32_t         fb_height;
    uint32_t         fb_pitch;
    uint8_t          fb_bpp;
} boot_info_t;

/* Hardware summary prepared for SLM at init */
typedef struct hw_summary {
    uint64_t total_ram_bytes;
    uint32_t cpu_count;             /* 1 for BSP, more if SMP detected */
    int      acpi_available;
    int      framebuffer_available;
    uint32_t module_count;
    char     cmdline[512];
} hw_summary_t;
```

### Architecture-Specific Structures

Descriptor tables (GDT/IDT on x86, exception vector tables on ARM, trap vectors on RISC-V) and their structures are defined in the architecture-specific spec (`arch/<arch>.md`) and implemented in `kernel/arch/<arch>/boot/` and `kernel/arch/<arch>/cpu/`.

The portable boot code interacts with these through the HAL:
- `arch_interrupt_init()` — sets up the interrupt/exception dispatch table
- `arch_set_interrupt_handler()` — registers handlers for specific vectors
- `arch_set_kernel_stack()` — updates the kernel stack for privilege transitions

## Interface

### Architecture Boot Entry Point

Each architecture implements `arch_boot_init()` in `kernel/arch/<arch>/boot/`. This function:
1. Validates the boot protocol (Multiboot2 magic on x86, DTB signature on ARM/RISC-V)
2. Performs early hardware setup (page tables, mode transitions)
3. Calls `kernel_main()` with boot parameters

See `arch/<arch>.md` for architecture-specific assembly entry points, descriptor table setup, and mode transition details.

### Kernel Main (`kernel/boot/main.c`)

```c
/* Portable kernel entry point called from arch_boot_init().
 * Receives pre-parsed boot_info_t, initializes all subsystems
 * in order, then starts the SLM for hardware-driven configuration. */
void kernel_main(boot_info_t *info);

/* Build hw_summary_t from boot_info_t for SLM consumption */
void boot_build_hw_summary(const boot_info_t *info, hw_summary_t *summary);
```

Boot information parsing is architecture-specific: `arch_parse_memory_map()` and `arch_parse_modules()` fill the portable `boot_info_t` before calling `kernel_main()`.

## Behavior

### Boot Sequence (State Machine)

```
ARCH_BOOT -> PARSE_BOOT_INFO -> KERNEL_MAIN -> INIT_SUBSYSTEMS -> SLM_HANDOFF
```

Architecture-specific boot (`arch_boot_init()`) handles: mode transitions, early page tables, descriptor table setup, BSS clearing, then calls `kernel_main()`.

**Detailed initialization order in `kernel_main()`:**

1. Early serial output via `arch_serial_early_init()`
2. Print boot banner: `"AUTON Kernel booting..."`
3. Initialize CPU via `arch_cpu_init()`
4. Initialize interrupts via `arch_interrupt_init()`
5. Initialize PMM using `boot_info.mmap`
6. Initialize VMM via `arch_mmu_init()` + portable higher-half mapping
7. Initialize slab allocator
8. Initialize core drivers via `drivers_init_core()` (arch-specific serial, display, timer, input)
9. Initialize timer via `arch_timer_init(100)` — 100 Hz tick
10. Initialize scheduler
11. Initialize IPC subsystem
12. Initialize device framework
13. Build `hw_summary_t` from boot info via `boot_build_hw_summary()`
14. Initialize SLM runtime, passing `hw_summary_t`
15. SLM begins hardware discovery and driver loading sequence

### Boot Information Parsing

Boot information parsing is architecture-specific and implemented in `kernel/arch/<arch>/boot/`:
- **x86_64**: Multiboot2 tag parsing (memory map, modules, command line, framebuffer, ACPI RSDP)
- **AArch64**: Device Tree Blob (DTB) parsing (memory nodes, chosen node for cmdline, reserved regions)
- **RISC-V**: SBI + DTB parsing (similar to AArch64)

Each architecture's parser fills the portable `boot_info_t` structure via `arch_parse_memory_map()` and `arch_parse_modules()`. The portable kernel never accesses raw boot protocol data directly.

### SLM Handoff

After all subsystems are initialized, the boot sequence creates a dedicated SLM kernel thread and sends it the `hw_summary_t`. The SLM thread then:

1. Receives the hardware summary via the SLM command channel (IPC)
2. Initiates PCI enumeration via the device framework
3. For each discovered device, issues `HARDWARE_IDENTIFY` intent
4. For each identified device, issues `DRIVER_SELECT` intent
5. Loads selected drivers via the device framework
6. Proceeds to network configuration, filesystem setup, etc.

### Edge Cases

- **Boot protocol validation fails**: `arch_panic()` halts all CPUs, prints error to serial if possible
- **No usable memory regions**: panic with `"FATAL: No usable memory found"`
- **No firmware tables**: set `firmware.data_address = 0`, SLM falls back to probing-based discovery
- **Module not found** (e.g., no initramfs): SLM proceeds without, reports warning
- **Framebuffer not available**: architecture-specific fallback (VGA text on x86, serial-only on others)

## Architecture-Specific Details

The following are defined in each architecture's spec (`arch/<arch>.md`):
- **Descriptor tables**: GDT/IDT layout (x86), exception vector table (ARM), trap vectors (RISC-V)
- **Interrupt layout**: vector assignments, IRQ routing
- **Boot protocol header**: Multiboot2 header (x86), DTB (ARM/RISC-V)
- **Initial page tables**: identity mapping for early boot
- **Mode transitions**: real→protected→long mode (x86), EL2→EL1 (ARM), M→S mode (RISC-V)

## Files

| File | Purpose |
|------|---------|
| `kernel/boot/main.c`             | Portable `kernel_main()`, subsystem init ordering |
| `kernel/arch/<arch>/boot/`       | Architecture-specific entry, mode transitions, boot parsing |
| `kernel/arch/<arch>/cpu/`        | Interrupt/exception table setup |
| `kernel/arch/<arch>/include/`    | Architecture constants (memory layout, page size) |

## Dependencies

- None (boot is the root subsystem; all others depend on it)
- Architecture-specific bootloader provides initial environment (GRUB2 for x86, U-Boot/UEFI for ARM, OpenSBI for RISC-V)
- Boot calls into: `mm` (PMM/VMM init), `sched`, `ipc`, `dev`, `slm`, `drivers`

## Acceptance Criteria

1. Kernel boots in QEMU for the configured architecture
2. Boot protocol is validated; invalid boot data halts CPU via `arch_panic()`
3. Architecture-specific mode transitions complete successfully
4. Interrupt/exception table is set up; exception handlers fire correctly
5. `kernel_main()` is reached and prints `"AUTON Kernel booting..."` to serial
6. Memory map is parsed correctly: `total_available` matches QEMU configured RAM
7. All boot modules are enumerated with correct start/end addresses
8. Firmware data address is captured (ACPI RSDP on x86, DTB pointer on ARM/RISC-V)
9. `hw_summary_t` is built and passed to SLM runtime at init
10. Full subsystem initialization completes without panic
11. Page fault handler catches invalid memory access and prints diagnostic
