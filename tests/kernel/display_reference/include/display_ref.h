/* Reference framebuffer and scancode arithmetic for the drivers specified in
 * agent/kernel_spec/subsystems/drivers.md.
 *
 * NOT kernel code and NOT shipped. It exists so display_test.c can be proved
 * correct, and so the two pieces of arithmetic most likely to be wrong are
 * executable rather than prose.
 *
 * Why these two and nothing else: both are pure functions of their inputs and
 * need no hardware. Mode setting and port I/O cannot be proved on a host — under
 * emulation they would be verified against QEMU's model of the device rather
 * than the device, which is the gap agent/hardware/CONFORMANCE-HARDWARE.md
 * records for silicon.
 */
#ifndef DISPLAY_REF_H
#define DISPLAY_REF_H

#include <stdint.h>

typedef struct dr_geometry {
	uint32_t width;     /* pixels */
	uint32_t height;    /* pixels */
	uint32_t pitch;     /* BYTES per scanline, from the Multiboot2 tag */
	uint8_t  bpp;       /* bits per pixel */
} dr_geometry_t;

/* A pixel's byte offset. Multiboot2 §3.6.12.
 *
 * `pitch` is read, never computed. The firmware pads scanlines to an alignment
 * boundary and usually does; a driver that computes width * bytes_per_pixel
 * writes past the end of every row, progressively further down the screen. */
uint32_t dr_offset(const dr_geometry_t *g, uint32_t x, uint32_t y);

/* Whether a pixel is addressable. Bounds are width and height — never
 * pitch / (bpp/8), because the padding is not addressable and treating it as
 * usable writes into whatever follows the framebuffer. */
int dr_in_bounds(const dr_geometry_t *g, uint32_t x, uint32_t y);

/* Bytes the framebuffer actually occupies. */
uint64_t dr_size(const dr_geometry_t *g);

#define DR_SCANCODE_RELEASE 0x80

/* Scancode set 1 -> character, or 0 for a key that produces none.
 * A release is the press code with bit 7 set; that is arithmetic, not a table
 * entry, and it is handled here rather than in the table. */
char dr_translate(uint8_t scancode, int shifted, int *is_release);

#endif /* DISPLAY_REF_H */
