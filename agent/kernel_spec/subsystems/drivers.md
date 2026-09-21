---
subsystem: drivers
provides: [serial, timer, keyboard, framebuffer, e1000, virtio-net, virtio-blk, ahci, nvme, input]
depends_on: [dev, mm, arch]
optional: [e1000, virtio-net, virtio-blk, ahci, nvme, framebuffer, keyboard]
# `input` is the keyboard path a framebuffer image needs; `serial` and `timer` are the two every image has.
---

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


The register block above is the **legacy PCI** interface. Firecracker's disk is `virtio-mmio:2`
and has no PCI bus at all, so a driver specified only against those offsets cannot reach the
machine this driver most exists for. The MMIO register map, the device-status order and the
feature-negotiation discipline are specified once under *VirtIO Network* below and apply
unchanged here — they are properties of VirtIO, not of the network device.

Normative: **VIRTIO 1.2** §4.1 (PCI transport), §4.2 (MMIO transport), §5.2 (Block Device).

```c
/* Device id, per transport. VIRTIO 1.2 §5.2.1: the block device is type 2. */
#define VIRTIO_BLK_DEVICE_TYPE      2
#define VIRTIO_BLK_PCI_MODERN       0x1042    /* 0x1040 + type */
/* VIRTIO_DEVICE_BLK (0x1001) above is the transitional id. */

/* The feature subset AUTON negotiates. VIRTIO 1.2 §5.2.3.
 * VIRTIO_BLK_F_FLUSH is required for any write path that claims durability: a
 * write the device has acknowledged is not a write that has reached the medium.
 * Everything else is declined for the reason the network driver declines its
 * offloads — an unexercised path in ring-0 DMA code. */
#define VIRTIO_BLK_F_SIZE_MAX       (1ULL << 1)
#define VIRTIO_BLK_F_SEG_MAX        (1ULL << 2)
#define VIRTIO_BLK_F_RO             (1ULL << 5)   /* device is read-only */
#define VIRTIO_BLK_F_BLK_SIZE       (1ULL << 6)
#define VIRTIO_BLK_F_FLUSH          (1ULL << 9)

/* Request type, the `type` field of virtio_blk_req_t above. §5.2.6. */
#define VIRTIO_BLK_T_IN             0   /* read from device */
#define VIRTIO_BLK_T_OUT            1   /* write to device */
#define VIRTIO_BLK_T_FLUSH          4

/* Status byte, written by the device into the third descriptor. §5.2.6. */
#define VIRTIO_BLK_S_OK             0
#define VIRTIO_BLK_S_IOERR          1
#define VIRTIO_BLK_S_UNSUPP         2

/* Device configuration space, §5.2.4. `capacity` is in 512-byte sectors
 * regardless of VIRTIO_BLK_F_BLK_SIZE — the logical block size changes how the
 * device is addressed, never the unit `capacity` is counted in. */
typedef struct virtio_blk_config {
    uint64_t capacity;          /* 512-byte sectors */
    uint32_t size_max;
    uint32_t seg_max;
    uint8_t  reserved[20];
    uint32_t blk_size;          /* valid only with VIRTIO_BLK_F_BLK_SIZE */
} __attribute__((packed)) virtio_blk_config_t;

/* One queue, index 0. §5.2.2. The network device's two-queue convention does
 * not apply: a block device multiplexes reads and writes over the same queue,
 * and each request carries its own direction. */
#define VIRTIO_BLK_QUEUE            0
```

**The request is a three-descriptor chain**, VIRTIO 1.2 §5.2.6, and its flags are **not
uniform** — which is the single thing this specification most exists to prevent:

| # | Contents | Device-writable |
|---|---|---|
| 0 | `virtio_blk_req_t` header | **no** |
| 1 | the data buffer | **only for `VIRTIO_BLK_T_IN`** |
| 2 | one status byte | **yes, always** |

A chain built with one flag value is wrong in both directions. Uniformly writable lets the device
overwrite the request header it is meant to read; uniformly read-only gives it nowhere to report
status, so every request appears to succeed. The first is a memory-corruption primitive and the
second is silent data loss.

Descriptors 0 and 2 are fixed-size and tiny; only descriptor 1 varies. A flush request has no
data buffer and is therefore a **two**-descriptor chain, which is the case a driver that assumes
three will corrupt.

**Initialisation** follows §3.1.1 exactly as the network driver does — reset, `ACKNOWLEDGE`,
`DRIVER`, negotiate, `FEATURES_OK`, **read the status back**, set up the queue, `DRIVER_OK`. It
is not restated here.

The driver satisfies the block interface defined under *Driver Interfaces* below — `blk_read`,
`blk_write`, `blk_get_info` — which already names virtio-blk as one of its three implementations.

**Markers**, asserted by `kernel_spec/drivers/virtio-blk.md`:

```
[BLK] virtio-blk up
[BLK] capacity 1048576 sectors
```

### SLM-Managed Driver: VirtIO Network

The driver every microVM needs. `e1000` is the only network driver this index provided until now,
which meant the only machines an image could be built for were machines with an Intel 82540EM —
a Firecracker target was refused outright (`reports/w6-target-capability-join-report.md`).

**Two transports, one device model.** This is the fact the section exists to carry. MMIO discovery
reads a magic value and a device type from a register; PCI discovery walks a capability list. The
virtqueues, the descriptor chains and the packet header behind them are identical, and a driver
specified only for PCI cannot serve the case that motivates it.

The ring structures are specified once, under *VirtIO Block* above (`virtq_desc_t`,
`virtq_avail_t`, `virtq_used_t`). They are not restated here.

Normative: **VIRTIO 1.2**, §4.1 (PCI transport), §4.2 (MMIO transport), §5.1 (Network Device).
Inventoried as `oasis-virtio/virtio-spec` in `agent/hardware/vendors.yaml`.

```c
/* Device id, per transport. VIRTIO 1.2 §5.1.1: the network device is type 1.
 * Modern virtio-pci ids are 0x1040 + device type (§4.1.2); the transitional id
 * 0x1000 is also accepted. Over MMIO there is no vendor:device pair at all —
 * the type is read from a register. */
#define VIRTIO_NET_DEVICE_TYPE      1
#define VIRTIO_NET_PCI_MODERN       0x1041
#define VIRTIO_NET_PCI_TRANSITIONAL 0x1000

/* MMIO transport registers, VIRTIO 1.2 §4.2.2. Offsets from the device base. */
#define VIRTIO_MMIO_MAGIC_VALUE     0x000   /* must read 0x74726976 ("virt") */
#define VIRTIO_MMIO_VERSION         0x004   /* 2 for a 1.x device */
#define VIRTIO_MMIO_DEVICE_ID       0x008   /* 1 = network */
#define VIRTIO_MMIO_QUEUE_SEL       0x030
#define VIRTIO_MMIO_QUEUE_NUM_MAX   0x034
#define VIRTIO_MMIO_QUEUE_NUM       0x038
#define VIRTIO_MMIO_QUEUE_READY     0x044
#define VIRTIO_MMIO_QUEUE_NOTIFY    0x050
#define VIRTIO_MMIO_STATUS          0x070
#define VIRTIO_MMIO_QUEUE_DESC_LOW  0x080
#define VIRTIO_MMIO_QUEUE_DRIVER_LOW 0x090
#define VIRTIO_MMIO_QUEUE_DEVICE_LOW 0x0A0

/* Device status bits, VIRTIO 1.2 §2.1. The order is normative: a driver that
 * sets DRIVER_OK before FEATURES_OK has negotiated nothing. */
#define VIRTIO_STATUS_ACKNOWLEDGE   1
#define VIRTIO_STATUS_DRIVER        2
#define VIRTIO_STATUS_DRIVER_OK     4
#define VIRTIO_STATUS_FEATURES_OK   8
#define VIRTIO_STATUS_FAILED        128

/* The feature subset AUTON negotiates. VIRTIO 1.2 §5.1.3.
 * VIRTIO_F_VERSION_1 is mandatory for a non-transitional device. Everything
 * else here is declined deliberately: checksum offload, segmentation offload
 * and multiqueue each add a path with no test behind it, and an unexercised
 * path in ring-0 DMA code is the risk this project is trying not to take. */
#define VIRTIO_NET_F_MAC            (1ULL << 5)   /* device supplies a MAC */
#define VIRTIO_NET_F_STATUS         (1ULL << 16)  /* link status readable */
#define VIRTIO_F_VERSION_1          (1ULL << 32)

/* Packet header, VIRTIO 1.2 §5.1.6. Prepended to every buffer in both
 * directions. With the offload features declined above, every field is zero on
 * transmit and ignored on receive — but the header is still present and still
 * occupies its bytes, which is the part a driver gets wrong. */
typedef struct virtio_net_hdr {
    uint8_t  flags;
    uint8_t  gso_type;
    uint16_t hdr_len;
    uint16_t gso_size;
    uint16_t csum_start;
    uint16_t csum_offset;
    uint16_t num_buffers;   /* present when VIRTIO_NET_F_MRG_RXBUF or VERSION_1 */
} __attribute__((packed)) virtio_net_hdr_t;

/* Device configuration space, VIRTIO 1.2 §5.1.4. Readable once
 * VIRTIO_NET_F_MAC and VIRTIO_NET_F_STATUS are negotiated. */
typedef struct virtio_net_config {
    uint8_t  mac[6];
    uint16_t status;        /* bit 0: VIRTIO_NET_S_LINK_UP */
    uint16_t max_virtqueue_pairs;
    uint16_t mtu;
} __attribute__((packed)) virtio_net_config_t;

/* Queue indices, VIRTIO 1.2 §5.1.2. Queue 0 receives, queue 1 transmits.
 * Getting this backwards produces a device that accepts packets and never
 * delivers one, with no error anywhere. */
#define VIRTIO_NET_QUEUE_RX     0
#define VIRTIO_NET_QUEUE_TX     1
```

**Initialisation**, VIRTIO 1.2 §3.1.1, in this order:

1. Reset the device (write 0 to status).
2. Set `ACKNOWLEDGE`, then `DRIVER`.
3. Read device features; write back the subset above.
4. Set `FEATURES_OK`, then **read status back** — a device that cleared it has refused the
   negotiation, and continuing past that point programs a device that is not in the state the
   driver believes.
5. Set up the receive and transmit virtqueues.
6. Set `DRIVER_OK`.

**The receive path** fills queue 0 with buffers *before* `DRIVER_OK`. A device signalled ready
with an empty receive queue drops every packet until one arrives, and the symptom is a link that
is up and a network that does not work.

The driver satisfies the shared network interface defined under *Driver Interfaces* below —
`net_send`, `net_receive`, `net_receive_nonblock`, `net_get_mac`, `net_link_status` — which
already names virtio-net as one of its two implementations.

**Markers**, asserted by `kernel_spec/drivers/virtio-net.md`:

```
[NET] virtio-net up
[NET] link up, mac 52:54:00:12:34:56
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

### SLM-Managed Driver: Framebuffer (Multiboot2)

The VESA section above describes a BIOS interface. **AUTON does not call it.** GRUB sets the mode
before handover and passes a linear framebuffer in the Multiboot2 information structure, which
`subsystems/boot.md` already parses into `boot_info_t` — `framebuffer_addr`, `fb_width`,
`fb_height`, `fb_pitch`, `fb_bpp`. Re-entering real mode to call VBE would be a much larger thing
and would buy nothing this image needs.

So the basis for this driver is a **boot protocol, not a device datasheet**. That is why
`driver_strategy.py --device 1234:1111` refuses: no publisher in `vendors.yaml` speaks for QEMU's
invented vendor id, and none needs to. The document is the Multiboot2 Specification, inventoried
as `gnu-multiboot/multiboot2-spec`.

Normative: **Multiboot2 Specification**, §3.6.12 (framebuffer info tag).

```c
/* Everything this driver needs, already parsed. No mode setting, no VBE. */
typedef struct fb_geometry {
    volatile uint8_t *base;     /* boot_info_t.framebuffer_addr */
    uint32_t width;             /* pixels */
    uint32_t height;            /* pixels */
    uint32_t pitch;             /* BYTES per scanline — see below */
    uint8_t  bpp;               /* bits per pixel; 32 is the only case handled */
} fb_geometry_t;
```

**`pitch` is not `width * bytes_per_pixel`.** The firmware may pad each scanline to an alignment
boundary, and it usually does. A driver that computes the row stride instead of reading it writes
past the end of every scanline — progressively further with each row, so the corruption is
invisible at the top of the screen and total at the bottom. This is the framebuffer's equivalent
of the ring-index bug, and it is the case the host test most exists for.

```c
/* The only address arithmetic in the driver, and the only place pitch is used.
 * A pixel's byte offset. Multiboot2 §3.6.12. */
static inline uint32_t fb_offset(const fb_geometry_t *g, uint32_t x, uint32_t y)
{
    return y * g->pitch + x * (g->bpp / 8);
}
```

Bounds are checked against `width` and `height`, never against `pitch / (bpp/8)` — the padding is
not addressable and a driver that treats it as usable writes into whatever follows.

**Markers**, asserted by `kernel_spec/drivers/framebuffer.md`:

```
[FB] mode set 1024x768x32
[FB] pitch 4096 bytes
```

### SLM-Managed Driver: PS/2 Keyboard (i8042)

Binds against `keyboard_state` above, which is already shared by every architecture's keyboard
path.

**Which machines this serves, and which it does not.** The i8042 exists on the QEMU PC and on
most bare metal. `kernel_spec/targets/firecracker.md` records it as **vestigial** — *"reset
signalling only, no keyboard behind it"* — so on a microVM this driver would bind to a controller
that will never report a keypress. A target's device list is what decides; the driver must not be
selected merely because the chip is present.

There is **no open specification.** The i8042 is a 1980s controller documented in datasheets and
by convention, and `vendors.yaml` inventories neither. `driver_strategy.py` will refuse
`synthesize` for it, and that refusal is correct: this is the case
`kernel_spec/drivers/README.md` admits `status: undrivable` for, and the record says so rather
than citing a document nobody can produce.

```c
/* i8042 ports and the status bits that gate them. */
#define I8042_DATA          0x60
#define I8042_STATUS        0x64
#define I8042_STATUS_OBF    0x01    /* output buffer full — data may be read */
#define I8042_STATUS_IBF    0x02    /* input buffer full — do NOT write */

/* Scancode set 1. A release is the press code with bit 7 set. */
#define SCANCODE_RELEASE    0x80
```

The scancode-to-character mapping is a **table**, not logic:
[`kernel_spec/drivers/scancodes.yaml`](../drivers/scancodes.yaml). Which byte means which key is a
fact to look up, and a switch statement spanning 128 cases is a fact nobody can review.

**Markers**, asserted by `kernel_spec/drivers/ps2-keyboard.md`:

```
[INPUT] keyboard ready
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
