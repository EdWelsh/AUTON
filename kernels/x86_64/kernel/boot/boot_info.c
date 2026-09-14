/* Multiboot2 info parsing -> portable hw_summary.
 * The Multiboot2 boot info is a tag list: { u32 total_size, u32 reserved },
 * followed by 8-byte-aligned tags { u32 type, u32 size, ...payload }, ending
 * with a type-0 tag. We read the basic-memory tag (type 4) for RAM size. */
#include <stdint.h>
#include "boot_info.h"

#define MB2_BOOT_MAGIC   0x36D76289u
#define MB2_TAG_END      0u
#define MB2_TAG_MODULE   3u
#define MB2_TAG_BASIC_MEM 4u

struct mb2_tag {
	uint32_t type;
	uint32_t size;
};

struct mb2_tag_basic_mem {
	uint32_t type;
	uint32_t size;
	uint32_t mem_lower;   /* KiB below 1 MiB */
	uint32_t mem_upper;   /* KiB above 1 MiB */
};

struct mb2_tag_module {
	uint32_t type;
	uint32_t size;
	uint32_t mod_start;
	uint32_t mod_end;
	char     cmdline[];   /* NUL-terminated */
};

static void copy_cmdline(char *dst, const char *src, uint32_t cap)
{
	uint32_t i = 0;
	for (; i < cap - 1 && src[i]; i++)
		dst[i] = src[i];
	dst[i] = '\0';
}

int boot_magic_valid(uint32_t magic)
{
	return magic == MB2_BOOT_MAGIC;
}

hw_summary_t boot_parse(uint32_t mb_info_ptr, uint32_t magic)
{
	hw_summary_t hw = { 0 };

	if (!boot_magic_valid(magic) || mb_info_ptr == 0)
		return hw;

	/* The info pointer is a low physical address, identity-mapped. */
	const uint8_t *base = (const uint8_t *)(uintptr_t)mb_info_ptr;
	const uint8_t *p = base + 8;   /* skip total_size + reserved */

	for (;;) {
		const struct mb2_tag *tag = (const struct mb2_tag *)p;
		if (tag->type == MB2_TAG_END)
			break;

		if (tag->type == MB2_TAG_BASIC_MEM) {
			const struct mb2_tag_basic_mem *m =
				(const struct mb2_tag_basic_mem *)p;
			uint64_t kib = (uint64_t)m->mem_lower + (uint64_t)m->mem_upper;
			hw.total_ram_bytes = kib * 1024u;
		} else if (tag->type == MB2_TAG_MODULE &&
			   hw.module_count < BOOT_MAX_MODULES) {
			const struct mb2_tag_module *m =
				(const struct mb2_tag_module *)p;
			boot_module_t *mod = &hw.modules[hw.module_count++];
			mod->start = m->mod_start;
			mod->end = m->mod_end;
			copy_cmdline(mod->cmdline, m->cmdline, sizeof(mod->cmdline));
		}

		/* Advance to the next tag, padded up to an 8-byte boundary. */
		p += (tag->size + 7u) & ~7u;
	}
	return hw;
}
