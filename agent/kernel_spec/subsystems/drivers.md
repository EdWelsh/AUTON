# Drivers Specification

## Overview

The driver subsystem provides **architecture-specific core drivers** (always loaded at boot — serial console, display, timer, input) and **portable SLM-managed drivers** (loaded on demand when the SLM identifies hardware). Core drivers vary by architecture (see `arch/<arch>.md` for the specific set); portable drivers use MMIO through the I/O HAL and work across all architectures. All drivers implement a uniform interface (probe/init/remove/suspend/resume) and register with the device framework via `dev_driver_register()`.

Core drivers per architecture:
- **x86_64**: 16550A UART (COM1), VGA text mode, PIT 8254, PS/2 keyboard
- **AArch64**: PL011 UART, framebuffer, GICv2 + ARM architected timer, device-tree input
- **RISC-V**: ns16550 UART, framebuffer, PLIC + CLINT timer, device-tree input

## Data Structures

### Core Drivers (Architecture-Specific)

Core driver data structures, I/O port/register addresses, and implementation details are architecture-specific and defined in `arch/<arch>.md`. The core drivers access hardware through the I/O HAL:
- `arch_io_read8(addr)` / `arch_io_write8(addr, val)` — replaces raw `inb`/`outb` on x86, volatile MMIO on ARM/RISC-V
- `arch_io_read16(addr)` / `arch_io_write16(addr, val)`
- `arch_io_read32(addr)` / `arch_io_write32(addr, val)`

All core drivers expose a **portable interface** (see Interface section below) regardless of architecture. The implementation lives in `kernel/drivers/arch/<arch>/`.

#### Keyboard State (Portable)

```c
/* Keyboard buffer (shared by all architecture keyboard drivers) */
#define KB_BUFFER_SIZE      256

typedef struct keyboard_state {
    char     buffer[KB_BUFFER_SIZE];    /* circular key buffer */
    uint32_t head;
    uint32_t tail;
    uint32_t count;
    int      shift_pressed;
    int      ctrl_pressed;
    int      alt_pressed;
    int      caps_lock;
    int      initialized;
} keyboard_state_t;
```

### SLM-Managed Driver: AHCI (SATA)

```c
/* AHCI HBA memory registers */
typedef struct ahci_hba_mem {
    uint32_t cap;           /* host capabilities */
    uint32_t ghc;           /* global host control */
    uint32_t is;            /* interrupt status */
    uint32_t pi;            /* ports implemented (bitmask) */
    uint32_t vs;            /* version */
    uint32_t ccc_ctl;       /* command completion coalescing control */
    uint32_t ccc_ports;
    uint32_t em_loc;
    uint32_t em_ctl;
    uint32_t cap2;          /* extended capabilities */
    uint32_t bohc;          /* BIOS/OS handoff */
    uint8_t  reserved[0xA0 - 0x2C];
    uint8_t  vendor[0x100 - 0xA0];
    /* Port registers at offset 0x100 + port*0x80 */
} __attribute__((packed)) ahci_hba_mem_t;

/* AHCI port registers */
typedef struct ahci_port {
    uint32_t clb;           /* command list base address (low) */
    uint32_t clbu;          /* command list base address (high) */
    uint32_t fb;            /* FIS base address (low) */
    uint32_t fbu;           /* FIS base address (high) */
    uint32_t is;            /* interrupt status */
    uint32_t ie;            /* interrupt enable */
    uint32_t cmd;           /* command and status */
    uint32_t reserved0;
    uint32_t tfd;           /* task file data */
    uint32_t sig;           /* signature */
    uint32_t ssts;          /* SATA status */
    uint32_t sctl;          /* SATA control */
    uint32_t serr;          /* SATA error */
    uint32_t sact;          /* SATA active */
    uint32_t ci;            /* command issue */
    uint32_t sntf;          /* SATA notification */
    uint32_t fbs;           /* FIS-based switching control */
    uint32_t reserved1[11];
    uint32_t vendor[4];
} __attribute__((packed)) ahci_port_t;

/* AHCI command header */
typedef struct ahci_cmd_header {
    uint16_t flags;         /* command FIS length, ATAPI, write, prefetch */
    uint16_t prdtl;         /* PRDT length (entries) */
    uint32_t prdbc;         /* PRD byte count transferred */
    uint32_t ctba;          /* command table base address (low) */
    uint32_t ctbau;         /* command table base address (high) */
    uint32_t reserved[4];
} __attribute__((packed)) ahci_cmd_header_t;

/* AHCI driver state */
typedef struct ahci_state {
    ahci_hba_mem_t *hba;            /* MMIO base of HBA registers */
    uint32_t        port_count;     /* number of implemented ports */
    uint32_t        port_mask;      /* bitmask of active ports */
    int             initialized;
} ahci_state_t;
```

### SLM-Managed Driver: NVMe

```c
/* NVMe controller registers (BAR0 MMIO) */
typedef struct nvme_regs {
    uint64_t cap;       /* controller capabilities */
    uint32_t vs;        /* version */
    uint32_t intms;     /* interrupt mask set */
    uint32_t intmc;     /* interrupt mask clear */
    uint32_t cc;        /* controller configuration */
    uint32_t reserved;
    uint32_t csts;      /* controller status */
    uint32_t nssr;      /* NVM subsystem reset */
    uint32_t aqa;       /* admin queue attributes */
    uint64_t asq;       /* admin submission queue base */
    uint64_t acq;       /* admin completion queue base */
} __attribute__((packed)) nvme_regs_t;

/* NVMe submission queue entry (64 bytes) */
typedef struct nvme_sqe {
    uint32_t cdw0;      /* command dword 0 (opcode, fuse, CID) */
    uint32_t nsid;      /* namespace ID */
    uint64_t reserved;
    uint64_t mptr;      /* metadata pointer */
    uint64_t prp1;      /* PRP entry 1 */
    uint64_t prp2;      /* PRP entry 2 */
    uint32_t cdw10, cdw11, cdw12, cdw13, cdw14, cdw15;
} __attribute__((packed)) nvme_sqe_t;

/* NVMe completion queue entry (16 bytes) */
typedef struct nvme_cqe {
    uint32_t result;    /* command-specific result */
    uint32_t reserved;
    uint16_t sq_head;   /* SQ head pointer */
    uint16_t sq_id;     /* SQ identifier */
    uint16_t cid;       /* command identifier */
    uint16_t status;    /* status field (phase bit + status code) */
} __attribute__((packed)) nvme_cqe_t;

typedef struct nvme_state {
    nvme_regs_t *regs;              /* MMIO base */
    nvme_sqe_t  *admin_sq;          /* admin submission queue */
    nvme_cqe_t  *admin_cq;          /* admin completion queue */
    uint32_t     admin_sq_tail;
    uint32_t     admin_cq_head;
    uint32_t     queue_depth;
    int          initialized;
} nvme_state_t;
```

### SLM-Managed Driver: VirtIO Block

```c
/* VirtIO PCI device IDs */
#define VIRTIO_VENDOR_ID        0x1AF4
#define VIRTIO_DEVICE_BLK       0x1001  /* transitional virtio-blk */
#define VIRTIO_DEVICE_NET       0x1000  /* transitional virtio-net */

/* VirtIO common PCI registers (legacy interface) */
#define VIRTIO_REG_DEVICE_FEATURES  0x00
#define VIRTIO_REG_GUEST_FEATURES   0x04
#define VIRTIO_REG_QUEUE_ADDR       0x08
#define VIRTIO_REG_QUEUE_SIZE       0x0C
#define VIRTIO_REG_QUEUE_SELECT     0x0E
#define VIRTIO_REG_QUEUE_NOTIFY     0x10
#define VIRTIO_REG_DEVICE_STATUS    0x12
#define VIRTIO_REG_ISR              0x13

/* VirtIO virtqueue descriptor */
typedef struct virtq_desc {
    uint64_t addr;      /* guest physical address */
    uint32_t len;       /* length */
    uint16_t flags;     /* NEXT, WRITE, INDIRECT */
    uint16_t next;      /* next descriptor index (if NEXT) */
} __attribute__((packed)) virtq_desc_t;

/* VirtIO available ring */
typedef struct virtq_avail {
    uint16_t flags;
    uint16_t idx;
    uint16_t ring[];    /* descriptor chain heads */
} __attribute__((packed)) virtq_avail_t;

/* VirtIO used ring entry */
typedef struct virtq_used_elem {
    uint32_t id;        /* descriptor chain head */
    uint32_t len;       /* bytes written */
} __attribute__((packed)) virtq_used_elem_t;

typedef struct virtq_used {
    uint16_t flags;
    uint16_t idx;
    virtq_used_elem_t ring[];
} __attribute__((packed)) virtq_used_t;

/* VirtIO block request header */
typedef struct virtio_blk_req {
    uint32_t type;      /* 0=read, 1=write, 4=flush */
    uint32_t reserved;
    uint64_t sector;    /* start sector (512-byte sectors) */
} __attribute__((packed)) virtio_blk_req_t;
```

### SLM-Managed Driver: Network (e1000)

```c
/* Intel e1000 registers (MMIO offsets) */
#define E1000_CTRL      0x0000  /* device control */
#define E1000_STATUS    0x0008  /* device status */
#define E1000_EERD      0x0014  /* EEPROM read */
#define E1000_ICR       0x00C0  /* interrupt cause read */
#define E1000_IMS       0x00D0  /* interrupt mask set */
#define E1000_IMC       0x00D8  /* interrupt mask clear */
#define E1000_RCTL      0x0100  /* receive control */
#define E1000_TCTL      0x0400  /* transmit control */
#define E1000_RDBAL     0x2800  /* RX descriptor base low */
#define E1000_RDBAH     0x2804  /* RX descriptor base high */
#define E1000_RDLEN     0x2808  /* RX descriptor length */
#define E1000_RDH       0x2810  /* RX descriptor head */
#define E1000_RDT       0x2818  /* RX descriptor tail */
#define E1000_TDBAL     0x3800  /* TX descriptor base low */
#define E1000_TDBAH     0x3804  /* TX descriptor base high */
#define E1000_TDLEN     0x3808  /* TX descriptor length */
#define E1000_TDH       0x3810  /* TX descriptor head */
#define E1000_TDT       0x3818  /* TX descriptor tail */
#define E1000_RAL       0x5400  /* receive address low */
#define E1000_RAH       0x5404  /* receive address high */

/* e1000 TX/RX descriptor */
typedef struct e1000_rx_desc {
    uint64_t addr;      /* buffer physical address */
    uint16_t length;    /* received length */
    uint16_t checksum;
    uint8_t  status;
    uint8_t  errors;
    uint16_t special;
} __attribute__((packed)) e1000_rx_desc_t;

typedef struct e1000_tx_desc {
    uint64_t addr;      /* buffer physical address */
    uint16_t length;    /* data length */
    uint8_t  cso;       /* checksum offset */
    uint8_t  cmd;       /* command field */
    uint8_t  status;
    uint8_t  css;       /* checksum start */
    uint16_t special;
} __attribute__((packed)) e1000_tx_desc_t;

/* e1000 driver state */
#define E1000_NUM_RX_DESC   32
#define E1000_NUM_TX_DESC   8
#define E1000_RX_BUF_SIZE   2048

typedef struct e1000_state {
    volatile uint8_t *mmio_base;    /* MMIO base address */
    e1000_rx_desc_t  *rx_descs;     /* RX descriptor ring */
    e1000_tx_desc_t  *tx_descs;     /* TX descriptor ring */
    void             *rx_buffers[E1000_NUM_RX_DESC];
    uint16_t          rx_cur;       /* current RX descriptor index */
    uint16_t          tx_cur;       /* current TX descriptor index */
    uint8_t           mac_addr[6];  /* MAC address */
    int               link_up;
    int               initialized;
} e1000_state_t;
```

### SLM-Managed Driver: VESA Framebuffer

```c
/* VESA framebuffer driver state */
typedef struct vesa_state {
    volatile uint8_t *framebuffer;  /* linear framebuffer address */
    uint32_t width;                 /* pixels */
    uint32_t height;
    uint32_t pitch;                 /* bytes per scanline */
    uint8_t  bpp;                   /* bits per pixel (typically 32) */
    int      initialized;
} vesa_state_t;
```

### Driver Template

```c
/* Standard driver template skeleton.
 * All SLM-managed drivers follow this pattern. */

typedef struct my_driver_state {
    /* Device-specific state here */
    device_t *dev;          /* back-pointer to device descriptor */
    int       initialized;
} my_driver_state_t;

/* Driver operations implementation */
static int my_driver_probe(device_t *dev);
static int my_driver_init(device_t *dev);
static void my_driver_remove(device_t *dev);
static int my_driver_suspend(device_t *dev);
static int my_driver_resume(device_t *dev);

/* Driver registration structure */
static driver_t my_driver = {
    .name           = "my_driver",
    .ops = {
        .probe      = my_driver_probe,
        .init       = my_driver_init,
        .remove     = my_driver_remove,
        .suspend    = my_driver_suspend,
        .resume     = my_driver_resume,
    },
    .bus            = BUS_PCI,
    .match_vendor   = 0x1234,       /* specific vendor or 0xFFFF for any */
    .match_device   = 0x5678,       /* specific device or 0xFFFF for any */
    .match_class    = 0xFF,         /* or specific class code */
    .match_subclass = 0xFF,
    .loaded         = 0,
    .device_count   = 0,
};

/* Registration: called during driver init or by SLM on demand */
void my_driver_register(void) {
    dev_driver_register(&my_driver);
}
```

## Interface

### Core Driver Interfaces

```c
/* === Serial (kernel/include/serial.h) === */

/* Initialize COM1 at 115200 baud, 8N1, FIFO enabled */
void serial_init(void);

/* Write a single character (blocks until THR empty) */
void serial_putchar(char c);

/* Write a null-terminated string */
void serial_write(const char *str);

/* Formatted output (subset of printf: %d, %x, %s, %c, %p, %u, %lu, %lx) */
void serial_printf(const char *fmt, ...);

/* Read one character (blocking) */
char serial_getchar(void);

/* Check if data is available to read (non-blocking) */
int serial_available(void);

/* === VGA Text Mode (kernel/include/vga.h) === */

/* Initialize VGA text mode: clear screen, set cursor to 0,0 */
void vga_init(void);

/* Write a single character with automatic scrolling */
void vga_putchar(char c);

/* Write a null-terminated string */
void vga_write(const char *str);

/* Formatted output */
void vga_printf(const char *fmt, ...);

/* Clear the screen */
void vga_clear(void);

/* Set foreground and background colors */
void vga_set_color(vga_color_t fg, vga_color_t bg);

/* Move cursor to specific position */
void vga_set_cursor(uint16_t x, uint16_t y);

/* === PIT Timer (kernel/include/timer.h) === */

/* Initialize PIT channel 0 at given frequency. Installs IRQ0 handler. */
void timer_init(uint32_t frequency_hz);

/* Get total ticks since init */
uint64_t timer_get_ticks(void);

/* Get elapsed milliseconds since init */
uint64_t timer_get_ms(void);

/* Timer interrupt handler (called from IRQ0, calls sched_schedule) */
void timer_handler(void);

/* === PS/2 Keyboard (kernel/include/keyboard.h) === */

/* Initialize PS/2 keyboard controller. Installs IRQ1 handler. */
void keyboard_init(void);

/* Get next character from keyboard buffer (blocking) */
char keyboard_getchar(void);

/* Check if a character is available (non-blocking) */
int keyboard_available(void);

/* Keyboard interrupt handler (called from IRQ1) */
void keyboard_handler(void);

/* Get current modifier key state */
int keyboard_shift_pressed(void);
int keyboard_ctrl_pressed(void);
int keyboard_alt_pressed(void);
```

### SLM-Managed Driver Interfaces

```c
/* === Block device interface (shared by AHCI, NVMe, virtio-blk) === */

/* Read sectors from a block device.
 * dev_id: kernel device ID, lba: starting sector, count: number of sectors,
 * buf: destination buffer (must be large enough for count*512 bytes).
 * Returns 0 on success, negative on error. */
int blk_read(uint32_t dev_id, uint64_t lba, uint32_t count, void *buf);

/* Write sectors to a block device.
 * Returns 0 on success, negative on error. */
int blk_write(uint32_t dev_id, uint64_t lba, uint32_t count, const void *buf);

/* Get block device info */
typedef struct blk_info {
    uint64_t sector_count;      /* total sectors */
    uint32_t sector_size;       /* bytes per sector (usually 512) */
    char     model[40];         /* device model string */
    char     serial[20];        /* device serial number */
} blk_info_t;

int blk_get_info(uint32_t dev_id, blk_info_t *info);

/* === Network device interface (shared by e1000, virtio-net) === */

/* Send an Ethernet frame. Returns 0 on success. */
int net_send(uint32_t dev_id, const void *frame, uint32_t length);

/* Receive an Ethernet frame (blocking). Returns frame length. */
int net_receive(uint32_t dev_id, void *buf, uint32_t buf_size);

/* Receive (non-blocking). Returns frame length, or 0 if none available. */
int net_receive_nonblock(uint32_t dev_id, void *buf, uint32_t buf_size);

/* Get MAC address */
void net_get_mac(uint32_t dev_id, uint8_t mac[6]);

/* Check link status (1 = up, 0 = down) */
int net_link_status(uint32_t dev_id);

/* === Display interface (VESA framebuffer) === */

/* Set pixel at (x, y) to color (0xAARRGGBB) */
void fb_set_pixel(uint32_t x, uint32_t y, uint32_t color);

/* Fill rectangle with color */
void fb_fill_rect(uint32_t x, uint32_t y, uint32_t w, uint32_t h,
                  uint32_t color);

/* Get framebuffer info */
void fb_get_info(uint32_t *width, uint32_t *height, uint32_t *bpp);
```

### Driver Registration

```c
/* Register all core drivers (called from kernel_main during boot) */
void drivers_init_core(void);

/* Register all SLM-managed driver skeletons (makes them available
 * for binding but does not init hardware). Called after dev_init(). */
void drivers_register_all(void);

/* Specific driver registration functions */
void ahci_driver_register(void);
void nvme_driver_register(void);
void virtio_blk_driver_register(void);
void virtio_net_driver_register(void);
void e1000_driver_register(void);
void vesa_driver_register(void);
void usb_hc_driver_register(void);
```

## Behavior

### Core Driver Initialization Order

```
drivers_init_core() [called from kernel_main]:
  1. serial_init()    -- architecture-specific serial console, needed for all debug output
  2. display_init()   -- text display (VGA on x86, framebuffer/serial on others)
  3. timer_init(100)  -- 100 Hz tick via arch_timer_init()
  4. keyboard_init()  -- input device (PS/2 on x86, device-tree input on ARM/RISC-V)
  All core drivers are registered as platform devices with dev framework.
```

### SLM-Managed Driver Loading Flow

```
SLM receives DRIVER_SELECT result for a device:
  1. SLM determines driver name (e.g., "ahci")
  2. SLM calls dev_slm_load_driver(dev_id, "ahci") via IPC
  3. Device framework finds "ahci" in registered drivers
  4. dev_driver_bind(&ahci_driver, device):
     a. ahci_driver.ops.probe(device):
        - Check vendor/device/class match
        - Check BAR0 is valid MMIO region
        - Return 0 if match
     b. ahci_driver.ops.init(device):
        - Map AHCI MMIO registers (BAR0) to virtual address
        - Reset HBA (set GHC.HR)
        - Enable AHCI mode (set GHC.AE)
        - Enumerate ports (read PI register)
        - For each implemented port:
          * Allocate command list and FIS structures
          * Start command engine
          * Identify device (IDENTIFY command)
        - Register block device interface
        - Return 0 on success
  5. Device state -> DEV_STATE_ACTIVE
```

### Serial Driver Details

Serial driver initialization and I/O are architecture-specific:
- **x86_64/RISC-V (16550A)**: Port I/O or MMIO to configure baud rate, FIFO, line control
- **AArch64 (PL011)**: MMIO registers for baud rate, data, flags

All serial drivers use the I/O HAL (`arch_io_read8`/`arch_io_write8`) for register access.
See `arch/<arch>.md` for the specific initialization sequence.

### Keyboard Input Processing

Keyboard input handling varies by architecture:
- **x86_64 (PS/2)**: IRQ1 handler reads scancode, converts via lookup table
- **AArch64/RISC-V**: Device-tree keyboard or virtio-input

All keyboard drivers fill the portable `keyboard_state_t` buffer and expose the same interface (`keyboard_getchar`, `keyboard_available`).

### Block Device Read (AHCI Example)

```
ahci_read(dev, lba, count, buf):
  1. Select port for this device
  2. Find free command slot in command list
  3. Build command FIS (H2D register FIS):
     - FIS type = 0x27 (H2D)
     - Command = 0x25 (READ DMA EXT)
     - LBA = lba (48-bit)
     - Count = count
  4. Set up PRDT (Physical Region Descriptor Table):
     - Entry: base = physical_addr(buf), byte_count = count * 512
  5. Issue command: set bit in CI (Command Issue) register
  6. Wait for completion: poll port->ci until bit clears, or use IRQ
  7. Check TFD (Task File Data) for errors
  8. Return 0 on success, -EIO on error
```

### Edge Cases

- **Serial not present**: serial_init() checks for UART presence; if absent, all serial output becomes no-op
- **Display not available**: fallback to serial-only output
- **Timer frequency too high/low**: clamp to architecture-supported range
- **Keyboard buffer overflow**: drop new keystrokes when buffer is full
- **AHCI port not connected**: skip ports where SATA status shows no device (DET != 3)
- **NVMe controller in error state**: reset controller before init; abort if reset fails
- **e1000 EEPROM read failure**: fall back to MMIO-based MAC address read
- **VirtIO feature negotiation failure**: reject unsupported features, negotiate minimum set
- **Driver init fails after probe succeeds**: unbind driver, set device to DEV_STATE_ERROR

## Files

| File | Purpose |
|------|---------|
| `kernel/drivers/arch/<arch>/`    | Architecture-specific core drivers (serial, display, timer, input) |
| `kernel/drivers/common/ahci.c`   | AHCI/SATA storage driver (portable MMIO) |
| `kernel/drivers/common/nvme.c`   | NVMe storage driver (portable MMIO) |
| `kernel/drivers/common/virtio_blk.c` | VirtIO block device driver |
| `kernel/drivers/common/virtio_net.c` | VirtIO network driver |
| `kernel/drivers/common/e1000.c`  | Intel e1000 Ethernet driver (portable MMIO) |
| `kernel/drivers/common/vesa.c`   | VESA framebuffer driver |
| `kernel/drivers/common/usb_hc.c` | USB host controller driver (UHCI/EHCI/xHCI stub) |
| `kernel/drivers/drivers.c`       | Driver registration coordinator |
| `kernel/include/serial.h`        | Portable serial interface |
| `kernel/include/display.h`       | Portable display interface |
| `kernel/include/timer.h`         | Portable timer interface |
| `kernel/include/keyboard.h`      | Portable keyboard interface |
| `kernel/include/blk.h`           | Block device interface |
| `kernel/include/netdev.h`        | Network device interface |
| `kernel/include/fb.h`            | Framebuffer interface |

## Dependencies

- **dev**: device framework for driver registration and device binding
- **mm**: `kmalloc`/`kfree` for driver state; PMM for DMA buffers; VMM for MMIO mapping
- **arch/cpu**: interrupt handlers registered via `arch_set_interrupt_handler()`
- **sched**: timer driver calls `sched_schedule()`; keyboard unblocks waiting processes
- **ipc**: SLM-managed drivers receive load/unload commands via IPC
- **slm**: SLM selects which drivers to load based on hardware identification

## Acceptance Criteria

1. Serial: `serial_printf("Hello from AUTON!")` appears in QEMU serial output (`-serial stdio`)
2. Serial: `serial_getchar()` correctly reads typed input from QEMU serial
3. VGA: text displayed on QEMU VGA window at 80x25 resolution
4. VGA: scrolling works when output exceeds 25 lines
5. VGA: color changes with `vga_set_color()` are visible
6. PIT: timer fires at 100 Hz; `timer_get_ticks()` increments 100 times per second (+/- 2%)
7. Keyboard: key presses in QEMU are captured and echoed to serial
8. Keyboard: shift, ctrl, and caps lock modifiers produce correct ASCII
9. AHCI: SATA disk in QEMU is discovered; `blk_read()` reads sectors correctly
10. AHCI: `blk_write()` + `blk_read()` round-trip verifies data integrity
11. NVMe: NVMe device in QEMU is discovered and initialized
12. VirtIO: virtio-blk device in QEMU is discovered; read/write works
13. e1000: NIC in QEMU is discovered; MAC address is read; link status is reported
14. e1000: `net_send()` transmits Ethernet frame visible in QEMU network capture
15. e1000: `net_receive()` receives Ethernet frame sent to QEMU NIC
16. All SLM-managed drivers implement the uniform probe/init/remove interface
17. `dev_driver_register()` successfully adds each driver to the registry
18. Driver template skeleton compiles and links when vendor/device IDs are filled in
19. Driver `remove()` frees all resources (MMIO unmapped, DMA buffers freed, IRQ unregistered)
