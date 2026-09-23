# Plan: I2 "host this repo" (intent-H)

## Summary
The second headline intent, chosen because it is Doom's opposite: network and HTTP, **no
writable storage** (`auton-intent-to-os-compiler.prd.md:201, 207-209`). Its probe is external
and unambiguous: *`git clone` the served URL, diff against HEAD.* `package_image.py "host this
repo"` currently stops at `no service spec for 'host-repo'`. This plan writes that spec, reusing
`fileserver.md`'s original read-only boot-module design (which F8 is moving off), serves the
repo as git's **dumb HTTP** layout, and grades the image by an actual `git clone`.

## User Story
As a user who says "host this repo", I want an image that serves my repository so that
`git clone http://…` works, with nothing writable in it.

## Problem → Solution
The intent resolves, but no spec exists, so the package is blocked → `services/host-repo.md`
(a read-only HTTP server over a CPIO module containing a bare repo after `git update-server-info`);
`package_image.py` packs the repo as the asset; the probe is `git clone` via hostfwd, then
`git diff HEAD` against the source is empty; the image size is compared with Doom's.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-intent-to-os-compiler.prd.md`
- **PRD Phase**: H, I2 host-this-repo
- **Estimated Files**: 7 + generated service + report
- **Depends on**: `w12-kernel-base` (the base's `http.c`, `tcp.c`, `dhcp.c` all exist: no new driver needed); protocol from `w13-factory-f6-rerun`. **Not** on storage

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/intent_manifest.py` | 87-95 | the `host-repo` rule: requires `ipv4 tcp http-server dhcp-client`, markers `[NET] dhcp bound`, `[HTTP] listening on 80` |
| P0 | `agent/kernel_spec/services/fileserver.md` (git `HEAD` before w14) | 73-106 | the CPIO-module read-only design and the path-resolution boundary, reused |
| P0 | `scripts/run-acceptance.sh` | 48-100 | hostfwd HTTP probe that already passes on the base |
| P0 | `agent/tools/package_image.py` | blocked_by logic; assets handling | where the repo becomes a module asset |
| P1 | `agent/kernel_spec/subsystems/pkg.md` | *Module assets* (w11) | `pkg_module_asset("repo.cpio")` |
| P1 | `.claude/PRPs/reports/w4-intent-leakage-enforcement.md` | all | the `excludes` measurement the size comparison uses |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| Dumb HTTP transport | git-scm.com/docs/http-protocol §"Dumb Clients"; `git update-server-info` | a client fetches `info/refs`, `HEAD`, `objects/info/packs`, then pack/idx or loose objects. Pure static GET |
| Content types | same | the client does not require specific types for dumb fetch; `application/octet-stream` is fine |

KEY_INSIGHT: `git clone --bare . r.git && git -C r.git repack -a -d && git -C r.git update-server-info`
gives a handful of static files (one pack), ideal for a CPIO module.
GOTCHA: `git clone http://…` tries smart HTTP first (`/info/refs?service=git-upload-pack`). The
server must answer that URL with a **plain** `info/refs` (the query ignored) or a 404. Either makes
the client fall back to dumb. It must not answer 200 with an HTML error page.

## Patterns to Mirror
### SECURITY_BOUNDARY
// SOURCE: agent/kernel_spec/services/fileserver.md:93-106 (decode once, reject `..` by segment, 404 not 403).
### ACCEPTANCE_PROBE
// SOURCE: scripts/run-acceptance.sh:62-76 (`/dev/tcp` probe); this plan uses `git clone` as the client instead.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/services/host-repo.md` | CREATE | requires the rule's capabilities + `module-asset`; excludes `writable, fs, udp-only services, preemptive, ipc`; assets `[repo.cpio]`; the query-string rule above |
| `agent/tools/intent_manifest.py` | UPDATE | add `module-asset` and `assets=("repo.cpio",)` to `host-repo`; a marker `[HTTP] repo mounted <n> files` |
| `agent/tools/package_image.py` | UPDATE | `--repo <path>` builds `repo.cpio` (bare, repacked, update-server-info) into the package's `assets/`, recorded by hash in `PROVENANCE.json` |
| `tests/kernel/host_repo_test.c` + reference + runner | CREATE | CPIO index, query-string stripping, traversal corpus |
| `scripts/run-intent-probe.sh` | CREATE | `host-repo`: boot the package ISO with `-initrd`-style module + hostfwd, `git clone`, `git diff --stat HEAD` empty. Leaves room for a `doom` probe (w14-intent-doom-boots) |
| `agent/kernel_spec/services/README.md` | UPDATE | row |

## NOT Building
- Smart HTTP, push, auth, TLS.
- A writable anything. The leakage gate proves it.

## Step-by-Step Tasks
### Task 1: Spec + rule update (before any run)
- **VALIDATE**: `intent_service.py "host this repo"` stub replaced by the written spec; `service_spec.py --resolve host-repo` shows no `writable`.

### Task 2: Host tests + reference (CPIO in place, the smart-HTTP fallback, the traversal corpus)

### Task 3: Packaging the repo as an asset
- **GOTCHA**: The asset is the *user's* repo and may be large. Refuse over a stated size (for example 64 MiB, the module-memory budget in `boot.md`), naming the limit. Never silently truncate.

### Task 4: Build (protocol or human, labelled)

### Task 5: The probe, and the rubric
- **ACTION**: `run-intent-probe.sh host-repo <package>` → **worked** (clone matches HEAD) / **honestly refused** / **failed**, per the PRD's grading.
- **VALIDATE**: clone of this repo at HEAD matches; the image contains no `writable` symbols (leakage gate).

### Task 6: The size comparison
- **ACTION**: kernel bytes for host-repo vs play-doom (when both build), to show `excludes` works in both directions (PRD I1/I2 rationale).

## Validation Commands
```bash
tests/kernel/run_host_repo_test.sh --self-test
.venv/bin/python agent/tools/package_image.py "host this repo" --repo . --output /tmp/hr --target agent/kernel_spec/targets/qemu-pc.md
scripts/run-intent-probe.sh host-repo /tmp/hr
```

## Acceptance Criteria
- [ ] `git clone` of the served URL equals HEAD
- [ ] No writable code in the image
- [ ] The package is complete (no `blocked_by`)
- [ ] Graded with the PRD's three-way rubric

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The client refuses the dumb fallback | L | H | the query-string gotcha; tested against real `git` in Task 5 |
| A large repo exceeds module memory | M | M | a stated limit and a refusal |


---

## Progress: Tasks 1-2 (2026-09-22)

`host-repo.md` + intent rule + `run_host_repo_test.sh` (28 checks, 7/7 injected bugs) and `--clone`, which packs a real bare repo and clones it over the dumb-HTTP layout. **Remaining**: Task 3 (`package_image.py --repo`, 64 MiB refusal), Task 4 build, Task 5 `run-intent-probe.sh`, Task 6 size comparison.


---

## Closed 2026-09-23

host-repo.md, the intent rule, the 28-check suite, `--clone` against real git, `package_image.py --repo` and `run-intent-probe.sh host-repo` are done. The build is a generation run.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
