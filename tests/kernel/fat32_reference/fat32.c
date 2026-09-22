/* Reference FAT32, read half: agent/kernel_spec/subsystems/fs.md "FAT32".
 *
 * NOT kernel code and not shipped. It proves fat32_test.c, and the test proves
 * it against mtools, an implementation this repo did not write. The format is
 * Microsoft's "FAT: General Overview of On-Disk Format" v1.03 (fatgen103),
 * cited below by section.
 */
#include <stdint.h>
#include <stddef.h>
#include "fat32.h"
#include "blk.h"

#define FAT_MASK   0x0FFFFFFFu      /* fatgen103 "FAT32 cluster entries are 28 bits" */
#define FAT_EOC    0x0FFFFFF8u      /* >= is end of chain */
#define FAT_BAD    0x0FFFFFF7u
#define ATTR_RO    0x01
#define ATTR_HID   0x02
#define ATTR_SYS   0x04
#define ATTR_VOL   0x08
#define ATTR_DIR   0x10
#define ATTR_LFN   (ATTR_RO | ATTR_HID | ATTR_SYS | ATTR_VOL)

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | p[1] << 8); }
static uint32_t rd32(const uint8_t *p)
{
	return (uint32_t)p[0] | (uint32_t)p[1] << 8 | (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

int fat32__sector(fat32_vol_t *v, uint32_t lba)
{
	if (v->cached_lba == lba)
		return FAT32_OK;
	if (blk_read(v->dev, lba, 1, v->buf) != 0) {
		v->cached_lba = 0xFFFFFFFFu;
		return FAT32_EIO;
	}
	v->cached_lba = lba;
	return FAT32_OK;
}

uint32_t fat32__lba(const fat32_vol_t *v, uint32_t cluster)
{
	/* fatgen103 "FirstSectorofCluster = ((N – 2) * BPB_SecPerClus) + FirstDataSector" */
	return v->first_data_sector + (cluster - 2) * v->sectors_per_cluster;
}

static int valid_cluster(const fat32_vol_t *v, uint32_t c)
{
	return c >= 2 && c < v->total_clusters + 2;
}

int fat32_mount(fat32_vol_t *v, uint32_t dev)
{
	v->dev = dev;
	v->cached_lba = 0xFFFFFFFFu;
	v->writable = 0;
	if (fat32__sector(v, 0) != FAT32_OK)
		return FAT32_EIO;
	const uint8_t *b = v->buf;
	if (b[510] != 0x55 || b[511] != 0xAA)
		return FAT32_EBADFS;

	v->bytes_per_sector    = rd16(b + 11);
	v->sectors_per_cluster = b[13];
	v->reserved_sectors    = rd16(b + 14);
	v->num_fats            = b[16];
	uint32_t root_entries  = rd16(b + 17);
	uint32_t total16       = rd16(b + 19);
	uint32_t fat16_size    = rd16(b + 22);
	uint32_t total32       = rd32(b + 32);
	v->fat_size            = rd32(b + 36);
	v->root_cluster        = rd32(b + 44);
	v->fsinfo_sector       = rd16(b + 48);

	if (v->bytes_per_sector != FAT32_SECTOR)
		return FAT32_EBADFS;      /* fs.md: 512-byte sectors only, stated */
	uint32_t spc = v->sectors_per_cluster;
	if (spc == 0 || (spc & (spc - 1)) || v->num_fats == 0 || v->reserved_sectors == 0)
		return FAT32_EBADFS;
	/* FAT32 has no fixed root directory and no 16-bit FAT size. */
	if (root_entries != 0 || fat16_size != 0 || v->fat_size == 0)
		return FAT32_EBADFS;

	uint32_t total = total16 ? total16 : total32;
	v->first_data_sector = v->reserved_sectors + v->num_fats * v->fat_size;
	if (total <= v->first_data_sector)
		return FAT32_EBADFS;
	v->total_clusters = (total - v->first_data_sector) / spc;
	/* fatgen103 "FAT Type Determination": the type is decided by the count of
	 * clusters, never by the "FAT32   " string in the BPB. */
	if (v->total_clusters < 65525)
		return FAT32_EBADFS;
	if (!valid_cluster(v, v->root_cluster))
		return FAT32_EBADFS;
	return FAT32_OK;
}

int fat32_fat_get(fat32_vol_t *v, uint32_t c, uint32_t *out)
{
	if (!valid_cluster(v, c) && c != 0 && c != 1)
		return FAT32_ECHAIN;
	uint32_t byte = c * 4;
	int r = fat32__sector(v, v->reserved_sectors + byte / FAT32_SECTOR);
	if (r != FAT32_OK)
		return r;
	*out = rd32(v->buf + byte % FAT32_SECTOR) & FAT_MASK;
	return FAT32_OK;
}

/* The next cluster in a chain: 0 at end of chain, or an error. */
static int next_cluster(fat32_vol_t *v, uint32_t c, uint32_t *next)
{
	uint32_t e;
	int r = fat32_fat_get(v, c, &e);
	if (r != FAT32_OK)
		return r;
	if (e >= FAT_EOC) {
		*next = 0;
		return FAT32_OK;
	}
	if (e == FAT_BAD || e == 0 || !valid_cluster(v, e))
		return FAT32_ECHAIN;      /* a free or bad cluster inside a chain */
	*next = e;
	return FAT32_OK;
}

/* --- directories ---------------------------------------------------------- */

static uint8_t lfn_checksum(const uint8_t *short_name)
{
	/* fatgen103 "ChkSum": rotate right, add. */
	uint8_t sum = 0;
	for (int i = 0; i < 11; i++)
		sum = (uint8_t)(((sum & 1) << 7) + (sum >> 1) + short_name[i]);
	return sum;
}

static void short_to_text(const uint8_t *n, char *out)
{
	int k = 0;
	for (int i = 0; i < 8 && n[i] != ' '; i++)
		out[k++] = (char)(i == 0 && n[i] == 0x05 ? 0xE5 : n[i]);
	if (n[8] != ' ') {
		out[k++] = '.';
		for (int i = 8; i < 11 && n[i] != ' '; i++)
			out[k++] = (char)n[i];
	}
	out[k] = 0;
}

static char upper(char c) { return (c >= 'a' && c <= 'z') ? (char)(c - 32) : c; }

static int same_name(const char *a, const char *b)
{
	for (; *a && *b; a++, b++)
		if (upper(*a) != upper(*b))
			return 0;
	return *a == *b;
}

typedef int (*dir_cb)(fat32_vol_t *v, const uint8_t *ent, const char *name,
                      uint32_t lba, uint32_t off, void *ctx);

/* Walk a directory's entries. `name` is the long name when a valid LFN set
 * precedes the entry, else the 8.3 text. cb returns nonzero to stop. */
static int dir_walk(fat32_vol_t *v, uint32_t cluster, dir_cb cb, void *ctx)
{
	char lname[FAT32_NAME_MAX + 1];
	int lfn_ok = 0;
	uint8_t lfn_sum = 0;
	int lfn_next = 0;           /* the ordinal expected next, counting down */
	uint32_t steps = 0;

	while (cluster) {
		if (++steps > v->total_clusters)
			return FAT32_ECHAIN;
		for (uint32_t s = 0; s < v->sectors_per_cluster; s++) {
			uint32_t lba = fat32__lba(v, cluster) + s;
			for (uint32_t off = 0; off < FAT32_SECTOR; off += 32) {
				int r = fat32__sector(v, lba);
				if (r != FAT32_OK)
					return r;
				uint8_t ent[32];
				for (int i = 0; i < 32; i++)
					ent[i] = v->buf[off + i];
				if (ent[0] == 0x00)
					return FAT32_OK;          /* end of directory */
				if (ent[0] == 0xE5) {
					lfn_ok = 0;
					continue;
				}
				if ((ent[11] & 0x3F) == ATTR_LFN) {
					int ord = ent[0] & 0x1F;
					if (ent[0] & 0x40) {      /* last (first stored) */
						lfn_ok = ord >= 1 && ord <= 20;
						lfn_sum = ent[13];
						lfn_next = ord;
						for (int i = 0; i <= FAT32_NAME_MAX; i++)
							lname[i] = 0;
					}
					if (!lfn_ok || ord != lfn_next || ent[13] != lfn_sum) {
						lfn_ok = 0;
						continue;
					}
					static const int pos[13] = {1, 3, 5, 7, 9, 14, 16, 18, 20, 22, 24, 28, 30};
					for (int i = 0; i < 13; i++) {
						int at = (ord - 1) * 13 + i;
						uint16_t ch = rd16(ent + pos[i]);
						if (at < FAT32_NAME_MAX && ch != 0xFFFF && ch != 0)
							lname[at] = (char)(ch < 0x80 ? ch : '?');
					}
					lfn_next--;
					continue;
				}
				if (ent[11] & ATTR_VOL) {
					lfn_ok = 0;
					continue;
				}
				char text[FAT32_NAME_MAX + 1];
				const char *name = text;
				/* A long name belongs to this entry only if the set was complete
				 * and its checksum is this short name's. Otherwise it is an
				 * orphan (fatgen103 "Long Directory Entries") and ignored. */
				if (lfn_ok && lfn_next == 0 && lfn_sum == lfn_checksum(ent))
					name = lname;
				else
					short_to_text(ent, text);
				lfn_ok = 0;
				if (cb(v, ent, name, lba, off, ctx))
					return 1;
			}
		}
		int r = next_cluster(v, cluster, &cluster);
		if (r != FAT32_OK)
			return r;
	}
	return FAT32_OK;
}

struct find_ctx { const char *want; fat32_file_t *f; int found; };

static int find_cb(fat32_vol_t *v, const uint8_t *ent, const char *name,
                   uint32_t lba, uint32_t off, void *ctx)
{
	(void)v;
	struct find_ctx *c = ctx;
	char shortname[13];
	short_to_text(ent, shortname);
	if (!same_name(name, c->want) && !same_name(shortname, c->want))
		return 0;
	c->f->first_cluster = (uint32_t)rd16(ent + 20) << 16 | rd16(ent + 26);
	c->f->size = rd32(ent + 28);
	c->f->is_dir = (ent[11] & ATTR_DIR) != 0;
	c->f->dirent_lba = lba;
	c->f->dirent_off = off;
	c->found = 1;
	return 1;
}

int fat32__lookup(fat32_vol_t *v, uint32_t dir_cluster, const char *name, fat32_file_t *f)
{
	struct find_ctx c = {name, f, 0};
	int r = dir_walk(v, dir_cluster, find_cb, &c);
	if (r < 0)
		return r;
	return c.found ? FAT32_OK : FAT32_ENOENT;
}

int fat32_open(fat32_vol_t *v, const char *path, fat32_file_t *f)
{
	f->first_cluster = v->root_cluster;
	f->size = 0;
	f->is_dir = 1;
	f->dirent_lba = f->dirent_off = 0;
	while (*path == '/')
		path++;
	while (*path) {
		char part[FAT32_NAME_MAX + 1];
		int n = 0;
		while (*path && *path != '/') {
			if (n == FAT32_NAME_MAX)
				return FAT32_ENOENT;
			part[n++] = *path++;
		}
		part[n] = 0;
		while (*path == '/')
			path++;
		if (!f->is_dir)
			return FAT32_ENOTDIR;
		int r = fat32__lookup(v, f->first_cluster ? f->first_cluster : v->root_cluster, part, f);
		if (r != FAT32_OK)
			return r;
	}
	return FAT32_OK;
}

/* A file's chain must hold exactly the clusters its size needs, and must not
 * loop. A step bound alone stops a hang but not a wrong answer: a loop within
 * the first N clusters returns N clusters of the wrong data with success. So
 * the chain is walked with Brent's cycle detection (constant memory) first. */
static int chain_check(fat32_vol_t *v, uint32_t first, uint32_t needed)
{
	uint32_t hare = first, tortoise = first, power = 1, lam = 1, count = 1;
	if (needed == 0)
		return FAT32_OK;               /* an empty file owns no clusters */
	if (!valid_cluster(v, first))
		return FAT32_ECHAIN;
	while (count < needed) {
		int r = next_cluster(v, hare, &hare);
		if (r != FAT32_OK)
			return r;
		if (!hare)
			return FAT32_ECHAIN;           /* shorter than the size says */
		count++;
		if (hare == tortoise)
			return FAT32_ECHAIN;           /* Brent: a cycle */
		if (power == lam) {
			tortoise = hare;
			power *= 2;
			lam = 0;
		}
		lam++;
	}
	return FAT32_OK;
}

int32_t fat32_read(fat32_vol_t *v, const fat32_file_t *f, uint32_t off, void *buf, uint32_t len)
{
	if (f->is_dir)
		return FAT32_ENOTDIR;
	if (off >= f->size)
		return 0;
	if (len > f->size - off)
		len = f->size - off;
	uint32_t csize = v->sectors_per_cluster * FAT32_SECTOR;
	int rc = chain_check(v, f->first_cluster, (f->size + csize - 1) / csize);
	if (rc != FAT32_OK)
		return rc;
	uint32_t cluster = f->first_cluster;
	uint32_t steps = 0;
	for (uint32_t skip = off / csize; skip; skip--) {
		if (++steps > v->total_clusters)
			return FAT32_ECHAIN;
		int r = next_cluster(v, cluster, &cluster);
		if (r != FAT32_OK)
			return r;
		if (!cluster)
			return FAT32_ECHAIN;  /* chain shorter than the size says */
	}
	uint8_t *out = buf;
	uint32_t done = 0, pos = off % csize;
	while (done < len) {
		if (!valid_cluster(v, cluster))
			return FAT32_ECHAIN;
		uint32_t lba = fat32__lba(v, cluster) + pos / FAT32_SECTOR;
		int r = fat32__sector(v, lba);
		if (r != FAT32_OK)
			return r;
		uint32_t in = pos % FAT32_SECTOR;
		uint32_t n = FAT32_SECTOR - in;
		if (n > len - done)
			n = len - done;
		for (uint32_t i = 0; i < n; i++)
			out[done + i] = v->buf[in + i];
		done += n;
		pos += n;
		if (pos == csize && done < len) {
			if (++steps > v->total_clusters)
				return FAT32_ECHAIN;
			r = next_cluster(v, cluster, &cluster);
			if (r != FAT32_OK)
				return r;
			if (!cluster)
				return FAT32_ECHAIN;
			pos = 0;
		}
	}
	return (int32_t)done;
}

struct list_ctx { void (*fn)(const fat32_dirent_t *, void *); void *ctx; int n; };

static int list_cb(fat32_vol_t *v, const uint8_t *ent, const char *name,
                   uint32_t lba, uint32_t off, void *ctx)
{
	(void)v; (void)lba; (void)off;
	struct list_ctx *c = ctx;
	if (ent[0] == '.' )           /* "." and ".." */
		return 0;
	fat32_dirent_t d;
	int i = 0;
	for (; name[i] && i < FAT32_NAME_MAX; i++)
		d.name[i] = name[i];
	d.name[i] = 0;
	d.size = rd32(ent + 28);
	d.is_dir = (ent[11] & ATTR_DIR) != 0;
	c->fn(&d, c->ctx);
	c->n++;
	return 0;
}

int fat32_list(fat32_vol_t *v, const char *path,
               void (*fn)(const fat32_dirent_t *e, void *ctx), void *ctx)
{
	fat32_file_t d;
	int r = fat32_open(v, path, &d);
	if (r != FAT32_OK)
		return r;
	if (!d.is_dir)
		return FAT32_ENOTDIR;
	struct list_ctx c = {fn, ctx, 0};
	r = dir_walk(v, d.first_cluster ? d.first_cluster : v->root_cluster, list_cb, &c);
	return r < 0 ? r : c.n;
}
