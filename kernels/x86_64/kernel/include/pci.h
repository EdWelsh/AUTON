/* Minimal PCI enumeration (bus 0) via config ports 0xCF8/0xCFC. */
#ifndef AUTON_PCI_H
#define AUTON_PCI_H

#include <stdint.h>

typedef struct pci_device {
	uint8_t  bus;
	uint8_t  slot;
	uint16_t vendor_id;
	uint16_t device_id;
} pci_device_t;

/* Scan bus 0; fill 'out' (up to max) and return the number of devices found. */
uint32_t pci_scan(pci_device_t *out, uint32_t max);

/* Raw config-space access (bus/slot/func/offset, offset 4-byte aligned). */
uint32_t pci_config_read32(uint8_t bus, uint8_t slot, uint8_t func, uint8_t off);
void     pci_config_write32(uint8_t bus, uint8_t slot, uint8_t func,
			    uint8_t off, uint32_t val);

/* Read base address register 'bar' (0..5), masking the low flag bits to give a
 * usable physical base address. */
uint64_t pci_bar(const pci_device_t *dev, uint8_t bar);

/* Set the command register's Memory Space + Bus Master bits so the device can
 * decode its MMIO BAR and perform DMA. */
void pci_enable_bus_master(const pci_device_t *dev);

#endif /* AUTON_PCI_H */
