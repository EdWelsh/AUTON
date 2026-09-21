/* See include/display_ref.h. NOT kernel code and NOT shipped. */
#include "display_ref.h"

uint32_t dr_offset(const dr_geometry_t *g, uint32_t x, uint32_t y)
{
	return y * g->pitch + x * (uint32_t)(g->bpp / 8u);
}

int dr_in_bounds(const dr_geometry_t *g, uint32_t x, uint32_t y)
{
	return x < g->width && y < g->height;
}

uint64_t dr_size(const dr_geometry_t *g)
{
	return (uint64_t)g->pitch * g->height;
}

/* Mirrors kernel_spec/drivers/scancodes.yaml, set 1. Kept as two flat arrays so
 * the reference stays trivially comparable against the table — the table is the
 * source of truth and a test asserts they agree. */
static const char unshifted[128] = {
	[0x02]='1',[0x03]='2',[0x04]='3',[0x05]='4',[0x06]='5',[0x07]='6',
	[0x08]='7',[0x09]='8',[0x0a]='9',[0x0b]='0',[0x0c]='-',[0x0d]='=',
	[0x10]='q',[0x11]='w',[0x12]='e',[0x13]='r',[0x14]='t',[0x15]='y',
	[0x16]='u',[0x17]='i',[0x18]='o',[0x19]='p',[0x1a]='[',[0x1b]=']',
	[0x1e]='a',[0x1f]='s',[0x20]='d',[0x21]='f',[0x22]='g',[0x23]='h',
	[0x24]='j',[0x25]='k',[0x26]='l',[0x27]=';',[0x28]='\'',[0x29]='`',
	[0x2b]='\\',[0x2c]='z',[0x2d]='x',[0x2e]='c',[0x2f]='v',[0x30]='b',
	[0x31]='n',[0x32]='m',[0x33]=',',[0x34]='.',[0x35]='/',[0x39]=' ',
};

static const char shifted_map[128] = {
	[0x02]='!',[0x03]='@',[0x04]='#',[0x05]='$',[0x06]='%',[0x07]='^',
	[0x08]='&',[0x09]='*',[0x0a]='(',[0x0b]=')',[0x0c]='_',[0x0d]='+',
	[0x10]='Q',[0x11]='W',[0x12]='E',[0x13]='R',[0x14]='T',[0x15]='Y',
	[0x16]='U',[0x17]='I',[0x18]='O',[0x19]='P',[0x1a]='{',[0x1b]='}',
	[0x1e]='A',[0x1f]='S',[0x20]='D',[0x21]='F',[0x22]='G',[0x23]='H',
	[0x24]='J',[0x25]='K',[0x26]='L',[0x27]=':',[0x28]='"',[0x29]='~',
	[0x2b]='|',[0x2c]='Z',[0x2d]='X',[0x2e]='C',[0x2f]='V',[0x30]='B',
	[0x31]='N',[0x32]='M',[0x33]='<',[0x34]='>',[0x35]='?',[0x39]=' ',
};

char dr_translate(uint8_t scancode, int shifted, int *is_release)
{
	if (is_release)
		*is_release = (scancode & DR_SCANCODE_RELEASE) != 0;
	uint8_t code = (uint8_t)(scancode & (uint8_t)~DR_SCANCODE_RELEASE);
	return shifted ? shifted_map[code] : unshifted[code];
}
