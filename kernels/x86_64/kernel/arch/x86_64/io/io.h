/* x86_64 port I/O HAL. Portable code goes through these wrappers. */
#ifndef AUTON_ARCH_IO_H
#define AUTON_ARCH_IO_H

#include <stdint.h>

static inline void io_write8(uint16_t port, uint8_t val)
{
	__asm__ volatile("outb %0, %1" : : "a"(val), "Nd"(port));
}

static inline uint8_t io_read8(uint16_t port)
{
	uint8_t val;
	__asm__ volatile("inb %1, %0" : "=a"(val) : "Nd"(port));
	return val;
}

static inline void io_write32(uint16_t port, uint32_t val)
{
	__asm__ volatile("outl %0, %1" : : "a"(val), "Nd"(port));
}

static inline uint32_t io_read32(uint16_t port)
{
	uint32_t val;
	__asm__ volatile("inl %1, %0" : "=a"(val) : "Nd"(port));
	return val;
}

#endif /* AUTON_ARCH_IO_H */
