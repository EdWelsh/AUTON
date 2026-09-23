# Plan: Conformance Harness: Semantic (FDIV class) and Fault (F00F class) (H10, H10a, H10b)

## Summary
The PRD's headline capability: test whether a chip honours its own documentation, the FDIV
method. The oracle is the crux (*"Without an oracle a conformance suite only detects
self-inconsistency"*). This plan builds one harness with two suites and two execution venues:

- **H10a, semantic**: FP results compared bit-for-bit against **Berkeley SoftFloat** (the
  oracle), over spec-derived corner cases and the historical FDIV operands.
- **H10b, fault**: invalid and reserved encodings must raise the architected exception
  (`#UD`, `#GP`) and the core must continue.
- **Venue 1, now**: a host program run natively on real x86 silicon (the CI runner, any x86
  Linux box). This is real hardware, not QEMU.
- **Venue 2**: an in-kernel suite in a bootable image with per-vector recoverable handlers, run
  under QEMU for harness correctness, and on metal (windows-linux B4) for verdicts.

Every test cites the spec clause it checks. A divergence the harness cannot explain goes to H11's
disclosure pipeline, which already exists.

## User Story
As hardware-truth, I want a suite that compares this CPU's answers and faults to the
specification's, so that AUTON can say "this machine diverges from its documentation" with a
citation, or say that it checked and found nothing.

## Problem → Solution
No conformance code exists; QEMU cannot show divergence → a clause-cited test corpus, a SoftFloat
oracle table generated on the host, a native runner on real silicon (CI), an in-kernel runner
with recoverable exceptions, and a verdict format that feeds `disclosure.record`.

## Metadata
- **Complexity**: XL (split into the tasks below; each lands separately)
- **Source PRD**: `auton-hardware-truth.prd.md`
- **PRD Phase**: H10, H10a, H10b
- **Estimated Files**: ~14
- **Depends on**: H1, H5 (landed); H11 (landed, the sink for findings); `w12-kernel-base` (in-kernel venue)

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/hardware/CONFORMANCE-HARDWARE.md` | all | what emulation cannot show; the stated limits (no fleet ≥1000) |
| P0 | `.claude/PRPs/prds/auton-hardware-truth.prd.md` | Decisions Log, Research Summary | oracle rule; "report zero findings as a finding"; the model is never the oracle |
| P0 | `agent/tools/disclosure.py` | 41-133 | `record(silicon, vendor, spec_citation, expected, …)`, the sink |
| P0 | base `kernel/arch/x86_64/idt.c`, `isr.S` | all | today `exception_handler` halts on any vector with no vector number (`idt.c:88-95`) |
| P1 | `tests/kernel/identity_test.c`, `run_identity_test.sh` | all | host-run on real CPUs with a live CPUID cross-check; the native-venue pattern |
| P1 | `.github/workflows/portability.yml` | x86 steps | "assert the live check ran" pattern |
| P1 | `agent/kernel_spec/mitigations/f00f-idt-remap.md` | Verification | the F00F test's own statement of what it proves on unaffected silicon |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| Berkeley SoftFloat 3e | jhauser.us/arithmetic/SoftFloat.html (BSD-3) | IEEE-754 in software; `f64_div`, `f64_sqrt`, `extF80_div`, rounding modes |
| TestFloat 3e | same author (BSD-3) | `testfloat_gen` produces the corner-case operands IEEE conformance testing uses; reuse its generator, not its judgement |
| The FDIV operands | Nicely 1994; Coe/Tang analyses | `4195835 / 3145727` is the canonical case; the defect was 5 missing SRT table entries |
| #UD encodings | Intel SDM Vol. 2, `UD0/UD1/UD2`; Vol. 3A §6.15 (exception classes) | `UD2` (0F 0B) is architecturally guaranteed #UD; reserved encodings are "may be #UD". Only the *guaranteed* ones are assertable |

GOTCHA: SoftFloat and TestFloat are fetched at build time into `.cache/third_party/` (pinned sha)
and inventoried in `vendors.yaml`. BSD-3 is `permitted` in `licences.yaml`, but still do not
commit copies; the rule is inventory, then fetch.
GOTCHA: only assert **architecturally guaranteed** behaviour. "Reserved, may #UD" is not a
conformance failure when it does not fault, and flagging it would be a false finding sent to
disclosure.

## Patterns to Mirror
### NATIVE_HOST_RUN
// SOURCE: tests/kernel/identity_test.c + run_identity_test.sh (live CPUID on x86 hosts, SKIP elsewhere, and CI asserts no SKIP on x86)
### FINDING_SINK
// SOURCE: agent/tools/disclosure.py:85 `record(...)`: private, embargo-clocked.
### TEST_OK
// SOURCE: tests/kernel/mm_test.c:30-38

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/hardware/vendors.yaml` | UPDATE | inventory SoftFloat/TestFloat 3e (jhauser), with licence |
| `scripts/fetch-softfloat.sh` | CREATE | pinned fetch into `.cache/third_party/` |
| `agent/kernel_spec/conformance/README.md` | CREATE | the test-record format: `id`, `clause` (SDM/IEEE citation), `class` (semantic/fault), `guarantee` (architectural/model-specific), `oracle` |
| `agent/kernel_spec/conformance/{fp-div,fp-sqrt,fp-rounding,ud-guaranteed,gp-guaranteed}.yaml` | CREATE | the corpora, each entry clause-cited |
| `tests/conformance/gen_oracle.c` | CREATE | host: operands → SoftFloat results → `oracle_*.bin` (never computed by the hardware under test) |
| `tests/conformance/native_semantic.c` | CREATE | venue 1: execute x87/SSE2 on this CPU, compare bit-for-bit with the oracle, print divergences with clause ids |
| `tests/conformance/native_fault.c` | CREATE | venue 1: execute guaranteed-#UD encodings under `SIGILL` capture (Linux); record fault/no-fault |
| `tests/conformance/run_conformance.sh` | CREATE | build oracle, run both, emit `verdicts.json`; SKIP on non-x86 naming why |
| `agent/tools/conformance.py` | CREATE | `verdicts.json` → the summary; `--disclose` routes unexplained divergences to `disclosure.record` |
| `agent/kernel_spec/arch/x86_64.md` | UPDATE | REQUIRED: per-vector exception entry that passes the vector and a recoverable-context hook (`arch_expect_fault(vector, resume_rip)`) |
| `tests/kernel/fault_harness_test.c` + reference | CREATE | host test of the in-kernel harness's state machine (expect → fault → resume → verdict) |
| `.github/workflows/portability.yml` | UPDATE | run `run_conformance.sh` on x86 Linux and assert it did not SKIP |

## NOT Building
- Transient-execution/side-channel research (out of scope per the Decisions Log).
- The in-kernel suite's generation into every image (H10c, `w15-hardware-conformance-every-image`).
- A model as oracle, ever.

## Step-by-Step Tasks
### Task 1: The record format and first corpus
- **ACTION**: `conformance/README.md` + `fp-div.yaml`, including the FDIV operands and TestFloat-generated div corner cases (subnormals, boundaries, each rounding mode), each citing IEEE 754-2019 §5.4.1 / SDM `DIVSD`/`FDIV`.
- **VALIDATE**: a schema test in `agent/tests/unit/test_conformance_format.py` (every entry has a clause, a class and a guarantee).

### Task 2: The oracle, generated on the host
- **GOTCHA**: The oracle is built with SoftFloat compiled with `-O0 -ffp-contract=off`, and it must not call host FP. A "SoftFloat" that uses the host FPU is the hardware judging itself.
- **VALIDATE**: `f64_div(4195835, 3145727)` equals the known correct quotient bits.

### Task 3: Venue 1, native semantic (RED → GREEN on this Mac as SKIP, on CI as PASS)
- **IMPLEMENT**: SSE2 `divsd`/`sqrtsd` and x87 `fdiv` at 80-bit, with inline asm so the compiler cannot constant-fold, MXCSR/FPU CW set per rounding mode, and results compared by bit pattern.
- **GOTCHA**: The compiler will constant-fold `a/b` with literal operands. Read operands from the corpus file at runtime and use `volatile` asm.
- **VALIDATE**: CI x86: 0 divergences on a modern part (the expected result, reported as "checked, found nothing").

### Task 4: Venue 1, native fault
- **IMPLEMENT**: `UD2`, `UD0`/`UD1` forms the SDM guarantees, and a `LOCK` prefix on an instruction where #UD is architected (e.g. `LOCK NOP`). Capture `SIGILL` with `sigsetjmp`.
- **VALIDATE**: every guaranteed encoding faults on CI; a deliberately non-guaranteed control is reported as "not assertable", never as a failure.

### Task 5: The in-kernel harness spec + host proof
- **ACTION**: REQUIRED text in `x86_64.md`: vector-numbered stubs; `arch_expect_fault(vec, resume)`; an unexpected fault still halts with `[CPU] exception <vec> at <rip>`.
- **VALIDATE**: `fault_harness_test.c --self-test` PASS; generated into a tree later (H10c).

### Task 6: Verdicts, and zero as a finding
- **ACTION**: `conformance.py` summarises: per clause pass/diverge/not-assertable; an unexplained divergence → `disclosure.record(...)` behind `--disclose`; a clean run prints "0 divergences across N clause-cited checks on <silicon identity>". The PRD requires reporting zero as a finding.
- **VALIDATE**: a unit test with a synthetic divergence reaches `disclosure.record` with the clause as the spec citation.

## Validation Commands
```bash
scripts/fetch-softfloat.sh
tests/conformance/run_conformance.sh            # SKIP on arm64 Mac, naming why
.venv/bin/python agent/tools/conformance.py tests/conformance/out/verdicts.json
tests/kernel/run_fault_harness_test.sh --self-test
cd agent && ../.venv/bin/python -m pytest tests/unit/test_conformance_format.py -q
```

## Acceptance Criteria
- [ ] Every test cites a clause; every verdict names the silicon (H5 identity)
- [ ] The oracle never uses the hardware under test
- [ ] CI x86 runs both native suites and does not SKIP
- [ ] Zero divergences reported as a finding, with N and the identity
- [ ] The in-kernel harness is specified and host-proved

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| A false finding sent to a vendor | M | H | guaranteed-only assertions; `--disclose` is explicit; the embargo pipeline is private |
| The CI runner's virtualisation masks behaviour | M | M | stated in verdicts ("virtualised, microcode unknown"), per CONFORMANCE-HARDWARE.md |
| Compiler folding hides the silicon | H | H | runtime operands plus volatile asm (Task 3's gotcha) |


---

## Progress: Tasks 1-6 host-side (2026-09-22)

Oracle pinned and self-tested, 28 clause-cited entries, both venues, `conformance.py` verdicts + disclosure, fault-harness spec and its 15-check host proof, CI wired. **Remaining**: the native venues have run only under Rosetta (labelled as a translator); the x86 CI job asserts they do not SKIP, and has never run — the branch is unpushed.


---

## Closed 2026-09-23

Oracle, corpora, both venues, verdicts, disclosure, the fault-harness spec and its 15-check proof, and CI wiring are done. The x86 venues have run only under Rosetta; the CI job that asserts they do not SKIP needs the push.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
