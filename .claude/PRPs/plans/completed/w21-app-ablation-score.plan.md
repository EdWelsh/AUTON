# Plan: A9 — The ablation score: every required capability proved load-bearing, or the manifest over-claimed

## Summary
Three things can be wrong with a derived environment. Under-claim is caught by the probe (A10).
Leakage is caught by `gate_leakage` for kernels and by A8's inventory for containers.
**Over-claim** — requiring something the application never needs — is caught by nothing: the
image works, passes, and is not minimal. This phase is the only check on it. For each capability
in the manifest, rebuild without it and re-probe: the probe **must fail**. The result is reported
as `N of N` next to the image, the way injected-bug scores sit next to a suite. It is owned by the
Tester role, and the PRD's metric "over-claims caught: reported, not zero" is the point. A
minimiser that has never reported an over-claim is not evidence that it never over-claims.

## User Story
As the owner, I want every capability in a "minimal" environment to have been removed once and
shown to break the application, so that "minimum" is a measured claim.

## Problem → Solution
Over-claim is invisible → `ablate.py` loops `requires` × (A8 rebuild without it → A10 probe),
records `load-bearing` / `over-claimed` / `unprobeable` per capability, writes
`ABLATION.json`, and the Tester task's acceptance criterion is that file with no `unprobeable`
entries left unexplained.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A9 (answers Open Question 1, "is ablation affordable?", with a measurement)
- **Estimated Files**: 6
- **Depends on**: A8 (rebuild), A10 (probe)

---

## Semantics, per capability kind
| Kind | "Without it" means | Notes |
|---|---|---|
| `lib:` | the recipe omits the package providing it, or the file is deleted in a final layer | a lib the base image ships cannot be omitted by recipe; deletion layer is used and recorded |
| `path:` | the path is removed in a final layer | |
| `exec:` | the binary is removed | |
| `listen:` | the port is not published | the probe must then fail to connect — this proves the probe checks that port, not that the app needs it; recorded as `probe-coverage` |
| `runtime:` | not ablated | removing the interpreter proves nothing interesting; recorded `skipped: runtime` |
| kernel capabilities (`auton` substrate) | `excludes` gains it → `build_service` | a slice refusal is recorded as `load-bearing (by slice)`, no boot needed |

**Outcomes**: probe fails → `load-bearing`. Probe passes → `over-claimed` (the manifest is edited
by nobody; the result is reported). Build fails for an unrelated reason → `unprobeable` with the
build error, which counts against `N of N`.

## Mandatory Reading

| Priority | File | Why |
|---|---|---|
| P0 | `agent/tools/package_gate.py` (A8), `agent/tools/app_probe.py` (A10) | the two operations looped over |
| P0 | `agent/tools/build_service.py:232-300`, `:439` | kernel-side leakage call, for the `auton` substrate path |
| P1 | `docs/OPEN-WORK.md` §"What done already means" | how injected-bug scores are reported; `ABLATION.json` is reported the same way |
| P1 | `agent/orchestrator/agents/tester_agent.py`, `llm/tools.py:532-545` | Tester tools; add `run_ablation` |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/tools/ablate.py` | CREATE | the loop; `--sample K` for large manifests, reported as `sampled K of N` — never as `N of N` |
| `agent/tools/ablate_recipe.py` | CREATE | recipe transforms per kind (pure functions over the Dockerfile) |
| `agent/orchestrator/llm/tools.py`, `tester_agent.py` | UPDATE | `run_ablation` tool for the Tester |
| `agent/tests/unit/test_ablate_recipe.py` | CREATE | each transform |
| `agent/tests/unit/test_ablate.py` | CREATE | outcomes with faked build/probe |
| `agent/tests/integration/test_ablate_fixtures.py` | CREATE | the gate below (skips without docker) |

## NOT Building
- Automatic manifest trimming. An over-claim is reported; removing it is a reviewed change, because the probe's coverage is partial and a "not needed" can be "not exercised".
- Pairwise ablation. Two capabilities that substitute for each other each look like over-claims alone; that is noted in the report as a known limit, not solved.

---

## Step-by-Step Tasks

### Task 1: Transforms and outcomes (RED → GREEN)
- **ACTION**: unit tests for each kind's transform and for outcome classification with faked build/probe results.

### Task 2: Seeded over-claim fixture — the gate
- **ACTION**: `flask-hello` manifest plus one deliberately unneeded fact (`lib:libxml2.so.2`). `ablate.py` must report `load-bearing` for flask's needs and **`over-claimed` for libxml2**. A run that reports `N of N load-bearing` on this fixture fails the phase, because it proves the score cannot see over-claim.

### Task 3: Seeded under-probe fixture
- **ACTION**: a fixture whose probe never touches its database path: ablating `lib:libpq.so.5` passes the probe → reported `over-claimed` **with** a note that probe coverage is the likelier cause. Proves the report distinguishes "not needed" from "not exercised" only as honestly as the probe allows, and says so.

### Task 4: Cost measurement (Open Question 1)
- **ACTION**: record wall-clock per step and total for both fixtures, with and without layer cache; write into the report. `--sample` exists but is not used for the gate.

### Task 5: Tester wiring
- **ACTION**: `run_ablation` tool; Tester's task acceptance is `ABLATION.json` present and every `unprobeable` explained.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_ablate_recipe.py tests/unit/test_ablate.py -q
cd agent && ../.venv/bin/python -m pytest tests/integration/test_ablate_fixtures.py -q
.venv/bin/python agent/tools/ablate.py --package agent/tests/fixtures/apps/flask-hello/package
```

## Acceptance Criteria
- [ ] The seeded over-claim is reported as over-claimed.
- [ ] `ABLATION.json` sits beside the package, with `N of N` or the exact shortfall.
- [ ] Cost per ablation step is measured and reported.
- [ ] Sampling, when used, is never reported as a full score.

## Risks
| Risk | Mitigation |
|---|---|
| Thirty capabilities = thirty builds | final-layer deletion keeps rebuilds to one cached layer; measured in Task 4 |
| Base-image libs cannot be ablated by recipe | deletion layer; the report says which method was used per capability |
