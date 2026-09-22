---
service: fileserver
requires: [netif, ethernet, ipv4, tcp, http-server, vfs, fat32, virtio-blk, allocator, klog, terminal, scoped]
excludes: [writable, ext2, dhcp-client, preemptive, ipc]
entry: fileserver_serve
markers:
  - "[HTTP] docroot mounted from fat32"
  - "[HTTP] listening on :80"
  - "[HTTP] GET /index.html 200 1024"
assets: []
---

# File Server Service Specification

## Overview

Serves a read-only document root over HTTP/1.1 from **the FAT32 volume** on virtio-blk. One
TCP listener, one connection at a time, no writes.

**Retargeted in w14, and why**: this spec originally served a CPIO archive handed in as a
Multiboot2 module, because it was written before there was any storage. The factory PRD's F8
signal is stricter — *"`curl` retrieves a file that was written to the image's disk, not
compiled in"* — and a boot module is compiled in. With FAT32 and virtio-blk specified (w12,
w13), adding a file to the site is now an `mcopy` onto the image, not a rebuild.

The security boundary below is unchanged except for its last step, which is noted there.

This spec exists to test the service format against a shape structurally unlike
[dhcp.md](dhcp.md): connection-oriented rather than datagram, stateful across packets, and
dependent on storage. It was written second, and deliberately **without adding a field** — if
it had needed one, the format would have been wrong.

Two things it does differ in, both expressed with existing fields:

- `excludes: [writable, ext2]` while `requires: [vfs, fat32]`. All three come from the same
  subsystem spec. The capability index is per-capability precisely so a service can take the
  read-only half of `fs` and have the exclusion still mean something: this image can read the
  volume and cannot write it, and the leakage gate proves no write symbol is linked in.
- `assets: []` — it needs none. The content is on the disk image the harness builds with
  `mformat`/`mcopy`, which is the point of the retarget.

## Data Structures

### Connection

```c
typedef enum {
    CONN_IDLE, CONN_READING_REQUEST, CONN_SENDING_HEADERS,
    CONN_SENDING_BODY, CONN_CLOSING,
} conn_state_t;

typedef struct {
    conn_state_t state;
    int          sock;
    char         path[256];     /* resolved, docroot-relative */
    uint32_t     offset;        /* bytes of body already sent */
    uint32_t     length;        /* total body length */
    uint32_t     deadline;      /* uptime secs; idle connections are reaped */
} http_conn_t;
```

One connection, not a table. Concurrency needs a scheduler, which the service excludes. A
second client waits in the TCP backlog — acceptable for a document root, and honest.

## Interface (`kernel/include/fileserver.h`)

```c
/* Mount the first FAT32 volume read-only at "/". -1 if there is no block
 * device, no FAT32 volume on it, or no /index.html. */
int  fileserver_init(void);

/* The single serve loop. Binds TCP :80, never returns. */
void fileserver_serve(void);

/* One request line + headers in, one response out. Separated from the loop so
 * request parsing is testable without a socket. */
int  fileserver_handle(const char *request, uint32_t len, http_conn_t *conn);

/* Resolve a URL path against the docroot. Returns -1 on traversal or absence. */
int  fileserver_resolve(const char *url, char *out, uint32_t out_len);
```

## Behavior

### Startup

1. Mount the first virtio-blk device's FAT32 volume read-only. Absent → log and halt; a file server
   with nothing to serve should not pretend to start.
2. Check `/index.html` exists. A volume with no index is a misconfigured image, and finding
   that out at the first request is worse than finding it out at boot.
3. Log `[HTTP] docroot mounted from fat32`, then `[HTTP] listening on :80`.

   Directory entries are read on demand, not indexed at mount: the volume may hold more files
   than the image has memory for, and a read-only server has no reason to cache a namespace it
   does not own.

### Request handling (RFC 9112)

1. Read until CRLFCRLF or 8 KiB, whichever first. Over 8 KiB → `431`, close.
2. Only `GET` and `HEAD`. Anything else → `405` with `Allow: GET, HEAD`.
3. Resolve the path. A directory resolves to `index.html` within it; absent → `404`.
4. Respond with `Content-Length`, `Content-Type` from the extension, and the body for `GET`.
5. Log `[HTTP] GET <path> <status> <bytes>`.
6. `Connection: keep-alive` is **not** honoured — one request per connection. Keep-alive with
   a single connection slot would let one client hold the server indefinitely.

### Path resolution — the security boundary

`fileserver_resolve` is the whole attack surface and is specified tightly:

1. Reject any path not beginning `/`.
2. Percent-decode once. A second decode pass is how `%252e%252e` becomes `..`.
3. Reject the decoded path if it contains a NUL, a backslash, or any `..` segment — checked
   **after** decoding, on segment boundaries, not by substring.
4. Reject anything still over 255 bytes.
5. Look up by exact 8.3/LFN match per segment, walking the directory from the volume root.
   There are no symlinks in FAT32, so the directory walk is the only namespace — nothing can
   redirect a resolved path outside it.

A path that fails any step returns `-1` and is answered `404`, never `403`: a distinguishable
error tells a prober which files exist.

### Edge cases

| Case | Behaviour |
|---|---|
| No block device, or no FAT32 volume on it | Log `[HTTP] no volume to serve`, halt at init |
| Request with no CRLFCRLF before 8 KiB | `431`, close |
| Path resolving outside the docroot | `404` (never `403`) |
| Client disconnects mid-body | Reap, reset to `CONN_IDLE` |
| Connection idle past `deadline` (30s) | Close — a single slot cannot be held open |
| Zero-length file | `200` with `Content-Length: 0` |

## Files

| Path | Contents |
|---|---|
| `kernel/include/fileserver.h` | The interface above |
| `kernel/services/fileserver/docroot.c` | Volume mount and per-segment lookup |
| `kernel/services/fileserver/http.c` | `fileserver_handle`, `fileserver_resolve` |
| `kernel/services/fileserver/serve.c` | `fileserver_serve` — the loop and nothing else |

## Dependencies

`netif`, `ethernet`, `ipv4`, `tcp`, `http-server` from [net](../subsystems/net.md); `vfs` and
`fat32` from [fs](../subsystems/fs.md); `virtio-blk` from
[drivers](../subsystems/drivers.md); `allocator` from [mm](../subsystems/mm.md); `klog`
and `terminal` from [sys](../subsystems/sys.md).

`writable` and `ext2` are excluded though the same subsystem provides them. The image must
contain no write path at all — an excluded capability that ships anyway is the leakage this
field exists to make testable.

## Acceptance Criteria

1. All three `markers` appear on serial, in order.
2. `GET /index.html` returns `200` with a body matching the archive byte for byte.
3. `GET /../../etc/passwd`, `GET /%2e%2e/x` and `GET /%252e%252e/x` all return `404`.
4. `PUT /x` returns `405` with an `Allow` header.
5. A request larger than 8 KiB with no header terminator returns `431` rather than consuming
   memory.
6. The built image contains no ext2 code and no VFS write path.
7. A second client connecting while one is being served is queued, not dropped.
