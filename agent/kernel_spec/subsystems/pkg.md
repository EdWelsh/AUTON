# Package Manager Specification

## Overview

The package manager provides a simple package format (tar archive with a TOML-like manifest), a local package registry, dependency resolution, and SLM-driven installation. When a user requests "install a web server," the SLM translates this into package search, dependency resolution, fetching, extraction, and configuration steps. The package manager operates partially in-kernel (registry, extraction) and uses the network and filesystem subsystems for fetching and file installation.

## Data Structures

### Package Manifest

```c
/* Package manifest: describes a package's identity, dependencies, and files.
 * Stored as "MANIFEST" file in the root of the package tar archive. */

#define PKG_NAME_MAX        64
#define PKG_VERSION_MAX     16
#define PKG_DESC_MAX        256
#define PKG_CATEGORY_MAX    32
#define PKG_URL_MAX         256
#define PKG_MAX_DEPS        16
#define PKG_MAX_FILES       256
#define PKG_MAX_SCRIPTS     4

/* Dependency specification */
typedef struct pkg_dep {
    char    name[PKG_NAME_MAX];         /* required package name */
    char    min_version[PKG_VERSION_MAX]; /* minimum version (empty = any) */
} pkg_dep_t;

/* File entry: describes one file installed by the package */
typedef struct pkg_file_entry {
    char    path[256];          /* destination path (e.g., "/usr/bin/nginx") */
    char    archive_path[256];  /* path within tar archive */
    uint32_t permissions;       /* Unix permission bits */
    uint64_t size;              /* file size in bytes */
    uint8_t  sha256[32];       /* SHA-256 checksum of file contents */
} pkg_file_entry_t;

/* Script types */
typedef enum pkg_script_type {
    PKG_SCRIPT_PRE_INSTALL  = 0,
    PKG_SCRIPT_POST_INSTALL = 1,
    PKG_SCRIPT_PRE_REMOVE   = 2,
    PKG_SCRIPT_POST_REMOVE  = 3,
} pkg_script_type_t;

/* Install/remove scripts */
typedef struct pkg_script {
    pkg_script_type_t type;
    char              path[256];    /* path to script within archive */
} pkg_script_t;

/* Complete package manifest */
typedef struct pkg_manifest {
    char            name[PKG_NAME_MAX];
    char            version[PKG_VERSION_MAX];
    char            description[PKG_DESC_MAX];
    char            category[PKG_CATEGORY_MAX];
    char            maintainer[128];
    char            homepage[PKG_URL_MAX];
    uint64_t        installed_size;     /* total installed size in bytes */

    pkg_dep_t       dependencies[PKG_MAX_DEPS];
    uint32_t        dep_count;

    pkg_file_entry_t files[PKG_MAX_FILES];
    uint32_t         file_count;

    pkg_script_t    scripts[PKG_MAX_SCRIPTS];
    uint32_t        script_count;
} pkg_manifest_t;
```

### Package Archive Format

```c
/* Package archive: a tar file containing:
 *   MANIFEST          - package manifest (text format, parsed into pkg_manifest_t)
 *   data/             - directory containing all package files
 *   scripts/          - directory containing install/remove scripts
 *
 * The tar format used is POSIX ustar (simplified). */

/* TAR header (512 bytes, POSIX ustar format) */
typedef struct tar_header {
    char name[100];         /* file name */
    char mode[8];           /* octal permission string */
    char uid[8];            /* owner user ID (octal) */
    char gid[8];            /* owner group ID (octal) */
    char size[12];          /* file size in bytes (octal) */
    char mtime[12];         /* modification time (octal) */
    char checksum[8];       /* header checksum */
    char typeflag;          /* '0'=file, '5'=directory, '2'=symlink */
    char linkname[100];     /* name of linked file */
    char magic[6];          /* "ustar" */
    char version[2];        /* "00" */
    char uname[32];         /* owner user name */
    char gname[32];         /* owner group name */
    char devmajor[8];
    char devminor[8];
    char prefix[155];       /* prefix for long names */
    char padding[12];       /* pad to 512 bytes */
} __attribute__((packed)) tar_header_t;

#define TAR_BLOCK_SIZE      512
#define TAR_MAGIC           "ustar"
#define TAR_TYPE_FILE       '0'
#define TAR_TYPE_DIRECTORY  '5'
#define TAR_TYPE_SYMLINK    '2'
```

### Package Registry

```c
/* Registry entry: records an installed or available package */
typedef enum pkg_status {
    PKG_STATUS_AVAILABLE,       /* in remote repository, not installed */
    PKG_STATUS_INSTALLED,       /* installed locally */
    PKG_STATUS_UPGRADING,       /* upgrade in progress */
    PKG_STATUS_REMOVING,        /* removal in progress */
    PKG_STATUS_BROKEN,          /* installation failed or corrupt */
} pkg_status_t;

typedef struct pkg_registry_entry {
    pkg_manifest_t  manifest;       /* package manifest */
    pkg_status_t    status;
    uint64_t        install_time;   /* tick when installed */
    char            download_url[PKG_URL_MAX]; /* URL to fetch .tar package */
    int             active;
} pkg_registry_entry_t;

/* Package registry */
#define PKG_REGISTRY_MAX    512

typedef struct pkg_registry {
    pkg_registry_entry_t entries[PKG_REGISTRY_MAX];
    uint32_t             count;         /* total entries */
    uint32_t             installed;     /* installed count */
    char                 repo_url[PKG_URL_MAX]; /* base URL for package repo */
    int                  initialized;
} pkg_registry_t;
```

### Dependency Resolution

```c
/* Installation plan: ordered list of packages to install */
#define PKG_PLAN_MAX    64

typedef struct pkg_install_plan {
    struct pkg_plan_entry {
        char        name[PKG_NAME_MAX];
        char        version[PKG_VERSION_MAX];
        char        url[PKG_URL_MAX];
        uint64_t    size;
        int         already_installed;  /* 1 if dep is already satisfied */
    } steps[PKG_PLAN_MAX];
    uint32_t    step_count;
    uint64_t    total_download_size;
    uint64_t    total_install_size;
} pkg_install_plan_t;
```

## Interface (`kernel/include/pkg.h`)

### Package Manager Initialization

```c
/* Initialize the package manager. Loads registry from persistent storage
 * (or creates empty registry). Sets up repository URL.
 * Must be called after fs and net subsystems. */
void pkg_init(void);

/* Set the package repository base URL.
 * Packages are fetched from: repo_url/<package_name>-<version>.tar */
void pkg_set_repo(const char *repo_url);

/* Refresh the local package list from the remote repository.
 * Downloads the repository index and updates available packages.
 * Returns 0 on success, -1 if network unavailable. */
int pkg_refresh_index(void);
```

### Package Search and Query

```c
/* Search for packages by keyword (searches name, description, category).
 * Fills results array. Returns number of matches. */
uint32_t pkg_search(const char *keyword, pkg_registry_entry_t **results,
                    uint32_t max_results);

/* Search by category (e.g., "web", "database", "utility"). */
uint32_t pkg_search_category(const char *category,
                             pkg_registry_entry_t **results,
                             uint32_t max_results);

/* Get info about a specific package by name. Returns NULL if not found. */
const pkg_registry_entry_t *pkg_get_info(const char *name);

/* List all installed packages. */
uint32_t pkg_list_installed(pkg_registry_entry_t **results,
                            uint32_t max_results);

/* Check if a package is installed. Returns 1 if yes, 0 if no. */
int pkg_is_installed(const char *name);
```

### Dependency Resolution

```c
/* Resolve dependencies for a package. Builds an installation plan
 * that lists all packages to install in correct order.
 * Returns 0 on success, -1 if unresolvable dependency. */
int pkg_resolve_deps(const char *name, pkg_install_plan_t *plan);

/* Check if all dependencies of a package are satisfied.
 * Returns 0 if all satisfied, -1 if missing deps (fills missing array). */
int pkg_check_deps(const char *name, char missing[][PKG_NAME_MAX],
                   uint32_t *missing_count);
```

### Package Installation

```c
/* Install a package by name. Full pipeline:
 * 1. Resolve dependencies (install missing deps first)
 * 2. Download package archive from repository
 * 3. Verify archive integrity
 * 4. Extract files to filesystem
 * 5. Run post-install scripts
 * 6. Update registry
 * Returns 0 on success, negative on error. */
int pkg_install(const char *name);

/* Install from a local tar archive (already downloaded or on initramfs).
 * Skips the download step. */
int pkg_install_local(const char *archive_path);

/* Execute an installation plan (install all packages in order). */
int pkg_execute_plan(const pkg_install_plan_t *plan);
```

### Package Removal

```c
/* Remove an installed package.
 * 1. Check if other packages depend on it
 * 2. Run pre-remove scripts
 * 3. Remove installed files
 * 4. Run post-remove scripts
 * 5. Update registry
 * Returns 0 on success, -EBUSY if other packages depend on it. */
int pkg_remove(const char *name);

/* Remove a package and all packages that depend on it. */
int pkg_remove_recursive(const char *name);
```

### Package Update

```c
/* Check if updates are available for installed packages.
 * Compares local versions with repository versions.
 * Fills 'outdated' array. Returns count. */
uint32_t pkg_check_updates(pkg_registry_entry_t **outdated,
                           uint32_t max_results);

/* Update a specific package to the latest version. */
int pkg_update(const char *name);

/* Update all installed packages. Returns count of updated packages. */
uint32_t pkg_update_all(void);
```

### Tar Archive Operations

```c
/* Parse a tar archive from memory. Iterates through file entries.
 * Calls callback for each file found. Returns 0 on success. */
typedef int (*tar_entry_cb_t)(const tar_header_t *header,
                              const void *data, uint64_t size,
                              void *user_data);

int tar_parse(const void *archive, uint64_t archive_size,
              tar_entry_cb_t callback, void *user_data);

/* Extract a tar archive to a directory.
 * Creates directories and writes files per tar contents. */
int tar_extract(const void *archive, uint64_t archive_size,
                const char *dest_dir);

/* Parse octal string from tar header field. */
uint64_t tar_parse_octal(const char *str, uint32_t len);

/* Verify tar header checksum. */
int tar_verify_checksum(const tar_header_t *header);
```

### Manifest Parsing

```c
/* Parse a MANIFEST file (text format) into pkg_manifest_t.
 * Format is line-based key=value:
 *   name=nginx
 *   version=1.0.0
 *   description=High-performance web server
 *   category=web
 *   depends=libc,libssl
 *   file=/usr/bin/nginx,data/nginx,0755,sha256:abc123...
 * Returns 0 on success. */
int pkg_parse_manifest(const char *text, uint32_t text_len,
                       pkg_manifest_t *manifest);
```

## Behavior

### SLM-Driven Installation Flow

```
User says: "install a web server"

SLM:
  1. Classify intent -> APP_INSTALL
  2. Extract entity: keyword = "web server"
  3. Start conversation context: goal = "Install web server"

  4. Search package registry:
     pkg_search("web server", ...) or pkg_search_category("web", ...)
     -> Finds: nginx, lighttpd, busybox-httpd

  5. Select best match (rule engine: first match; neural: ranked by relevance):
     -> Selected: "nginx"

  6. Resolve dependencies:
     pkg_resolve_deps("nginx", &plan)
     -> Plan: [libc, libssl, nginx] (libc and libssl are deps)

  7. Check already installed:
     -> libc already installed (skip)
     -> libssl not installed (include)

  8. Execute plan:
     For each package in plan:
       a. Download: http_get(repo_url + "/libssl-1.0.0.tar", &response)
       b. Extract to temp: tar_extract(response.body, ..., "/tmp/pkg")
       c. Parse MANIFEST in archive
       d. Copy files to final destinations:
          vfs_create("/usr/lib/libssl.so", 0644)
          vfs_write(fd, file_data, file_size)
       e. Run post-install script if present
       f. Update registry: status = PKG_STATUS_INSTALLED
       g. Repeat for nginx

  9. Configure service:
     SLM sends SYSTEM_MANAGE/SVC_START for nginx

  10. Report to user: "Installed nginx web server. Running on port 80."
```

### Dependency Resolution Algorithm

```
pkg_resolve_deps(name, plan):
  visited = {}

  function resolve(pkg_name):
    if pkg_name in visited: return 0  (already handled)
    visited[pkg_name] = true

    entry = pkg_get_info(pkg_name)
    if entry == NULL: return -1  (package not found)

    for each dep in entry.manifest.dependencies:
      if !pkg_is_installed(dep.name):
        result = resolve(dep.name)  // resolve deps of deps first
        if result < 0: return -1

    // Add this package after its deps (topological order)
    if !pkg_is_installed(pkg_name):
      plan.steps[plan.step_count++] = {
        name = pkg_name,
        version = entry.manifest.version,
        url = entry.download_url,
        size = entry.manifest.installed_size,
        already_installed = 0
      }

    return 0

  return resolve(name)
```

### Tar Archive Extraction

```
tar_extract(archive, size, dest_dir):
  ptr = archive
  while ptr < archive + size:
    header = (tar_header_t *)ptr

    1. If header is all zeros (two zero blocks): end of archive
    2. Verify checksum: tar_verify_checksum(header)
    3. Parse file size: tar_parse_octal(header->size, 12)
    4. Build destination path: dest_dir + "/" + header->name

    5. Switch header->typeflag:
       TAR_TYPE_DIRECTORY:
         vfs_mkdir(dest_path, parse_mode(header->mode))
       TAR_TYPE_FILE:
         fd = vfs_create(dest_path, parse_mode(header->mode))
         vfs_write(fd, ptr + TAR_BLOCK_SIZE, file_size)
         vfs_close(fd)
       TAR_TYPE_SYMLINK:
         vfs_symlink(dest_path, header->linkname)

    6. Advance ptr: skip header (512) + file data (rounded to 512)
       ptr += TAR_BLOCK_SIZE + ((file_size + TAR_BLOCK_SIZE - 1) / TAR_BLOCK_SIZE) * TAR_BLOCK_SIZE
```

### Package Registry Persistence

```
The registry is stored as a file: /var/pkg/registry

pkg_save_registry():
  1. Open /var/pkg/registry for writing
  2. For each entry with active == 1:
     Write: "name|version|status|install_time|url\n"
  3. Close

pkg_load_registry():
  1. Open /var/pkg/registry for reading
  2. Read line by line
  3. Parse each line into pkg_registry_entry_t
  4. If detailed manifest needed: read from /var/pkg/manifests/<name>.manifest
  5. Close
```

### Version Comparison

```c
/* Compare two version strings (e.g., "1.2.3" vs "1.3.0").
 * Returns: <0 if a < b, 0 if equal, >0 if a > b.
 * Splits by '.', compares each component numerically. */
int pkg_version_compare(const char *version_a, const char *version_b);
```

### Edge Cases

- **Package not found in repository**: `pkg_install()` returns -ENOENT; SLM reports "package not found"
- **Circular dependency**: `resolve()` uses visited set to prevent infinite loops; returns -1 if cycle detected
- **Network unavailable during download**: `http_get()` fails; installation aborted, partial state cleaned up
- **Disk full during extraction**: `vfs_write()` returns -ENOSPC; installation rolled back (remove partial files)
- **Tar archive corrupt**: checksum mismatch; `tar_extract()` returns -EINVAL; SLM reports error
- **Post-install script fails**: package marked as PKG_STATUS_BROKEN; SLM notified
- **Remove package with dependents**: `pkg_remove()` returns -EBUSY with list of dependent packages
- **Already installed**: `pkg_install()` checks registry, skips if already current version
- **Downgrade attempt**: version comparison prevents installing older version unless forced

## Files

| File | Purpose |
|------|---------|
| `kernel/pkg/pkg.c`         | Package manager core: init, install, remove, update |
| `kernel/pkg/registry.c`    | Package registry: load, save, search, query |
| `kernel/pkg/deps.c`        | Dependency resolution algorithm |
| `kernel/pkg/tar.c`         | Tar archive parsing and extraction |
| `kernel/pkg/manifest.c`    | Manifest file parsing |
| `kernel/include/pkg.h`     | Package manager interface and data structures |

## Dependencies

- **fs**: VFS for creating directories, writing files, reading manifests
- **net**: HTTP client for downloading packages from repository
- **mm**: `kmalloc`/`kfree` for archive buffers, manifest parsing
- **ipc**: SLM command channel for receiving install/remove requests
- **slm**: SLM translates user intent into package operations; knowledge base has package catalog

## Acceptance Criteria

1. Tar parser correctly iterates a test archive: all file names, sizes, and data match
2. Tar checksum validation rejects a modified archive
3. `tar_extract()` creates correct directory structure and file contents
4. Manifest parser extracts all fields from a test MANIFEST file
5. Package registry saves and loads correctly across "reboot" (write + read back matches)
6. `pkg_search("web")` finds packages with "web" in name/description/category
7. `pkg_install("nginx")` resolves deps, downloads, extracts, and registers successfully
8. Dependency resolution produces correct topological order: deps before dependents
9. Circular dependency detection returns -1 instead of infinite loop
10. `pkg_is_installed("nginx")` returns 1 after successful install
11. `pkg_remove("nginx")` removes installed files and updates registry
12. `pkg_remove()` on package with dependents returns -EBUSY
13. Version comparison: "1.2.3" < "1.3.0" < "2.0.0"
14. `pkg_install_local()` works with archive on initramfs (no network needed)
15. Full SLM-driven flow: "install a web server" -> search -> resolve -> fetch -> extract -> configure
16. Update detection: modified repo index shows newer version, `pkg_check_updates()` lists it
