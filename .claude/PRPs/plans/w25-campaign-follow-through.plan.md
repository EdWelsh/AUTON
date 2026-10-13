# Plan: w25 — campaign follow-through (the unplanned remainder of both open PRDs)

**Written 2026-10-12.** Closes the planning of `auton-completion.prd.md` and
`auton-application-to-environment.prd.md`. Every PRD row already had a plan (w17–w24); this plan
covers what those plans left as **OPEN** or "deliberately no phase", so that nothing in either PRD is
without a written next step, a gate, and an owner. Executing it is separate from planning it.

**Source PRDs**: `prds/auton-completion.prd.md`, `prds/auton-application-to-environment.prd.md`.
**Evidence**: [`w24-campaign-failure-investigations`](./w24-campaign-failure-investigations.plan.md).
**Result so far**: campaign finished 2026-10-10, 1 of 12 passed (R8). Re-running a run is a changed
experiment and needs a pre-registration (stop rule).

## Part A — code items left OPEN in w24 (each: change, test, falsifier)

| # | From | Change | Test / gate | Falsified if |
|---|---|---|---|---|
| **DONE** A1 | F-1 | `agent/tests/unit/test_suite_interfaces_declared.py`: for every frozen suite, extract identifiers it takes from the interface header and assert each appears in its spec or the seeded header | Fails on a suite with an undeclared name (inject one) | A new suite ships and the identifier error returns in a gate-1 compile |
| **DONE** A2 | F-2 | Gate step greps `kernel/{mm,fs,net,services}/**` for `__asm__`/`asm(` and reports `file:line` as "inline assembly in portable code" | Fixture tree with one `cli; hlt` is reported by name | The failure is still a bare clang mnemonic error |
| **DONE** A3 | F-3 | Decide: driver suites build with an x86 target, or a host `io.h` shim stubs port I/O. Recommended: the shim (no cross toolchain dependency on the Mac) | The advisory VirtIO-block suite compiles on arm64; then promote it from advisory | It still fails on `inl` |
| **DONE** A4 | F-4 | Per-task git operations wrap `GitCommandError`: save state and return `paused` (resumable), not `error` | `test_merge_branch.py` gains a case where checkout fails once, then the run resumes | A workspace fault still ends a run at "Orchestration failed" |
| **DONE** A5 | F-5 | A timed-out task is retried once before failing; measure the 27b's tokens/s and 32k prefill from `ollama` timings and set the fallback `max_tokens` from that number | Report records the measurement; unit test for one retry | A task is failed on its first timeout |
| **DONE** A6 | F-8 | Decide whether `build/kernel-integration.bin` should exist (a kernel with the test harness) or the validator step be removed. Recommended: remove the step; the gates already decide a run | `test_composition_validator.py` has no integration-image path | The validator names a file nothing builds |
| **DONE** A7 | F-9 | `base_for` in `scripts/campaign.py`: a dependant does not start on a base whose main has no source for what it extends | Campaign refuses R2 on an R1 tree with no allocator source and says why | R2 starts on an empty tree |
| **DONE** A8 | F-10 | Record free memory with each memory-guard pause; the runbook says no Docker work alongside a campaign | A paused session's log carries the free-memory figure | Pauses stay unexplained |

**Status 2026-10-13:** A1 (`test_suite_interfaces_declared.py`), A2 (`tests/kernel/portable_asm_check.sh`, run by the mm and vmm gates, warns), A7 (already in `campaign.py: generated_something`, tested in `test_campaign_harness_stop.py`) done; pre-registration written: `reports/w25-campaign-attempt3-preregistration.md`.

A4 (`engine.py`: a `GitCommandError` pauses, resumable), A5 retry-once (`client.py`; the 27b tokens/s measurement still needs a loaded model, so it stays open), A8 (`generation_run.py`: free memory recorded at each pause) done 2026-10-13. A3 (shim: `tests/kernel/host_io_shim.h`, force-included by the virtio-blk tree build; the gate stays advisory until a generated driver has actually compiled through it) and A6 (integration step removed from `CompositionValidator`; the verdict is build + unit run) decided with the recommended defaults 2026-10-13.

Order: A1, A2, A7 first (they stop silent failures), then A4, A5, A8, then the decisions A3, A6.
A3 and A6 are design decisions: take the recommendation unless the owner says otherwise, and record it
in the commit.

## Part B — the next campaign attempt (pre-registered before it runs)

R1 is the critical path (F-9). Its last attempt (F-2c) was a model-capability result: the allocator and
VMM have real behavioural bugs, found only at the end because the gates became honest late.

1. Land Part A items A1, A2, A7.
2. Write `reports/w25-campaign-attempt3-preregistration.md` **before** any run: the change under test
   (the swarm can now see behaviour through `run_gate`; host env supplies the HAL), the gates, the
   stop rule (two attempts, then stop), and what would falsify the hypothesis that R1 fails for model
   capability and not harness.
3. Order: R1 → R2 → R3/R4/R5/R6/R7 → R9 → R10/R11/R12. A dependant runs only when its base run's gates
   are green. R8 stays passed.
4. After each run, read its gate log first and update the matching w24 section; a new failure is a
   finding, not a surprise (w24 F-11).

## Part C — scenarios and rows with no phase, and why

| Row | State | Next step |
|---|---|---|
| C1–C3 | reachable once R12, R6, R5 pass | graded by `run-intent-probe.sh`; no new work |
| C4, C5 (need TLS) | **no phase, deliberately** (completion PRD *What we are NOT building*) | A TLS phase is a new PRD, with the SSH crypto gate's rule: reuse or port, never synthesize. Not part of this plan |
| C6 (wifi) | needs real silicon plus a wifi driver | Out of scope; rides on X3 |
| D1, D2, D3 | owner | D3 (push the branch, about 60 commits) costs a minute and makes CI run; do it first |
| X1–X4 | owner / hardware | `docs/ACQUIRE.md`; Linux stand-ins rehearse but do not close these rows |
| C3 microVM substrate (application PRD) | done on a QEMU guest | real KVM is X-class, owner hardware |
| Application PRD live-model runs | A2 passed, A3 1 of 3 fully agent-driven (2 of 3 with 4 h budget) | A larger-model attempt is a changed experiment: pre-register it |

## Completion definition for the two PRDs

Planned: every row above has a plan, a gate, or a recorded reason it has none. **Not** done: 1 of 12
generation runs passed, and the owner/hardware rows are open. The PRDs move to `completed/` as
*planned*, with a banner saying so; this plan and `docs/OPEN-WORK.md` carry what is left.
