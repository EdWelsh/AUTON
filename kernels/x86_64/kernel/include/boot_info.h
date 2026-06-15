/* Portable boot information (subset of kernel_spec/subsystems/boot.md).
 * The seed kernel reads only what it needs from the Multiboot v1 info struct. */
#ifndef AUTON_BOOT_INFO_H
#define AUTON_BOOT_INFO_H

#include <stdint.h>

/* Hardware summary handed to the SLM runtime at init. */
typedef struct hw_summary {
	uint64_t total_ram_bytes;
	uint32_t pci_device_count;
} hw_summary_t;

/* Parse the raw Multiboot v1 info pointer into a hardware summary.
 * 'magic' is the value left in EAX by the bootloader (0x2BADB002). */
hw_summary_t boot_parse(uint32_t mb_info_ptr, uint32_t magic);

/* True if 'magic' is the Multiboot v1 boot magic. */
int boot_magic_valid(uint32_t magic);

#endif /* AUTON_BOOT_INFO_H */
