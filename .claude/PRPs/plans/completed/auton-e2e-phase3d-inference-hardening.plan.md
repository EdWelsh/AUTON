# Plan: Rung 3d — Inference Hardening

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 3d — Inference hardening
**Complexity**: Medium

## Summary

Make the neural backend degrade honestly instead of emitting nonsense: verify every fallback
path actually triggers, measure load time and the RAM floor, and guard degenerate output so
the OS says "I don't know" rather than producing garbage. Runs parallel with 3c.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Backend selection | `kernel/slm/slm.c` `slm_init` | Neural if RAM ≥128 MB *and* a loadable module, else rule engine — the existing honest-degradation shape |
| Fallback chaining | `kernel/slm/chat.c` | `sysinfo_answer` → `roles_dispatch` → `slm_process_text`; neural tried, rule engine falls back |
| Honest status | `kernel/slm/roles.c:20-40` | `CAP_WORKING` vs `CAP_ROADMAP` with a note explaining what's missing — the project's honesty convention |
| Result struct | `kernel/include/slm.h:22-28` | `slm_intent_result_t` with `response[2048]` — shared by both backends |
| Boot markers | `kernel_main.c` | `[SLM] Backend: <name>` — the observable signal for which path ran |

## Files to Change

| File | Action | Why |
|---|---|---|
| `kernel/slm/slm.c` | UPDATE | Backend-selection edge cases (corrupt/oversized/truncated module) |
| `kernel/slm/neural/neural_backend.c` | UPDATE | Degenerate-output detection; bail to the caller rather than emit garbage |
| `agent/kernel_spec/tests/acceptance_tests.py` | UPDATE | A marker set per fallback scenario |
| `.claude/PRPs/reports/e2e-rung3d-*.md` | CREATE | Load time, RAM floor, fallback matrix |

## Tasks

### Task 1: Enumerate and test every failure mode
- **Action**: Build the matrix and assert each: no module; truncated module; wrong magic;
  wrong version; module larger than RAM; RAM below the 128 MB threshold. Each must produce a
  stated fallback and a distinguishable serial marker.
- **Mirror**: `auton_format.py:86-88` already rejects bad magic/version host-side — the
  kernel needs the equivalent, failing loudly rather than parsing garbage.
- **Validate**: each scenario boots to a usable `auton>` on the rule engine, with a marker
  naming the reason.

### Task 2: Measure load time and RAM floor
- **Action**: Time module load → first token at several `-m` values; find the true minimum
  that still selects neural.
- **Validate**: numbers recorded in the report; the 128 MB threshold either confirmed or corrected.

### Task 3: Degenerate-output guard
- **Action**: Detect repetition loops, empty generations, and runaway length; on detection
  fall back to the rule engine rather than printing the output.
- **Constraint**: the guard must be cheap and freestanding — no allocation, no libc.
- **Mirror**: `roles.c`'s honesty convention — say what happened, don't paper over it.
- **Validate**: a deliberately degenerate model triggers fallback; a good model never does
  (no false positives against the 3a baseline).

### Task 4: Extend acceptance coverage
- **Action**: Add the fallback scenarios to `acceptance_tests.py` so the E2E spine asserts
  them on every run.
- **Validate**: `scripts/e2e.sh` exercises the fallback matrix, not just the happy path.

## Validation

```bash
make -C kernels/x86_64 iso && make -C kernels/x86_64 run          # no module -> rule engine
head -c 1000000 SLM/work/auton-slm.bin > /tmp/truncated.bin       # truncated module
make -C kernels/x86_64 iso-neural MODEL=/tmp/truncated.bin run-neural
qemu-system-x86_64 -cdrom build/auton-neural.iso -m 64M ...       # below the threshold
scripts/e2e.sh --rung 3a                                          # fallback matrix asserted
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Guard false-positives on legitimate short answers | **M** | Tune against the 3a baseline; a false fallback is a regression and must fail the eval |
| Corrupt-module handling faults instead of falling back | **M** | Bounds-check before every read; treat the module as untrusted input — it is |
| Fallback markers collide with existing ones | **L** | Distinct prefixes; the marker list is single-sourced after Phase 2 Task 1 |
| Hardening masks a real model regression | **M** | Report the fallback *rate* in the eval; a rising rate is a signal, not a success |

## Acceptance
- [ ] Every enumerated failure mode has a stated fallback and a distinct marker
- [ ] Load time and true RAM floor measured and recorded
- [ ] Degenerate-output guard triggers on bad output, never on the 3a baseline
- [ ] Fallback matrix asserted by the E2E spine
- [ ] No garbage answer reachable by any tested path
