/* Intel e1000 (82540EM, QEMU default NIC) driver. MMIO register access +
 * legacy descriptor rings in identity-mapped low RAM (phys == virt for DMA). */
#include "e1000.h"
#include "phys.h"
#include "kernel.h"

/* ---- registers (byte offsets into BAR0) ---- */
#define REG_CTRL    0x0000
#define REG_STATUS  0x0008
#define REG_ICR     0x00C0
#define REG_IMC     0x00D8
#define REG_RCTL    0x0100
#define REG_TCTL    0x0400
#define REG_TIPG    0x0410
#define REG_RDBAL   0x2800
#define REG_RDBAH   0x2804
#define REG_RDLEN   0x2808
#define REG_RDH     0x2810
#define REG_RDT     0x2818
#define REG_TDBAL   0x3800
#define REG_TDBAH   0x3804
#define REG_TDLEN   0x3808
#define REG_TDH     0x3810
#define REG_TDT     0x3818
#define REG_RAL     0x5400
#define REG_RAH     0x5404
#define REG_MTA     0x5200          /* 128 entries */

#define CTRL_SLU    0x00000040      /* set link up */
#define CTRL_ASDE   0x00000020      /* auto-speed detect enable */
#define CTRL_RST    0x04000000      /* device reset */

#define RCTL_EN     0x00000002
#define RCTL_BAM    0x00008000      /* accept broadcast */
#define RCTL_SECRC  0x04000000      /* strip Ethernet CRC */
/* BSIZE bits 16-17 = 00 => 2048-byte buffers (default). */

#define TCTL_EN     0x00000002
#define TCTL_PSP    0x00000008      /* pad short packets */

#define TXD_CMD_EOP 0x01
#define TXD_CMD_IFCS 0x02
#define TXD_CMD_RS  0x08
#define TXD_STA_DD  0x01

#define RXD_STA_DD  0x01
#define RXD_STA_EOP 0x02

#define NUM_RX      32
#define NUM_TX      32
#define BUF_SIZE    2048

struct rx_desc {
	uint64_t addr;
	uint16_t length;
	uint16_t checksum;
	uint8_t  status;
	uint8_t  errors;
	uint16_t special;
} __attribute__((packed));

struct tx_desc {
	uint64_t addr;
	uint16_t length;
	uint8_t  cso;
	uint8_t  cmd;
	uint8_t  status;
	uint8_t  css;
	uint16_t special;
} __attribute__((packed));

/* Descriptor rings are written back by the NIC via DMA, so they must be
 * volatile — otherwise -O2 caches the status byte and never observes the DD
 * (descriptor-done) bit the card sets. */
static volatile uint32_t *mmio;
static volatile struct rx_desc *rx_ring;
static volatile struct tx_desc *tx_ring;
static uint8_t *rx_buf[NUM_RX];
static uint8_t *tx_buf[NUM_TX];
static uint32_t rx_cur;
static uint32_t rdt_val;        /* last value written to RDT (ring tail) */
static uint32_t tx_cur;
static uint32_t stat_tx_ok, stat_tx_fail, stat_rx_ok;     /* diagnostics */

void e1000_debug(void)
{
	kprintf("[NET] e1000 stats: tx_ok=%u tx_fail=%u rx=%u\n",
		stat_tx_ok, stat_tx_fail, stat_rx_ok);
	kprintf("[NET] regs STATUS=%x RCTL=%x RDH=%x RDT=%x TDH=%x TDT=%x\n",
		mmio[REG_STATUS / 4], mmio[REG_RCTL / 4],
		mmio[REG_RDH / 4], mmio[REG_RDT / 4],
		mmio[REG_TDH / 4], mmio[REG_TDT / 4]);
}

static inline uint32_t reg_read(uint32_t r) { return mmio[r / 4]; }
static inline void reg_write(uint32_t r, uint32_t v) { mmio[r / 4] = v; }

static void delay(void)
{
	for (volatile int i = 0; i < 1000000; i++)
		;
}

static void read_mac(uint8_t mac[6])
{
	uint32_t ral = reg_read(REG_RAL);
	uint32_t rah = reg_read(REG_RAH);

	mac[0] = (uint8_t)(ral);
	mac[1] = (uint8_t)(ral >> 8);
	mac[2] = (uint8_t)(ral >> 16);
	mac[3] = (uint8_t)(ral >> 24);
	mac[4] = (uint8_t)(rah);
	mac[5] = (uint8_t)(rah >> 8);
}

static void rx_init(void)
{
	rx_ring = dma_alloc(sizeof(struct rx_desc) * NUM_RX, 16);
	for (uint32_t i = 0; i < NUM_RX; i++) {
		rx_buf[i] = dma_alloc(BUF_SIZE, 16);
		rx_ring[i].addr = (uint64_t)(uintptr_t)rx_buf[i];
		rx_ring[i].status = 0;
	}
	reg_write(REG_RDBAL, (uint32_t)(uintptr_t)rx_ring);
	reg_write(REG_RDBAH, (uint32_t)((uint64_t)(uintptr_t)rx_ring >> 32));
	reg_write(REG_RDLEN, sizeof(struct rx_desc) * NUM_RX);
	reg_write(REG_RDH, 0);
	rdt_val = NUM_RX - 1;
	reg_write(REG_RDT, rdt_val);
	rx_cur = 0;
	reg_write(REG_RCTL, RCTL_EN | RCTL_BAM | RCTL_SECRC);
}

static void tx_init(void)
{
	tx_ring = dma_alloc(sizeof(struct tx_desc) * NUM_TX, 16);
	for (uint32_t i = 0; i < NUM_TX; i++) {
		tx_buf[i] = dma_alloc(BUF_SIZE, 16);
		tx_ring[i].addr = (uint64_t)(uintptr_t)tx_buf[i];
		tx_ring[i].status = TXD_STA_DD;     /* mark free */
	}
	reg_write(REG_TDBAL, (uint32_t)(uintptr_t)tx_ring);
	reg_write(REG_TDBAH, (uint32_t)((uint64_t)(uintptr_t)tx_ring >> 32));
	reg_write(REG_TDLEN, sizeof(struct tx_desc) * NUM_TX);
	reg_write(REG_TDH, 0);
	reg_write(REG_TDT, 0);
	tx_cur = 0;
	reg_write(REG_TIPG, 0x0060200A);
	reg_write(REG_TCTL, TCTL_EN | TCTL_PSP | (0x0F << 4) | (0x3F << 12));
}

int e1000_init(const pci_device_t *dev, uint8_t mac_out[6])
{
	uint64_t bar0 = pci_bar(dev, 0);

	if (!bar0)
		return -1;
	pci_enable_bus_master(dev);
	mmio = (volatile uint32_t *)(uintptr_t)bar0;

	/* Reset, then wait for the RST bit to self-clear before reconfiguring. */
	reg_write(REG_CTRL, reg_read(REG_CTRL) | CTRL_RST);
	for (int i = 0; i < 1000; i++) {
		if (!(reg_read(REG_CTRL) & CTRL_RST))
			break;
		delay();
	}
	reg_write(REG_IMC, 0xFFFFFFFF);         /* mask all interrupts (we poll) */
	(void)reg_read(REG_ICR);

	/* Link up + auto speed. */
	reg_write(REG_CTRL, reg_read(REG_CTRL) | CTRL_SLU | CTRL_ASDE);

	/* Clear the multicast table filter. */
	for (uint32_t i = 0; i < 128; i++)
		reg_write(REG_MTA + i * 4, 0);

	read_mac(mac_out);
	rx_init();
	tx_init();
	return 0;
}

int e1000_tx(const void *frame, uint16_t len)
{
	if (len > BUF_SIZE)
		return -1;

	uint32_t i = tx_cur;
	kmemcpy(tx_buf[i], frame, len);
	tx_ring[i].length = len;
	tx_ring[i].cmd = TXD_CMD_EOP | TXD_CMD_IFCS | TXD_CMD_RS;
	tx_ring[i].status = 0;

	tx_cur = (tx_cur + 1) % NUM_TX;
	reg_write(REG_TDT, tx_cur);

	/* Wait for the card to report descriptor done. */
	for (int spin = 0; spin < 1000000; spin++) {
		if (tx_ring[i].status & TXD_STA_DD) {
			stat_tx_ok++;
			return 0;
		}
	}
	stat_tx_fail++;
	return -1;      /* timed out (link down?) */
}

uint16_t e1000_poll(void *buf, uint16_t maxlen)
{
	volatile struct rx_desc *d = &rx_ring[rx_cur];

	/* Re-arm the receive tail every poll. Besides causing a VM exit (so the
	 * CPU-bound poll loop yields to QEMU's main loop), writing RDT triggers
	 * qemu_flush_queued_packets(), prompting the SLIRP backend to retry any
	 * reply it queued while the NIC briefly could not receive. Without this
	 * a queued first packet (e.g. the DHCP offer) is never delivered. */
	reg_write(REG_RDT, rdt_val);

	if (!(d->status & RXD_STA_DD))
		return 0;

	uint16_t len = d->length;
	if (len > maxlen)
		len = maxlen;
	kmemcpy(buf, rx_buf[rx_cur], len);

	d->status = 0;
	rdt_val = rx_cur;                        /* hand the buffer back */
	reg_write(REG_RDT, rdt_val);
	rx_cur = (rx_cur + 1) % NUM_RX;
	stat_rx_ok++;
	return len;
}
