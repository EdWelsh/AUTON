/* Minimal boot types for the allocator self-test. Mirrors the shape declared in
 * agent/kernel_spec/subsystems/boot.md; not kernel code. */
#ifndef AUTON_TEST_BOOT_H
#define AUTON_TEST_BOOT_H
#include <stdint.h>

typedef struct boot_mmap_entry {
	uint64_t base;
	uint64_t length;
	uint32_t type;          /* 1 = usable */
	uint32_t reserved;
} __attribute__((packed)) boot_mmap_entry_t;

typedef struct boot_mmap {
	boot_mmap_entry_t entries[128];
	uint32_t count;
	uint64_t total_usable;
} boot_mmap_t;

#endif
