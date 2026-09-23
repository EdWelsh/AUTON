# Plan: Native Bench (no Docker) — AUTON E2E Phase 0

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 0 — Native bench
**Complexity**: Medium (Small work, gated by one genuinely unknown spike)

## Summary

Make AUTON's kernel build and boot on macOS with no Docker in the loop: install the
Homebrew cross-toolchain, parameterize the two hardcoded tool invocations in the Makefile,
add a native boot script and a preflight that fails loudly, and correct the README. The
entire plan is gated on Task 0 — a spike proving `i686-elf-grub-mkrescue` produces an ISO
QEMU will actually boot. If that fails, stop and switch to the containerized-ISO fallback
rather than working around it.

Phase 1 (LLM config repair) is marked parallel-with-0 in the PRD and touches no files this
plan touches, so it can run concurrently.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Script header | `scripts/auton-boot.sh:1-4` | `#!/usr/bin/env bash`, one-or-two-line purpose comment, `set -euo pipefail` |
| Script root resolution | `scripts/auton-boot.sh:6-7` | `ARCH="${1:-x86_64}"`; `ROOT="$(cd "$(dirname "$0")/.." && pwd)"` |
| Env overrides | `scripts/auton-boot.sh:10-11` | `${MEM:-128M}`, `${CC:-gcc}`, `${BOOT_TIMEOUT:-45}` — every tunable has an inline default |
| Check/report | `scripts/run-acceptance.sh:19-27,95-101` | `check()` emitting `PASS  <name>` / `FAIL  <name>`, `fail=1`, terminal `ALL PASS` or `FAILURES` + `exit 1` |
| Continue-on-failure | `scripts/run-acceptance.sh:4` | Uses `set -uo pipefail` (no `-e`) deliberately, so every check reports before exiting |
| Makefile overridable tool | `kernels/x86_64/kernel/arch/x86_64/toolchain.mk:8` | `CC ?= x86_64-elf-gcc` with a comment naming the override case — the exact idiom to copy for `GRUB_MKRESCUE` |
| Release staging | `scripts/build-iso.sh:5-17` | Mirrors a Makefile target rather than reimplementing it; stages a named artifact |
| Tests | `agent/kernel_spec/tests/acceptance_tests.py:23,34+` | Structured `expected_serial_patterns: list[str]` per test case — the canonical marker source |

**Not found / stated explicitly**: there is no existing preflight, no platform-detection
helper, and no shared shell library under `scripts/`. Task 3 creates the first one; it
follows the `check()` reporting convention above rather than inventing a new format.

## Files to Change

| File | Action | Why |
|---|---|---|
| `kernels/x86_64/Makefile` | UPDATE | `grub-mkrescue` is hardcoded in both `iso` (:46) and `iso-neural` (:66); macOS needs `i686-elf-grub-mkrescue`. Same for `qemu-system-x86_64` in `run` (:51) / `run-neural` (:71) |
| `scripts/lib/toolchain.sh` | CREATE | Three scripts each hardcode `CC="${CC:-gcc}"`, which is wrong on macOS. One resolver, sourced by all |
| `scripts/preflight.sh` | CREATE | Toolchain presence + free-disk floor, failing with a specific message before any long operation |
| `scripts/auton-boot-native.sh` | CREATE | Native build+boot entry point, per PRD scope |
| `scripts/run-acceptance.sh` | UPDATE | Source the resolver instead of `CC="${CC:-gcc}"`, so the 12 markers can be asserted natively |
| `scripts/auton-boot.sh` | UPDATE | Same one-line resolver change; keeps the Docker path behaviour identical |
| `scripts/build-iso.sh` | UPDATE | Same; otherwise release ISOs can only be built in Docker |
| `README.md` | UPDATE | Add "Quick Start (native macOS)" beside "Quick Start (Docker)" at :319; state the toolchain and the disk floor |
| `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md` | UPDATE | Phase 0 row → `in-progress`, plan path recorded (done as part of this planning step) |

## Tasks

### Task 0: GATE — prove the native ISO path works
- **Action**: Install the toolchain, then prove each link in the chain separately before
  writing any code:
  1. `brew install qemu xorriso x86_64-elf-gcc x86_64-elf-binutils i686-elf-grub`
  2. `make -C kernels/x86_64 clean && make -C kernels/x86_64` — proves the cross compiler
     alone produces `build/kernel.bin` (do **not** pass `CC=gcc`)
  3. Stage an isodir by hand and run `i686-elf-grub-mkrescue -o /tmp/spike.iso <isodir>`,
     adding `--directory=$(brew --prefix i686-elf-grub)/lib/grub/i386-pc` if the module
     path isn't found automatically — proves ISO generation
  4. `qemu-system-x86_64 -cdrom /tmp/spike.iso -serial stdio -display none -no-reboot -m 128M`
     — proves the ISO is actually BIOS-bootable
- **Mirror**: nothing yet — this is a spike, run by hand, no files committed.
- **Validate**: step 4 prints `AUTON Kernel booting` and reaches `[BOOT] OK`.
- **STOP CONDITION**: if step 3 or 4 fails, do not work around it. Record what failed and
  switch to the fallback (build the ISO in a slim amd64 container, run QEMU natively) —
  that changes Tasks 1–2 materially and warrants re-planning.

### Task 1: Parameterize the Makefile's external tools
- **Action**: Add `GRUB_MKRESCUE ?= grub-mkrescue` and `QEMU ?= qemu-system-x86_64` near the
  top of `kernels/x86_64/Makefile`, with a comment naming the macOS override case. Replace
  the four hardcoded call sites: `iso` (:46), `iso-neural` (:66), `run` (:51), `run-neural` (:71).
- **Mirror**: `toolchain.mk:8` — `CC ?= x86_64-elf-gcc` preceded by a comment showing the
  override. Use the identical `?=` + comment shape.
- **Validate**: `make -C kernels/x86_64 GRUB_MKRESCUE=i686-elf-grub-mkrescue iso` builds
  `build/auton.iso`; the Docker path (`docker compose run acceptance`) is unaffected because
  the defaults are unchanged.

### Task 2: `scripts/lib/toolchain.sh` — per-platform tool resolution
- **Action**: One sourceable file exporting `CC`, `GRUB_MKRESCUE`, and `QEMU`, resolved by
  `uname -s`: on Darwin leave `CC` to the Makefile default (`x86_64-elf-gcc`) and set
  `GRUB_MKRESCUE=i686-elf-grub-mkrescue`; on Linux keep today's `gcc` / `grub-mkrescue`.
  Respect any value already set in the environment — never overwrite an explicit override.
- **Mirror**: `auton-boot.sh:6-7` for root resolution; the `${VAR:-default}` idiom used
  throughout `run-acceptance.sh` for respecting caller overrides.
- **Why this exists**: `auton-boot.sh:10`, `run-acceptance.sh:11`, and `build-iso.sh:15` all
  hardcode `CC="${CC:-gcc}"`. On macOS `gcc` resolves to Apple clang, which cannot emit
  ELF64 — every one of these fails natively today. Fixing it in three places would drift.
- **Validate**: `bash -c 'source scripts/lib/toolchain.sh && echo "$CC $GRUB_MKRESCUE"'`
  prints the cross-compiler and `i686-elf-grub-mkrescue` on this host.

### Task 3: `scripts/preflight.sh` — fail loudly, fail early
- **Action**: Check each required tool is on PATH (`$CC`, `$GRUB_MKRESCUE`, `xorriso`,
  `$QEMU`) and that free space on the build volume exceeds a floor (`MIN_FREE_GB`, default
  5). Report per-check `PASS`/`FAIL` lines; exit 1 on any failure with the exact `brew
  install` command or the shortfall in GiB.
- **Mirror**: `run-acceptance.sh:19-27` `check()` and the `ALL PASS` / `FAILURES` + `exit 1`
  ending at :95-101. Use `set -uo pipefail` (not `-e`) so every check reports before exiting.
- **Why the disk floor**: the PRD records image-blob corruption at this disk level twice;
  `/System/Volumes/Data` is at 98% (11 GiB free) as of 2026-09-10.
- **Validate**: passes as-is on this host; `MIN_FREE_GB=999 scripts/preflight.sh` fails with
  a specific shortfall message rather than a stack trace.

### Task 4: `scripts/auton-boot-native.sh`
- **Action**: Run the preflight, then `make ... iso` and exec QEMU — no Docker anywhere.
  Accept `ARCH` as `$1`, honour `MEM`, and pass a `MODEL` through to `iso-neural` when set
  so the neural boot works natively too.
- **Mirror**: `scripts/auton-boot.sh` in full — same header, same `set -euo pipefail`, same
  `ROOT`/`ARCH` resolution, same `exec qemu…` ending. The only deliberate differences are
  sourcing the resolver instead of `CC=gcc`, and the preflight call.
- **Validate**: `scripts/auton-boot-native.sh` reaches an interactive `auton>` prompt with
  Docker Desktop never started.

### Task 5: Make native acceptance assert the markers
- **Action**: Change `run-acceptance.sh:11`, `auton-boot.sh:10`, and `build-iso.sh:15` to
  source `scripts/lib/toolchain.sh` instead of hardcoding `CC="${CC:-gcc}"`. No other
  behaviour change; the marker list stays exactly as it is.
- **Mirror**: the existing call shape — `make -C "$KDIR" iso` with tools coming from the
  environment.
- **Validate**: `scripts/run-acceptance.sh` prints `ALL PASS` natively (12 boot markers plus
  `net_dhcp_ip` and `http_get`), matching the Docker result.
- **Boundary**: `run-acceptance.sh` duplicates the marker list that
  `acceptance_tests.py:34+` holds as structured `expected_serial_patterns`. Two sources of
  truth. **Do not reconcile that here** — it belongs to Phase 2 (the E2E spine), which owns
  the harness. Note it and move on.

### Task 6: README truth-up
- **Action**: Add a "Quick Start (native macOS)" section beside "Quick Start (Docker)"
  (:319): the `brew install` line, `scripts/auton-boot-native.sh`, `scripts/preflight.sh`,
  and the disk floor. State plainly that Docker remains the fallback and is still required
  for the OS-image backend.
- **Mirror**: the existing "Quick Start (Docker)" section's structure — fenced command block
  then a short prose paragraph explaining what the command does.
- **Validate**: a reader following only the README gets from a clean checkout to `auton>`
  on macOS without opening Docker.

## Validation

```bash
# Gate (Task 0) — run by hand, before anything else
brew install qemu xorriso x86_64-elf-gcc x86_64-elf-binutils i686-elf-grub
make -C kernels/x86_64 clean && make -C kernels/x86_64          # cross-compiler only
qemu-system-x86_64 -cdrom /tmp/spike.iso -serial stdio -display none -no-reboot -m 128M

# Per-task
bash -c 'source scripts/lib/toolchain.sh && echo "$CC | $GRUB_MKRESCUE | $QEMU"'
scripts/preflight.sh                       # expect ALL PASS
MIN_FREE_GB=999 scripts/preflight.sh       # expect FAILURES + exit 1

# Phase 0 success signal (the PRD's bar)
make -C kernels/x86_64 GRUB_MKRESCUE=i686-elf-grub-mkrescue run   # expect [BOOT] OK + auton>
scripts/auton-boot-native.sh                                      # same, via the script
scripts/run-acceptance.sh                                         # expect ALL PASS

# Non-regression: the Docker path must be untouched (run only if the daemon is up)
docker compose run acceptance                                     # expect ALL PASS
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `i686-elf-grub-mkrescue` lacks i386-pc modules or won't drive Homebrew `xorriso` | **M** | Task 0 is a hard gate before any file is written. Fallback: containerized ISO build + native QEMU, which still removes the double-emulation tax |
| `grub-mkrescue` demands `mtools`/`mformat` even for a BIOS-only ISO | **M** | `brew install mtools` and add it to the preflight; cheap if needed, harmless if not |
| Apple clang shadows the cross compiler via an inherited `CC=gcc` | **H** *(certain without Task 2)* | Precisely why Task 2 exists. Preflight asserts `$CC` actually reports an `x86_64-elf` target, not just that a binary named `gcc` exists |
| Disk exhaustion mid-build | **M** | `MIN_FREE_GB` floor checked before every build; 11 GiB free today |
| Makefile change silently breaks the Docker path | **L** | `?=` keeps existing defaults byte-identical; Docker non-regression is an explicit validation step |
| Native QEMU is still TCG on arm64 and disappoints on speed | **L** | Accepted and already stated in the PRD; single-layer emulation is the win here, not native execution. Real speed arrives with KVM in the Windows/Linux PRD |
| Scope creep into the E2E harness | **M** | Task 5's boundary note: the duplicated marker list is Phase 2's problem, explicitly not this plan's |

## Acceptance

- [ ] Task 0 gate passed (or the fallback decision is recorded and this plan re-scoped)
- [ ] `make -C kernels/x86_64 run` reaches `[BOOT] OK` and an interactive `auton>` on macOS
- [ ] `scripts/auton-boot-native.sh` does the same, Docker Desktop never started
- [ ] `scripts/run-acceptance.sh` prints `ALL PASS` natively
- [ ] `scripts/preflight.sh` passes here and fails with a specific message when starved
- [ ] Docker path verified unchanged (or explicitly deferred with the daemon-down reason noted)
- [ ] README lets a reader reach `auton>` natively without opening Docker
- [ ] Patterns mirrored, not reinvented — `?=` from `toolchain.mk:8`, `check()` from
      `run-acceptance.sh:19`, script skeleton from `auton-boot.sh`
- [ ] No changes to kernel C source, the acceptance marker list, or the SLM pipeline
