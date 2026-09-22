/* FAT32 as specified in agent/kernel_spec/subsystems/fs.md ("FAT32").
 *
 * The read half (capability `fat32`) and the write half (capability
 * `writable`) are separate objects, so an image that excludes `writable` links
 * no write path at all (fs.md, and services/fileserver.md's excludes).
 *
 * Freestanding-shaped: no allocation, caller-owned state, one sector buffer
 * inside the volume. Sector size 512 only; others are refused at mount.
 */
#ifndef AUTON_FAT32_H
#define AUTON_FAT32_H
#include <stdint.h>

#define FAT32_SECTOR       512
#define FAT32_NAME_MAX     255

/* Errors: negative, named. */
#define FAT32_OK           0
#define FAT32_EIO         -1   /* the block device failed */
#define FAT32_EBADFS      -2   /* not FAT32 (by cluster count), or a bad BPB */
#define FAT32_ENOENT      -3
#define FAT32_ENOTDIR     -4
#define FAT32_ECHAIN      -5   /* a cluster chain loops or leaves the volume */
#define FAT32_ENOSPC      -6
#define FAT32_EEXIST      -7
#define FAT32_ENAME       -8   /* not representable as an 8.3 name (write side) */
#define FAT32_EROFS       -9   /* mounted read-only */

typedef struct {
    uint32_t dev;
    uint32_t bytes_per_sector;
    uint32_t sectors_per_cluster;
    uint32_t reserved_sectors;
    uint32_t num_fats;
    uint32_t fat_size;            /* sectors per FAT */
    uint32_t root_cluster;
    uint32_t total_clusters;      /* data clusters: valid numbers are 2..total+1 */
    uint32_t first_data_sector;
    uint32_t fsinfo_sector;
    int      writable;            /* mounted read-write (dirty flag cleared) */
    uint32_t cached_lba;          /* sector held in buf; 0xFFFFFFFF = none */
    uint8_t  buf[FAT32_SECTOR];
} fat32_vol_t;

typedef struct {
    uint32_t first_cluster;       /* 0 for an empty file */
    uint32_t size;
    int      is_dir;
    /* where the directory entry lives, so the write half can update size */
    uint32_t dirent_lba;
    uint32_t dirent_off;
} fat32_file_t;

typedef struct {
    char     name[FAT32_NAME_MAX + 1];   /* the long name if present, else NAME.EXT */
    uint32_t size;
    int      is_dir;
} fat32_dirent_t;

/* --- read half (`fat32`) --- */
int     fat32_mount(fat32_vol_t *v, uint32_t dev);
int     fat32_open(fat32_vol_t *v, const char *path, fat32_file_t *f);
int32_t fat32_read(fat32_vol_t *v, const fat32_file_t *f, uint32_t off, void *buf, uint32_t len);
/* Calls fn for each entry in directory `path`; returns entries seen or <0. */
int     fat32_list(fat32_vol_t *v, const char *path,
                   void (*fn)(const fat32_dirent_t *e, void *ctx), void *ctx);
/* The FAT entry for cluster c, masked to 28 bits. Exposed for the tests. */
int     fat32_fat_get(fat32_vol_t *v, uint32_t c, uint32_t *out);

/* --- write half (`writable`) --- */
int     fat32_mount_rw(fat32_vol_t *v, uint32_t dev);    /* clears the clean-shutdown bit */
int     fat32_unmount(fat32_vol_t *v);                   /* sets it again */
int     fat32_create(fat32_vol_t *v, const char *path, fat32_file_t *f);
int     fat32_mkdir(fat32_vol_t *v, const char *path);
int32_t fat32_append(fat32_vol_t *v, fat32_file_t *f, const void *buf, uint32_t len);
int     fat32_truncate(fat32_vol_t *v, fat32_file_t *f, uint32_t size);

/* Internal, shared by the two halves. Not for callers. */
int     fat32__sector(fat32_vol_t *v, uint32_t lba);           /* load into v->buf */
int     fat32__flush(fat32_vol_t *v);                          /* write v->buf back */
int     fat32__lookup(fat32_vol_t *v, uint32_t dir_cluster, const char *name,
                      fat32_file_t *f);
uint32_t fat32__lba(const fat32_vol_t *v, uint32_t cluster);
#endif
