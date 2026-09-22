/* Minimal boot types for the allocator self-test. Mirrors the shape declared in
 * agent/kernel_spec/subsystems/boot.md (field names
 * included: the gate compiles against the tree's own kernel/include/boot.h); not kernel code. */
#ifndef AUTON_TEST_BOOT_H
#define AUTON_TEST_BOOT_H
#include <stdint.h>

typedef struct boot_mmap_entry {
	uint64_t base_addr;
	uint64_t length;
	uint32_t type;          /* 1=available, 2=reserved, 3=firmware reclaimable */
	uint32_t reserved;
} __attribute__((packed)) boot_mmap_entry_t;

typedef struct boot_mmap {
	boot_mmap_entry_t entries[128];
	uint32_t count;
	uint64_t total_available;   /* total usable bytes */
	uint64_t highest_address;   /* highest usable address */
} boot_mmap_t;

#endif
