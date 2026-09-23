# Plan: Service #3, File Server over FAT32 (F8)

## Summary
`services/fileserver.md` exists, but serves a CPIO archive handed in as a boot module, which is
the storage-free design written before F7. The PRD's F8 success signal is stricter: *"`curl`
retrieves a file that was written to the image's disk, not compiled in."* This plan retargets
the spec to a read-only FAT32 volume on virtio-blk (from `w13-generate-storage`), keeps its
path-resolution security boundary word for word, and builds the image under the Generation
Experiment Protocol, with a human fallback labelled as such.

## User Story
As a user who says "be a file server", I want an image that serves files from its disk over
HTTP, so that adding a file is a disk copy, not a rebuild.

## Problem → Solution
The file server reads a boot-module CPIO; `roles.c` says `file` is roadmap → `fileserver.md`
requires `fat32` + `virtio-blk` and still excludes `writable`; a generated image serves `mcopy`'d
files; the storage acceptance script gains a `curl` step.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-service-kernel-factory.prd.md` phase 8
- **Estimated Files**: 4 spec/test + generated service + report
- **Depends on**: `w13-generate-storage`, `w13-factory-f6-rerun` (protocol; tells whether the loop or a human writes this)

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/kernel_spec/services/fileserver.md` | all | the spec to retarget; "Path resolution: the security boundary" is kept verbatim |
| P0 | `scripts/run-acceptance.sh` | 48-100 | a proven hostfwd HTTP probe via `/dev/tcp` |
| P0 | `w13-factory-f6-rerun.plan.md` | protocol | |
| P1 | base `kernel/server/http.c`, `kernel/server/serve.c` | all | the HTTP server already in the base (`http-server` capability) |
| P1 | `agent/tools/build_service.py` | leakage gate | proves no `writable` symbol ships |

## Patterns to Mirror
### HTTP_PROBE
// SOURCE: scripts/run-acceptance.sh:62-76
```bash
http_get() {
	exec 3<>"/dev/tcp/127.0.0.1/${HOST_PORT}" 2>/dev/null || return 1
	printf 'GET / HTTP/1.0\r\n\r\n' >&3
	auton_timeout 5 cat <&3
```
### SECURITY_BOUNDARY
// SOURCE: agent/kernel_spec/services/fileserver.md:93-106: decode once, reject `..` by segment after decoding, 404 never 403.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/services/fileserver.md` | UPDATE | requires `vfs, fat32, virtio-blk` in place of `initramfs`; assets `[]`; markers `[HTTP] docroot mounted from virtio-blk`, `[HTTP] listening on :80`, `[HTTP] GET /index.html 200 <n>`; resolution walks the FAT32 root directory, not a CPIO index |
| `tests/kernel/fileserver_test.c` + `run_fileserver_test.sh` | CREATE | host tests of `fileserver_resolve` and `fileserver_handle`: the traversal corpus below |
| `scripts/run-storage-acceptance.sh` | UPDATE | `--service fileserver`: `mcopy` an `index.html` and a nested file, boot with hostfwd, `curl` both, and compare bytes |
| `<ws>/kernel/services/fileserver/*` | GENERATED (or human, labelled) | the service |
| `agent/kernel_spec/services/README.md` | UPDATE | table row |

## NOT Building
- Uploads, PUT, WebDAV. `writable` stays excluded.
- TLS.
- Directory listings (404 for a directory without `index.html`, as today).

## Step-by-Step Tasks
### Task 1: Retarget the spec (before any run)
- **ACTION**: Edit `fileserver.md` as above. Keep "Path resolution" verbatim except step 5, which becomes *"look up by exact 8.3/LFN match per segment; there are no symlinks in FAT32, so the directory walk is the only namespace"*.
- **VALIDATE**: `service_spec.py --validate` / `--resolve` OK; the slice contains `fat32`, not `writable`.

### Task 2: Host tests (human, frozen before the run)
- **IMPLEMENT**: the traversal corpus: `/../x`, `/%2e%2e/x`, `/%252e%252e/x` (must 404 without double decode), `/a/../../x`, backslash, embedded NUL, a 256-byte path, `/` → `index.html`, a missing file → 404, `POST` → 405 with `Allow`, a >8 KiB header → 431.
- **VALIDATE**: `--self-test` against a small reference over the FAT32 reference.

### Task 3: Run (protocol 1-4), or the human path
- **DECISION RULE**: if the F6 re-run produced a passing service, run the loop (pre-registered). Otherwise implement by hand and mark `authored_by: human` in `authorship.yaml`.

### Task 4: Gates
- **ORDER**: `run_fileserver_test.sh` tree mode → `build_service.py fileserver` (the leakage gate proves no `writable` symbols) → `run-storage-acceptance.sh --service fileserver` (`curl` bytes match `mcopy`'d bytes).

### Task 5: roles.c row and report
- **ACTION**: record the result. `roles.c` truth-up is F12; do not edit it here.

## Validation Commands
```bash
tests/kernel/run_fileserver_test.sh --self-test
.venv/bin/python agent/tools/build_service.py fileserver --tree <ws> --iso
scripts/run-storage-acceptance.sh <ws> --service fileserver
```

## Acceptance Criteria
- [ ] `curl` retrieves a file copied onto the disk image, byte-identical
- [ ] The traversal corpus answers 404, never 403, never file contents
- [ ] The leakage gate shows no `writable` symbol in the image
- [ ] Authorship recorded honestly (agent or human)

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The FAT32 write path leaks into a read-only image | M | M | `w12` split plus the leakage gate |
| TCP under SLIRP is flaky | L | M | the base's HTTP probe already passes in `run-acceptance.sh` |


---

## Progress: Tasks 1-2 (2026-09-22)

Spec retargeted to the FAT32 volume; host suite `run_fileserver_test.sh` (29 checks, 8/8 injected bugs, the fake volume made deliberately permissive so the traversal tests are not vacuous). **Remaining**: Task 3 (build — generation or a labelled human path), Task 4 gates (leakage + `run-storage-acceptance.sh --service fileserver`), Task 5 report.


---

## Closed 2026-09-23

Spec retargeted to the FAT32 volume and the 29-check suite (8/8 injected bugs) are done. The build and the two-boot acceptance are a generation run: docs/OPEN-WORK.md.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
