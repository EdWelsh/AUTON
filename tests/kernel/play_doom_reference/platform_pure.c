/* Reference implementation of the play-doom host-test interface.
 *
 * Not kernel code and not a template: it exists so the suite can be run
 * (--self-test) and scored (--inject) before anything is generated. Each
 * -DBUG_n introduces one defect the suite must catch; see run_play_doom_test.sh. */
#include "play_doom.h"

typedef struct { uint8_t pressed, key; } ev_t;

static ev_t     q[DOOM_KEYQ];
static uint32_t head, tail, dropped;
static int      extended;

static const uint8_t base_map[128] = {
	[0x01] = 27, [0x1c] = 13, [0x0f] = 9, [0x0e] = 0x7f,
#ifdef BUG_5
	[0x1d] = 0x80 + 0x1d,               /* KEY_RCTRL: a fire key that does not fire */
#else
	[0x1d] = 0xa3,
#endif
	[0x39] = 0xa2, [0x2a] = 0xb6, [0x36] = 0xb6, [0x38] = 0xb8,
	[0x02] = '1', [0x03] = '2', [0x04] = '3', [0x05] = '4', [0x06] = '5',
	[0x07] = '6', [0x08] = '7', [0x09] = '8', [0x0a] = '9', [0x0b] = '0',
	[0x10] = 'q', [0x11] = 'w', [0x12] = 'e', [0x13] = 'r', [0x14] = 't',
	[0x15] = 'y', [0x16] = 'u', [0x17] = 'i', [0x18] = 'o', [0x19] = 'p',
	[0x1e] = 'a', [0x1f] = 's', [0x20] = 'd', [0x21] = 'f', [0x22] = 'g',
	[0x23] = 'h', [0x24] = 'j', [0x25] = 'k', [0x26] = 'l',
	[0x2c] = 'z', [0x2d] = 'x', [0x2e] = 'c', [0x2f] = 'v', [0x30] = 'b',
	[0x31] = 'n', [0x32] = 'm',
};
static const uint8_t ext_map[128] = {
	[0x1d] = 0xa3, [0x38] = 0xb8,
	[0x48] = 0xad, [0x50] = 0xaf, [0x4b] = 0xac, [0x4d] = 0xae,
};

void play_doom_keys_reset(void) { head = tail = dropped = 0; extended = 0; }
uint32_t play_doom_keys_dropped(void) { return dropped; }

int play_doom_key_scancode(uint8_t byte)
{
	if (byte == 0xe0) {
#ifndef BUG_4
		extended = 1;                   /* BUG_4: the prefix is forgotten */
#endif
		return 0;
	}
	int ext = extended;
	extended = 0;
#ifdef BUG_3
	int pressed = 1;                    /* releases reported as presses */
#else
	int pressed = !(byte & 0x80);
#endif
	uint8_t make = byte & 0x7f;
	uint8_t key = ext ? ext_map[make] : base_map[make];
#ifndef BUG_10
	if (!key)
		return 0;                       /* BUG_10: unmapped bytes queued as key 0 */
#endif
	if (head - tail == DOOM_KEYQ) {
#ifdef BUG_1
		tail++;                         /* overwrite the oldest instead of dropping */
#else
#ifndef BUG_2
		dropped++;                      /* BUG_2: the drop is not counted */
#endif
		return 0;
#endif
	}
	q[head % DOOM_KEYQ] = (ev_t){ (uint8_t)pressed, key };
	head++;
	return 1;
}

int DG_GetKey(int *pressed, unsigned char *key)
{
	if (head == tail)
		return 0;
	ev_t e = q[tail % DOOM_KEYQ];
	tail++;
	*pressed = e.pressed;
	*key = e.key;
	return 1;
}

void play_doom_blit(const uint32_t *src, uint8_t *fb, uint32_t pitch,
                    uint32_t fb_w, uint32_t fb_h)
{
#ifdef BUG_7
	uint32_t x0 = 0, y0 = 0;            /* top-left, not centred */
#else
	uint32_t x0 = (fb_w - DOOM_RESX) / 2, y0 = (fb_h - DOOM_RESY) / 2;
#endif
	for (uint32_t y = 0; y < DOOM_RESY; y++) {
#ifdef BUG_6
		uint8_t *row = fb + (size_t)(y0 + y) * fb_w * 4;   /* stride computed, not read */
#else
		uint8_t *row = fb + (size_t)(y0 + y) * pitch;
#endif
		uint32_t *dst = (uint32_t *)(void *)row + x0;
		for (uint32_t x = 0; x < DOOM_RESX; x++)
			dst[x] = src[(size_t)y * DOOM_RESX + x];
	}
}

size_t play_doom_wad_read(const uint8_t *base, size_t size, uint32_t offset,
                          void *buf, size_t len)
{
	if (offset >= size)
		return 0;
#if defined(BUG_9)
	if (len > size - offset + 1)        /* off by one: one byte past the module */
		len = size - offset + 1;
#elif !defined(BUG_8)
	if (len > size - offset)            /* BUG_8: no clamp at the end of the module */
		len = size - offset;
#endif
	uint8_t *out = buf;
	for (size_t i = 0; i < len; i++)
		out[i] = base[offset + i];
	return len;
}
