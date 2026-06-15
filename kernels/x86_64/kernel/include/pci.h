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

#endif /* AUTON_PCI_H */
