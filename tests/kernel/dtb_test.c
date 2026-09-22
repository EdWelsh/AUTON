/* Host suite for the aarch64 device-tree parser (arch/aarch64.md).
 *
 * The fixtures are REAL: dumped from `qemu-system-aarch64 -M virt,dumpdtb=`
 * and recompiled compactly with dtc, so the node and property content is
 * QEMU's, not this test's idea of what a device tree looks like.
 *
 * On aarch64 the DTB is the only source of truth about the machine, and it is
 * firmware-supplied input. So half of this suite is the corrupt cases: a
 * parser that trusts the blob's own length fields is the same defect as a
 * network stack that trusts a header.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "fdt.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-60s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

static uint8_t *slurp(const char *path, size_t *len)
{
	FILE *f = fopen(path, "rb");
	if (!f) {
		fprintf(stderr, "cannot open %s\n", path);
		exit(2);
	}
	fseek(f, 0, SEEK_END);
	long n = ftell(f);
	fseek(f, 0, SEEK_SET);
	uint8_t *b = malloc((size_t)n);
	if (fread(b, 1, (size_t)n, f) != (size_t)n)
		exit(2);
	fclose(f);
	*len = (size_t)n;
	return b;
}

static void put_be32(uint8_t *p, uint32_t v)
{
	p[0] = (uint8_t)(v >> 24); p[1] = (uint8_t)(v >> 16);
	p[2] = (uint8_t)(v >> 8);  p[3] = (uint8_t)v;
}

int main(int argc, char **argv)
{
	const char *dir = argc > 1 ? argv[1] : "tests/kernel/dtb_fixtures";
	char path[512];
	size_t len = 0, len2 = 0;

	snprintf(path, sizeof path, "%s/virt.dtb", dir);
	uint8_t *dtb = slurp(path, &len);
	snprintf(path, sizeof path, "%s/virt-bootargs.dtb", dir);
	uint8_t *dtb2 = slurp(path, &len2);

	/* --- a real machine's tree ------------------------------------------ */
	ok("a real QEMU virt DTB validates", fdt_validate(dtb) == 0, NULL);

	uint64_t base = 0, size = 0;
	ok("its memory node is found", fdt_memory(dtb, &base, &size) == 0, NULL);
	ok("memory starts at 0x40000000, where virt puts it", base == 0x40000000ULL, NULL);
	ok("and the default machine has 128 MiB", size == 0x8000000ULL, NULL);

	uint64_t pl011 = 0;
	ok("the PL011 is found by compatible string",
	   fdt_find_compatible(dtb, "arm,pl011", &pl011) == 0, NULL);
	ok("at 0x9000000", pl011 == 0x9000000ULL,
	   "a kernel that gets this wrong cannot report that it got it wrong");
	{
		/* Matching an entry that is NOT first in the list. "arm,primecell" is
		 * the second entry for several nodes (pl011 at 0x9000000, pl031 at
		 * 0x9010000, pl061 at 0x9030000); which one comes first is QEMU's
		 * business, so the check is that one of them was found — a parser
		 * that compares the whole property as one string finds none. */
		uint64_t any = 0;
		int found = fdt_find_compatible(dtb, "arm,primecell", &any) == 0;
		ok("a compatible in the SECOND position of a list is matched",
		   found && (any == 0x9000000ULL || any == 0x9010000ULL || any == 0x9030000ULL),
		   "comparing the whole property as one string finds nothing here");
	}
	ok("the GIC is found too",
	   fdt_find_compatible(dtb, "arm,cortex-a15-gic", &base) == 0, NULL);
	ok("a compatible nobody offers is not found",
	   fdt_find_compatible(dtb, "acme,nothing", &base) == -1, NULL);

	/* --- bootargs, present and absent ------------------------------------ */
	char args[256];
	memset(args, 'X', sizeof args);      /* poisoned: an unterminated copy shows */
	ok("a machine booted with -append has bootargs",
	   fdt_bootargs(dtb2, args, sizeof args) == 0 &&
	   strcmp(args, "console=ttyAMA0 auton.mode=chat") == 0, args);
	ok("a machine booted without -append has none, which is not an error",
	   fdt_bootargs(dtb, args, sizeof args) == -1 && args[0] == 0, NULL);
	{
		/* A bootargs property whose last byte is not NUL. A well-formed tree
		 * includes the terminator in the length, so only a malformed one shows
		 * whether the parser terminates the string itself. */
		uint8_t *bad = malloc(len2);
		memcpy(bad, dtb2, len2);
		const char *needle = "console=ttyAMA0 auton.mode=chat";
		uint8_t *at = NULL;
		for (size_t i = 0; i + strlen(needle) + 1 < len2; i++)
			if (memcmp(bad + i, needle, strlen(needle)) == 0) {
				at = bad + i;
				break;
			}
		ok("the bootargs fixture could be poisoned", at != NULL, NULL);
		if (at)
			at[strlen(needle)] = 'Z';        /* the NUL becomes a character */
		char out[64];
		memset(out, 'X', sizeof out);
		int rc = fdt_bootargs(bad, out, sizeof out);
		ok("an unterminated bootargs is still returned terminated",
		   rc == 0 && strcmp(out, "console=ttyAMA0 auton.mode=chatZ") == 0,
		   "a parser that relies on the blob's terminator returns the buffer's "
		   "own contents past the value");
		free(bad);
	}

	ok("the second machine's memory is its own (512 MiB)",
	   fdt_memory(dtb2, &base, &size) == 0 && size == 0x20000000ULL,
	   "the parser must read the tree, not remember the last one");

	/* --- corrupt input, which firmware can hand us ----------------------- */
	{
		uint8_t *bad = malloc(len);
		memcpy(bad, dtb, len);
		put_be32(bad, 0xdeadbeef);
		ok("a bad magic is refused", fdt_validate(bad) == -1, NULL);
		memcpy(bad, dtb, len);
		put_be32(bad + 20, 15);
		ok("a version below 16 is refused", fdt_validate(bad) == -1, NULL);
		memcpy(bad, dtb, len);
		put_be32(bad + 8, 0x7fffffff);
		ok("a struct offset past the blob is refused", fdt_validate(bad) == -1,
		   "the header's own totalsize bounds it");
		memcpy(bad, dtb, len);
		put_be32(bad + 36, 0x7fffffff);
		ok("a struct size past the blob is refused", fdt_validate(bad) == -1, NULL);
		memcpy(bad, dtb, len);
		put_be32(bad + 12, 0x7fffffff);
		ok("a strings offset past the blob is refused", fdt_validate(bad) == -1, NULL);
		free(bad);
	}
	ok("a NULL blob is refused, not dereferenced", fdt_validate(NULL) == -1, NULL);

	{
		/* A property whose own length runs past the struct block. The header
		 * is intact, so only a per-property bounds check catches it; without
		 * one the walk reads past the blob, which is what ASan is here for. */
		uint8_t *bad = malloc(len);
		memcpy(bad, dtb, len);
		uint32_t off_struct = (uint32_t)((bad[8] << 24) | (bad[9] << 16) |
		                                 (bad[10] << 8) | bad[11]);
		uint8_t *q = bad + off_struct;
		uint8_t *stop = bad + len - 12;
		int poisoned = 0;
		while (q < stop) {
			uint32_t token = (uint32_t)((q[0] << 24) | (q[1] << 16) | (q[2] << 8) | q[3]);
			if (token == 3) {                 /* FDT_PROP: lie about both fields */
				put_be32(q + 4, 0x0F000000);      /* length past the blob */
				put_be32(q + 8, 0x0F000000);      /* name offset past the strings */
				poisoned = 1;
				break;
			}
			q += 4;
		}
		ok("the fixture could be poisoned", poisoned, "no FDT_PROP token found");
		uint64_t ignored = 0;
		ok("a property length past the blob is refused, not followed",
		   fdt_memory(bad, &ignored, &ignored) == -1 &&
		   fdt_find_compatible(bad, "arm,pl011", &ignored) == -1,
		   "a parser that trusts the blob's length fields walks off the end");
		free(bad);
	}

	{
		/* Truncation: the header still claims the full size. A parser that
		 * believes it walks off the end of the allocation, which is what
		 * ASan is here to notice. */
		uint8_t *cut = malloc(len / 2);
		memcpy(cut, dtb, len / 2);
		put_be32(cut + 4, (uint32_t)(len / 2));       /* honest totalsize */
		put_be32(cut + 36, (uint32_t)len);            /* lying struct size */
		ok("a struct block larger than the blob is refused",
		   fdt_validate(cut) == -1, NULL);
		free(cut);
	}

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	free(dtb);
	free(dtb2);
	return fails ? 1 : 0;
}
