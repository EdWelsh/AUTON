/* w25 A3: port I/O for host-built driver suites.
 *
 * The x86_64 io.h uses `inl`/`outl`, which the Mac's arm64 clang cannot assemble, so a driver
 * suite built on the host failed at the first port access (w24 F-3). Force-included with
 * `-include`, this defines io.h's include guard first, so the real header is skipped and the
 * driver sees functions with the same names that touch a small host-side register file.
 * Register programming stays unverified here, exactly as run_virtio_blk_test.sh says. */
#ifndef AUTON_ARCH_IO_H
#define AUTON_ARCH_IO_H
#include <stdint.h>

static uint32_t host_io_regs[65536];

static inline void io_write8(uint16_t port, uint8_t val)   { host_io_regs[port] = val; }
static inline uint8_t io_read8(uint16_t port)               { return (uint8_t)host_io_regs[port]; }
static inline void io_write32(uint16_t port, uint32_t val) { host_io_regs[port] = val; }
static inline uint32_t io_read32(uint16_t port)             { return host_io_regs[port]; }
#endif
