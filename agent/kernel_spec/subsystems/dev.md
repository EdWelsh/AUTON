# Device Framework Specification

## Overview

The device framework provides unified hardware discovery, device description, and driver management for the AUTON kernel. It handles PCI bus enumeration (via the Device Discovery HAL), firmware table parsing (ACPI or Device Tree depending on architecture), and maintains a registry of all detected hardware. The SLM uses device descriptors to intelligently select and load drivers. The framework also monitors for hot-plug events and notifies the SLM when hardware changes occur at runtime.

PCI configuration access is architecture-specific: port I/O (0xCF8/0xCFC) on x86, ECAM (memory-mapped) on ARM/RISC-V. The portable device framework calls `arch_pci_config_read32()` / `arch_pci_config_write32()` from the HAL.

## Data Structures

### PCI Configuration

```c
/* PCI configuration space access is architecture-specific:
 * - x86_64: port I/O via 0xCF8/0xCFC
 * - AArch64/RISC-V: ECAM (PCIe Enhanced Configuration Access Mechanism)
 * The portable code uses arch_pci_config_read32()/arch_pci_config_write32() */

/* PCI configuration header offsets (universal) */
#define PCI_VENDOR_ID       0x00
#define PCI_DEVICE_ID       0x02
#define PCI_COMMAND         0x04
#define PCI_STATUS          0x06
#define PCI_REVISION        0x08
#define PCI_PROG_IF         0x09
#define PCI_SUBCLASS        0x0A
#define PCI_CLASS           0x0B
#define PCI_HEADER_TYPE     0x0E
#define PCI_BAR0            0x10
#define PCI_BAR1            0x14
#define PCI_BAR2            0x18
#define PCI_BAR3            0x1C
#define PCI_BAR4            0x20
#define PCI_BAR5            0x24
#define PCI_SUBSYSTEM_VENDOR 0x2C
#define PCI_SUBSYSTEM_ID    0x2E
#define PCI_IRQ_LINE        0x3C
#define PCI_IRQ_PIN         0x3D

/* PCI device class codes */
#define PCI_CLASS_STORAGE       0x01
#define PCI_CLASS_NETWORK       0x02
#define PCI_CLASS_DISPLAY       0x03
#define PCI_CLASS_MULTIMEDIA    0x04
#define PCI_CLASS_MEMORY        0x05
#define PCI_CLASS_BRIDGE        0x06
#define PCI_CLASS_SERIAL_BUS    0x0C

/* PCI subclass codes (selected) */
#define PCI_SUBCLASS_IDE        0x01
#define PCI_SUBCLASS_SATA       0x06    /* AHCI */
#define PCI_SUBCLASS_NVM        0x08    /* NVMe */
#define PCI_SUBCLASS_ETHERNET   0x00
#define PCI_SUBCLASS_VGA        0x00
#define PCI_SUBCLASS_USB        0x03

/* PCI address: bus/device/function */
typedef struct pci_addr {
    uint8_t bus;
    uint8_t device;
    uint8_t function;
} pci_addr_t;
```

### Device Descriptor

```c
/* Maximum BARs per device */
#define DEV_MAX_BARS    6

/* Base Address Register (BAR) descriptor */
typedef struct dev_bar {
    uint64_t base;          /* base address (physical) */
    uint64_t size;          /* region size in bytes */
    int      is_mmio;       /* 1 = memory-mapped I/O, 0 = port I/O */
    int      is_64bit;      /* 1 = 64-bit BAR (consumes two slots) */
    int      prefetchable;  /* 1 = prefetchable memory */
} dev_bar_t;

/* Device state */
typedef enum dev_state {
    DEV_STATE_DISCOVERED,   /* found during enumeration, no driver */
    DEV_STATE_IDENTIFIED,   /* SLM has identified the device */
    DEV_STATE_DRIVER_BOUND, /* a driver has been bound to this device */
    DEV_STATE_ACTIVE,       /* device is operational */
    DEV_STATE_SUSPENDED,    /* device is in low-power state */
    DEV_STATE_ERROR,        /* device error, needs attention */
    DEV_STATE_REMOVED       /* device was hot-unplugged */
} dev_state_t;

/* Device type classification */
typedef enum dev_type {
    DEV_TYPE_UNKNOWN    = 0,
    DEV_TYPE_STORAGE    = 1,    /* disk, SSD, NVMe */
    DEV_TYPE_NETWORK    = 2,    /* Ethernet, WiFi */
    DEV_TYPE_DISPLAY    = 3,    /* VGA, GPU */
    DEV_TYPE_INPUT      = 4,    /* keyboard, mouse */
    DEV_TYPE_SERIAL     = 5,    /* UART, serial ports */
    DEV_TYPE_USB_HOST   = 6,    /* USB host controller */
    DEV_TYPE_AUDIO      = 7,    /* sound devices */
    DEV_TYPE_BRIDGE     = 8,    /* PCI bridges */
    DEV_TYPE_TIMER      = 9,    /* PIT, HPET, APIC timer */
    DEV_TYPE_PLATFORM   = 10,   /* platform/ISA devices */
} dev_type_t;

/* Bus type the device is attached to */
typedef enum bus_type {
    BUS_PCI,            /* PCI/PCIe bus */
    BUS_ISA,            /* legacy ISA (keyboard, serial, PIT) */
    BUS_PLATFORM,       /* platform devices (ACPI-discovered) */
    BUS_VIRTIO,         /* VirtIO (para-virtualized) */
} bus_type_t;

/* Unified device descriptor */
#define DEV_NAME_MAX    64
#define DEV_MAX_DEVICES 256

typedef struct device {
    /* Identity */
    uint32_t    dev_id;             /* unique kernel device ID */
    char        name[DEV_NAME_MAX]; /* human-readable name (filled by SLM) */
    dev_type_t  type;
    dev_state_t state;
    bus_type_t  bus;

    /* PCI identity (zero for non-PCI devices) */
    uint16_t    vendor_id;
    uint16_t    device_id_pci;      /* PCI device ID */
    uint16_t    subsystem_vendor;
    uint16_t    subsystem_id;
    uint8_t     class_code;
    uint8_t     subclass;
    uint8_t     prog_if;
    uint8_t     revision;
    pci_addr_t  pci_addr;           /* bus/device/function */

    /* Resources */
    dev_bar_t   bars[DEV_MAX_BARS]; /* BARs (MMIO/PIO regions) */
    uint8_t     bar_count;
    uint8_t     irq_line;           /* legacy IRQ number */
    uint8_t     irq_pin;            /* PCI IRQ pin (A/B/C/D) */
    int         msi_capable;        /* 1 if MSI/MSI-X supported */
    int         dma_capable;        /* 1 if bus-mastering DMA available */

    /* Driver binding */
    struct driver *bound_driver;    /* pointer to bound driver, or NULL */

    /* Linkage */
    struct device *next;            /* next in global device list */
} device_t;
```

### Firmware Abstraction

The device framework supports multiple firmware types via `arch_get_firmware_type()`:

```c
/* Firmware type (from HAL) */
typedef enum {
    FIRMWARE_ACPI,          /* x86, some ARM servers */
    FIRMWARE_DEVICE_TREE,   /* ARM, RISC-V */
    FIRMWARE_NONE,          /* minimal/embedded */
} firmware_type_t;
```

#### ACPI Structures (x86_64, some ARM servers)

```c
/* ACPI RSDP (Root System Description Pointer) */
typedef struct acpi_rsdp {
    char     signature[8];      /* "RSD PTR " */
    uint8_t  checksum;
    char     oem_id[6];
    uint8_t  revision;          /* 0 = ACPI 1.0, 2 = ACPI 2.0+ */
    uint32_t rsdt_address;      /* 32-bit physical address of RSDT */
    /* ACPI 2.0+ fields */
    uint32_t length;
    uint64_t xsdt_address;     /* 64-bit physical address of XSDT */
    uint8_t  ext_checksum;
    uint8_t  reserved[3];
} __attribute__((packed)) acpi_rsdp_t;

/* ACPI SDT header (common to all tables) */
typedef struct acpi_sdt_header {
    char     signature[4];      /* e.g., "APIC", "FACP", "MCFG" */
    uint32_t length;
    uint8_t  revision;
    uint8_t  checksum;
    char     oem_id[6];
    char     oem_table_id[8];
    uint32_t oem_revision;
    uint32_t creator_id;
    uint32_t creator_revision;
} __attribute__((packed)) acpi_sdt_header_t;

/* ACPI MADT (Multiple APIC Description Table) entry types */
#define MADT_ENTRY_LOCAL_APIC   0
#define MADT_ENTRY_IO_APIC      1
#define MADT_ENTRY_ISO           2   /* Interrupt Source Override */

/* Parsed ACPI information */
typedef struct acpi_info {
    acpi_sdt_header_t *rsdt;    /* Root/Extended SDT */
    acpi_sdt_header_t *madt;    /* MADT (APIC table) */
    acpi_sdt_header_t *fadt;    /* FADT (fixed ACPI description) */
    acpi_sdt_header_t *mcfg;    /* MCFG (PCIe enhanced config) */
    uint32_t local_apic_addr;   /* local APIC base address */
    uint32_t io_apic_addr;      /* I/O APIC base address */
    uint8_t  io_apic_id;
    int      table_count;       /* number of ACPI tables found */
} acpi_info_t;
```

#### Device Tree Structures (AArch64, RISC-V)

```c
/* Flattened Device Tree header */
typedef struct fdt_header {
    uint32_t magic;             /* 0xD00DFEED */
    uint32_t totalsize;
    uint32_t off_dt_struct;
    uint32_t off_dt_strings;
    uint32_t off_mem_rsvmap;
    uint32_t version;
    uint32_t last_comp_version;
    uint32_t boot_cpuid_phys;
    uint32_t size_dt_strings;
    uint32_t size_dt_struct;
} __attribute__((packed)) fdt_header_t;

/* Parsed Device Tree information */
typedef struct dt_info {
    fdt_header_t *fdt;          /* pointer to FDT in memory */
    uint64_t      fdt_phys;     /* physical address of FDT */
    uint64_t      fdt_size;     /* FDT total size */
    int           node_count;   /* number of device nodes found */
} dt_info_t;
```

### Driver Interface

```c
/* Forward declaration */
typedef struct device device_t;

/* Driver operations: uniform interface that every driver implements */
typedef struct driver_ops {
    /* Probe: check if this driver can handle the given device.
     * Returns 0 if yes (claim device), -1 if not. */
    int (*probe)(device_t *dev);

    /* Init: initialize the device. Allocate resources, configure hardware.
     * Returns 0 on success, negative error code on failure. */
    int (*init)(device_t *dev);

    /* Remove: shut down the device, release all resources.
     * Called before driver unload or device removal. */
    void (*remove)(device_t *dev);

    /* Suspend: put device in low-power state (optional, can be NULL). */
    int (*suspend)(device_t *dev);

    /* Resume: wake device from low-power state (optional, can be NULL). */
    int (*resume)(device_t *dev);
} driver_ops_t;

/* Driver descriptor */
#define DRV_NAME_MAX    64
#define DRV_MAX_DRIVERS 64

typedef struct driver {
    char            name[DRV_NAME_MAX];     /* driver name (e.g., "e1000") */
    driver_ops_t    ops;                    /* driver operations */
    bus_type_t      bus;                    /* which bus this driver serves */

    /* PCI match criteria (for PCI drivers) */
    uint16_t        match_vendor;           /* 0xFFFF = match any */
    uint16_t        match_device;           /* 0xFFFF = match any */
    uint8_t         match_class;            /* 0xFF = match any */
    uint8_t         match_subclass;         /* 0xFF = match any */

    /* State */
    int             loaded;                 /* 1 if driver is initialized */
    int             device_count;           /* number of devices using this driver */
    struct driver  *next;                   /* next in driver registry */
} driver_t;
```

### Device Framework State

```c
typedef struct dev_framework {
    device_t       *devices;            /* linked list of all devices */
    uint32_t        device_count;       /* total devices discovered */
    uint32_t        next_dev_id;        /* next device ID to assign */
    driver_t       *drivers;            /* linked list of registered drivers */
    uint32_t        driver_count;       /* total registered drivers */
    firmware_type_t firmware_type;      /* ACPI, Device Tree, or None */
    acpi_info_t     acpi;               /* parsed ACPI tables (if ACPI) */
    dt_info_t       dt;                 /* parsed Device Tree (if DTB) */
    int             pci_enumerated;     /* 1 if PCI scan completed */
    int             firmware_parsed;    /* 1 if firmware tables parsed */
} dev_framework_t;
```

## Interface (`kernel/include/dev.h`)

### Framework Initialization

```c
/* Initialize the device framework. Allocates device and driver registries.
 * Must be called after mm subsystem is ready. */
void dev_init(void);

/* Initialize firmware parsing based on architecture.
 * Calls arch_firmware_parse() which handles ACPI (x86) or DTB (ARM/RISC-V).
 * Returns 0 on success, -1 if firmware data invalid. */
int dev_firmware_init(uint64_t firmware_data_addr, int firmware_type);

/* Parse ACPI tables starting from RSDP address (x86 path).
 * Populates acpi_info_t with MADT, FADT, MCFG etc.
 * Returns 0 on success, -1 if RSDP invalid or no ACPI. */
int dev_acpi_init(uint64_t rsdp_phys_addr, int is_v2);

/* Parse Device Tree Blob (ARM/RISC-V path).
 * Traverses FDT nodes to discover devices, memory, interrupts.
 * Returns 0 on success, -1 if DTB invalid. */
int dev_dt_init(uint64_t dtb_phys_addr);

/* Enumerate all PCI devices via arch_pci_config_read32().
 * Scans bus 0-255, device 0-31, function 0-7.
 * Creates device_t for each discovered device and adds to device list.
 * Returns number of devices found. */
uint32_t dev_pci_enumerate(void);

/* Register legacy ISA/platform devices (serial, VGA, PIT, PS/2).
 * These are not PCI-discoverable and must be added manually. */
void dev_register_platform_devices(void);
```

### PCI Configuration Access

```c
/* Portable PCI config wrappers (call arch_pci_config_read32/write32 from HAL).
 * Architecture handles the mechanism: port I/O on x86, ECAM on ARM/RISC-V. */
uint8_t  pci_read8(pci_addr_t addr, uint8_t offset);
uint16_t pci_read16(pci_addr_t addr, uint8_t offset);
uint32_t pci_read32(pci_addr_t addr, uint8_t offset);

void pci_write8(pci_addr_t addr, uint8_t offset, uint8_t value);
void pci_write16(pci_addr_t addr, uint8_t offset, uint16_t value);
void pci_write32(pci_addr_t addr, uint8_t offset, uint32_t value);

/* Enable bus-mastering for DMA on a PCI device */
void pci_enable_bus_master(pci_addr_t addr);

/* Enable memory-space and I/O-space access for a PCI device */
void pci_enable_device(pci_addr_t addr);
```

### Device Operations

```c
/* Get the full list of discovered devices. */
device_t *dev_get_devices(void);

/* Find device by kernel device ID. Returns NULL if not found. */
device_t *dev_get_by_id(uint32_t dev_id);

/* Find devices by type. Fills 'out' array, returns count found. */
uint32_t dev_find_by_type(dev_type_t type, device_t **out, uint32_t max);

/* Find devices by PCI vendor/device ID. */
device_t *dev_find_by_pci_id(uint16_t vendor, uint16_t device_id);

/* Get a human-readable string describing a device (for serial output). */
void dev_describe(const device_t *dev, char *buf, uint32_t bufsize);

/* Print all devices to serial (debug). */
void dev_list_all(void);
```

### Driver Management

```c
/* Register a driver with the device framework.
 * The driver is added to the registry and can be matched against devices. */
int dev_driver_register(driver_t *drv);

/* Unregister a driver. Calls remove() on all devices bound to it first. */
void dev_driver_unregister(driver_t *drv);

/* Attempt to bind a driver to a device. Calls driver->ops.probe(), then
 * driver->ops.init() if probe succeeds.
 * Returns 0 on success, -1 if probe failed, -2 if init failed. */
int dev_driver_bind(driver_t *drv, device_t *dev);

/* Unbind a driver from a device. Calls driver->ops.remove(). */
void dev_driver_unbind(device_t *dev);

/* Auto-match: for each unbound device, try all registered drivers.
 * Returns number of newly bound devices. */
uint32_t dev_auto_bind(void);
```

### SLM-Driven Driver Loading

```c
/* Send all unbound device descriptors to the SLM for identification
 * and driver selection. The SLM responds with driver names to load.
 * This is the primary driver loading mechanism. */
void dev_slm_identify_devices(void);

/* SLM requests loading a specific driver by name for a device.
 * Framework finds the driver in the registry and binds it.
 * Returns 0 on success, -1 if driver not found, -2 if bind failed. */
int dev_slm_load_driver(uint32_t dev_id, const char *driver_name);

/* Build a device summary string for SLM consumption.
 * Format: "PCI vendor:device class:subclass [BAR0=addr IRQ=N]"
 * The SLM uses this to identify devices. */
void dev_build_slm_summary(const device_t *dev, char *buf, uint32_t bufsize);
```

### Hot-Plug Monitoring

```c
/* Start hot-plug monitoring. Periodically re-scans PCI bus and
 * compares against known device list. New devices trigger SLM notification.
 * Called as a background kernel thread. */
void dev_hotplug_monitor(void);

/* Callback type for hot-plug events */
typedef void (*dev_hotplug_cb_t)(device_t *dev, int added);

/* Register a callback for hot-plug events */
void dev_hotplug_register(dev_hotplug_cb_t callback);
```

## Behavior

### PCI Enumeration Algorithm

```
dev_pci_enumerate():
  For bus = 0 to 255:
    For device = 0 to 31:
      For function = 0 to 7:
        1. Read vendor_id at (bus, device, function, 0x00)
        2. If vendor_id == 0xFFFF: skip (no device)
        3. Read device_id, class, subclass, prog_if, revision
        4. Read header_type
        5. Allocate device_t, fill PCI identity fields
        6. Parse BARs:
           For bar_index = 0 to 5:
             a. Read BAR register
             b. Write 0xFFFFFFFF, read back to determine size
             c. Restore original value
             d. If BAR & 0x1: port I/O bar, mask off bit 0 for base
             e. Else: MMIO bar, check bit 2 for 64-bit
             f. If 64-bit: read next BAR register for upper 32 bits
        7. Read IRQ line, IRQ pin
        8. Check if MSI capable (scan capabilities list)
        9. Classify dev_type from class/subclass
        10. Set state = DEV_STATE_DISCOVERED
        11. Add to device list

        If header_type bit 7 clear AND function == 0:
           break (single-function device, skip functions 1-7)
```

### BAR Size Detection

```
For each BAR register:
  1. Save original value
  2. Write 0xFFFFFFFF to BAR
  3. Read back value
  4. Restore original value
  5. Mask off type bits (bit 0 for I/O, bits 0-3 for MMIO)
  6. Invert and add 1 to get size: size = ~(readback & mask) + 1
  7. If size == 0: BAR not implemented, skip
```

### ACPI Parsing

```
dev_acpi_init(rsdp_phys, is_v2):
  1. Map RSDP physical address to virtual
  2. Validate RSDP signature "RSD PTR " and checksum
  3. If is_v2: use XSDT address (64-bit), else use RSDT address (32-bit)
  4. Map RSDT/XSDT to virtual
  5. Validate RSDT/XSDT checksum
  6. Iterate table entries in RSDT/XSDT:
     - Each entry is a 32-bit (RSDT) or 64-bit (XSDT) physical address
     - Map each table, check signature:
       "APIC" -> MADT: parse local APIC address, I/O APIC address
       "FACP" -> FADT: parse fixed ACPI hardware info
       "MCFG" -> MCFG: parse PCIe enhanced config space base
  7. Store parsed info in acpi_info_t
```

### SLM Device Identification Flow

```
dev_slm_identify_devices():
  For each device with state == DEV_STATE_DISCOVERED:
    1. Build summary string via dev_build_slm_summary()
       Example: "PCI 8086:100E class=02:00 [MMIO=0xFEBC0000/128KB IRQ=11]"
    2. Send HARDWARE_IDENTIFY intent to SLM via IPC:
       args = summary string
    3. SLM responds with device name and type
       Example: "Intel 82540EM Gigabit Ethernet (e1000)"
    4. Update device->name and device->type
    5. Set state = DEV_STATE_IDENTIFIED
    6. Send DRIVER_SELECT intent to SLM:
       args = device name + type
    7. SLM responds with driver name
       Example: "e1000"
    8. Call dev_slm_load_driver(dev->dev_id, "e1000")
    9. If successful: state = DEV_STATE_DRIVER_BOUND -> DEV_STATE_ACTIVE
```

### Driver Binding

```
dev_driver_bind(drv, dev):
  1. Call drv->ops.probe(dev)
  2. If probe returns -1: return -1 (driver doesn't support this device)
  3. Call drv->ops.init(dev)
  4. If init returns error: return -2
  5. dev->bound_driver = drv
  6. dev->state = DEV_STATE_DRIVER_BOUND (then ACTIVE after init)
  7. drv->device_count++
  8. Return 0
```

### Hot-Plug Detection

```
dev_hotplug_monitor() [runs as background kernel thread]:
  Loop every 5 seconds:
    1. Perform quick PCI scan (just read vendor_id for each slot)
    2. Compare against known device list
    3. New device found:
       a. Full enumeration of new device (BARs, IRQ, etc.)
       b. Add to device list
       c. Send IPC_MSG_DEV_DISCOVERED to SLM
       d. SLM identifies and loads driver
    4. Known device missing:
       a. Call dev_driver_unbind() if driver bound
       b. Set state = DEV_STATE_REMOVED
       c. Send IPC_MSG_DEV_REMOVED to SLM
       d. Call registered hot-plug callbacks
```

### Edge Cases

- **PCI bus with no devices**: enumeration returns 0 devices; SLM notified, proceeds with platform devices only
- **BAR reads all zeros**: BAR not implemented, `bar_count` for that device is decremented
- **ACPI not available**: `dev_acpi_init()` returns -1; on ARM/RISC-V, `dev_dt_init()` is used instead. If neither available, fallback to legacy PCI enumeration only
- **Driver probe fails for all drivers**: device stays in `DEV_STATE_IDENTIFIED`; SLM may retry or report "no driver available"
- **Driver init fails**: device stays unbound; SLM receives error and may try alternate driver
- **Hot-plug of device already known**: ignored (deduplicated by PCI address)
- **Multiple devices matching same driver**: driver serves all; `device_count` incremented per device

## Files

| File | Purpose |
|------|---------|
| `kernel/dev/dev.c`        | Device framework core: init, device list, driver registry |
| `kernel/dev/pci.c`        | Portable PCI bus enumeration, BAR parsing (calls HAL for config access) |
| `kernel/dev/acpi.c`       | ACPI table discovery and parsing (x86, some ARM) |
| `kernel/dev/dt.c`         | Device Tree parsing (ARM, RISC-V) |
| `kernel/dev/hotplug.c`    | Hot-plug monitoring thread |
| `kernel/include/dev.h`    | Device framework interface and data structures |

## Dependencies

- **mm**: `kmalloc`/`kfree` for device_t and driver_t allocation; `vmm_map_range` for MMIO BAR mapping
- **boot**: `boot_acpi_t` provides RSDP address for ACPI parsing
- **ipc**: SLM command channel for device identification and driver selection
- **sched**: background thread for hot-plug monitoring
- **slm**: SLM provides HARDWARE_IDENTIFY and DRIVER_SELECT intent processing

## Acceptance Criteria

1. PCI enumeration in QEMU discovers all emulated devices (VGA, IDE/AHCI, NIC, etc.)
2. Device descriptors contain correct vendor/device IDs verified against QEMU config
3. BAR addresses and sizes are correctly parsed for MMIO and port I/O BARs
4. ACPI RSDP is located and RSDT/XSDT tables are parsed without checksum errors
5. MADT parsing discovers local APIC and I/O APIC addresses
6. `dev_list_all()` prints all devices with correct classification to serial
7. `dev_build_slm_summary()` produces parseable summary strings for each device
8. SLM receives device summaries and responds with driver selections
9. `dev_driver_register()` adds driver to registry; `dev_driver_bind()` calls probe+init
10. `dev_auto_bind()` correctly matches PCI vendor/device/class criteria
11. Driver unbind calls `remove()` and frees device binding
12. Platform devices (serial, VGA, PIT, PS/2) are registered as non-PCI devices
13. Hot-plug simulation: add QEMU device at runtime, framework detects and notifies SLM
14. Hot-unplug: remove QEMU device, framework detects and calls driver `remove()`
15. No resource leaks: all MMIO mappings created for devices are tracked and unmappable
