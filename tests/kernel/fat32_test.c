/* Host tests for FAT32 (agent/kernel_spec/subsystems/fs.md "FAT32").
 *
 *   fat32_test <volume.img> <scratch.img> <fat16.img>
 *
 * run_fat32_test.sh builds all three with mtools, runs this, then checks what
 * this wrote with mtools' own reader. That last step is the point: a
 * filesystem proved only against its own reader is proved self-consistent,
 * not correct. mtools is an implementation this repo did not write.
 *
 * <volume.img> is read, then written. <scratch.img> is corrupted on purpose
 * (a looping chain, an orphaned long name). <fat16.img> must be refused.
 */
#define _POSIX_C_SOURCE 200809L
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include <unistd.h>

#include "blk.h"
#include "fat32.h"

static int fails;
static void ok(const char *name, int cond, const char *detail)
{
	if (cond) {
		printf("PASS  %-60s\n", name);
	} else {
		printf("FAIL  %-60s  %s\n", name, detail ? detail : "");
		fails++;
	}
}

/* --- the block device: one file per dev id -------------------------------- */
static int fds[3];

int blk_read(uint32_t dev, uint64_t lba, uint32_t count, void *buf)
{
	ssize_t want = (ssize_t)count * 512;
	return pread(fds[dev], buf, (size_t)want, (off_t)(lba * 512)) == want ? 0 : -1;
}

int blk_write(uint32_t dev, uint64_t lba, uint32_t count, const void *buf)
{
	ssize_t want = (ssize_t)count * 512;
	return pwrite(fds[dev], buf, (size_t)want, (off_t)(lba * 512)) == want ? 0 : -1;
}

int blk_get_info(uint32_t dev, blk_info_t *info)
{
	off_t end = lseek(fds[dev], 0, SEEK_END);
	memset(info, 0, sizeof *info);
	info->sector_count = (uint64_t)end / 512;
	info->sector_size = 512;
	return 0;
}

static uint8_t seed_expect(uint32_t i) { return (uint8_t)("0123456789abcdef"[i % 16]); }
static uint8_t big_expect(uint32_t i) { return (uint8_t)(i * 7 + 3); }

static int has_name;
static const char *looking_for;
static void find_name(const fat32_dirent_t *e, void *ctx)
{
	(void)ctx;
	if (strcmp(e->name, looking_for) == 0)
		has_name = 1;
}

static uint32_t raw32(uint32_t dev, uint32_t lba, uint32_t off)
{
	uint8_t s[512];
	blk_read(dev, lba, 1, s);
	return (uint32_t)s[off] | (uint32_t)s[off + 1] << 8 | (uint32_t)s[off + 2] << 16 |
	       (uint32_t)s[off + 3] << 24;
}

static void raw_put32(uint32_t dev, uint32_t lba, uint32_t off, uint32_t val)
{
	uint8_t s[512];
	blk_read(dev, lba, 1, s);
	for (int i = 0; i < 4; i++)
		s[off + i] = (uint8_t)(val >> (8 * i));
	blk_write(dev, lba, 1, s);
}

static int fats_identical(fat32_vol_t *v)
{
	uint8_t a[512], b[512];
	for (uint32_t s = 0; s < v->fat_size; s++) {
		blk_read(v->dev, v->reserved_sectors + s, 1, a);
		blk_read(v->dev, v->reserved_sectors + v->fat_size + s, 1, b);
		if (memcmp(a, b, 512) != 0)
			return 0;
	}
	return 1;
}

int main(int argc, char **argv)
{
	if (argc != 4) {
		fprintf(stderr, "usage: %s volume.img scratch.img fat16.img\n", argv[0]);
		return 2;
	}
	for (int i = 0; i < 3; i++)
		if ((fds[i] = open(argv[i + 1], O_RDWR)) < 0) {
			perror(argv[i + 1]);
			return 2;
		}
	char why[160];
	static uint8_t buf[200000];
	fat32_vol_t v;
	fat32_file_t f;

	/* --- mount and type determination --------------------------------------- */
	int r = fat32_mount(&v, 0);
	snprintf(why, sizeof why, "rc %d", r);
	ok("mounts a volume mformat -F made", r == FAT32_OK, why);
	snprintf(why, sizeof why, "%u clusters", v.total_clusters);
	ok("it is FAT32 by cluster count (>= 65525)", v.total_clusters >= 65525, why);
	fat32_vol_t v16;
	ok("a FAT16 volume is refused, whatever its label says",
	   fat32_mount(&v16, 2) == FAT32_EBADFS, NULL);

	/* --- reads of what mtools wrote ------------------------------------------ */
	r = fat32_open(&v, "SEED.TXT", &f);
	int32_t n = r == FAT32_OK ? fat32_read(&v, &f, 0, buf, sizeof buf) : r;
	int seed_ok = n == 1000;
	for (int i = 0; seed_ok && i < 1000; i++)
		seed_ok = buf[i] == seed_expect((uint32_t)i);
	snprintf(why, sizeof why, "read %d", n);
	ok("reads an 8.3 file mcopy wrote, byte for byte", seed_ok, why);
	ok("lookup is case-insensitive", fat32_open(&v, "seed.txt", &f) == FAT32_OK, NULL);

	r = fat32_open(&v, "A long file name.txt", &f);
	n = r == FAT32_OK ? fat32_read(&v, &f, 0, buf, sizeof buf) : r;
	ok("reads a file by its long name", n == 18 && memcmp(buf, "long name content\n", 18) == 0,
	   NULL);
	looking_for = "A long file name.txt";
	has_name = 0;
	fat32_list(&v, "/", find_name, NULL);
	ok("the listing shows the long name", has_name, NULL);

	r = fat32_open(&v, "DIR/NESTED.TXT", &f);
	n = r == FAT32_OK ? fat32_read(&v, &f, 0, buf, sizeof buf) : r;
	ok("reads a file in a subdirectory", n == 7 && memcmp(buf, "nested\n", 7) == 0, NULL);
	ok("a file used as a directory is refused",
	   fat32_open(&v, "SEED.TXT/X", &f) == FAT32_ENOTDIR, NULL);
	ok("a missing file is ENOENT", fat32_open(&v, "NOPE.TXT", &f) == FAT32_ENOENT, NULL);

	r = fat32_open(&v, "BIG.BIN", &f);
	n = r == FAT32_OK ? fat32_read(&v, &f, 0, buf, sizeof buf) : r;
	int big_ok = n == 70000;
	for (int i = 0; big_ok && i < 70000; i++)
		big_ok = buf[i] == big_expect((uint32_t)i);
	ok("reads a multi-cluster file intact", big_ok, NULL);
	n = fat32_read(&v, &f, 4000, buf, 1000);
	int mid_ok = n == 1000;
	for (int i = 0; mid_ok && i < 1000; i++)
		mid_ok = buf[i] == big_expect((uint32_t)(4000 + i));
	ok("a read at an offset crossing a cluster boundary", mid_ok, NULL);
	ok("a read past the end returns 0", fat32_read(&v, &f, 70000, buf, 10) == 0, NULL);

	/* --- corruption on the scratch copy -------------------------------------- */
	fat32_vol_t s;
	fat32_mount(&s, 1);
	fat32_file_t sb;
	fat32_open(&s, "BIG.BIN", &sb);
	uint32_t second;
	fat32_fat_get(&s, sb.first_cluster, &second);

	/* The top 4 bits of a FAT32 entry are reserved and must be ignored
	 * (fatgen103). mtools always writes them as zero, so without this an
	 * implementation that forgets the mask passes every other test. */
	uint32_t first_byte = sb.first_cluster * 4;
	for (uint32_t k = 0; k < s.num_fats; k++)
		raw_put32(1, s.reserved_sectors + k * s.fat_size + first_byte / 512, first_byte % 512,
		          0xF0000000u | second);
	s.cached_lba = 0xFFFFFFFFu;
	n = fat32_read(&s, &sb, 0, buf, sizeof buf);
	big_ok = n == 70000;
	for (int i = 0; big_ok && i < 70000; i++)
		big_ok = buf[i] == big_expect((uint32_t)i);
	snprintf(why, sizeof why, "read %d", n);
	ok("reserved top 4 bits of a FAT entry are ignored", big_ok, why);
	/* Make the second cluster point back at the first: a loop. */
	uint32_t fat_byte = second * 4;
	for (uint32_t k = 0; k < s.num_fats; k++)
		raw_put32(1, s.reserved_sectors + k * s.fat_size + fat_byte / 512, fat_byte % 512,
		          sb.first_cluster);
	s.cached_lba = 0xFFFFFFFFu;
	n = fat32_read(&s, &sb, 0, buf, sizeof buf);
	snprintf(why, sizeof why, "returned %d", n);
	ok("a looping cluster chain is an error, not a hang", n == FAT32_ECHAIN, why);
	/* A chain pointing past the volume. */
	for (uint32_t k = 0; k < s.num_fats; k++)
		raw_put32(1, s.reserved_sectors + k * s.fat_size + fat_byte / 512, fat_byte % 512,
		          s.total_clusters + 10);
	s.cached_lba = 0xFFFFFFFFu;
	ok("a chain leaving the volume is an error",
	   fat32_read(&s, &sb, 0, buf, sizeof buf) == FAT32_ECHAIN, NULL);

	/* Orphan the long name: corrupt the checksum in every LFN entry before the
	 * short entry of "A long file name.txt". */
	fat32_file_t lf;
	fat32_open(&s, "A long file name.txt", &lf);
	uint8_t sec[512];
	blk_read(1, lf.dirent_lba, 1, sec);
	for (int back = (int)lf.dirent_off - 32; back >= 0 && (sec[back + 11] & 0x3F) == 0x0F;
	     back -= 32)
		sec[back + 13] ^= 0xFF;
	blk_write(1, lf.dirent_lba, 1, sec);
	s.cached_lba = 0xFFFFFFFFu;
	ok("a long name whose checksum does not match is ignored",
	   fat32_open(&s, "A long file name.txt", &lf) == FAT32_ENOENT, NULL);
	looking_for = "ALONGF~1.TXT";
	has_name = 0;
	fat32_list(&s, "/", find_name, NULL);
	ok("the entry is still reachable by its 8.3 alias", has_name, NULL);

	/* --- writes --------------------------------------------------------------- */
	ok("a read-only mount refuses writes", fat32_create(&v, "NO.TXT", &f) == FAT32_EROFS, NULL);

	/* Lie in FSInfo: next-free points at SEED.TXT's first cluster. A writer that
	 * trusts the hint overwrites SEED.TXT. */
	fat32_file_t seed;
	fat32_open(&v, "SEED.TXT", &seed);
	raw_put32(0, v.fsinfo_sector, 488, 5000000);
	raw_put32(0, v.fsinfo_sector, 492, seed.first_cluster);

	r = fat32_mount_rw(&v, 0);
	ok("mounts read-write", r == FAT32_OK, NULL);
	int dirty = 1;
	for (uint32_t k = 0; k < v.num_fats; k++)
		dirty &= !(raw32(0, v.reserved_sectors + k * v.fat_size, 4) & 0x08000000u);
	ok("mount-rw clears the clean-shutdown bit in every FAT", dirty, NULL);
	ok("FSInfo hints are marked unknown", raw32(0, v.fsinfo_sector, 488) == 0xFFFFFFFFu &&
	   raw32(0, v.fsinfo_sector, 492) == 0xFFFFFFFFu, NULL);

	r = fat32_create(&v, "WROTE.TXT", &f);
	int32_t a1 = r == FAT32_OK ? fat32_append(&v, &f, "hello from the reference\n", 25) : r;
	int32_t a2 = fat32_append(&v, &f, "second line\n", 12);
	ok("creates and appends to a new file", a1 == 25 && a2 == 12 && f.size == 37, NULL);
	ok("creating an existing name is EEXIST",
	   fat32_create(&v, "WROTE.TXT", &f) == FAT32_EEXIST, NULL);
	ok("a name that is not 8.3 is refused, not mangled",
	   fat32_create(&v, "not an 8.3 name.text", &f) == FAT32_ENAME, NULL);

	/* FRAG.BIN lands first-fit in HOLE.BIN's freed clusters, then continues past
	 * AFTER.BIN: a fragmented chain. */
	uint32_t csize = v.sectors_per_cluster * 512;
	uint32_t fraglen = 5 * csize + 100;
	for (uint32_t i = 0; i < fraglen; i++)
		buf[i] = (uint8_t)(i * 13 + 1);
	fat32_create(&v, "FRAG.BIN", &f);
	n = fat32_append(&v, &f, buf, fraglen);
	uint32_t c = f.first_cluster, prev = 0;
	int jumps = 0;
	while (c < 0x0FFFFFF8u) {
		if (prev && c != prev + 1)
			jumps++;
		prev = c;
		fat32_fat_get(&v, c, &c);
	}
	snprintf(why, sizeof why, "wrote %d, %d discontinuities", n, jumps);
	ok("a file larger than the free hole gets a fragmented chain",
	   n == (int32_t)fraglen && jumps >= 1, why);

	fat32_open(&v, "SEED.TXT", &seed);
	n = fat32_read(&v, &seed, 0, buf + 100000, 1000);
	seed_ok = n == 1000;
	for (int i = 0; seed_ok && i < 1000; i++)
		seed_ok = buf[100000 + i] == seed_expect((uint32_t)i);
	ok("FSInfo's lying next-free did not overwrite SEED.TXT", seed_ok, NULL);

	ok("mkdir creates a directory", fat32_mkdir(&v, "MAILDIR") == FAT32_OK, NULL);
	r = fat32_create(&v, "MAILDIR/M0000001.EML", &f);
	a1 = r == FAT32_OK ? fat32_append(&v, &f, "Subject: hi\r\n\r\nbody\r\n", 21) : r;
	ok("creates a file inside the new directory", a1 == 21, NULL);

	fat32_create(&v, "TRUNC.BIN", &f);
	fat32_append(&v, &f, buf, 3 * csize);
	uint32_t t_first = f.first_cluster, t_second;
	fat32_fat_get(&v, t_first, &t_second);
	ok("truncate shrinks a file", fat32_truncate(&v, &f, 100) == FAT32_OK && f.size == 100,
	   NULL);
	uint32_t e_first, e_second;
	fat32_fat_get(&v, t_first, &e_first);
	fat32_fat_get(&v, t_second, &e_second);
	ok("the kept cluster ends the chain; the rest are freed",
	   e_first >= 0x0FFFFFF8u && e_second == 0, NULL);

	ok("every FAT copy is identical after the writes", fats_identical(&v), NULL);
	ok("unmount succeeds", fat32_unmount(&v) == FAT32_OK, NULL);
	int clean = 1;
	for (uint32_t k = 0; k < v.num_fats; k++)
		clean &= !!(raw32(0, v.reserved_sectors + k * v.fat_size, 4) & 0x08000000u);
	ok("unmount sets the clean-shutdown bit again", clean, NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
