/* Host suite for the play-doom platform arithmetic (services/play-doom.md,
 * "Host-test interface"). Frozen before any generation run.
 *
 * Each group is a way a Doom image fails without failing loudly: a frame
 * sheared by a computed stride, arrows that arrive as keypad presses, a fire
 * key the engine does not bind, a WAD read one byte past its module. */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "play_doom.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-62s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

static int get(int *pressed, int *key)
{
	unsigned char k = 0;
	int p = 0;
	int r = DG_GetKey(&p, &k);
	*pressed = p;
	*key = k;
	return r;
}

static int one(uint8_t b1, int b2, int *pressed, int *key)
{
	play_doom_keys_reset();
	play_doom_key_scancode(b1);
	if (b2 >= 0)
		play_doom_key_scancode((uint8_t)b2);
	return get(pressed, key);
}

static void keys(void)
{
	int p, k;
	struct { uint8_t pre; uint8_t make; int key; const char *name; } t[] = {
		{0, 0x01, 27, "escape"},  {0, 0x1c, 13, "enter"}, {0, 0x0f, 9, "tab"},
		{0, 0x0e, 0x7f, "backspace"}, {0, 0x1d, 0xa3, "left ctrl fires"},
		{0xe0, 0x1d, 0xa3, "right ctrl fires"}, {0, 0x39, 0xa2, "space uses"},
		{0, 0x2a, 0xb6, "left shift runs"}, {0, 0x36, 0xb6, "right shift runs"},
		{0, 0x38, 0xb8, "alt"}, {0xe0, 0x48, 0xad, "up arrow"},
		{0xe0, 0x50, 0xaf, "down arrow"}, {0xe0, 0x4b, 0xac, "left arrow"},
		{0xe0, 0x4d, 0xae, "right arrow"}, {0, 0x15, 'y', "y (menu confirm)"},
		{0, 0x31, 'n', "n (menu cancel)"}, {0, 0x02, '1', "1 (weapon)"},
	};
	for (size_t i = 0; i < sizeof t / sizeof t[0]; i++) {
		char name[80], why[80];
		snprintf(name, sizeof name, "key: %s", t[i].name);
		int got = one(t[i].pre ? t[i].pre : t[i].make, t[i].pre ? t[i].make : -1, &p, &k);
		snprintf(why, sizeof why, "want press of %#x, got %s %#x", t[i].key,
		         got ? (p ? "press" : "release") : "nothing", k);
		ok(name, got == 1 && p == 1 && k == t[i].key, why);
	}

	ok("release: make | 0x80 is the same key, released",
	   one(0x1d | 0x80, -1, &p, &k) == 1 && p == 0 && k == 0xa3,
	   "a release reported as a press holds the key down forever");
	ok("extended release: E0 C8 releases up",
	   one(0xe0, 0x48 | 0x80, &p, &k) == 1 && p == 0 && k == 0xad, NULL);
	ok("keypad 8 (48 without E0) is not the up arrow",
	   one(0x48, -1, &p, &k) == 0,
	   "dropping the E0 prefix turns every arrow into a keypad press");
	ok("the E0 prefix applies to one byte only",
	   (play_doom_keys_reset(), play_doom_key_scancode(0xe0),
	    play_doom_key_scancode(0x48), play_doom_key_scancode(0x1c),
	    get(&p, &k), get(&p, &k) == 1 && k == 13), NULL);
	ok("an unmapped scancode is ignored, not queued",
	   one(0x58, -1, &p, &k) == 0, "F12 is not in the table; a queued key 0 is a phantom press");
	ok("a prefix byte alone queues nothing", one(0xe0, -1, &p, &k) == 0, NULL);
	ok("an empty queue returns 0", (play_doom_keys_reset(), get(&p, &k) == 0), NULL);
}

static void queue(void)
{
	int p, k;
	play_doom_keys_reset();
	for (int i = 0; i < DOOM_KEYQ; i++)
		play_doom_key_scancode(0x1c);
	ok("a full queue refuses the next event",
	   play_doom_key_scancode(0x01) == 0, "the newest event must be dropped");
	ok("the drop is counted", play_doom_keys_dropped() == 1, "a silent drop is a lost keypress nobody can see");
	int n = 0, first = -1, last = -1;
	while (get(&p, &k)) {
		if (first < 0) first = k;
		last = k;
		n++;
	}
	ok("a full queue holds exactly DOOM_KEYQ events", n == DOOM_KEYQ, NULL);
	ok("the oldest events are kept, the newest dropped",
	   first == 13 && last == 13, "escape (the dropped event) must not appear");
	play_doom_keys_reset();
	play_doom_key_scancode(0x01);
	play_doom_key_scancode(0x1c);
	ok("events drain oldest first",
	   get(&p, &k) && k == 27 && get(&p, &k) && k == 13, NULL);
	ok("reset zeroes the drop count", (play_doom_keys_reset(), play_doom_keys_dropped() == 0), NULL);
}

static void blit(void)
{
	uint32_t *src = malloc(sizeof(uint32_t) * DOOM_RESX * DOOM_RESY);
	for (uint32_t i = 0; i < DOOM_RESX * DOOM_RESY; i++)
		src[i] = 0x00100000u + i;

	/* 1000 x 768 at 32 bpp, padded to 4096 bytes a row: pitch != width * 4. */
	const uint32_t w = 1000, h = 768, pitch = 4096;
	const uint32_t x0 = (w - DOOM_RESX) / 2, y0 = (h - DOOM_RESY) / 2;
	uint8_t *fb = malloc((size_t)pitch * h);
	memset(fb, 0xee, (size_t)pitch * h);
	play_doom_blit(src, fb, pitch, w, h);

	uint32_t px;
	memcpy(&px, fb + (size_t)y0 * pitch + x0 * 4, 4);
	ok("frame origin lands at the centre", px == src[0], "x0 = (w-640)/2, y0 = (h-400)/2");
	memcpy(&px, fb + (size_t)(y0 + 399) * pitch + (x0 + 639) * 4, 4);
	ok("last pixel lands at the centre's far corner, rows by pitch",
	   px == src[399 * DOOM_RESX + 639], "a computed stride shears every row after the first");
	memcpy(&px, fb + (size_t)(y0 + 200) * pitch + (x0 + 320) * 4, 4);
	ok("middle pixel is where pitch says", px == src[200 * DOOM_RESX + 320], NULL);

	int border_ok = 1;
	for (uint32_t y = 0; y < h && border_ok; y++)
		for (uint32_t x = 0; x < pitch / 4; x++) {
			int inside = y >= y0 && y < y0 + DOOM_RESY && x >= x0 && x < x0 + DOOM_RESX;
			uint32_t v;
			memcpy(&v, fb + (size_t)y * pitch + x * 4, 4);
			if (!inside && v != 0xeeeeeeeeu) { border_ok = 0; break; }
		}
	ok("nothing outside the centred rectangle is written", border_ok,
	   "the border stays as it was; the padding is not addressable");
	free(fb);
	free(src);
}

static void wad(void)
{
	const size_t size = 64;
	uint8_t *mod = malloc(size);          /* exact size: ASan sees a byte past */
	for (size_t i = 0; i < size; i++) mod[i] = (uint8_t)(i + 1);
	uint8_t buf[128];

	ok("an in-range read returns len", play_doom_wad_read(mod, size, 8, buf, 16) == 16
	   && buf[0] == 9 && buf[15] == 24, NULL);
	ok("a read crossing the end is short",
	   play_doom_wad_read(mod, size, 60, buf, 16) == 4 && buf[3] == 64,
	   "past the end is a short count, as w_file_stdc.c returns at EOF");
	ok("a read at offset == size returns 0", play_doom_wad_read(mod, size, 64, buf, 8) == 0, NULL);
	ok("a read past the end returns 0", play_doom_wad_read(mod, size, 1000, buf, 8) == 0, NULL);
	ok("a zero-length read returns 0", play_doom_wad_read(mod, size, 0, buf, 0) == 0, NULL);
	free(mod);
}

int main(void)
{
	keys();
	queue();
	blit();
	wad();
	printf("\n%s: %d failure(s)\n", fails ? "FAIL" : "PASS", fails);
	return fails ? 1 : 0;
}
