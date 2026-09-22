/* Reference FAT32, write half (capability `writable`): fs.md "FAT32".
 *
 * A separate object on purpose: an image that excludes `writable` (a read-only
 * file server) links none of this, and the leakage gate can prove it.
 *
 * Every mutation is written through before the call returns. A caller that
 * acknowledges data (the KV store's +OK, SMTP's 250) may do so as soon as the
 * call succeeds.
 */
#include <stdint.h>
#include <stddef.h>
#include "fat32.h"
#include "blk.h"

#define FAT_MASK     0x0FFFFFFFu
#define FAT_EOC      0x0FFFFFFFu
#define CLEAN_BIT    0x08000000u      /* fatgen103: FAT[1] ClnShutBitMask, 1 = clean */
#define ATTR_DIR     0x10
#define ATTR_ARCHIVE 0x20
#define DATE_1980    0x0021           /* 1980-01-01: day 1, month 1 (0 is invalid) */

static void wr16(uint8_t *p, uint16_t x) { p[0] = (uint8_t)x; p[1] = (uint8_t)(x >> 8); }
static void wr32(uint8_t *p, uint32_t x)
{
	p[0] = (uint8_t)x; p[1] = (uint8_t)(x >> 8); p[2] = (uint8_t)(x >> 16); p[3] = (uint8_t)(x >> 24);
}
static uint32_t rd32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int fat32__flush(fat32_vol_t *v)
{
	return blk_write(v->dev, v->cached_lba, 1, v->buf) == 0 ? FAT32_OK : FAT32_EIO;
}

/* Set a FAT entry in EVERY copy, preserving the reserved top 4 bits
 * (fatgen103: "the high 4 bits ... must be preserved"). */
static int fat_set(fat32_vol_t *v, uint32_t c, uint32_t val)
{
	uint32_t byte = c * 4;
	for (uint32_t i = 0; i < v->num_fats; i++) {
		uint32_t lba = v->reserved_sectors + i * v->fat_size + byte / FAT32_SECTOR;
		int r = fat32__sector(v, lba);
		if (r != FAT32_OK)
			return r;
		uint8_t *p = v->buf + byte % FAT32_SECTOR;
		wr32(p, (rd32(p) & ~FAT_MASK) | (val & FAT_MASK));
		if ((r = fat32__flush(v)) != FAT32_OK)
			return r;
	}
	return FAT32_OK;
}

static int set_clean_bit(fat32_vol_t *v, int clean)
{
	for (uint32_t i = 0; i < v->num_fats; i++) {
		int r = fat32__sector(v, v->reserved_sectors + i * v->fat_size);
		if (r != FAT32_OK)
			return r;
		uint32_t e = rd32(v->buf + 4);
		wr32(v->buf + 4, clean ? (e | CLEAN_BIT) : (e & ~CLEAN_BIT));
		if ((r = fat32__flush(v)) != FAT32_OK)
			return r;
	}
	return FAT32_OK;
}

int fat32_mount_rw(fat32_vol_t *v, uint32_t dev)
{
	int r = fat32_mount(v, dev);
	if (r != FAT32_OK)
		return r;
	/* FSInfo's free count and next-free are hints, and are never trusted
	 * (fatgen103 "FSInfo Sector Structure"). Mark both unknown, so no other
	 * implementation trusts a value this one has invalidated. */
	if (v->fsinfo_sector && v->fsinfo_sector < v->reserved_sectors) {
		if ((r = fat32__sector(v, v->fsinfo_sector)) != FAT32_OK)
			return r;
		if (rd32(v->buf) == 0x41615252 && rd32(v->buf + 484) == 0x61417272) {
			wr32(v->buf + 488, 0xFFFFFFFFu);
			wr32(v->buf + 492, 0xFFFFFFFFu);
			if ((r = fat32__flush(v)) != FAT32_OK)
				return r;
		}
	}
	if ((r = set_clean_bit(v, 0)) != FAT32_OK)
		return r;
	v->writable = 1;
	return FAT32_OK;
}

int fat32_unmount(fat32_vol_t *v)
{
	if (!v->writable)
		return FAT32_OK;
	int r = set_clean_bit(v, 1);
	v->writable = 0;
	return r;
}

static int zero_cluster(fat32_vol_t *v, uint32_t c)
{
	for (uint32_t s = 0; s < v->sectors_per_cluster; s++) {
		v->cached_lba = fat32__lba(v, c) + s;
		for (int i = 0; i < FAT32_SECTOR; i++)
			v->buf[i] = 0;
		int r = fat32__flush(v);
		if (r != FAT32_OK)
			return r;
	}
	return FAT32_OK;
}

/* First-fit from cluster 2, scanning the FAT itself. Linked after `prev` when
 * prev is nonzero. The new cluster is zeroed: freed data never leaks into a
 * new file, and a new directory cluster reads as empty. */
static int alloc_cluster(fat32_vol_t *v, uint32_t prev, uint32_t *out)
{
	for (uint32_t c = 2; c < v->total_clusters + 2; c++) {
		uint32_t e;
		int r = fat32_fat_get(v, c, &e);
		if (r != FAT32_OK)
			return r;
		if (e != 0)
			continue;
		if ((r = fat_set(v, c, FAT_EOC)) != FAT32_OK)
			return r;
		if (prev && (r = fat_set(v, prev, c)) != FAT32_OK)
			return r;
		if ((r = zero_cluster(v, c)) != FAT32_OK)
			return r;
		*out = c;
		return FAT32_OK;
	}
	return FAT32_ENOSPC;
}

static int write_dirent(fat32_vol_t *v, const fat32_file_t *f)
{
	int r = fat32__sector(v, f->dirent_lba);
	if (r != FAT32_OK)
		return r;
	uint8_t *e = v->buf + f->dirent_off;
	wr16(e + 20, (uint16_t)(f->first_cluster >> 16));
	wr16(e + 26, (uint16_t)f->first_cluster);
	wr32(e + 28, f->is_dir ? 0 : f->size);
	wr16(e + 24, DATE_1980);                 /* last write date */
	return fat32__flush(v);
}

/* "name.ext" to the 11-byte padded form; FAT32_ENAME if not 8.3. Lower case is
 * folded: 8.3 names are upper case on disk and lookup is case-insensitive. */
static int to_short(const char *name, uint8_t out[11])
{
	static const char ok_punct[] = "!#$%&'()-@^_`{}~";
	for (int i = 0; i < 11; i++)
		out[i] = ' ';
	int i = 0, k = 0, in_ext = 0;
	if (!name[0] || name[0] == '.')
		return FAT32_ENAME;
	for (; name[i]; i++) {
		char c = name[i];
		if (c == '.') {
			if (in_ext)
				return FAT32_ENAME;
			in_ext = 1;
			k = 8;
			continue;
		}
		if (c >= 'a' && c <= 'z')
			c = (char)(c - 32);
		int good = (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
		for (const char *p = ok_punct; !good && *p; p++)
			good = (c == *p);
		if (!good)
			return FAT32_ENAME;
		if ((!in_ext && k >= 8) || (in_ext && k >= 11))
			return FAT32_ENAME;
		out[k++] = (uint8_t)c;
	}
	return FAT32_OK;
}

/* Split "a/b/c" into parent directory cluster and leaf name. */
static int parent_of(fat32_vol_t *v, const char *path, uint32_t *dir, const char **leaf)
{
	const char *slash = 0;
	for (const char *p = path; *p; p++)
		if (*p == '/')
			slash = p;
	if (!slash || slash == path) {
		*dir = v->root_cluster;
		*leaf = slash ? slash + 1 : path;
		return FAT32_OK;
	}
	char buf[FAT32_NAME_MAX + 1];
	int n = (int)(slash - path);
	if (n > FAT32_NAME_MAX)
		return FAT32_ENOENT;
	for (int i = 0; i < n; i++)
		buf[i] = path[i];
	buf[n] = 0;
	fat32_file_t d;
	int r = fat32_open(v, buf, &d);
	if (r != FAT32_OK)
		return r;
	if (!d.is_dir)
		return FAT32_ENOTDIR;
	*dir = d.first_cluster ? d.first_cluster : v->root_cluster;
	*leaf = slash + 1;
	return FAT32_OK;
}

/* Find a free 32-byte slot in a directory, extending it by a cluster if full. */
static int free_slot(fat32_vol_t *v, uint32_t dir, uint32_t *lba_out, uint32_t *off_out)
{
	uint32_t c = dir, last = dir, steps = 0;
	while (c) {
		if (++steps > v->total_clusters)
			return FAT32_ECHAIN;
		for (uint32_t s = 0; s < v->sectors_per_cluster; s++) {
			uint32_t lba = fat32__lba(v, c) + s;
			int r = fat32__sector(v, lba);
			if (r != FAT32_OK)
				return r;
			for (uint32_t off = 0; off < FAT32_SECTOR; off += 32)
				if (v->buf[off] == 0x00 || v->buf[off] == 0xE5) {
					*lba_out = lba;
					*off_out = off;
					return FAT32_OK;
				}
		}
		last = c;
		uint32_t e;
		int r = fat32_fat_get(v, c, &e);
		if (r != FAT32_OK)
			return r;
		c = (e >= 0x0FFFFFF8u) ? 0 : e;
	}
	uint32_t fresh;
	int r = alloc_cluster(v, last, &fresh);
	if (r != FAT32_OK)
		return r;
	*lba_out = fat32__lba(v, fresh);
	*off_out = 0;
	return FAT32_OK;
}

static int make_entry(fat32_vol_t *v, const char *path, uint8_t attr, fat32_file_t *f)
{
	if (!v->writable)
		return FAT32_EROFS;
	uint32_t dir;
	const char *leaf;
	int r = parent_of(v, path, &dir, &leaf);
	if (r != FAT32_OK)
		return r;
	uint8_t shortname[11];
	if ((r = to_short(leaf, shortname)) != FAT32_OK)
		return r;
	fat32_file_t existing;
	r = fat32__lookup(v, dir, leaf, &existing);
	if (r == FAT32_OK)
		return FAT32_EEXIST;
	if (r != FAT32_ENOENT)
		return r;

	uint32_t lba, off;
	if ((r = free_slot(v, dir, &lba, &off)) != FAT32_OK)
		return r;
	if ((r = fat32__sector(v, lba)) != FAT32_OK)
		return r;
	uint8_t *e = v->buf + off;
	int was_end = (e[0] == 0x00);
	for (int i = 0; i < 32; i++)
		e[i] = 0;
	for (int i = 0; i < 11; i++)
		e[i] = shortname[i];
	e[11] = attr;
	wr16(e + 16, DATE_1980);                 /* creation date */
	wr16(e + 18, DATE_1980);                 /* last access date */
	wr16(e + 24, DATE_1980);                 /* last write date */
	/* Keep the directory terminated: if this slot was the end marker, the next
	 * slot must now be. A zeroed cluster already reads as the end. */
	(void)was_end;
	if ((r = fat32__flush(v)) != FAT32_OK)
		return r;

	f->first_cluster = 0;
	f->size = 0;
	f->is_dir = (attr & ATTR_DIR) != 0;
	f->dirent_lba = lba;
	f->dirent_off = off;
	return FAT32_OK;
}

int fat32_create(fat32_vol_t *v, const char *path, fat32_file_t *f)
{
	return make_entry(v, path, ATTR_ARCHIVE, f);
}

int fat32_mkdir(fat32_vol_t *v, const char *path)
{
	fat32_file_t d;
	uint32_t parent;
	const char *leaf;
	int r = parent_of(v, path, &parent, &leaf);
	if (r != FAT32_OK)
		return r;
	if ((r = make_entry(v, path, ATTR_DIR, &d)) != FAT32_OK)
		return r;
	uint32_t c;
	if ((r = alloc_cluster(v, 0, &c)) != FAT32_OK)
		return r;
	d.first_cluster = c;
	if ((r = write_dirent(v, &d)) != FAT32_OK)
		return r;
	/* "." and "..": fatgen103 "FAT Directory Structure". ".." of a directory
	 * in the root points at cluster 0, not the root cluster number. */
	if ((r = fat32__sector(v, fat32__lba(v, c))) != FAT32_OK)
		return r;
	uint32_t up = (parent == v->root_cluster) ? 0 : parent;
	for (int k = 0; k < 2; k++) {
		uint8_t *e = v->buf + 32 * k;
		for (int i = 0; i < 11; i++)
			e[i] = ' ';
		e[0] = '.';
		if (k == 1)
			e[1] = '.';
		e[11] = ATTR_DIR;
		uint32_t to = k == 0 ? c : up;
		wr16(e + 20, (uint16_t)(to >> 16));
		wr16(e + 26, (uint16_t)to);
		wr16(e + 24, DATE_1980);
		wr16(e + 16, DATE_1980);
	}
	return fat32__flush(v);
}

int32_t fat32_append(fat32_vol_t *v, fat32_file_t *f, const void *buf, uint32_t len)
{
	if (!v->writable)
		return FAT32_EROFS;
	if (f->is_dir)
		return FAT32_ENOTDIR;
	uint32_t csize = v->sectors_per_cluster * FAT32_SECTOR;
	const uint8_t *in = buf;
	uint32_t done = 0;
	int r;

	/* Find the last cluster of the chain. */
	uint32_t last = f->first_cluster, steps = 0;
	if (last) {
		for (;;) {
			uint32_t e;
			if (++steps > v->total_clusters)
				return FAT32_ECHAIN;
			if ((r = fat32_fat_get(v, last, &e)) != FAT32_OK)
				return r;
			if (e >= 0x0FFFFFF8u)
				break;
			last = e;
		}
	}

	while (done < len) {
		uint32_t pos = f->size % csize;
		if (!last || (pos == 0 && f->size > 0)) {
			uint32_t c;
			if ((r = alloc_cluster(v, last, &c)) != FAT32_OK)
				return done ? (int32_t)done : r;
			if (!f->first_cluster)
				f->first_cluster = c;
			last = c;
			pos = 0;
		}
		uint32_t lba = fat32__lba(v, last) + pos / FAT32_SECTOR;
		if ((r = fat32__sector(v, lba)) != FAT32_OK)
			return r;
		uint32_t at = pos % FAT32_SECTOR;
		uint32_t n = FAT32_SECTOR - at;
		if (n > len - done)
			n = len - done;
		for (uint32_t i = 0; i < n; i++)
			v->buf[at + i] = in[done + i];
		if ((r = fat32__flush(v)) != FAT32_OK)
			return r;
		done += n;
		f->size += n;
	}
	if ((r = write_dirent(v, f)) != FAT32_OK)
		return r;
	return (int32_t)done;
}

int fat32_truncate(fat32_vol_t *v, fat32_file_t *f, uint32_t size)
{
	if (!v->writable)
		return FAT32_EROFS;
	if (size > f->size)
		return FAT32_ENOSPC;       /* only shrinking is specified */
	uint32_t csize = v->sectors_per_cluster * FAT32_SECTOR;
	uint32_t keep = (size + csize - 1) / csize;
	uint32_t c = f->first_cluster, prev = 0, i = 0, steps = 0;
	int r;
	while (c && c < 0x0FFFFFF8u) {
		if (++steps > v->total_clusters)
			return FAT32_ECHAIN;
		uint32_t next;
		if ((r = fat32_fat_get(v, c, &next)) != FAT32_OK)
			return r;
		if (i == keep && prev)
			if ((r = fat_set(v, prev, FAT_EOC)) != FAT32_OK)
				return r;
		if (i >= keep && (r = fat_set(v, c, 0)) != FAT32_OK)
			return r;
		prev = c;
		c = next;
		i++;
	}
	if (keep == 0)
		f->first_cluster = 0;
	f->size = size;
	return write_dirent(v, f);
}
