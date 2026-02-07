# AUTON Kernel Architecture

## Overview

AUTON is a custom x86_64 kernel built from scratch, inspired by Linux architecture but with a custom API. Its core innovation is an embedded **Small Language Model (SLM)** that serves as the system's central intelligence — handling hardware discovery, driver configuration, OS installation, application management, and ongoing system administration.

The SLM is **pluggable**: a lightweight rule-based engine runs on minimal hardware (IoT, embedded), while systems with sufficient resources can load a real neural language model for richer understanding.

**The OS lifecycle is SLM-driven at every stage:**
1. **Boot** — Kernel loads, SLM initializes
2. **Hardware Discovery** — SLM probes and identifies hardware components
3. **Driver Configuration** — SLM determines and loads needed drivers
4. **Installation** — SLM sets up filesystems, network, base system
5. **Application Setup** — SLM installs/configures apps based on device purpose
6. **Runtime Management** — SLM stays resident for ongoing admin, updates, troubleshooting

## Target Platform

- **Architecture**: x86_64 (AMD64)
- **Boot Protocol**: Multiboot2 (GRUB-compatible)
- **Test Platform**: QEMU (`qemu-system-x86_64`)
- **Language**: C11 (kernel) + NASM x86_64 Assembly (boot, interrupts, context switch)
- **Compiler**: `x86_64-elf-gcc` cross-compiler
- **Assembler**: `nasm`

## Memory Layout

```
0x0000_0000_0000_0000 - 0x0000_7FFF_FFFF_FFFF  User space (processes)
0xFFFF_8000_0000_0000 - 0xFFFF_FFFF_FFFF_FFFF  Kernel space

Kernel Physical Layout:
0x0010_0000 (1 MB)     Kernel load address
0x0020_0000 (2 MB)     Kernel heap start
0x0040_0000 (4 MB)     SLM runtime memory pool
0x0080_0000 (8 MB)     Process memory pool start
```

## Subsystems

### 1. Boot (`kernel/boot/`)
- Multiboot2 header and entry point
- GDT (Global Descriptor Table) setup for 64-bit mode
- IDT (Interrupt Descriptor Table) with exception handlers
- Transition: real mode → protected mode → long mode
- Stack setup and BSS clearing
- Hardware enumeration structures passed to SLM
- Jump to C `kernel_main()`

### 2. Memory Management (`kernel/mm/`)
- **Physical Memory Manager (PMM)**: Bitmap-based page allocator (4KB pages)
- **Virtual Memory Manager (VMM)**: 4-level paging (PML4 → PDPT → PD → PT)
- **Slab Allocator**: kmalloc/kfree for kernel objects
- Memory map parsed from Multiboot2 info
- SLM memory pool: dedicated region for model weights and inference buffers

### 3. Scheduler (`kernel/sched/`)
- Preemptive round-robin with priority classes
- Priority levels: KERNEL > SLM > SYSTEM > USER > BACKGROUND
- Timer interrupt (PIT or APIC) drives preemption
- Context switching via assembly (save/restore registers + stack)
- SLM inference tasks get elevated priority to keep the system responsive

### 4. Inter-Process Communication (`kernel/ipc/`)
- Message-passing IPC (not shared memory for security)
- Structured message format: type + payload
- Ring buffer per process pair
- Blocking and non-blocking send/receive
- SLM command channel: dedicated high-priority IPC path for SLM ↔ kernel

### 5. Device Framework (`kernel/dev/`)
- **Device discovery**: PCI enumeration, ACPI table parsing, port probing
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
- **Core drivers** (always loaded):
  - Serial UART 16550A (COM1) — console I/O, early boot output
  - VGA text mode — 80x25 framebuffer
  - PIT (8254) — scheduler timer tick
  - PS/2 keyboard — input
- **SLM-managed drivers** (loaded on demand based on hardware detection):
  - Storage: AHCI/SATA, NVMe, virtio-blk
  - Network: virtio-net, Intel e1000 (QEMU), RTL8139
  - Display: VESA framebuffer, virtio-gpu
  - USB: UHCI/EHCI/xHCI host controller
- **Driver template**: standardized skeleton that the SLM uses when generating driver configs
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
# Toolchain
CC = x86_64-elf-gcc
AS = nasm
LD = x86_64-elf-ld

# Flags
CFLAGS = -ffreestanding -mno-red-zone -fno-exceptions -fno-rtti -Wall -Wextra -std=c11
ASFLAGS = -f elf64
LDFLAGS = -T linker.ld -nostdlib

# Targets
all: kernel.bin
kernel.bin: boot.o kernel.o mm.o sched.o ipc.o dev.o slm.o drivers.o fs.o net.o pkg.o sys.o
	$(LD) $(LDFLAGS) -o $@ $^
```

## Directory Structure (generated by agents)

```
kernel/
├── boot/           # Assembly boot code, GDT, IDT
├── mm/             # Physical + virtual memory management
├── sched/          # Process scheduler
├── ipc/            # Inter-process communication
├── dev/            # Device framework (discovery, driver interface)
├── slm/            # SLM runtime (rule engine + neural backend)
│   ├── engine/     # Core SLM dispatch, intent classification
│   ├── rules/      # Rule-based backend (pattern matching)
│   ├── neural/     # Neural model backend (GGUF/ONNX loader)
│   └── knowledge/  # Device database, driver catalog, package registry
├── drivers/        # Device drivers (core + SLM-managed)
├── fs/             # VFS + filesystem implementations
├── net/            # Network stack
├── pkg/            # Package manager
├── sys/            # System services, init, logging
├── include/        # Header files (interfaces)
├── lib/            # Utility functions (string, printf, list)
├── Makefile        # Build rules
└── linker.ld       # Linker script
```

## Coding Standards

- Linux kernel style: tabs for indentation, K&R braces
- 80-column soft limit, 100-column hard limit
- Every exported function has a prototype in a header file
- All memory allocations must have corresponding frees
- No dynamic memory allocation in interrupt handlers
- Use `static` for file-scoped functions
- Comments for non-obvious logic, not for self-evident code
