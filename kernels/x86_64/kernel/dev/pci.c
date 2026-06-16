/* PCI bus 0 enumeration through the 0xCF8/0xCFC configuration mechanism. */
#include "pci.h"
#include "../arch/x86_64/io/io.h"

#define PCI_CONFIG_ADDR 0xCF8
#define PCI_CONFIG_DATA 0xCFC

#define PCI_CMD         0x04
#define PCI_BAR0        0x10
#define PCI_CMD_MEMORY  0x0002
#define PCI_CMD_MASTER  0x0004

static uint32_t pci_config_addr(uint8_t bus, uint8_t slot, uint8_t func, uint8_t off)
{
	return (uint32_t)0x80000000u
		| ((uint32_t)bus << 16)
		| ((uint32_t)slot << 11)
		| ((uint32_t)func << 8)
		| ((uint32_t)off & 0xFC);
}

uint32_t pci_config_read32(uint8_t bus, uint8_t slot, uint8_t func, uint8_t off)
{
	io_write32(PCI_CONFIG_ADDR, pci_config_addr(bus, slot, func, off));
	return io_read32(PCI_CONFIG_DATA);
}

void pci_config_write32(uint8_t bus, uint8_t slot, uint8_t func,
			uint8_t off, uint32_t val)
{
	io_write32(PCI_CONFIG_ADDR, pci_config_addr(bus, slot, func, off));
	io_write32(PCI_CONFIG_DATA, val);
}

uint64_t pci_bar(const pci_device_t *dev, uint8_t bar)
{
	uint8_t off = (uint8_t)(PCI_BAR0 + bar * 4);
	uint32_t v = pci_config_read32(dev->bus, dev->slot, 0, off);

	if (v & 0x1)
		return (uint64_t)(v & 0xFFFFFFFCu);     /* I/O space BAR */
	/* Memory BAR: bit 2 set => 64-bit, base spans the next BAR too. */
	uint64_t base = (uint64_t)(v & 0xFFFFFFF0u);
	if ((v & 0x6) == 0x4) {
		uint32_t hi = pci_config_read32(dev->bus, dev->slot, 0,
						(uint8_t)(off + 4));
		base |= (uint64_t)hi << 32;
	}
	return base;
}

void pci_enable_bus_master(const pci_device_t *dev)
{
	uint32_t cmd = pci_config_read32(dev->bus, dev->slot, 0, PCI_CMD);
	cmd |= PCI_CMD_MEMORY | PCI_CMD_MASTER;
	pci_config_write32(dev->bus, dev->slot, 0, PCI_CMD, cmd);
}

uint32_t pci_scan(pci_device_t *out, uint32_t max)
{
	uint32_t count = 0;

	for (uint8_t slot = 0; slot < 32; slot++) {
		uint32_t id = pci_config_read32(0, slot, 0, 0x00);
		uint16_t vendor = (uint16_t)(id & 0xFFFF);
		if (vendor == 0xFFFF)
			continue;   /* no device in this slot */

		if (out && count < max) {
			out[count].bus = 0;
			out[count].slot = slot;
			out[count].vendor_id = vendor;
			out[count].device_id = (uint16_t)(id >> 16);
		}
		count++;
	}
	return count;
}
