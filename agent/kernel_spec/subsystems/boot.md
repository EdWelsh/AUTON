# Boot Subsystem Specification

## Overview

The boot subsystem initializes the CPU from real mode through protected mode into 64-bit long mode, sets up core descriptor tables (GDT, IDT), parses Multiboot2 information, and hands control to the C kernel entry point. After basic kernel initialization, the boot subsystem enumerates hardware and passes a structured hardware report to the SLM runtime for intelligent driver loading and system configuration.

## Data Structures

### Multiboot2 Information Parsing

```c
/* Multiboot2 tag types we care about */
#define MB2_TAG_END         0
#define MB2_TAG_CMDLINE     1
#define MB2_TAG_MODULE      3
#define MB2_TAG_MEMINFO     4
#define MB2_TAG_MMAP        6
#define MB2_TAG_FRAMEBUFFER 8
#define MB2_TAG_ACPI_OLD    14
#define MB2_TAG_ACPI_NEW    15

/* Generic Multiboot2 tag header */
typedef struct mb2_tag {
    uint32_t type;
    uint32_t size;
} __attribute__((packed)) mb2_tag_t;

/* Memory map entry from Multiboot2 */
typedef struct mb2_mmap_entry {
    uint64_t base_addr;
    uint64_t length;
    uint32_t type;          /* 1=available, 2=reserved, 3=ACPI reclaimable */
    uint32_t reserved;
} __attribute__((packed)) mb2_mmap_entry_t;

/* Parsed memory map for kernel use */
typedef struct boot_mmap {
    mb2_mmap_entry_t entries[128];
    uint32_t         count;
    uint64_t         total_available;   /* total usable bytes */
    uint64_t         highest_address;   /* highest usable address */
} boot_mmap_t;

/* Module loaded by bootloader (e.g., initramfs, SLM weights) */
typedef struct boot_module {
    uint64_t start;         /* physical start address */
    uint64_t end;           /* physical end address */
    char     cmdline[256];  /* module command line string */
} boot_module_t;

/* ACPI RSDP pointer passed from Multiboot2 */
typedef struct boot_acpi {
    uint64_t rsdp_address;  /* physical address of RSDP */
    int      is_v2;         /* 0 = ACPI 1.0 RSDP, 1 = ACPI 2.0+ XSDP */
} boot_acpi_t;

/* Master boot information structure passed to kernel_main() */
typedef struct boot_info {
    boot_mmap_t     mmap;
    boot_module_t   modules[16];
    uint32_t        module_count;
    boot_acpi_t     acpi;
    char            cmdline[512];       /* kernel command line */
    uint64_t        framebuffer_addr;   /* linear framebuffer if available */
    uint32_t        fb_width;
    uint32_t        fb_height;
    uint32_t        fb_pitch;
    uint8_t         fb_bpp;
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

### GDT Structures

```c
/* GDT entry (8 bytes each, except TSS which is 16) */
typedef struct gdt_entry {
    uint16_t limit_low;
    uint16_t base_low;
    uint8_t  base_mid;
    uint8_t  access;
    uint8_t  granularity;   /* includes limit_high nibble */
    uint8_t  base_high;
} __attribute__((packed)) gdt_entry_t;

/* GDT pointer for lgdt instruction */
typedef struct gdt_ptr {
    uint16_t limit;         /* sizeof(gdt) - 1 */
    uint64_t base;          /* linear address of GDT */
} __attribute__((packed)) gdt_ptr_t;

/* Task State Segment (64-bit) */
typedef struct tss {
    uint32_t reserved0;
    uint64_t rsp0;          /* kernel stack for ring 0 */
    uint64_t rsp1;
    uint64_t rsp2;
    uint64_t reserved1;
    uint64_t ist[7];        /* Interrupt Stack Table entries */
    uint64_t reserved2;
    uint16_t reserved3;
    uint16_t iomap_base;
} __attribute__((packed)) tss_t;
```

### IDT Structures

```c
/* IDT gate descriptor (16 bytes in long mode) */
typedef struct idt_entry {
    uint16_t offset_low;    /* offset bits 0..15 */
    uint16_t selector;      /* code segment selector in GDT */
    uint8_t  ist;           /* IST index (bits 0..2), rest zero */
    uint8_t  type_attr;     /* type and attributes */
    uint16_t offset_mid;    /* offset bits 16..31 */
    uint32_t offset_high;   /* offset bits 32..63 */
    uint32_t reserved;
} __attribute__((packed)) idt_entry_t;

/* IDT pointer for lidt instruction */
typedef struct idt_ptr {
    uint16_t limit;
    uint64_t base;
} __attribute__((packed)) idt_ptr_t;
```

## Interface

### Assembly Entry Points (`kernel/boot/boot.asm`)

```nasm
; Multiboot2 header in .multiboot2 section
; Entry point: _start (32-bit protected mode from GRUB)
;   - Validates Multiboot2 magic (EAX == 0x36D76289)
;   - Saves Multiboot2 info pointer (EBX)
;   - Sets up initial identity-mapped page tables for first 4MB
;   - Enables PAE in CR4
;   - Loads PML4 into CR3
;   - Sets EFER.LME (Long Mode Enable) via MSR 0xC0000080
;   - Enables paging in CR0
;   - Far jump to 64-bit _start64

; _start64 (64-bit long mode):
;   - Loads 64-bit GDT
;   - Sets up segment registers (DS, ES, FS, GS, SS = kernel data)
;   - Sets RSP to top of 16KB kernel stack
;   - Clears BSS (rep stosb)
;   - Calls kernel_main(multiboot2_info_ptr)
```

### GDT Functions (`kernel/boot/gdt.c`)

```c
/* Initialize and load the GDT with kernel/user segments and TSS */
void gdt_init(void);

/* Update RSP0 in the TSS (called on context switch to set kernel stack) */
void gdt_set_kernel_stack(uint64_t stack_top);
```

### IDT Functions (`kernel/boot/idt.c`)

```c
/* Initialize all 256 IDT entries, install exception and IRQ handlers */
void idt_init(void);

/* Register a specific interrupt handler for vector number */
void idt_set_handler(uint8_t vector, void (*handler)(void), uint8_t ist_index);

/* Exception handler prototypes (installed for vectors 0-31) */
void exception_handler_div0(void);          /* #DE - Division Error */
void exception_handler_debug(void);         /* #DB - Debug */
void exception_handler_nmi(void);           /* #NMI */
void exception_handler_breakpoint(void);    /* #BP */
void exception_handler_overflow(void);      /* #OF */
void exception_handler_bound(void);         /* #BR */
void exception_handler_invalid_op(void);    /* #UD */
void exception_handler_device_na(void);     /* #NM */
void exception_handler_double_fault(void);  /* #DF - uses IST1 */
void exception_handler_invalid_tss(void);   /* #TS */
void exception_handler_seg_np(void);        /* #NP */
void exception_handler_stack_fault(void);   /* #SS */
void exception_handler_gpf(void);           /* #GP */
void exception_handler_page_fault(void);    /* #PF */

/* Common handler that receives vector number and error code */
void exception_dispatch(uint64_t vector, uint64_t error_code,
                        uint64_t rip, uint64_t cs, uint64_t rflags);
```

### Kernel Main (`kernel/boot/main.c`)

```c
/* Kernel entry point called from assembly after long mode transition.
 * Parses Multiboot2 tags into boot_info_t, initializes all subsystems
 * in order, then starts the SLM for hardware-driven configuration. */
void kernel_main(uint64_t multiboot2_info_phys);

/* Parse raw Multiboot2 tag list into structured boot_info_t */
void boot_parse_multiboot2(uint64_t mb2_phys, boot_info_t *info);

/* Build hw_summary_t from boot_info_t for SLM consumption */
void boot_build_hw_summary(const boot_info_t *info, hw_summary_t *summary);
```

## Behavior

### Boot Sequence (State Machine)

```
GRUB_LOAD -> VALIDATE_MAGIC -> SETUP_PAGES -> ENABLE_LONG_MODE -> JUMP_64BIT
    -> LOAD_GDT -> LOAD_IDT -> CLEAR_BSS -> PARSE_MB2 -> INIT_SUBSYSTEMS -> SLM_HANDOFF
```

**Detailed initialization order in `kernel_main()`:**

1. Parse Multiboot2 info structure into `boot_info_t`
2. Initialize serial driver (COM1) for early debug output
3. Print boot banner: `"AUTON Kernel booting..."`
4. Initialize GDT with TSS
5. Initialize IDT with exception handlers
6. Initialize PMM using `boot_info.mmap`
7. Initialize VMM (set up higher-half kernel mapping)
8. Initialize slab allocator
9. Initialize VGA text mode driver
10. Initialize PIT timer
11. Initialize PS/2 keyboard
12. Initialize scheduler
13. Initialize IPC subsystem
14. Initialize device framework
15. Build `hw_summary_t` from boot info
16. Initialize SLM runtime, passing `hw_summary_t`
17. SLM begins hardware discovery and driver loading sequence

### Multiboot2 Tag Parsing Algorithm

1. Start at `mb2_info_phys + 8` (skip fixed size/reserved header)
2. For each tag, read `type` and `size`
3. Switch on `type`:
   - `MB2_TAG_MMAP`: iterate memory map entries, fill `boot_mmap_t`
   - `MB2_TAG_MODULE`: record module start/end/cmdline
   - `MB2_TAG_CMDLINE`: copy kernel command line
   - `MB2_TAG_FRAMEBUFFER`: record framebuffer info
   - `MB2_TAG_ACPI_OLD` / `MB2_TAG_ACPI_NEW`: record RSDP address
   - `MB2_TAG_END`: stop parsing
4. Advance pointer to next tag: align to 8-byte boundary
5. Compute `total_available` and `highest_address` from memory map

### SLM Handoff

After all subsystems are initialized, the boot sequence creates a dedicated SLM kernel thread and sends it the `hw_summary_t`. The SLM thread then:

1. Receives the hardware summary via the SLM command channel (IPC)
2. Initiates PCI enumeration via the device framework
3. For each discovered device, issues `HARDWARE_IDENTIFY` intent
4. For each identified device, issues `DRIVER_SELECT` intent
5. Loads selected drivers via the device framework
6. Proceeds to network configuration, filesystem setup, etc.

### Edge Cases

- **Multiboot2 magic invalid**: halt CPU with `hlt` in a loop, print error to serial if possible
- **No usable memory regions**: panic with `"FATAL: No usable memory found"`
- **No ACPI tables**: set `acpi.rsdp_address = 0`, SLM falls back to port-based probing
- **Module not found** (e.g., no initramfs): SLM proceeds without, reports warning
- **Framebuffer not available**: VGA text mode used as fallback

## GDT Layout

| Entry | Index | Access | Description |
|-------|-------|--------|-------------|
| 0     | 0x00  | 0x00   | Null descriptor |
| 1     | 0x08  | 0x9A   | Kernel code segment (64-bit, ring 0) |
| 2     | 0x10  | 0x92   | Kernel data segment (ring 0) |
| 3     | 0x18  | 0xFA   | User code segment (64-bit, ring 3) |
| 4     | 0x20  | 0xF2   | User data segment (ring 3) |
| 5     | 0x28  | 0x89   | TSS descriptor (16 bytes, spans entries 5-6) |

## IDT Layout

| Vector(s) | Purpose |
|-----------|---------|
| 0-31      | CPU exceptions (#DE, #DB, NMI, #BP, #OF, #BR, #UD, #NM, #DF, #TS, #NP, #SS, #GP, #PF, etc.) |
| 32        | Timer interrupt (IRQ0, PIT) |
| 33        | Keyboard interrupt (IRQ1, PS/2) |
| 34-47     | Other hardware IRQs (PIC remapped) |
| 48-255    | Available for software interrupts / MSI |

## Multiboot2 Header

```nasm
section .multiboot2
align 8
mb2_header_start:
    dd 0xE85250D6                                          ; magic
    dd 0                                                   ; architecture (i386)
    dd mb2_header_end - mb2_header_start                   ; header length
    dd -(0xE85250D6 + 0 + (mb2_header_end - mb2_header_start)) ; checksum

    ; Framebuffer tag (request linear framebuffer)
    align 8
    dw 5        ; type = framebuffer
    dw 0        ; flags (optional)
    dd 20       ; size
    dd 0        ; width (0 = no preference)
    dd 0        ; height
    dd 0        ; depth

    ; Module alignment tag
    align 8
    dw 6        ; type = module alignment
    dw 0        ; flags
    dd 8        ; size

    ; End tag
    align 8
    dw 0        ; type
    dw 0        ; flags
    dd 8        ; size
mb2_header_end:
```

## Initial Page Tables (Assembly)

```nasm
; Identity map first 2MB using 2MB huge pages for initial boot
; PML4[0] -> PDPT[0] -> PD[0] = 0x0 | PRESENT | WRITABLE | HUGE
;
; Also map the same 2MB at higher-half (0xFFFF800000000000)
; PML4[256] -> same PDPT
;
; After VMM init, these are replaced with proper 4KB page mappings
```

## Files

| File | Purpose |
|------|---------|
| `kernel/boot/boot.asm`  | Multiboot2 header, real->protected->long mode transition |
| `kernel/boot/gdt.asm`   | GDT load helper (`lgdt` + segment reload) |
| `kernel/boot/gdt.c`     | GDT entries, TSS setup |
| `kernel/boot/idt.asm`   | IDT stub handlers (push vector, call common handler) |
| `kernel/boot/idt.c`     | IDT entries, exception dispatch, handler registration |
| `kernel/boot/main.c`    | `kernel_main()`, Multiboot2 parsing, subsystem init ordering |

## Dependencies

- None (boot is the root subsystem; all others depend on it)
- Multiboot2-compliant bootloader (GRUB2) provides initial environment
- Boot calls into: `mm` (PMM/VMM init), `sched`, `ipc`, `dev`, `slm`, `drivers`

## Acceptance Criteria

1. Kernel boots in QEMU: `qemu-system-x86_64 -kernel kernel.bin`
2. Multiboot2 magic (0x36D76289 in EAX) is validated; invalid magic halts CPU
3. CPU successfully transitions real mode -> protected mode -> long mode
4. GDT loaded with all 5 segments + TSS; verified by `sgdt` readback
5. IDT loaded with 256 entries; exception handlers fire on `int 0` (divide by zero)
6. `kernel_main()` is reached and prints `"AUTON Kernel booting..."` to serial (COM1)
7. Multiboot2 memory map is parsed correctly: `total_available` matches QEMU configured RAM
8. All boot modules are enumerated with correct start/end addresses
9. ACPI RSDP address is captured if present in Multiboot2 tags
10. `hw_summary_t` is built and passed to SLM runtime at init
11. Full subsystem initialization completes without panic
12. Page fault handler catches invalid memory access and prints diagnostic (RIP, CR2, error code)
