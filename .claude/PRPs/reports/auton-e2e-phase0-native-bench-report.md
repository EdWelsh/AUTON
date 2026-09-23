# Implementation Report: Native Bench (no Docker) — AUTON E2E Phase 0

## Summary

AUTON's x86_64 kernel now builds and boots entirely on macOS with no Docker in the loop.
The gate spike passed on the first attempt — `i686-elf-grub-mkrescue` produces a
BIOS-bootable ISO that QEMU boots to an interactive `auton>` prompt — so the containerized
fallback was not needed. The Makefile's external tools are parameterized, a per-platform
resolver replaces the `CC=gcc` hardcoding in three scripts, a preflight fails early on a
missing tool or a full disk, and `scripts/run-acceptance.sh` reports **ALL PASS (14/14)**
natively, including a real DHCP lease and a real HTTP 200 from the in-kernel TCP/IP stack.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Medium (small work, gated by one unknown) | Medium — accurate, but the unknown that bit was not the one predicted |
| Gate risk | `grub-mkrescue` on macOS: **M** likelihood of failure | Passed first try, no `--directory` flag needed |
| Files changed | 9 | 9 (5 updated, 3 created, 1 PRD) |
| Docker non-regression | Explicit validation step | **Not verified** — daemon down; preserved by construction |

The plan's risk table put "Apple clang shadows the cross compiler" at **H — certain without
Task 2**, and that was right. It missed two other issues entirely (below), both of which cost
more time than the risk it did predict.

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 0 | GATE — prove the native ISO path | Complete | Passed all 4 steps; fallback not needed |
| 1 | Parameterize Makefile external tools | Complete | `GRUB_MKRESCUE`/`QEMU` `?=` + 4 call sites |
| 2 | `scripts/lib/toolchain.sh` | Complete | **Deviated** — must *set* `CC`, and gained a `timeout` shim |
| 3 | `scripts/preflight.sh` | Complete | Checks target triple, not just binary presence |
| 4 | `scripts/auton-boot-native.sh` | Complete | `MODEL=` passthrough for the neural ISO |
| 5 | Wire the three existing scripts | Complete | Also replaced 3 `timeout` calls |
| 6 | README truth-up | Complete | New "Quick Start (native macOS — no Docker)" section |

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static analysis | Pass | `bash -n` clean on all 6 scripts; shellcheck not installed |
| Portability | Pass | All scripts verified under stock `/bin/bash` 3.2.57 |
| Unit-ish | Pass | Resolver: correct tools, honours overrides; shim: stdin passthrough, rc=124 on timeout, exit code preserved |
| Build | Pass | `make CC=x86_64-elf-gcc` → `build/kernel.bin`, ELF 64-bit x86-64, 201 KB |
| Integration | Pass | `scripts/run-acceptance.sh` = **ALL PASS 14/14**, exit 0 |
| Edge cases | Pass | `MIN_FREE_GB=999` fails with a specific shortfall; wrong `CC` rejected by triple check |
| Docker non-regression | **Deferred** | Daemon not running; see Issues |

Native acceptance, second run (after the shim fix):

```
12 boot markers ......... PASS
net_dhcp_ip ............. PASS   [NET] IP 10.0.2.15
http_get ................ PASS   auton> be a web server -> [HTTP] listening on :80
ALL PASS  (exit 0)
```

## Files Changed

| File | Action | Lines |
|---|---|---|
| `scripts/lib/toolchain.sh` | CREATED | +68 |
| `scripts/preflight.sh` | CREATED | +72 |
| `scripts/auton-boot-native.sh` | CREATED | +34 |
| `kernels/x86_64/Makefile` | UPDATED | +15 / -4 |
| `scripts/run-acceptance.sh` | UPDATED | +10 / -4 |
| `scripts/auton-boot.sh` | UPDATED | +6 / -2 |
| `scripts/build-iso.sh` | UPDATED | +5 / -1 |
| `README.md` | UPDATED | +36 |
| `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md` | UPDATED | Phase 0 → complete |

## Deviations from Plan

**1. `CC ?= x86_64-elf-gcc` in `toolchain.mk:8` is dead code.**
*What*: The plan (and the PRD's feasibility note) claimed the Makefile "already defaults `CC`
to `x86_64-elf-gcc`", and Task 2 said to "leave `CC` to the Makefile default" on Darwin.
*Why it's wrong*: GNU Make predefines `CC` with origin `default` (value `cc`), and `?=` only
assigns when a variable is genuinely undefined — so the assignment never fires. A bare `make`
picks up Apple clang and dies with `unsupported option '-mno-sse' for target 'arm64-apple-darwin'`.
This is also why all three scripts historically passed `CC=gcc` explicitly.
*Resolution*: `scripts/lib/toolchain.sh` sets `CC` per platform. **`toolchain.mk` was left
unchanged deliberately** — fixing the `?=` there would alter what a bare `make` does inside the
Docker image, and the Docker path could not be re-verified in this session. The reasoning is
recorded in a comment in the resolver instead.

**2. macOS has no `timeout`.**
*What*: Unanticipated by the plan. `scripts/run-acceptance.sh` called `timeout` three times;
neither `timeout` nor `gtimeout` exists here and coreutils is not installed.
*Why*: `timeout` is GNU coreutils, absent from stock macOS.
*Resolution*: `auton_timeout` in the resolver — uses the real binary when present, otherwise a
background-and-kill shim returning coreutils-compatible `124`. Scope creep beyond the plan's
Task 2, but Task 5's validation was unreachable without it.

**3. A `GRUB_MKRESCUE`/`QEMU` variable pair, not just `GRUB_MKRESCUE`.**
Minor: the plan named only `GRUB_MKRESCUE`; `QEMU` was added for symmetry so `make run` is
overridable too.

## Issues Encountered

**The timeout shim silently swallowed stdin (self-inflicted, caught and fixed).**
The first full acceptance run came back 13/14 with `http_get` failing on an empty body, and the
net serial showed no `[HTTP] listening on :80` — `be a web server` never reached the REPL. Cause:
bash redirects an asynchronous command's stdin to `/dev/null` when job control is off, so
`"$@" &` inside the shim severed QEMU from the harness's input pipe. Fixed with an explicit
`"$@" <&0 &`, which suppresses the substitution; re-run went 14/14. Worth flagging for Phase 2:
`auton_timeout` will carry every QEMU boot in the E2E spine, and this failure presents as a
kernel bug rather than a harness bug.

**Docker non-regression could not be verified.** The daemon is not running. Behaviour is
preserved by construction — on Linux the resolver yields exactly the previous `gcc` /
`grub-mkrescue` / `qemu-system-x86_64`, and the Makefile's `?=` defaults are byte-identical —
but that is reasoning, not evidence. **`docker compose run acceptance` should be run once the
daemon is up, before this is relied on.**

**Disk pressure.** `/System/Volumes/Data` was 8.2 GiB free at start, 6.9 GiB after the
toolchain install (~1.3 GiB), 7.0 GiB at finish. Above the 5 GiB floor but thin; the PRD's later
training phases will need headroom.

## Tests Written

No unit-test files — this phase delivers shell tooling, and the repo has no shell test
framework. Verification is behavioural and reproducible:

| Check | Command | Result |
|---|---|---|
| Toolchain resolution | `source scripts/lib/toolchain.sh` | correct per platform; honours overrides |
| Timeout shim | `auton_timeout 1 sleep 5` / `5 true` / `5 sh -c "exit 3"` | 124 / 0 / 3 |
| Stdin passthrough | `printf hello \| auton_timeout 5 cat` | `hello` |
| Preflight, healthy | `scripts/preflight.sh` | ALL PASS, exit 0 |
| Preflight, starved | `MIN_FREE_GB=999 scripts/preflight.sh` | FAILURES, exit 1, names the shortfall |
| bash 3.2 | `/bin/bash scripts/preflight.sh` | ALL PASS |
| Full acceptance | `scripts/run-acceptance.sh` | ALL PASS 14/14 |

## Next Steps

- [ ] Run `docker compose run acceptance` once the daemon is up (the one deferred check)
- [ ] Phase 1 — LLM config repair (parallel-ready, independent files)
- [ ] Phase 2 — E2E spine; note the `auton_timeout` stdin lesson and the marker-list
      single-sourcing this phase deliberately deferred
- [ ] Code review via `/code-review`; commit is **not** done — no commit was requested
