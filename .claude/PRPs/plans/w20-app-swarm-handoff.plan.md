# Plan: A7 — The swarm handoff: a manifest the target cannot satisfy becomes generation work

## Summary
A validated Manifest (A6) says what an application needs. Some of it the target already
supplies; some of it, on the `auton` substrate, is a kernel capability no tree implements yet.
This phase makes the second kind **work for the existing loop** rather than a dead end: the
Manager decomposes from the manifest, each unmapped kernel capability becomes a generation task
for the Architect/Developer loop that already runs, and the gate for that capability is the one
that already exists. No new gate is written in this phase. If a capability has no gate, the
handoff refuses and names it.

## User Story
As the owner, I want an application whose needs fall inside what the kernel *can* provide to
drive generation of whatever is missing, and one whose needs fall outside to be refused with
the reason.

## Problem → Solution
`engine.run(goal: str)` takes a sentence; nothing turns "these capabilities are unmapped in this
tree" into tasks → `manifest_goal.py` computes the unmapped set with the existing
`build_manifest.resolve()`, pairs each with its gate from a `capability_gates.yaml` table, and
emits a goal plus a **seed task list** the Manager must include; `orchestrator run --manifest`
feeds both in.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A7
- **Estimated Files**: 7
- **Depends on**: A6; `w17-run-resume` (generation runs exceed one session); the R-phase gates in `tests/kernel/` (already built)

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/tools/build_manifest.py` | 86-210 | `resolve()` and `unmapped_capabilities` — the existing answer to "what does this tree lack" |
| P0 | `agent/tools/build_service.py` | 170-230 | `[gate: capabilities]` refusal wording to mirror |
| P0 | `agent/kernel_spec/source_map.yaml` | 1-40 | "DO NOT fix by inventing mappings" |
| P0 | `agent/orchestrator/agents/manager_agent.py` | 27-60, 80-130 | `drop_undeliverable`, `decompose_goal` prompt |
| P0 | `agent/orchestrator/cli.py` | 90-130 | `run GOAL` |
| P1 | `docs/GENERATION-QUEUE.md` | the queue | each capability's gate command, which the table below encodes |
| P1 | `agent/kernel_spec/catalogue.yaml` | 1-25 | evidence-must-exist rule the gate table copies |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/capability_gates.yaml` | CREATE | kernel capability → gate command(s) in order, spec path. `mm` → `run_mm_test.sh`,`run_vmm_test.sh`; `virtio-blk`/`fat32` → storage gates; etc. Every command path must exist (test) |
| `agent/tools/manifest_goal.py` | CREATE | `plan(manifest, tree) -> Handoff(goal, seed_tasks, satisfied, refused)` |
| `agent/orchestrator/cli.py` | UPDATE | `run --manifest <json>` (mutually exclusive with GOAL) |
| `agent/orchestrator/agents/manager_agent.py` | UPDATE | `decompose_goal(goal, seed_tasks=())`: seeds are included verbatim and cannot be dropped; the prompt says the manager may add tasks around them, not replace them |
| `agent/tests/unit/test_manifest_goal.py` | CREATE | tests below |
| `agent/tests/unit/test_capability_gates.py` | CREATE | every gate path exists; every key is a real kernel capability |
| `agent/tests/unit/orchestrator/test_seed_tasks.py` | CREATE | a scripted manager that omits a seed still yields it in the graph |

## NOT Building
- New gates. A capability without an entry in `capability_gates.yaml` is refused: *"no gate exists for `ipc`; a generation task without a gate cannot be decided (completion PRD: every run is decided by a pre-registered gate)"*.
- Container-substrate generation. On `docker`/`kubernetes`/`server` nothing is unmapped by definition; the handoff is a no-op and A8 packages.

---

## Step-by-Step Tasks

### Task 1: Tests (RED)
- **ACTION**: (a) a manifest requiring `tcp` on the kernel-base tree where `mm` is unmapped → one seed task per unmapped capability, each carrying its gate commands in `acceptance_criteria`; (b) a capability with no gate → refused with the message above; (c) a fully mapped manifest → zero seeds, `satisfied` lists everything; (d) the manager cannot drop a seed.

### Task 2: Gate table
- **ACTION**: `capability_gates.yaml` built from `GENERATION-QUEUE.md`; the test asserts each command path exists under `tests/kernel/` or `scripts/`.

### Task 3: `manifest_goal.plan`
- **ACTION**: `build_manifest.resolve(tree, requires, excludes)` → `unmapped` → seeds `{task_id: "gen-<cap>", assigned_to: "developer", subsystem: <owner>, spec_reference: <spec>, produces: [<paths from the spec's source layout>], acceptance_criteria: [<gate commands>]}`.

### Task 4: CLI and seeds
- **ACTION**: `run --manifest`; the goal text lists satisfied capabilities as context and seeds as required work.

### Task 5: The gate
- **ACTION**: scripted-model run with a manifest whose only unmapped capability is one with a tiny fixture gate; the graph contains the seed, the loop merges it, and the listed gate command is the one the report cites. Then one live run is **not** required here: live generation is the campaign's job (`w18-generation-campaign`), and a manifest-driven R-run is added to it as an extra row once this lands.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_manifest_goal.py tests/unit/test_capability_gates.py tests/unit/orchestrator/test_seed_tasks.py -q
.venv/bin/python agent/tools/manifest_goal.py --manifest m.json --tree <ws>
```

## Acceptance Criteria
- [ ] An unmapped kernel capability yields a seed task whose acceptance criteria are its existing gate commands.
- [ ] A capability with no gate is refused, named.
- [ ] Seeds survive decomposition, by test.

## Risks
| Risk | Mitigation |
|---|---|
| `produces` for a seed is guessed | taken from the capability's spec (source layout section); if the spec has none, the seed is refused rather than guessed |
| The manager fights the seeds | seeds are inserted after parsing, not requested in the prompt only |
