/* x86_64 implementation of the HAL subset in kernel/include/hal.h. */
#include <stdint.h>
#include "hal.h"
#include "io/io.h"

#define PCI_CONFIG_ADDR 0xCF8
#define PCI_CONFIG_DATA 0xCFC

void arch_halt(void)
{
	__asm__ volatile("hlt");
}

void arch_disable_interrupts(void)
{
	__asm__ volatile("cli");
}

static uint32_t pci_config_addr(uint8_t bus, uint8_t dev, uint8_t func, uint8_t off)
{
	return (uint32_t)0x80000000u
		| ((uint32_t)bus << 16)
		| ((uint32_t)dev << 11)
		| ((uint32_t)func << 8)
		| ((uint32_t)off & 0xFC);
}

uint32_t arch_pci_config_read32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset)
{
	io_write32(PCI_CONFIG_ADDR, pci_config_addr(bus, dev, func, offset));
	return io_read32(PCI_CONFIG_DATA);
}

void arch_pci_config_write32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset, uint32_t val)
{
	io_write32(PCI_CONFIG_ADDR, pci_config_addr(bus, dev, func, offset));
	io_write32(PCI_CONFIG_DATA, val);
}
