/* The HAL subset the portable kernel calls (kernel_spec/arch/hal.md). Portable
 * code includes this and never an arch directory; agent/tools/hal_gate.py
 * refuses a tree where it does. Each architecture implements these in
 * kernel/arch/<arch>/hal.c. */
#ifndef AUTON_HAL_H
#define AUTON_HAL_H

#include <stdint.h>

/* hal.md "CPU HAL". arch_halt waits for the next interrupt: the polled
 * network loops depend on it yielding to QEMU until a tick (x86: hlt). */
void arch_halt(void);
void arch_disable_interrupts(void);

/* hal.md "Device Discovery HAL": PCI configuration space, however this
 * architecture reaches it (x86: ports 0xCF8/0xCFC; aarch64: ECAM MMIO). */
uint32_t arch_pci_config_read32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset);
void     arch_pci_config_write32(uint8_t bus, uint8_t dev, uint8_t func, uint8_t offset,
                                 uint32_t val);

#endif /* AUTON_HAL_H */
