/* PCI bus 0 enumeration through the 0xCF8/0xCFC configuration mechanism. */
#include "pci.h"
#include "../arch/x86_64/io/io.h"

#define PCI_CONFIG_ADDR 0xCF8
#define PCI_CONFIG_DATA 0xCFC

static uint32_t pci_config_read32(uint8_t bus, uint8_t slot, uint8_t func, uint8_t off)
{
	uint32_t addr = (uint32_t)0x80000000u
		| ((uint32_t)bus << 16)
		| ((uint32_t)slot << 11)
		| ((uint32_t)func << 8)
		| ((uint32_t)off & 0xFC);
	io_write32(PCI_CONFIG_ADDR, addr);
	return io_read32(PCI_CONFIG_DATA);
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
