/* Host tests for Multiboot2 boot-info parsing (subsystems/boot.md).
 *
 * Synthetic tag streams in the two shapes GRUB produces: BIOS (basic memory +
 * a memory map) and UEFI (the same plus an EFI memory map, with a basic-memory
 * tag that counts only up to the first hole). Under OVMF a 256 MiB guest was
 * reported as "7 MB RAM" because the parser trusted the basic-memory tag.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>

#include "boot_info.h"

static int fails;
static void ok(const char *name, int cond, const char *detail)
{
	if (cond) printf("PASS  %-58s\n", name);
	else { printf("FAIL  %-58s  %s\n", name, detail ? detail : ""); fails++; }
}

#define MAGIC 0x36D76289u
static uint8_t info[8192] __attribute__((aligned(8)));
static uint32_t at;

static void begin(void) { memset(info, 0, sizeof info); at = 8; }
static void put32(uint32_t v) { memcpy(info + at, &v, 4); at += 4; }
static void put64(uint64_t v) { memcpy(info + at, &v, 8); at += 8; }
static void pad(void) { at = (at + 7u) & ~7u; }
static void end(void) { put32(0); put32(8); uint32_t t = at; memcpy(info, &t, 4); }

static void basic_mem(uint32_t lower_kib, uint32_t upper_kib)
{ put32(4); put32(16); put32(lower_kib); put32(upper_kib); pad(); }

/* regions: {base, length, type} */
static void mmap(const uint64_t (*r)[3], int n)
{
	put32(6); put32(16 + 24u * (uint32_t)n); put32(24); put32(0);
	for (int i = 0; i < n; i++) { put64(r[i][0]); put64(r[i][1]); put32((uint32_t)r[i][2]); put32(0); }
	pad();
}

/* descriptors: {efi type, phys start, pages}; descr_size 48 (larger than the
 * 40-byte struct, as real firmware does: the stride is descr_size) */
static void efi_mmap(const uint64_t (*d)[3], int n)
{
	put32(17); put32(16 + 48u * (uint32_t)n); put32(48); put32(1);
	for (int i = 0; i < n; i++) {
		put32((uint32_t)d[i][0]); put32(0); put64(d[i][1]); put64(0); put64(d[i][2]); put64(0);
		put64(0);   /* 8 bytes of stride padding past the 40-byte descriptor */
	}
	pad();
}

static void module(uint32_t start, uint32_t end_, const char *cmd)
{
	uint32_t n = (uint32_t)strlen(cmd) + 1;
	put32(3); put32(16 + n); put32(start); put32(end_);
	memcpy(info + at, cmd, n); at += n; pad();
}

#define MiB (1024ull * 1024)

int main(void)
{
	char why[128];

	/* BIOS shape: basic memory agrees with the map (one region above 1 MiB). */
	begin();
	basic_mem(639, (255 * 1024) - 1024 + 1024 - 128);   /* arbitrary; the map wins */
	uint64_t bios[][3] = {{0, 639 * 1024, 1}, {0x9FC00, 1024, 2}, {0x100000, 254 * MiB, 1},
	                      {0xFFFC0000, 256 * 1024, 2}};
	mmap(bios, 4);
	end();
	hw_summary_t hw = boot_parse_info(info, MAGIC);
	uint64_t want = 639 * 1024 + 254 * MiB;
	snprintf(why, sizeof why, "got %llu, want %llu", (unsigned long long)hw.total_ram_bytes,
	         (unsigned long long)want);
	ok("BIOS shape: RAM is the sum of available map regions", hw.total_ram_bytes == want, why);
	ok("BIOS shape: sized from the memory map (tag 6)", hw.ram_source == 6, NULL);

	/* UEFI shape: basic memory stops at the first hole (~7 MiB), the map does not. */
	begin();
	basic_mem(640, 7 * 1024);
	uint64_t uefi[][3] = {{0, 640 * 1024, 1}, {0x100000, 7 * MiB, 1}, {0x800000, 1 * MiB, 2},
	                      {0x900000, 240 * MiB, 1}};
	mmap(uefi, 4);
	uint64_t efid[][3] = {{7, 0x100000, 7 * 256}, {2, 0x900000, 4096}, {4, 0x1900000, 57344}};
	efi_mmap(efid, 3);
	end();
	hw = boot_parse_info(info, MAGIC);
	want = 640 * 1024 + 247 * MiB;
	snprintf(why, sizeof why, "got %llu MiB", (unsigned long long)(hw.total_ram_bytes / MiB));
	ok("UEFI shape: the basic-memory hole is not taken as the total", hw.total_ram_bytes == want, why);

	/* EFI map only (no tag 6): sized from tag 17, stride = descr_size. */
	begin();
	basic_mem(640, 7 * 1024);
	efi_mmap(efid, 3);
	end();
	hw = boot_parse_info(info, MAGIC);
	want = (7 * 256 + 4096 + 57344) * 4096ull;
	snprintf(why, sizeof why, "got %llu, want %llu", (unsigned long long)hw.total_ram_bytes,
	         (unsigned long long)want);
	ok("EFI map only: usable EFI types summed", hw.total_ram_bytes == want, why);
	ok("EFI map only: sized from tag 17", hw.ram_source == 17, NULL);

	/* Reserved and ACPI EFI types are not RAM the kernel may use. */
	begin();
	uint64_t efir[][3] = {{7, 0x100000, 256}, {0, 0, 16}, {9, 0x200000, 16}, {10, 0x300000, 16}};
	efi_mmap(efir, 4);
	end();
	hw = boot_parse_info(info, MAGIC);
	ok("EFI reserved/ACPI types are excluded", hw.total_ram_bytes == 256 * 4096ull, NULL);

	/* Nothing but basic memory: the last resort. */
	begin();
	basic_mem(640, 130048);
	end();
	hw = boot_parse_info(info, MAGIC);
	ok("basic memory only: used as the last resort",
	   hw.total_ram_bytes == (640 + 130048) * 1024ull && hw.ram_source == 4, NULL);

	/* Modules still parse among the new tags, and padding is honoured. */
	begin();
	module(0x2000000, 0x2400000, "model");
	mmap(bios, 4);
	module(0x3000000, 0x3001000, "doom.wad");
	end();
	hw = boot_parse_info(info, MAGIC);
	ok("modules parse around the memory maps",
	   hw.module_count == 2 && strcmp(hw.modules[1].cmdline, "doom.wad") == 0 &&
	   hw.modules[0].end == 0x2400000, NULL);

	ok("a wrong magic yields an empty summary",
	   boot_parse_info(info, 0x2BADB002u).total_ram_bytes == 0, NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
