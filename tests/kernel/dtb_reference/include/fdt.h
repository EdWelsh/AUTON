/* The Flattened Device Tree parser an aarch64 kernel needs before it can print
 * anything, as specified in agent/kernel_spec/arch/aarch64.md.
 *
 * On aarch64 there is no BIOS and no ACPI: X0 holds a DTB, and everything —
 * how much RAM there is, where the UART is — comes out of it. A kernel that
 * gets this wrong cannot report that it got it wrong.
 *
 * NOT kernel code and NOT shipped. */
#ifndef AUTON_FDT_H
#define AUTON_FDT_H

#include <stdint.h>
#include <stddef.h>

#define FDT_MAGIC        0xd00dfeed
#define FDT_MIN_VERSION  16

/* 0 when `dtb` is a device tree this parser understands; -1 otherwise.
 * Checked before any offset in the blob is followed. */
int fdt_validate(const void *dtb);

/* The first memory node's base and size. 0 on success, -1 when absent. */
int fdt_memory(const void *dtb, uint64_t *base, uint64_t *size);

/* /chosen bootargs, NUL-terminated, or -1 when the property is absent.
 * Absent is not an error: a machine booted without -append has none. */
int fdt_bootargs(const void *dtb, char *out, size_t cap);

/* The MMIO base of the first node whose `compatible` list contains `want`.
 * 0 on success, -1 when no such node exists. */
int fdt_find_compatible(const void *dtb, const char *want, uint64_t *base);

#endif
