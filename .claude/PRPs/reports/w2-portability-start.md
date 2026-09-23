# Report: Portability — Begin the Long Lead (windows-linux)

**Plan**: `.claude/PRPs/plans/w2-portability-start.plan.md`
**Source PRD**: `auton-windows-linux.prd.md`

Started now because H10's conformance work needs real silicon and acquiring it has a lead time.
Scope was deliberately the build-and-boot path plus the identity cross-check — not the control
plane, not the installer.

## Task 1: what is host-dependent

| Construct | Where | Resolution |
|---|---|---|
| Homebrew tool names | `scripts/lib/toolchain.sh:19-26` | **Abstracted** — `uname -s` branch, and an explicit env value always wins |
| `timeout` absent on macOS | `toolchain.sh:35-68` | **Abstracted** — prefers real `timeout`/`gtimeout`, falls back to a shim with matching exit 124 |
| `brew install` hints | `preflight.sh:23` | **Accepted** — a Darwin-specific hint in a failure message, harmless elsewhere |
| `date -r <file>` | `e2e.sh:156` | **Accepted** — verified working on both: BSD `date -r` takes a file *or* an epoch, GNU takes a file. The call passes a file, so it is portable as written |
| `sysctl` vs `/proc` | `tests/kernel/identity_test.c` | **Guarded** — tries both, and prints SKIP rather than failing when neither answers |
| x86 CPUID | `identity_test.c` | **Guarded** by `#if defined(__x86_64__)`, and now reported by preflight (below) |

No `sed -i`, `stat -f/-c`, `grep -P` or `readlink -f` divergences found in the scripts.

## Task 4: the gap is now visible on every run

The sharpest finding is not a portability bug — it is that a skip inside a passing suite reads
as a pass.

`identity_test.c` has always printed `SKIP live CPUID cross-check — host is not x86`, and
`IDENTITY: ALL PASS` two lines later. H5's last acceptance criterion has **never been satisfied
on any host**, and nothing said so outside a report.

`preflight.sh` now says it:

```
NOTE  host arch (arm64) cannot run x86 CPUID
      -> tests/kernel/run_identity_test.sh verifies the folding formula
         against documented parts, but its live cross-check against
         this machine's own CPU is SKIPPED. Silicon identity is
         unverified against real hardware on this host.
```

It is a NOTE rather than a FAIL: the host is not broken, it simply cannot answer this question.
Making it a failure would train people to ignore preflight.

## Task 2: a second host

`.github/workflows/portability.yml` runs the unit suites and both spine self-tests on
`ubuntu-latest` (x86-64) as well as `macos-14` (arm64). The cheap subset only — no torch, no
corpus, no training. A job that takes an hour gets disabled.

One step exists solely to stop this being theatre:

```yaml
- name: Assert the live CPUID check ran (x86 only)
  if: matrix.label == 'linux-x86_64'
```

It greps for `SKIP.*live CPUID` and fails if found, then requires a `live CPU:` line. Without
it the matrix could be green with **both** hosts skipping and nobody noticing — which is the
same "silence reads as success" failure the note above is about, one level up.

## Task 3: the silicon H10 needs

`agent/hardware/CONFORMANCE-HARDWARE.md`. Five entries, each with what it proves and whether it
is obtainable. Two are worth repeating here.

**Two Intel steppings of one family** is the minimum that exercises anything. Doc 682436 lists
94 errata whose status varies by processor line; with one part, the matching logic is never
tested against a disagreement.

**A population of ≥1000 similar machines** is *not obtainable*, and that is recorded as a
stated limit rather than a gap to close. Mercurial cores — Google HotOS 2021, Meta 2021 — occur
at roughly one per thousand machines. AUTON cannot detect that class at any scale available
here.

The honest framing that follows: conformance verifies a machine against what vendors have
**already documented**, and reports divergence it cannot explain. Finding a *new* defect ahead
of disclosure needs either a fleet or a targeted semantic differential against a reference
implementation — and only the second is tractable. That is a narrowing of the hardware-truth
PRD's ambition, and it should be said now rather than discovered at H10.

## Acceptance

- [x] Host-dependent assumptions listed, each abstracted, guarded, or accepted with a reason
- [x] Unit suites and spine self-tests configured for Linux x86-64 as well as Darwin
- [ ] **`identity_test.c`'s live cross-check actually runs somewhere** — configured, not yet
      observed. No CI run has happened from this session; the workflow is committed and the
      assertion step will fail loudly if it skips
- [x] The silicon H10 needs is named, with obtainability stated
- [x] Preflight reports x86-dependent checks as unavailable rather than skipping silently

## Follow-on

- The first CI run is the proof. Until it goes green on `linux-x86_64` with a `live CPU:` line,
  H5's last criterion remains open.
- A shared CI runner has an unknown stepping and virtualised microcode state. It satisfies the
  identity cross-check and nothing beyond it — real conformance still needs owned hardware.
- Windows is untouched. The PRD covers it; nothing in this plan's scope reached it, and
  claiming otherwise would be worse than the gap.
