# Plan: Host-Agnostic Entry Point (windows-linux A2)

**Source PRD**: `auton-windows-linux.prd.md` — phase A2
**Depends on**: A1 nominally — see *Why this can start without A1* below
**Why this phase and not phase 0**: phase 0 is *"Proxmox reachability; name the physical test
machine"*, which needs hardware access nobody here has. A2 is script work, and it is what A1 and
A3 will both need on arrival.

## Summary

`scripts/lib/toolchain.sh` already resolves build tools per platform — Homebrew names on Darwin,
distro names elsewhere. `scripts/preflight.sh` already checks them and already announces what a
host **cannot** verify rather than passing silently.

What does not exist anywhere is **accelerator selection**. Grepped across `e2e.sh`,
`toolchain.sh` and `auton-boot.sh`: no `accel`, no `kvm`, no `hvf`, no `whpx`, no `tcg`. Every
boot runs under whatever QEMU picks by default, which on this Mac is TCG — and B1's headline
metric is *"the 10x"* of KVM against TCG, which cannot be measured until something selects.

## Evidence

- `scripts/lib/toolchain.sh:18-30` — the per-platform pattern to extend: a `case "$(uname -s)"`
  setting `CC`, `GRUB_MKRESCUE`, `QEMU`, with *"Any value already present in the environment wins
  — never override an explicit choice by the caller."*
- `scripts/lib/toolchain.sh:35-68` — `TIMEOUT_BIN` and `auton_timeout`, the precedent for *"prefer
  the real binary when present, otherwise a shim with the same argument order"*. Accelerator
  selection has the same shape: prefer the fast one, fall back, say which.
- `scripts/preflight.sh:103-116` — the pattern that matters most here: the host announces what it
  cannot check. *"Silicon identity is unverified against real hardware on this host."* Never a
  silent skip.
- `scripts/preflight.sh:36-40` — checking the **target triple** rather than the binary name,
  because *"Apple clang reports arm64-apple-darwin and silently fails much later"*. Accelerator
  availability needs the same treatment: `qemu-system-x86_64 -accel help` rather than assuming.
- `auton-windows-linux.prd.md:250` — A2's deliverable: *"One `e2e.sh` with host detection +
  `--accel` selection; three-host matrix documented"*.
- `auton-windows-linux.prd.md:252` — B1 depends on this: *"Same ISO, `/dev/kvm`, timed against
  TCG; the 10x metric"*.

## Why this can start without A1

A1 is a Linux bench nobody here has. A2's deliverable is selection logic plus a documented matrix,
and the selection logic is testable by inspection on any host: given a reported accelerator list,
does it choose correctly? That is a pure function of its input, and the input can be supplied.

What cannot be done here is **exercising the Linux and Windows branches**. The plan says so rather
than implying three-host coverage from one host — the same thing `preflight.sh` already does about
CPUID.

## Patterns to Mirror

- **Environment wins**: `toolchain.sh`'s `: "${CC:=...}"`. An explicit `AUTON_ACCEL` is never
  overridden.
- **Probe, do not assume**: `preflight.sh`'s triple check. Ask QEMU what it supports.
- **Announce what this host cannot verify**: `preflight.sh:103-116`, verbatim in shape.
- **Fallback with a shim, and say which**: `auton_timeout`.

## Tasks

### Task 1: Ask QEMU, do not guess from `uname`
- **Action**: `auton_accel()` in `scripts/lib/toolchain.sh` — run `$QEMU -accel help`, intersect
  with a per-platform preference order, return the best available and the reason.
- **Why probe**: `uname -s` says Darwin; it does not say whether this QEMU was built with HVF, or
  whether `/dev/kvm` is readable by this user. A Linux host without `/dev/kvm` access falls back
  to TCG and must know it did.
- **Preference order**: Darwin `hvf` → `tcg`; Linux `kvm` → `tcg`; Windows/WSL2 `whpx` → `kvm` →
  `tcg`.
- **Gotcha**: `-accel help` lists what the **binary** supports, not what the **host** permits.
  KVM appears in the list on a Linux box where `/dev/kvm` is not readable. Check the device too,
  and report which check failed.
- **Validate**: on this Mac it selects an accelerator and names it; given a synthetic list with no
  fast option it selects `tcg` and says why.

### Task 2: `--accel` on the entry points, with the environment winning
- **Action**: `scripts/e2e.sh` and `scripts/auton-boot.sh` take `--accel`, defaulting to
  `auton_accel()`. `AUTON_ACCEL` in the environment overrides both.
- **Gotcha**: an explicit `--accel kvm` on a host without it must **fail loudly**, not silently
  fall back. A caller who asked for KVM and got TCG will read a 10× slower run as a regression.
- **Validate**: `--accel nonesuch` is refused naming what is available; `AUTON_ACCEL` is honoured.

### Task 3: The three-host matrix, as a document
- **Action**: `docs/HOST-MATRIX.md` — per host: toolchain source, accelerator, what is verifiable
  there, and **what is not**.
- **Why a document rather than a comment**: A1, A3, B1 and C1 all consume it, and it is the thing
  a second machine gets handed.
- **Gotcha**: the rows for Linux and Windows are written from the specifications and **have not
  been run**. Say so per row. A matrix that looks uniformly verified when two thirds of it is
  untested is worse than no matrix.
- **Validate**: every row states whether it has been exercised, and only the Darwin row says yes.

### Task 4: Preflight reports the accelerator, and what it costs
- **Action**: `preflight.sh` prints the selected accelerator and, when it is `tcg`, says what that
  means for timing.
- **Why**: B1's metric is a ratio against TCG. A run that does not record which accelerator it
  used produces a number nobody can compare.
- **Gotcha**: this is the `preflight.sh:103-116` pattern — a NOTE, not a FAIL. TCG is slow, not
  broken, and failing a preflight for it would make the Mac unusable.
- **Validate**: `preflight.sh` on this host names the accelerator; the message is a NOTE.

### Task 5: Record the timing baseline this host can produce
- **Action**: Time one boot under the selected accelerator and record it, so B1 has one end of its
  ratio when a Linux host appears.
- **Gotcha**: this is **one point, on one machine, under one accelerator**. It is not the 10×
  metric and must not be reported as it. B1 needs both ends.
- **Validate**: the number is recorded with the host, the accelerator and the QEMU version.

## Validation

```bash
source scripts/lib/toolchain.sh && auton_accel
scripts/preflight.sh                       # names the accelerator, as a NOTE
scripts/e2e.sh --accel tcg                 # explicit, honoured
scripts/e2e.sh --accel nonesuch            # refused, names what is available
AUTON_ACCEL=tcg scripts/e2e.sh             # environment wins
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| An explicit `--accel` silently falls back and a 10× slowdown reads as a regression | **H** | Task 2's gotcha — explicit requests fail loudly |
| `-accel help` is trusted over host permission | **H** | Task 1's gotcha — check `/dev/kvm` too, report which check failed |
| The matrix implies three-host coverage from one host | **H** | Task 3's gotcha — per-row "exercised?" |
| One timing number is reported as the 10× metric | **M** | Task 5's gotcha — it is one end of a ratio |
| A preflight fails on TCG and the Mac becomes unusable | **M** | Task 4's gotcha — NOTE, not FAIL |

## Acceptance
- [ ] `auton_accel()` probes QEMU and the host, never infers from `uname` alone
- [ ] Preference order per platform, with the fallback named
- [ ] `--accel` on `e2e.sh` and `auton-boot.sh`; an explicit unavailable choice fails loudly
- [ ] `AUTON_ACCEL` in the environment wins, as `CC` does
- [ ] `docs/HOST-MATRIX.md` states per row whether it has been exercised; only Darwin says yes
- [ ] `preflight.sh` names the accelerator as a NOTE
- [ ] One timing baseline recorded, labelled as one end of B1's ratio
