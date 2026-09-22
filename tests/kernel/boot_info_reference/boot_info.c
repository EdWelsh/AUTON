/* Multiboot2 info parsing -> portable hw_summary.
 * The Multiboot2 boot info is a tag list: { u32 total_size, u32 reserved },
 * followed by 8-byte-aligned tags { u32 type, u32 size, ...payload }, ending
 * with a type-0 tag.
 *
 * RAM is sized from the memory map (type 6), falling back to the EFI memory
 * map (type 17), then to basic memory (type 4). Type 4's mem_upper is only the
 * contiguous RAM above 1 MiB up to the first hole: under BIOS that is all of
 * it, under OVMF the first hole is near 8 MiB, and a 256 MiB guest reported
 * "7 MB RAM" (w12 B3). boot.md already required the map; BIOS hid it. */
#include <stdint.h>
#include "boot_info.h"

#define MB2_BOOT_MAGIC   0x36D76289u
#define MB2_TAG_END      0u
#define MB2_TAG_MODULE   3u
#define MB2_TAG_BASIC_MEM 4u
#define MB2_TAG_MMAP      6u
#define MB2_TAG_EFI_MMAP  17u
#define MB2_MMAP_AVAILABLE 1u

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

struct mb2_tag_mmap {
	uint32_t type;
	uint32_t size;
	uint32_t entry_size;
	uint32_t entry_version;
	/* entries follow: { u64 base, u64 length, u32 type, u32 reserved } */
};

struct mb2_tag_efi_mmap {
	uint32_t type;
	uint32_t size;
	uint32_t descr_size;
	uint32_t descr_version;
	/* EFI_MEMORY_DESCRIPTORs follow, each descr_size bytes */
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

static uint64_t rd64(const uint8_t *p)
{
	uint64_t v;
	__builtin_memcpy(&v, p, 8);
	return v;
}

static uint32_t rd32(const uint8_t *p)
{
	uint32_t v;
	__builtin_memcpy(&v, p, 4);
	return v;
}

/* Sum of available regions in a type-6 map. */
static uint64_t mmap_ram(const uint8_t *tag, uint32_t tag_size)
{
	const struct mb2_tag_mmap *m = (const struct mb2_tag_mmap *)tag;
	if (m->entry_size < 24)
		return 0;
	uint64_t sum = 0;
	for (uint32_t off = sizeof(*m); off + 24 <= tag_size; off += m->entry_size)
		if (rd32(tag + off + 16) == MB2_MMAP_AVAILABLE)
			sum += rd64(tag + off + 8);
	return sum;
}

/* Sum of memory usable after ExitBootServices in a type-17 EFI map (UEFI 2.x
 * EFI_MEMORY_TYPE): loader code/data (1, 2), boot services code/data (3, 4),
 * conventional (7). */
static uint64_t efi_mmap_ram(const uint8_t *tag, uint32_t tag_size)
{
	const struct mb2_tag_efi_mmap *m = (const struct mb2_tag_efi_mmap *)tag;
	if (m->descr_size < 32)
		return 0;
	uint64_t sum = 0;
	for (uint32_t off = sizeof(*m); off + 32 <= tag_size; off += m->descr_size) {
		uint32_t t = rd32(tag + off);
		if (t == 1 || t == 2 || t == 3 || t == 4 || t == 7)
			sum += rd64(tag + off + 24) * 4096u;   /* NumberOfPages */
	}
	return sum;
}

hw_summary_t boot_parse_info(const void *info, uint32_t magic)
{
	hw_summary_t hw = { 0 };

	if (!boot_magic_valid(magic) || info == 0)
		return hw;

	const uint8_t *base = (const uint8_t *)info;
	const uint8_t *p = base + 8;   /* skip total_size + reserved */
	uint64_t ram_basic = 0, ram_mmap = 0, ram_efi = 0;

	for (;;) {
		const struct mb2_tag *tag = (const struct mb2_tag *)p;
		if (tag->type == MB2_TAG_END)
			break;

		if (tag->type == MB2_TAG_BASIC_MEM) {
			const struct mb2_tag_basic_mem *m =
				(const struct mb2_tag_basic_mem *)p;
			ram_basic = ((uint64_t)m->mem_lower + (uint64_t)m->mem_upper) * 1024u;
		} else if (tag->type == MB2_TAG_MMAP) {
			ram_mmap = mmap_ram(p, tag->size);
		} else if (tag->type == MB2_TAG_EFI_MMAP) {
			ram_efi = efi_mmap_ram(p, tag->size);
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

	if (ram_mmap) {
		hw.total_ram_bytes = ram_mmap;
		hw.ram_source = MB2_TAG_MMAP;
	} else if (ram_efi) {
		hw.total_ram_bytes = ram_efi;
		hw.ram_source = MB2_TAG_EFI_MMAP;
	} else if (ram_basic) {
		hw.total_ram_bytes = ram_basic;
		hw.ram_source = MB2_TAG_BASIC_MEM;
	}
	return hw;
}

hw_summary_t boot_parse(uint32_t mb_info_ptr, uint32_t magic)
{
	/* The info pointer is a low physical address, identity-mapped. */
	return boot_parse_info((const void *)(uintptr_t)mb_info_ptr, magic);
}
