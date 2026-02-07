# AUTON Kernel Architecture

## Overview

AUTON is a custom kernel built from scratch, supporting multiple target architectures through a **Hardware Abstraction Layer (HAL)**. Its core innovation is an embedded **Small Language Model (SLM)** that serves as the system's central intelligence — handling hardware discovery, driver configuration, OS installation, application management, and ongoing system administration.

The SLM is **pluggable**: a lightweight rule-based engine runs on minimal hardware (IoT, embedded), while systems with sufficient resources can load a real neural language model for richer understanding.

**The OS lifecycle is SLM-driven at every stage:**
1. **Boot** — Kernel loads via architecture-specific boot protocol, SLM initializes
2. **Hardware Discovery** — SLM probes and identifies hardware components
3. **Driver Configuration** — SLM determines and loads needed drivers
4. **Installation** — SLM sets up filesystems, network, base system
5. **Application Setup** — SLM installs/configures apps based on device purpose
6. **Runtime Management** — SLM stays resident for ongoing admin, updates, troubleshooting

## Target Platform

- **Architecture**: Configurable via `[kernel].arch` in `auton.toml`
- **Supported architectures**: x86_64, AArch64, RISC-V 64 (extensible — see `arch_registry.py`)
- **Boot Protocol**: Architecture-defined (see `arch/<arch>.md`)
- **Test Platform**: QEMU (architecture-specific binary from arch profile)
- **Language**: C11 (portable kernel) + architecture-specific assembly (boot, interrupts, context switch)
- **Toolchain**: Derived from architecture profile (`cc`, `asm`, `ld`)

See [HAL Contract](arch/hal.md) for the abstract interfaces every architecture implements.
See `arch/<arch>.md` for architecture-specific details (registers, page tables, boot protocol, assembly).

## Memory Layout

Architecture-defined in `kernel/arch/<arch>/include/arch_memory.h`:

```c
#define ARCH_KERNEL_VBASE    /* Virtual base of kernel space */
#define ARCH_USER_VBASE      /* Start of user space */
#define ARCH_USER_VTOP       /* End of user space */
#define ARCH_KERNEL_LOAD     /* Physical load address */
#define ARCH_PAGE_SIZE       /* Page size (typically 4096) */
#define ARCH_PT_LEVELS       /* Number of page table levels */
#define ARCH_STACK_SIZE      /* Default kernel stack size per process */
```

Portable kernel code uses these constants — never hardcoded addresses.

## Subsystems

### 1. Boot (`kernel/boot/` + `kernel/arch/<arch>/boot/`)
- Architecture-specific entry point via HAL (`arch_boot_init()`)
- Descriptor table / interrupt vector setup via HAL (`arch_interrupt_init()`)
- Early serial output via HAL (`arch_serial_early_init()`)
- Parses boot information into portable `boot_info_t` structure
- Hardware enumeration structures passed to SLM
- Jump to portable C `kernel_main()`

### 2. Memory Management (`kernel/mm/`)
- **Physical Memory Manager (PMM)**: Bitmap-based page allocator (`ARCH_PAGE_SIZE` pages)
- **Virtual Memory Manager (VMM)**: Page tables via MMU HAL (`arch_map_page()`, `arch_flush_tlb()`)
- **Slab Allocator**: kmalloc/kfree for kernel objects
- Memory map parsed from boot info
- Address space management via `arch_create_address_space()`, `arch_switch_address_space()`
- SLM memory pool: dedicated region for model weights and inference buffers

### 3. Scheduler (`kernel/sched/`)
- Preemptive round-robin with priority classes
- Priority levels: KERNEL > SLM > SYSTEM > USER > BACKGROUND
- Timer interrupt via Timer HAL (`arch_timer_init()`) drives preemption
- Context switching via HAL (`arch_context_switch()`, `arch_setup_initial_context()`)
- CPU idle via `arch_halt()`
- SLM inference tasks get elevated priority to keep the system responsive

### 4. Inter-Process Communication (`kernel/ipc/`)
- Message-passing IPC (not shared memory for security)
- Structured message format: type + payload
- Ring buffer per process pair
- Blocking and non-blocking send/receive
- SLM command channel: dedicated high-priority IPC path for SLM ↔ kernel

### 5. Device Framework (`kernel/dev/`)
- **Device discovery**: PCI enumeration via HAL (`arch_pci_config_read()`), firmware parsing via HAL (`arch_firmware_parse()`)
- **Firmware abstraction**: ACPI on x86, Device Tree on ARM/RISC-V, selectable via `arch_get_firmware_type()`
- **Device descriptor**: standardized struct describing each detected device
  - vendor/device IDs, class, resources (MMIO, IRQ, DMA)
- **Driver interface**: uniform API that all drivers implement
  - `probe()`, `init()`, `remove()`, `suspend()`, `resume()`
- **SLM-driven loading**: SLM receives device descriptors, determines which driver to load
- **Hot-plug support**: SLM monitors for device changes at runtime

### 6. SLM Runtime (`kernel/slm/`)
- **Pluggable architecture**: two backends, selected at boot based on available resources
  - **Rule Engine** (default): keyword matching, pattern rules, decision trees
    - Parses hardware descriptors → driver mappings
    - Parses user intent → system commands
    - Works on any hardware (no GPU, minimal RAM)
  - **Neural Backend** (optional): loads a real small language model
    - Supports GGUF/ONNX model formats
    - CPU inference with quantization (INT4/INT8)
    - Requires ~256MB+ RAM for the model
- **Intent system**: all SLM interactions go through an intent classifier
  - `HARDWARE_IDENTIFY` — "what is this PCI device?"
  - `DRIVER_SELECT` — "which driver handles this network card?"
  - `INSTALL_CONFIGURE` — "set up the filesystem on /dev/sda"
  - `APP_INSTALL` — "install a web server"
  - `SYSTEM_MANAGE` — "check disk usage", "update packages"
  - `TROUBLESHOOT` — "why is the network down?"
- **Knowledge base**: embedded device database, driver catalog, package registry
- **Conversation context**: maintains state across multi-step operations

### 7. Drivers (`kernel/drivers/`)
- **Core drivers** (architecture-specific, always loaded — see `arch/<arch>.md`):
  - Serial console (16550A on x86/RISC-V, PL011 on ARM)
  - Display (VGA text on x86, framebuffer on others)
  - Timer (PIT on x86, architected timer on ARM, CLINT on RISC-V)
  - Input (PS/2 on x86, device-tree keyboard on ARM/RISC-V)
- **Portable SLM-managed drivers** (loaded on demand based on hardware detection):
  - Storage: AHCI/SATA, NVMe, virtio-blk
  - Network: virtio-net, Intel e1000 (QEMU), RTL8139
  - Display: VESA framebuffer, virtio-gpu
  - USB: UHCI/EHCI/xHCI host controller
- **Driver template**: standardized skeleton that the SLM uses when generating driver configs
- All hardware I/O goes through the I/O HAL (`arch_io_read8/16/32()`, `arch_io_write8/16/32()`)
- All drivers register with the device framework via `driver_register()`

### 8. Filesystem (`kernel/fs/`)
- **VFS layer**: Linux-inspired virtual filesystem switch
  - Inode, dentry, superblock abstractions
  - Mount table, path resolution
- **Supported filesystems**:
  - initramfs (in-memory, for boot)
  - ext2 (simple, well-documented, good starting point)
  - devfs (device nodes)
  - procfs (process information)
- SLM uses VFS to set up partitions, create filesystems, install files

### 9. Network Stack (`kernel/net/`)
- Ethernet frame handling
- ARP, IPv4, ICMP, UDP, TCP (minimal)
- DHCP client (SLM triggers network config)
- DNS resolver (for package downloads)
- HTTP client (for fetching packages/updates)
- Socket API for userspace

### 10. Package Manager (`kernel/pkg/`)
- Simple package format: tar archive + metadata manifest
- Package registry: local database of available/installed packages
- SLM-driven installation: "install a web server" → resolve deps → fetch → extract → configure
- Dependency resolution
- This runs partially in kernel (registry) and partially in userspace (fetch/extract)

### 11. System Services (`kernel/sys/`)
- Init system: SLM-driven service startup ordering
- Service descriptors: what each service needs, how to start/stop
- Logging: kernel log ring buffer, SLM can query logs for troubleshooting
- Resource monitoring: CPU, memory, disk, network usage
- SLM queries these for runtime system management

## SLM Interaction Model

The SLM is not just a component — it's the OS's brain. Everything flows through it:

```
User/Admin                    SLM                         Kernel
    |                          |                            |
    |--- "set up this PC" ---->|                            |
    |                          |--- probe_hardware() ------>|
    |                          |<-- device_list[] ----------|
    |                          |--- load_driver("e1000") -->|
    |                          |<-- OK --------------------|
    |                          |--- dhcp_configure() ------>|
    |                          |<-- IP: 192.168.1.x -------|
    |                          |--- mkfs("/dev/sda1") ----->|
    |                          |<-- OK --------------------|
    |                          |--- install_pkg("nginx") -->|
    |                          |<-- OK --------------------|
    |<-- "PC ready. nginx    --|                            |
    |    running on port 80"   |                            |
```

The SLM maintains a **conversation context** so multi-step operations work naturally:
- "Set up this machine as a web server" → hardware detect → drivers → network → install nginx → configure
- "The network isn't working" → check driver status → check DHCP → check cable → diagnose

## Build System

```makefile
# Architecture (from auton.toml)
ARCH ?= x86_64

# Include architecture-specific toolchain settings
include kernel/arch/$(ARCH)/toolchain.mk

# Common flags
CFLAGS += -ffreestanding -fno-exceptions -Wall -Wextra -std=c11
LDFLAGS = -T kernel/arch/$(ARCH)/linker.ld -nostdlib

# Architecture sources
ARCH_SRCS = $(wildcard kernel/arch/$(ARCH)/**/*.c kernel/arch/$(ARCH)/**/*.S)

# Portable sources
KERN_SRCS = $(wildcard kernel/boot/*.c kernel/mm/*.c kernel/sched/*.c \
              kernel/ipc/*.c kernel/dev/*.c kernel/slm/**/*.c \
              kernel/drivers/common/*.c kernel/fs/*.c kernel/net/*.c \
              kernel/pkg/*.c kernel/sys/*.c kernel/lib/*.c)

# Targets
all: kernel.bin
kernel.bin: $(ARCH_OBJS) $(KERN_OBJS)
	$(LD) $(LDFLAGS) -o $@ $^
```

## Directory Structure (generated by agents)

```
kernel/
├── arch/               # Architecture-specific HAL implementations
│   ├── x86_64/
│   │   ├── boot/       # Multiboot2 entry, GDT, IDT, long mode
│   │   ├── cpu/        # CPUID, PIC/APIC, MSRs
│   │   ├── mm/         # PML4 page tables, CR3, invlpg
│   │   ├── sched/      # Context switch (push/pop x86_64 regs)
│   │   ├── timer/      # PIT 8254
│   │   ├── io/         # Port I/O (inb/outb) + MMIO
│   │   ├── dev/        # ACPI parsing, PCI config via 0xCF8/0xCFC
│   │   ├── include/    # arch_context.h, arch_memory.h
│   │   └── toolchain.mk
│   ├── aarch64/
│   │   ├── boot/       # DTB/UEFI, EL2→EL1 transition
│   │   ├── cpu/        # GIC, exception vectors (VBAR_EL1)
│   │   ├── mm/         # Translation tables, TTBR0/TTBR1
│   │   ├── sched/      # Context switch (X19-X30, SP)
│   │   ├── timer/      # ARM architected timer
│   │   ├── io/         # MMIO wrappers
│   │   ├── dev/        # FDT parsing, ECAM PCI
│   │   ├── include/    # arch_context.h, arch_memory.h
│   │   └── toolchain.mk
│   └── riscv64/
│       ├── boot/       # SBI+DTB, S-mode entry
│       ├── cpu/        # PLIC, trap vectors (stvec)
│       ├── mm/         # Sv39 page tables, satp CSR
│       ├── sched/      # Context switch (s0-s11, ra, sp)
│       ├── timer/      # CLINT timer
│       ├── io/         # MMIO wrappers
│       ├── dev/        # FDT parsing, ECAM PCI
│       ├── include/    # arch_context.h, arch_memory.h
│       └── toolchain.mk
├── boot/           # Portable boot coordination (calls arch_boot_init)
├── mm/             # Portable PMM, slab (calls arch MMU HAL)
├── sched/          # Portable scheduler (calls arch_context_switch)
├── ipc/            # Fully portable
├── dev/            # Portable device framework (calls arch discovery HAL)
├── slm/            # Fully portable
│   ├── engine/     # Core SLM dispatch, intent classification
│   ├── rules/      # Rule-based backend (pattern matching)
│   ├── neural/     # Neural model backend (GGUF/ONNX loader)
│   └── knowledge/  # Device database, driver catalog, package registry
├── drivers/
│   ├── common/     # Portable: PCI bus driver, AHCI, NVMe, virtio, e1000
│   └── arch/       # Arch-specific: serial, timer, console, input
├── fs/             # Fully portable
├── net/            # Fully portable
├── pkg/            # Fully portable
├── sys/            # Fully portable
├── include/
│   └── arch/       # HAL headers (arch_boot.h, arch_cpu.h, arch_mmu.h, etc.)
├── lib/            # Portable utilities (string, printf, list)
└── Makefile        # Top-level: includes arch/$(ARCH)/toolchain.mk
```

## Coding Standards

- Linux kernel style: tabs for indentation, K&R braces
- 80-column soft limit, 100-column hard limit
- Every exported function has a prototype in a header file
- All memory allocations must have corresponding frees
- No dynamic memory allocation in interrupt handlers
- Use `static` for file-scoped functions
- Comments for non-obvious logic, not for self-evident code
- Portable code calls HAL interfaces — never raw architecture instructions or registers directly
