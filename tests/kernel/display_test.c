/* Host test for the framebuffer and scancode arithmetic specified in
 * agent/kernel_spec/subsystems/drivers.md.
 *
 * The case this exists for: `pitch` is NOT `width * bytes_per_pixel`. Firmware
 * pads scanlines to an alignment boundary and usually does. A driver that
 * computes the stride instead of reading it writes past the end of every row,
 * progressively further down the screen — invisible at the top, total at the
 * bottom.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "display_ref.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-58s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

int main(void)
{
	/* A padded mode: 1024 pixels at 32bpp is 4096 bytes, but firmware may
	 * pad. Both cases below are real. */
	dr_geometry_t unpadded = { 1024, 768, 4096, 32 };
	dr_geometry_t padded   = { 1000, 768, 4096, 32 };   /* 4000 -> 4096 */

	ok("origin is offset zero", dr_offset(&unpadded, 0, 0) == 0, NULL);
	ok("x advances by bytes-per-pixel",
	   dr_offset(&unpadded, 1, 0) == 4, NULL);
	ok("y advances by pitch", dr_offset(&unpadded, 0, 1) == 4096, NULL);

	/* The bug, stated as a test. */
	ok("a padded row advances by pitch, not width*bpp",
	   dr_offset(&padded, 0, 1) == 4096,
	   "computing the stride writes 96 bytes past the end of row 0");
	ok("padding accumulates down the screen",
	   dr_offset(&padded, 0, 100) == 409600
	   && dr_offset(&padded, 0, 100) != 100u * padded.width * 4,
	   "the error grows with every row — invisible at the top, total at the bottom");
	ok("the last addressable pixel is inside the buffer",
	   dr_offset(&padded, padded.width - 1, padded.height - 1)
	   + (padded.bpp / 8) <= dr_size(&padded), NULL);

	/* Bounds are width and height, never pitch. */
	ok("a pixel inside the visible area is in bounds",
	   dr_in_bounds(&padded, 999, 767), NULL);
	ok("a pixel in the padding is OUT of bounds",
	   !dr_in_bounds(&padded, 1000, 0),
	   "the padding is not addressable; treating it as usable writes past the row");
	ok("a pixel below the last row is out of bounds",
	   !dr_in_bounds(&padded, 0, 768), NULL);
	ok("buffer size uses pitch, not width",
	   dr_size(&padded) == 4096ULL * 768, NULL);

	/* 24bpp, where bytes-per-pixel is not a power of two. */
	dr_geometry_t bpp24 = { 800, 600, 2400, 24 };
	ok("24bpp advances three bytes per pixel",
	   dr_offset(&bpp24, 1, 0) == 3, NULL);
	ok("24bpp rows still advance by pitch",
	   dr_offset(&bpp24, 0, 1) == 2400, NULL);

	/* --- scancodes ------------------------------------------------- */
	int release = -1;
	ok("a letter translates unshifted",
	   dr_translate(0x1e, 0, &release) == 'a' && release == 0, NULL);
	ok("the same key shifted", dr_translate(0x1e, 1, &release) == 'A', NULL);
	ok("a digit translates", dr_translate(0x02, 0, &release) == '1', NULL);
	ok("a shifted digit is its symbol",
	   dr_translate(0x02, 1, &release) == '!', NULL);
	ok("space is the same either way",
	   dr_translate(0x39, 0, &release) == ' '
	   && dr_translate(0x39, 1, &release) == ' ', NULL);

	/* A release is the press code with bit 7 set. */
	ok("a release is flagged",
	   dr_translate(0x1e | DR_SCANCODE_RELEASE, 0, &release) == 'a'
	   && release == 1,
	   "a driver that misses this repeats every keypress forever");
	ok("a release yields the same character as its press",
	   dr_translate(0x9e, 0, &release) == dr_translate(0x1e, 0, NULL), NULL);

	ok("a control key produces no character",
	   dr_translate(0x1c, 0, &release) == 0,
	   "enter is a key, not a character");
	ok("an unmapped scancode produces no character",
	   dr_translate(0x7f, 0, &release) == 0, NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails,
	       fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
