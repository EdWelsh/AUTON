# Filesystem Specification

## Overview

The filesystem subsystem provides a Linux-inspired Virtual Filesystem Switch (VFS) layer that abstracts all file operations behind a uniform inode/dentry/superblock interface. Concrete filesystem implementations (initramfs, ext2, devfs, procfs) register with the VFS and handle the actual on-disk or in-memory data layout. The SLM uses VFS operations to partition disks, format filesystems, mount volumes, and install files during system setup.

## Data Structures

### VFS Core Abstractions

```c
/* Forward declarations */
typedef struct inode inode_t;
typedef struct dentry dentry_t;
typedef struct superblock superblock_t;
typedef struct file file_t;
typedef struct vfs_mount vfs_mount_t;
typedef struct fs_type fs_type_t;

/* File types */
typedef enum file_type {
    FT_REGULAR  = 1,    /* regular file */
    FT_DIRECTORY = 2,   /* directory */
    FT_CHARDEV  = 3,    /* character device */
    FT_BLKDEV   = 4,    /* block device */
    FT_SYMLINK  = 5,    /* symbolic link */
    FT_PIPE     = 6,    /* named pipe / FIFO */
    FT_SOCKET   = 7,    /* socket */
} file_type_t;

/* File permissions (Unix-style octal) */
#define PERM_READ       0x04
#define PERM_WRITE      0x02
#define PERM_EXEC       0x01
#define PERM_OWNER_SHIFT 6
#define PERM_GROUP_SHIFT 3
#define PERM_OTHER_SHIFT 0

/* Standard permission sets */
#define PERM_RWXR_XR_X  0755
#define PERM_RW_R__R__  0644
#define PERM_RWXRWXRWX  0777

/* Inode: in-memory representation of a file/directory/device */
#define INODE_NAME_MAX  256

typedef struct inode {
    uint64_t    ino;            /* inode number (unique within filesystem) */
    file_type_t type;           /* file type */
    uint32_t    permissions;    /* Unix-style permission bits */
    uint32_t    uid;            /* owner user ID */
    uint32_t    gid;            /* owner group ID */
    uint64_t    size;           /* file size in bytes */
    uint64_t    blocks;         /* number of 512-byte blocks allocated */
    uint64_t    atime;          /* access time (ticks) */
    uint64_t    mtime;          /* modification time (ticks) */
    uint64_t    ctime;          /* creation time (ticks) */
    uint32_t    nlink;          /* hard link count */

    /* Device numbers (for FT_CHARDEV and FT_BLKDEV) */
    uint16_t    dev_major;
    uint16_t    dev_minor;

    /* Filesystem-specific private data */
    void       *fs_private;

    /* Operations */
    struct inode_ops    *i_ops;  /* inode operations */
    struct file_ops     *f_ops;  /* default file operations for this inode */

    /* Owning superblock */
    superblock_t *sb;

    /* Linkage */
    struct inode *next;         /* hash chain in inode cache */
    uint32_t     ref_count;     /* reference count */
} inode_t;

/* Inode operations: metadata operations on files/directories */
typedef struct inode_ops {
    /* Look up a name within a directory inode.
     * Returns dentry if found, NULL if not found. */
    dentry_t *(*lookup)(inode_t *dir, const char *name);

    /* Create a new file in a directory. Returns inode of new file. */
    inode_t *(*create)(inode_t *dir, const char *name, uint32_t permissions);

    /* Create a new directory. Returns inode of new directory. */
    inode_t *(*mkdir)(inode_t *dir, const char *name, uint32_t permissions);

    /* Remove a file from a directory. */
    int (*unlink)(inode_t *dir, const char *name);

    /* Remove a directory. */
    int (*rmdir)(inode_t *dir, const char *name);

    /* Rename a file/directory. */
    int (*rename)(inode_t *old_dir, const char *old_name,
                  inode_t *new_dir, const char *new_name);

    /* Read symlink target. Returns bytes written to buf. */
    int (*readlink)(inode_t *inode, char *buf, uint32_t bufsize);

    /* Create symlink. */
    int (*symlink)(inode_t *dir, const char *name, const char *target);

    /* Get/set extended attributes (optional, can be NULL) */
    int (*getattr)(inode_t *inode, const char *name, void *buf, uint32_t size);
    int (*setattr)(inode_t *inode, const char *name, const void *buf, uint32_t size);
} inode_ops_t;

/* File operations: data I/O on open files */
typedef struct file_ops {
    /* Read data from file. Returns bytes read, 0 on EOF, negative on error. */
    int64_t (*read)(file_t *file, void *buf, uint64_t count);

    /* Write data to file. Returns bytes written, negative on error. */
    int64_t (*write)(file_t *file, const void *buf, uint64_t count);

    /* Seek to position. Returns new position, negative on error. */
    int64_t (*seek)(file_t *file, int64_t offset, int whence);

    /* Read directory entries. Returns bytes read, 0 when done. */
    int (*readdir)(file_t *file, struct dirent *entries, uint32_t max_entries);

    /* Memory-map file (optional, can be NULL). */
    int (*mmap)(file_t *file, uint64_t offset, uint64_t length, uint64_t vaddr);

    /* Sync file data to disk. */
    int (*fsync)(file_t *file);

    /* Called when file is opened. */
    int (*open)(inode_t *inode, file_t *file);

    /* Called when file is closed (last reference released). */
    int (*release)(file_t *file);
} file_ops_t;

/* Seek whence values */
#define SEEK_SET    0   /* absolute position */
#define SEEK_CUR    1   /* relative to current */
#define SEEK_END    2   /* relative to end */
```

### Dentry (Directory Entry Cache)

```c
/* Dentry: cached mapping from name to inode */
#define DENTRY_NAME_MAX     256

typedef struct dentry {
    char            name[DENTRY_NAME_MAX];
    inode_t        *inode;          /* associated inode (NULL if negative dentry) */
    struct dentry  *parent;         /* parent directory dentry */
    struct dentry  *children;       /* first child (linked list of siblings) */
    struct dentry  *next_sibling;   /* next sibling in parent's children list */
    vfs_mount_t    *mount;          /* mount point this dentry belongs to */
    uint32_t        ref_count;
    int             is_mountpoint;  /* 1 if another filesystem is mounted here */
} dentry_t;

/* Directory entry returned by readdir */
typedef struct dirent {
    uint64_t    ino;
    file_type_t type;
    char        name[DENTRY_NAME_MAX];
} dirent_t;
```

### Superblock

```c
/* Superblock: per-mounted-filesystem state */
typedef struct superblock {
    fs_type_t      *fs_type;        /* filesystem type descriptor */
    uint32_t        dev_id;         /* block device ID (0 for in-memory fs) */
    uint64_t        block_size;     /* filesystem block size */
    uint64_t        total_blocks;   /* total blocks in filesystem */
    uint64_t        free_blocks;    /* free blocks */
    uint64_t        total_inodes;   /* total inodes */
    uint64_t        free_inodes;    /* free inodes */
    inode_t        *root_inode;     /* root inode of this filesystem */
    void           *fs_private;     /* filesystem-specific data */

    /* Superblock operations */
    struct sb_ops  *s_ops;

    uint32_t        flags;          /* mount flags */
    int             read_only;
} superblock_t;

/* Superblock operations */
typedef struct sb_ops {
    /* Read an inode from disk given its number. */
    inode_t *(*read_inode)(superblock_t *sb, uint64_t ino);

    /* Write inode metadata back to disk. */
    int (*write_inode)(superblock_t *sb, inode_t *inode);

    /* Delete an inode (free its blocks on disk). */
    int (*delete_inode)(superblock_t *sb, inode_t *inode);

    /* Sync all dirty data to disk. */
    int (*sync_fs)(superblock_t *sb);

    /* Report filesystem statistics. */
    int (*statfs)(superblock_t *sb, struct statfs *stat);
} sb_ops_t;

/* Filesystem statistics */
typedef struct statfs {
    uint64_t block_size;
    uint64_t total_blocks;
    uint64_t free_blocks;
    uint64_t total_inodes;
    uint64_t free_inodes;
    char     fs_type_name[16];
} statfs_t;
```

### Filesystem Type Registration

```c
/* Filesystem type: describes a filesystem implementation */
#define FS_TYPE_NAME_MAX    16

typedef struct fs_type {
    char            name[FS_TYPE_NAME_MAX];     /* e.g., "ext2", "initramfs" */

    /* Mount a filesystem on a block device (or memory).
     * Returns superblock on success, NULL on failure. */
    superblock_t *(*mount)(fs_type_t *type, uint32_t dev_id, const void *data);

    /* Unmount a filesystem. */
    void (*unmount)(superblock_t *sb);

    /* Create/format a new filesystem on a block device.
     * 'options' may include block size, inode count, etc.
     * Returns 0 on success. */
    int (*mkfs)(uint32_t dev_id, const char *options);

    struct fs_type *next;   /* linked list of registered fs types */
} fs_type_t;
```

### Mount Table

```c
#define VFS_MAX_MOUNTS      32
#define VFS_PATH_MAX        4096

/* Mount entry */
typedef struct vfs_mount {
    superblock_t   *sb;             /* superblock of mounted filesystem */
    dentry_t       *mount_point;    /* dentry where this is mounted */
    dentry_t       *root_dentry;    /* root dentry of mounted filesystem */
    char            source[128];    /* source device (e.g., "/dev/sda1") */
    char            target[VFS_PATH_MAX]; /* mount point path (e.g., "/mnt") */
    char            fs_name[FS_TYPE_NAME_MAX]; /* filesystem type name */
    uint32_t        flags;          /* mount flags */
    int             active;
} vfs_mount_t;

/* Mount flags */
#define MNT_READONLY    (1 << 0)
#define MNT_NOEXEC      (1 << 1)
#define MNT_NOSUID      (1 << 2)
```

### Open File Table

```c
#define VFS_MAX_OPEN_FILES  1024
#define VFS_FD_MAX          256     /* max file descriptors per process */

/* Open file descriptor */
typedef struct file {
    inode_t        *inode;          /* inode for this file */
    file_ops_t     *f_ops;         /* file operations */
    uint64_t        offset;         /* current read/write position */
    uint32_t        flags;          /* open flags (O_RDONLY, O_WRONLY, etc.) */
    uint32_t        ref_count;      /* reference count (for dup/fork) */
    void           *private_data;   /* driver/fs private data */
} file_t;

/* Open flags */
#define O_RDONLY    0x0000
#define O_WRONLY    0x0001
#define O_RDWR     0x0002
#define O_CREAT    0x0040
#define O_TRUNC    0x0200
#define O_APPEND   0x0400
#define O_EXCL     0x0080
#define O_DIRECTORY 0x10000
```

### Ext2 On-Disk Structures

```c
/* Ext2 superblock (on-disk, at offset 1024 in partition) */
typedef struct ext2_superblock {
    uint32_t s_inodes_count;
    uint32_t s_blocks_count;
    uint32_t s_r_blocks_count;      /* reserved blocks */
    uint32_t s_free_blocks_count;
    uint32_t s_free_inodes_count;
    uint32_t s_first_data_block;    /* usually 1 for 1KB blocks, 0 for >1KB */
    uint32_t s_log_block_size;      /* block size = 1024 << s_log_block_size */
    uint32_t s_log_frag_size;
    uint32_t s_blocks_per_group;
    uint32_t s_frags_per_group;
    uint32_t s_inodes_per_group;
    uint32_t s_mtime;
    uint32_t s_wtime;
    uint16_t s_mnt_count;
    uint16_t s_max_mnt_count;
    uint16_t s_magic;               /* 0xEF53 */
    uint16_t s_state;
    uint16_t s_errors;
    uint16_t s_minor_rev_level;
    uint32_t s_lastcheck;
    uint32_t s_checkinterval;
    uint32_t s_creator_os;
    uint32_t s_rev_level;
    uint16_t s_def_resuid;
    uint16_t s_def_resgid;
    /* Rev 1 fields */
    uint32_t s_first_ino;
    uint16_t s_inode_size;
    /* ... additional fields truncated for brevity ... */
} __attribute__((packed)) ext2_superblock_t;

#define EXT2_MAGIC  0xEF53

/* Ext2 block group descriptor */
typedef struct ext2_bg_desc {
    uint32_t bg_block_bitmap;
    uint32_t bg_inode_bitmap;
    uint32_t bg_inode_table;
    uint16_t bg_free_blocks_count;
    uint16_t bg_free_inodes_count;
    uint16_t bg_used_dirs_count;
    uint16_t bg_pad;
    uint8_t  bg_reserved[12];
} __attribute__((packed)) ext2_bg_desc_t;

/* Ext2 inode (on-disk) */
typedef struct ext2_inode {
    uint16_t i_mode;
    uint16_t i_uid;
    uint32_t i_size;
    uint32_t i_atime;
    uint32_t i_ctime;
    uint32_t i_mtime;
    uint32_t i_dtime;
    uint16_t i_gid;
    uint16_t i_links_count;
    uint32_t i_blocks;              /* 512-byte blocks */
    uint32_t i_flags;
    uint32_t i_osd1;
    uint32_t i_block[15];           /* 12 direct + 1 indirect + 1 double + 1 triple */
    uint32_t i_generation;
    uint32_t i_file_acl;
    uint32_t i_dir_acl;
    uint32_t i_faddr;
    uint8_t  i_osd2[12];
} __attribute__((packed)) ext2_inode_t;

/* Ext2 directory entry (on-disk) */
typedef struct ext2_dir_entry {
    uint32_t inode;
    uint16_t rec_len;               /* total entry size (for alignment) */
    uint8_t  name_len;
    uint8_t  file_type;
    char     name[];                /* variable length, NOT null-terminated */
} __attribute__((packed)) ext2_dir_entry_t;
```

### Initramfs (CPIO Format)

```c
/* CPIO newc header (ASCII format used by Linux initramfs) */
typedef struct cpio_header {
    char magic[6];      /* "070701" */
    char ino[8];
    char mode[8];
    char uid[8];
    char gid[8];
    char nlink[8];
    char mtime[8];
    char filesize[8];   /* hex string */
    char devmajor[8];
    char devminor[8];
    char rdevmajor[8];
    char rdevminor[8];
    char namesize[8];   /* hex string, includes NUL */
    char check[8];
} __attribute__((packed)) cpio_header_t;

#define CPIO_MAGIC  "070701"
#define CPIO_TRAILER "TRAILER!!!"
```

## Interface (`kernel/include/fs.h`)

### VFS Initialization and Filesystem Registration

```c
/* Initialize the VFS subsystem. Sets up mount table, dentry cache,
 * and registers built-in filesystem types. */
void vfs_init(void);

/* Register a filesystem type (called by each fs implementation). */
int vfs_register_fs(fs_type_t *type);

/* Unregister a filesystem type. */
void vfs_unregister_fs(const char *name);

/* Find a registered filesystem type by name. */
fs_type_t *vfs_find_fs(const char *name);
```

### Mount/Unmount

```c
/* Mount a filesystem.
 * source: device path (e.g., "/dev/sda1") or NULL for in-memory fs
 * target: mount point path (e.g., "/mnt")
 * fs_name: filesystem type name (e.g., "ext2")
 * flags: mount flags (MNT_READONLY, etc.)
 * Returns 0 on success, negative on error. */
int vfs_mount(const char *source, const char *target,
              const char *fs_name, uint32_t flags);

/* Unmount a filesystem at the given path. Flushes dirty data.
 * Returns 0 on success, -EBUSY if files are still open. */
int vfs_unmount(const char *target);

/* Mount the root filesystem. Called during boot.
 * For initramfs: source=NULL, fs_name="initramfs"
 * For ext2: source="/dev/sda1", fs_name="ext2" */
int vfs_mount_root(const char *source, const char *fs_name);

/* Get mount info for a path. */
vfs_mount_t *vfs_get_mount(const char *path);

/* List all mounts (debug). */
void vfs_list_mounts(void);
```

### Path Resolution

```c
/* Resolve a path to a dentry. Follows mount points and symlinks.
 * Returns dentry on success, NULL on not found.
 * Starts from root if path begins with '/', else from cwd. */
dentry_t *vfs_resolve_path(const char *path);

/* Resolve parent directory + last component of a path.
 * Used by create/mkdir/unlink which need the parent dir. */
int vfs_resolve_parent(const char *path, dentry_t **parent, char *name_out);
```

### File Operations

```c
/* Open a file by path. Returns file descriptor (fd >= 0) on success.
 * Returns negative error code on failure. */
int vfs_open(const char *path, uint32_t flags);

/* Close a file descriptor. */
int vfs_close(int fd);

/* Read from an open file. Returns bytes read. */
int64_t vfs_read(int fd, void *buf, uint64_t count);

/* Write to an open file. Returns bytes written. */
int64_t vfs_write(int fd, const void *buf, uint64_t count);

/* Seek in an open file. Returns new position. */
int64_t vfs_seek(int fd, int64_t offset, int whence);

/* Get file size and metadata. */
int vfs_stat(const char *path, struct file_stat *stat);

typedef struct file_stat {
    uint64_t    ino;
    file_type_t type;
    uint32_t    permissions;
    uint64_t    size;
    uint64_t    blocks;
    uint64_t    atime;
    uint64_t    mtime;
    uint64_t    ctime;
    uint32_t    nlink;
    uint16_t    dev_major;
    uint16_t    dev_minor;
} file_stat_t;
```

### Directory Operations

```c
/* Create a directory. Returns 0 on success. */
int vfs_mkdir(const char *path, uint32_t permissions);

/* Remove an empty directory. Returns 0 on success, -ENOTEMPTY if not empty. */
int vfs_rmdir(const char *path);

/* Read directory entries. Returns count of entries read. */
int vfs_readdir(int fd, dirent_t *entries, uint32_t max_entries);

/* Create a file (like open with O_CREAT). Returns fd on success. */
int vfs_create(const char *path, uint32_t permissions);

/* Remove a file. */
int vfs_unlink(const char *path);

/* Rename a file or directory. */
int vfs_rename(const char *old_path, const char *new_path);
```

### Filesystem-Specific Operations

```c
/* Format a block device with a filesystem.
 * fs_name: filesystem type (e.g., "ext2")
 * dev_id: block device kernel ID
 * options: fs-specific options string (e.g., "block_size=4096,inode_count=1024")
 * Returns 0 on success. */
int vfs_mkfs(const char *fs_name, uint32_t dev_id, const char *options);

/* Sync all dirty buffers to disk. */
void vfs_sync(void);

/* Get filesystem statistics for a mount point. */
int vfs_statfs(const char *path, statfs_t *stat);
```

### Initramfs Operations

```c
/* Load initramfs from a memory region (boot module).
 * Parses CPIO archive and populates an in-memory filesystem.
 * Returns 0 on success. */
int initramfs_load(const void *data, uint64_t size);

/* Mount initramfs as root filesystem. */
int initramfs_mount_root(void);
```

### Devfs Operations

```c
/* Initialize devfs. Registers device nodes for all known devices. */
void devfs_init(void);

/* Add a device node to devfs. */
int devfs_add_device(const char *name, file_type_t type,
                     uint16_t major, uint16_t minor,
                     file_ops_t *f_ops);

/* Remove a device node. */
int devfs_remove_device(const char *name);
```

### Procfs Operations

```c
/* Initialize procfs. Creates /proc with process info entries. */
void procfs_init(void);

/* Procfs generates content dynamically on read. */
/* /proc/meminfo   -> memory statistics */
/* /proc/cpuinfo   -> CPU information */
/* /proc/mounts    -> mounted filesystems */
/* /proc/uptime    -> system uptime */
/* /proc/<pid>/    -> per-process information */
```

## Behavior

### Path Resolution Algorithm

```
vfs_resolve_path("/mnt/disk/file.txt"):
  1. Start at root dentry (mount table entry for "/")
  2. Split path by '/' into components: ["mnt", "disk", "file.txt"]
  3. For each component:
     a. Current dentry must be a directory
     b. Call inode->i_ops->lookup(inode, component_name)
     c. If lookup returns NULL: return NULL (not found)
     d. If returned dentry is_mountpoint:
        - Find mount entry for this dentry
        - Switch to mounted filesystem's root dentry
     e. If returned inode is symlink and following symlinks:
        - Read symlink target via readlink()
        - Recursively resolve (depth limit: 8 to prevent loops)
     f. Current dentry = returned dentry
  4. Return final dentry
```

### Ext2 Read File Algorithm

```
ext2_read(file, buf, count):
  1. inode = file->inode
  2. offset = file->offset
  3. If offset >= inode->size: return 0 (EOF)
  4. Clamp count to (inode->size - offset)
  5. While bytes_remaining > 0:
     a. block_index = offset / block_size
     b. block_offset = offset % block_size
     c. Resolve block_index to physical block number:
        - If block_index < 12: direct block = i_block[block_index]
        - If block_index < 12+256: single indirect
        - If block_index < 12+256+65536: double indirect
        - Else: triple indirect
     d. Read physical block from device: blk_read(dev_id, block_lba, ...)
     e. Copy data from block_offset to min(block_size - block_offset, bytes_remaining)
     f. Advance offset and buf pointer
  6. Update file->offset
  7. Return total bytes read
```

### Ext2 mkfs Algorithm

```
ext2_mkfs(dev_id, options):
  1. Get device size: blk_get_info(dev_id, &info)
  2. Choose block size (default 1024, option to use 4096)
  3. Calculate number of block groups:
     groups = total_blocks / blocks_per_group (default 8192 per group)
  4. Calculate inode count: total_blocks / 4 (1 inode per 4 blocks)
  5. For each block group:
     a. Write block group descriptor
     b. Allocate and zero block bitmap
     c. Allocate and zero inode bitmap
     d. Allocate inode table
  6. Write superblock at offset 1024
  7. Create root inode (inode 2):
     a. Type = directory
     b. Add "." and ".." entries
  8. Mark used blocks/inodes in bitmaps
  9. Sync to disk
```

### Initramfs Loading

```
initramfs_load(data, size):
  1. Create in-memory superblock with initramfs operations
  2. Create root inode (directory)
  3. ptr = data
  4. While ptr < data + size:
     a. Parse CPIO header at ptr
     b. If filename == "TRAILER!!!": break
     c. Extract filename, filesize, mode
     d. Create directory path components (mkdir as needed)
     e. If file: allocate inode, point data to memory region (zero-copy)
     f. If directory: allocate directory inode
     g. Advance ptr past header + name + file data (aligned to 4 bytes)
  5. Return 0
```

### SLM Filesystem Operations

The SLM uses VFS to perform disk setup during installation:

```
SLM "partition and format disk" flow:
  1. SLM queries block devices via dev subsystem
  2. SLM decides partition layout (e.g., 512MB boot + rest root)
  3. SLM writes partition table:
     - Builds MBR partition entries
     - Writes via blk_write to LBA 0
  4. SLM creates filesystems:
     - vfs_mkfs("ext2", boot_dev_id, "block_size=1024")
     - vfs_mkfs("ext2", root_dev_id, "block_size=4096")
  5. SLM mounts:
     - vfs_mount("/dev/sda2", "/", "ext2", 0)
     - vfs_mount("/dev/sda1", "/boot", "ext2", 0)
  6. SLM copies files from initramfs to root filesystem
```

### Edge Cases

- **Path too long**: paths exceeding `VFS_PATH_MAX` (4096) return -ENAMETOOLONG
- **Symlink loops**: depth limit of 8; exceeding returns -ELOOP
- **Mount on non-empty directory**: allowed (Linux behavior), hides existing contents
- **Open file during unmount**: `vfs_unmount()` returns -EBUSY
- **Ext2 superblock magic invalid**: mount fails with -EINVAL
- **Initramfs CPIO magic invalid**: `initramfs_load()` returns -EINVAL
- **Block device read error during file read**: `vfs_read()` returns -EIO
- **Directory entry name too long**: truncated to `DENTRY_NAME_MAX - 1`
- **Out of inodes**: create/mkdir returns -ENOSPC
- **Write to read-only mount**: returns -EROFS

### VFS Error Codes

```c
#define VFS_OK          0
#define -ENOENT        -2       /* no such file or directory */
#define -EIO           -5       /* I/O error */
#define -ENOMEM        -12      /* out of memory */
#define -EACCES        -13      /* permission denied */
#define -EEXIST        -17      /* file exists */
#define -ENOTDIR       -20      /* not a directory */
#define -EISDIR        -21      /* is a directory */
#define -EINVAL        -22      /* invalid argument */
#define -ENOSPC        -28      /* no space left on device */
#define -EROFS         -30      /* read-only file system */
#define -ENAMETOOLONG  -36      /* filename too long */
#define -ENOTEMPTY     -39      /* directory not empty */
#define -ELOOP         -40      /* too many symbolic links */
#define -EBUSY         -16      /* device or resource busy */
```

## Files

| File | Purpose |
|------|---------|
| `kernel/fs/vfs.c`         | VFS core: mount table, path resolution, fd table |
| `kernel/fs/inode.c`       | Inode cache and management |
| `kernel/fs/dentry.c`      | Dentry cache and management |
| `kernel/fs/initramfs.c`   | Initramfs (CPIO) filesystem implementation |
| `kernel/fs/ext2.c`        | Ext2 filesystem implementation |
| `kernel/fs/devfs.c`       | Device filesystem (/dev) |
| `kernel/fs/procfs.c`      | Process info filesystem (/proc) |
| `kernel/include/fs.h`     | VFS interface and data structures |

## Dependencies

- **mm**: `kmalloc`/`kfree` for inodes, dentries, file descriptors, superblocks
- **drivers** (blk): block device read/write for ext2 on-disk access
- **dev**: device IDs for devfs nodes
- **boot**: boot module data for initramfs
- **sched**: process context for per-process fd tables
- **slm**: SLM issues mkfs/mount/file operations during installation

## Acceptance Criteria

1. VFS initializes and mounts initramfs as root filesystem
2. `vfs_resolve_path("/")` returns root dentry
3. `vfs_resolve_path("/bin/hello")` finds file in initramfs
4. `vfs_open()` / `vfs_read()` reads initramfs file contents correctly
5. `vfs_mkdir("/tmp")` creates directory, `vfs_resolve_path("/tmp")` finds it
6. `vfs_create("/tmp/test")` + `vfs_write()` + `vfs_read()` round-trip works
7. `vfs_unlink()` removes file; subsequent open returns -ENOENT
8. `vfs_rmdir()` on non-empty directory returns -ENOTEMPTY
9. Ext2: `vfs_mkfs("ext2", dev_id, ...)` formats a QEMU disk image
10. Ext2: mount formatted disk, read/write files, unmount, remount, verify data persists
11. Ext2: indirect block addressing works for files > 12 blocks
12. Devfs: `/dev/sda` node exists after AHCI driver loads
13. Devfs: `vfs_open("/dev/sda")` returns fd usable with blk_read/blk_write
14. Procfs: `vfs_open("/proc/meminfo")` returns current memory statistics
15. Mount table tracks all mounts; `vfs_list_mounts()` lists them correctly
16. Path resolution crosses mount boundaries correctly
17. Symlink resolution follows links (up to depth 8) correctly
18. CPIO parser handles all test initramfs files without corruption
