# Plan: Orchestrator Lane (Stretch) — Phase 8

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 8 — Orchestrator lane (stretch)
**Complexity**: Large, and the lowest-confidence phase in the PRD — **cut without regret if Phase 1 lands weakly**

## Summary

Get the agent loop that writes the kernel running again, locally, and have it produce one
small real kernel change that passes the full E2E. Entirely dependent on local-model
tool-calling quality that Phase 1 may not be able to deliver.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Engine phases | `orchestrator/core/engine.py:239-404` | `planning → designing → developing → integrating → done`, with `error` as a terminal state |
| Task lifecycle | `engine.py:328-343` | `TaskGraph` states: FAILED / REVIEW / BLOCKED / APPROVED / MERGED |
| Agent roles | `orchestrator/agents/` | architect, developer, reviewer, tester, integrator, manager (+ SLM-side model_architect, training, data_scientist) |
| Validation gates | `orchestrator/validation/` | `BuildValidator`, `TestValidator`, `CompositionValidator` |
| Spec grounding | `base_agent.py:295-302` | Agents read `kernel_spec/subsystems/<name>.md` and `arch/<name>.md` as ground truth |
| Budget guard | `llm/client.py:69-80` | `CostTracker.check_budget()` raising `BudgetExceededError` |

## Files to Change

| File | Action | Why |
|---|---|---|
| `scripts/orchestrate-native.sh` | CREATE | Native equivalent of `docker compose run orchestrate` |
| `agent/config/auton.toml` | UPDATE | Task-scoped budget/turn caps for a local run |
| `.claude/PRPs/reports/e2e-orchestrator-lane.md` | CREATE | Outcome — including a negative one |

## Tasks

### Task 1: Native orchestrator run
- **Action**: Run the loop without Docker against the Phase 1 model, on a deliberately tiny
  goal (a comment fix or one small function), with tight step and budget caps.
- **Mirror**: the compose `orchestrate` service's shape — `auton run "<goal>"`.
- **Validate**: the loop reaches a terminal phase (`done` or `error`) rather than hanging.

### Task 2: Assess tool-calling honestly
- **Action**: Record how often the model emits well-formed tool calls versus prose. This
  number decides whether the phase continues.
- **Why**: `auton.toml`'s own comment already records that a reasoning model "burns the whole
  token budget thinking on long agent prompts and returns empty." Expect this to be the
  binding constraint.
- **Validate**: a recorded rate. **If it's poor, stop here and write the negative result** —
  that is a legitimate, useful outcome for a phase marked stretch.

### Task 3: One real kernel change
- **Action**: Give the loop a genuinely small, spec-grounded task; let architect → developer
  → reviewer → tester run; human-review every line before it lands.
- **Constraint**: **the human reviews before merge, always.** The agent loop writes; it does
  not commit unreviewed kernel code.
- **Validate**: a committed diff authored by the loop that passes `scripts/e2e.sh`.

### Task 4: Gate on the E2E spine
- **Action**: The loop's output must pass the Phase 2 spine — build, markers, transcript — not
  just its own internal validators.
- **Validate**: `scripts/e2e.sh` green on the loop's branch.

## Validation

```bash
scripts/orchestrate-native.sh "add a bounds comment to kernel/net/arp.c"
scripts/e2e.sh --skip-train             # the loop's change must pass the spine
git log --oneline -1                    # provenance recorded in the message
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Local model can't do reliable kernel-C tool-calling | **H** | Task 2 is an explicit stop-and-record point. A negative result is a valid deliverable |
| Loop burns hours producing nothing | **M** | Tight step/budget caps; `BudgetExceededError` already exists at `client.py:72` |
| Unreviewed generated code reaches the kernel | **M** | Human review before merge is non-negotiable; the spine gates on top |
| `_run_shell` uses `create_subprocess_shell` with interpolated tool arguments (`base_agent.py:320, 409-462`) | **H** | **Known security issue, out of scope here and belongs in the security PRD.** Until then, run this lane only against a local model on a trusted goal — never against untrusted spec or web content |
| Phase creeps from stretch into blocking | **M** | It depends on nothing downstream. Cut it and the PRD still completes |

## Acceptance
- [ ] Loop runs natively and reaches a terminal phase
- [ ] Tool-calling reliability measured and recorded
- [ ] Either a human-reviewed kernel change that passes the spine, **or** a written negative
      result explaining what blocked it
- [ ] No unreviewed generated code merged
