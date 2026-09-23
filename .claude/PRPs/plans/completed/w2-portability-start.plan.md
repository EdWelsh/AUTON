# Plan: Portability — Begin the Long Lead (windows-linux)

**Source PRD**: `.claude/PRPs/prds/auton-windows-linux.prd.md`
**Complexity**: Medium, and the reason to start now is schedule, not urgency
**Unblocks**: H10 (conformance requires real hardware)

## Summary

Hardware-truth's conformance work cannot run under emulation: QEMU implements an idealised CPU
and will not reproduce silicon divergence. Real hardware on real steppings is a long-lead item,
so it begins well before it is needed.

This plan does the part that is useful immediately and independent of hardware access: make the
build and boot path reproducible off a Darwin/arm64 host.

## Evidence

- `scripts/lib/toolchain.sh:18-27` — Darwin and non-Darwin branches exist; the Darwin branch
  hardcodes Homebrew names (`x86_64-elf-gcc`, `i686-elf-grub-mkrescue`).
- `scripts/preflight.sh` — already checks the toolchain, ISO tooling, QEMU and disk, and
  reports everything missing in one pass. The shape to extend, not replace.
- The identity test written for H5 reports `SKIP live CPUID cross-check — host is not x86`
  (`tests/kernel/identity_test.c`). The current development host is arm64, so **no x86 silicon
  identity has ever been cross-checked against an OS view.**
- `.claude/PRPs/reports/w1-hardware-silicon-identity.md` records that as an unmet acceptance
  criterion.
- `scripts/e2e.sh` exists and takes `--target`, so the lane is already parameterised.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Per-platform resolution | `scripts/lib/toolchain.sh` | Never override an explicit env value; branch on `uname -s` |
| Report everything missing | `scripts/preflight.sh` | `set -uo pipefail`, no `-e`; one run lists every failure |
| Parameterised target | `scripts/e2e.sh --target` | Tree is an argument, not a constant |
| Honest skip | `identity_test.c` | Announce what was not checked and why, rather than passing silently |

## Tasks

### Task 1: Name what is host-dependent
- **Action**: Audit every script for assumptions about the host: Homebrew paths, `sysctl` vs
  `/proc`, BSD vs GNU flag differences (`sed -i`, `stat`, `date`), and the `timeout` shim
  already handled in `toolchain.sh`.
- **Validate**: a list, each entry marked "abstracted", "guarded", or "accepted, and why".

### Task 2: A second host in CI
- **Action**: Run preflight, the unit suites, and the spine's self-tests on Linux x86-64 as
  well as Darwin. The kernel-only loop needs no torch and no corpus, so it is cheap.
- **Why x86-64 specifically**: it is the one host where `identity_test.c`'s live CPUID
  cross-check actually runs. That criterion has never been satisfied, and a Linux x86 runner
  satisfies it for free.
- **Validate**: the identity test reports a live CPU rather than a skip; the folded
  family/model matches `/proc/cpuinfo`.

### Task 3: Record the hardware the conformance work will need
- **Action**: A short document naming the silicon required for H10 and why each: at least two
  Intel steppings of one family (to see stepping-level divergence at all), one AMD part, one
  Arm part. Note which are obtainable and which are not.
- **Why now**: acquiring hardware has a lead time measured in weeks, and H10 is several waves
  out. Naming it now is the entire point of starting early.
- **Validate**: each entry says what it proves that emulation cannot.

### Task 4: Make the gap visible
- **Action**: `preflight.sh` reports whether the host can run the x86-dependent checks, rather
  than those checks quietly skipping. A developer on arm64 should be told that silicon identity
  is unverified on their machine.
- **Validate**: on Darwin/arm64, preflight says so explicitly.

## Validation

```bash
scripts/preflight.sh                       # names x86-dependent checks as unavailable on arm64
tests/kernel/run_identity_test.sh --self-test   # SKIP on arm64, live on x86
# on a Linux x86-64 host:
scripts/preflight.sh && tests/kernel/run_identity_test.sh --self-test   # live cross-check runs
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Portability work expands without bound | **H** | Scope is the build and boot path plus the identity cross-check. Not the control plane, not the installer |
| Real hardware never materialises | **M** | Task 3 records what is needed and what is obtainable. An unobtainable stepping is a stated limit on conformance, not a silent gap |
| CI on two hosts doubles the maintenance | **M** | The kernel-only loop is the cheap subset; the training lane stays single-host |
| Emulation treated as sufficient | **H** | The PRD is explicit that it is not. Task 4 makes the gap visible on every preflight run rather than only in a report |

## Acceptance
- [ ] Host-dependent assumptions listed, each abstracted, guarded, or accepted with a reason
- [ ] The unit suites and spine self-tests run on Linux x86-64 as well as Darwin
- [ ] `identity_test.c`'s live CPUID cross-check actually runs somewhere, satisfying H5's last criterion
- [ ] The silicon H10 needs is named, with obtainability stated
- [ ] Preflight reports x86-dependent checks as unavailable rather than skipping silently
