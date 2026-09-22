---
service: host-repo
requires: [netif, ethernet, ipv4, tcp, http-server, dhcp-client, module-asset, allocator, klog, terminal, scoped]
excludes: [writable, ext2, fat32, preemptive, ipc]
entry: host_repo_serve
markers:
  - "[HTTP] repo mounted 128 files"
  - "[HTTP] listening on :80"
  - "[HTTP] GET /info/refs 200 62"
assets: [repo.cpio]
---

# Repository Hosting Service Specification

## Overview

Serves a git repository over HTTP so that `git clone http://<ip>/` works, from a CPIO archive
handed in as a Multiboot2 module. Read-only, one connection at a time, **no writable storage of
any kind**.

This is the intent-compiler's second headline image, chosen because it is Doom's opposite
(`auton-intent-to-os-compiler.prd.md`): network and HTTP, no framebuffer, no input device, no
filesystem. Its probe is external and leaves no room for interpretation: **clone the served URL
and diff against HEAD**.

**Why a boot module and not the FAT32 volume**: the file server moved to the volume in w14
because its PRD signal is about a *disk*. This service's signal is about a *clone*, and the
repository is fixed when the image is built — so it travels in the image, like Doom's WAD. The
CPIO design the file server vacated is reused here rather than deleted, which is why it is
described again below.

**Why dumb HTTP and not smart HTTP**: the dumb protocol is a static file layout. The server
needs no pack negotiation, no `git-upload-pack`, no subprocess, and no writes — which is what
lets this image exclude `writable` entirely. `git clone` falls back to it automatically when
the smart endpoints are absent.

## The layout the archive must contain (REQUIRED)

A **bare** repository, as `git update-server-info` leaves it:

```
/HEAD                     ref: refs/heads/main
/info/refs                <sha>\trefs/heads/main   (tab-separated, one per line)
/objects/info/packs       P pack-<sha>.pack
/objects/<xx>/<38 hex>    loose objects, zlib streams
/objects/pack/pack-*.pack, pack-*.idx
/refs/heads/*, /refs/tags/*
```

`info/refs` and `objects/info/packs` are produced by `git update-server-info`. Without them a
dumb clone cannot enumerate anything and fails with "repository not found" — the packaging step
runs it, and the host tests check both files are present in the archive.

## Request handling

`GET` and `HEAD` only; anything else is `405`. Every response carries `Content-Length`, and
bodies are served as `application/octet-stream` except `info/refs` and `HEAD`, which are
`text/plain`.

### The query string (REQUIRED)

git requests `/info/refs?service=git-upload-pack` first, to discover whether **smart** HTTP is
available. The rule is exact:

- Strip the query string at the first `?` before resolving the path.
- Then serve `/info/refs` as the ordinary static file.

A smart server would answer that request with `application/x-git-upload-pack-advertisement`.
This one answers with the plain refs file, and **that is what makes git fall back to dumb
HTTP**. Answering `404` also makes it fall back, but then the client fetches the same file
again a moment later, so answering it is both correct and one round trip cheaper.

The query string must never reach path resolution: `/info/refs?service=x` looked up verbatim is
a miss, and the clone fails with no useful error.

## Path resolution — the security boundary

Identical in force to [fileserver.md](fileserver.md), against the archive index:

1. Reject any path not beginning `/`.
2. Strip the query string at the first `?`.
3. Percent-decode **once**. A second pass is how `%252e%252e` becomes `..`.
4. Reject the decoded path if it contains a NUL, a backslash, or any `..` **segment** — checked
   after decoding, on segment boundaries, never by substring.
5. Reject anything over 255 bytes.
6. Look the result up in the CPIO index by exact match. There is no filesystem walk and no
   symlink to follow: the archive index is the whole namespace.

Every failure is `404`, never `403`. A distinguishable error tells a prober which objects exist,
and git object names are content hashes — confirming one is confirming content.

## Interface (`kernel/include/host_repo.h`)

```c
/* Index the repo.cpio module read-only. Returns the file count, or -1 if the
 * module is absent, malformed, or has no /info/refs (a repository nobody ran
 * update-server-info on cannot be cloned, and saying so at boot beats failing
 * at the first fetch). */
int  host_repo_init(const void *module, uint32_t module_len);

/* The serve loop. Binds TCP :80, never returns. The front-matter `entry`. */
void host_repo_serve(void);

/* One request in, one response out. No socket, so it is testable without a NIC. */
int  host_repo_handle(const char *request, uint32_t len, http_conn_t *conn);

/* Resolve a URL (query string included) against the archive index. -1 on
 * traversal or absence. */
int  host_repo_resolve(const char *url, char *out, uint32_t out_len);
```

## Edge cases

| Case | Behaviour |
|---|---|
| Module absent, not CPIO, or without `/info/refs` | Log, halt at init |
| `/info/refs?service=git-upload-pack` | Serve `/info/refs` as text/plain |
| `/git-upload-pack` (smart endpoint) | `404`, which is the documented fallback signal |
| `POST /git-upload-pack` | `405`: a push or smart fetch is refused by method, before any path work |
| `/` | `404`. There is no index page; a repository root is not a web page |
| A loose object that is absent | `404`, and git tries the packs — a normal part of a dumb clone |
| Request with no CRLFCRLF before 8 KiB | `431`, close |
| Archive larger than the module budget | Refused at packaging, naming the limit; never truncated |

## Verification

`tests/kernel/run_host_repo_test.sh --self-test` runs the host suite against
`tests/kernel/host_repo_reference/`: the CPIO index, query-string stripping, the traversal
corpus, the methods, and the `/info/refs` requirement at init. `KERNEL_TREE=<dir>` gates a
generated `kernel/services/host-repo/`: exit 2 not generated, exit 1 wrong.

**The layout itself is proved on the host, end to end**, by
`tests/kernel/run_host_repo_test.sh --clone`: pack a real repository the way the packaging step
does, serve the archive's files with a plain static server, `git clone` it, and check the clone's
HEAD matches. That tests the *layout and the packaging*, which is where a dumb-HTTP mistake
lives, without needing a booted kernel.

The image's own grade is `scripts/run-intent-probe.sh host-repo <package>`: boot, `git clone`
through QEMU's hostfwd, `git diff --stat HEAD` empty — **worked**, **honestly refused**, or
**failed**, per the intent PRD's rubric.
