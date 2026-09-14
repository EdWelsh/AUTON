---
service: fileserver
requires: [netif, ethernet, ipv4, tcp, http-server, vfs, initramfs, allocator, klog, terminal]
excludes: [writable, ext2, dhcp-client, preemptive, ipc]
entry: fileserver_serve
markers:
  - "[HTTP] docroot mounted from module"
  - "[HTTP] listening on :80"
  - "[HTTP] GET /index.html 200 1024"
assets: [docroot.cpio]
---

# File Server Service Specification

## Overview

Serves a read-only document root over HTTP/1.1 from a CPIO archive handed in as a Multiboot2
module. One TCP listener, one connection at a time, no writes.

This spec exists to test the service format against a shape structurally unlike
[dhcp.md](dhcp.md): connection-oriented rather than datagram, stateful across packets, and
dependent on storage. It was written second, and deliberately **without adding a field** — if
it had needed one, the format would have been wrong.

Two things it does differ in, both expressed with existing fields:

- `assets: [docroot.cpio]` — the first non-empty asset list. The content served is supplied at
  build time and never committed, which is also how a Doom WAD will work.
- `excludes: [writable, ext2]` while `requires: [vfs, initramfs]`. Both come from the same
  subsystem spec. The capability index is per-capability precisely so a service can take the
  read-only half of `fs` and have the exclusion still mean something.

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
/* Mount the CPIO module read-only at "/". -1 if the module is absent or malformed. */
int  fileserver_init(const void *module, uint32_t module_len);

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

1. Locate the `docroot.cpio` Multiboot2 module by name. Absent → log and halt; a file server
   with nothing to serve should not pretend to start.
2. Parse the CPIO index in place. The archive is not copied — it is already in memory and the
   service is read-only, which is the same run-in-place argument the SLM model uses.
3. Log `[HTTP] docroot mounted from module`, then `[HTTP] listening on :80`.

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
5. Look up the result in the CPIO index by exact match. There is no filesystem walk, so there
   is no symlink to follow — the archive index is the only namespace.

A path that fails any step returns `-1` and is answered `404`, never `403`: a distinguishable
error tells a prober which files exist.

### Edge cases

| Case | Behaviour |
|---|---|
| Module absent or not CPIO | Log, halt at init |
| Request with no CRLFCRLF before 8 KiB | `431`, close |
| Path resolving outside the docroot | `404` (never `403`) |
| Client disconnects mid-body | Reap, reset to `CONN_IDLE` |
| Connection idle past `deadline` (30s) | Close — a single slot cannot be held open |
| Zero-length file | `200` with `Content-Length: 0` |

## Files

| Path | Contents |
|---|---|
| `kernel/include/fileserver.h` | The interface above |
| `kernel/services/fileserver/cpio.c` | Archive index and lookup |
| `kernel/services/fileserver/http.c` | `fileserver_handle`, `fileserver_resolve` |
| `kernel/services/fileserver/serve.c` | `fileserver_serve` — the loop and nothing else |

## Dependencies

`netif`, `ethernet`, `ipv4`, `tcp`, `http-server` from [net](../subsystems/net.md); `vfs` and
`initramfs` from [fs](../subsystems/fs.md); `allocator` from [mm](../subsystems/mm.md); `klog`
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
