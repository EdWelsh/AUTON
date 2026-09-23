# Plan: Orchestrator Scheduler Dispatch

**Source PRD**: `.claude/PRPs/prds/README.md` — Wave 0. Deliberately not in any PRD phase
table: it is one diagnostic, and it gates every generation phase in every PRD.
**Complexity**: Small to write, **unknown to diagnose** — the root cause is not yet isolated.

## Summary

The agent loop reaches a terminal phase, decomposes a goal into tasks, and then assigns none.
`Scheduler.get_assignments()` returns empty on every iteration while `get_ready_tasks()`
returns a task and an idle `developer` agent is registered. Nine iterations produce an
identical progress line and the run ends "Orchestration failed: unknown" with no kernel diff.

Until this dispatches, AUTON's premise — `README.md:11`, *"We don't write the kernel. The
agents do."* — cannot be exercised at all.

## Evidence

- `scripts/orchestrate-native.sh` run, 9 iterations, `grep -c "Assigned "` → **0**.
- Engine logs `No tasks schedulable and no agents busy` (`engine.py:311`) but does **not**
  break, so `task_graph.get_ready_tasks()` is non-empty at that moment.
- Agents registered: developer, reviewer, tester, integrator (from the run log).
- `base_agent.py:92` — agents initialise `AgentState.IDLE`, which
  `get_available_agent` (`scheduler.py:49-53`) accepts.
- Reproduced in isolation: loading the persisted tasks through `TaskGraph.add_task` yields
  `net-001 assigned_to='developer' state=READY`. The graph is correct outside the engine.
- Tool-calling measured at **8/8** against the real `DEVELOPER_TOOLS` set. The models work.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Assignment loop | `scheduler.py:56-77` | `for task in ready: slot = get_available_agent(task.assigned_to)` then mark busy |
| Availability test | `scheduler.py:49-53` | `not slot.busy and slot.agent.state in (IDLE, DONE)` — three conditions, any of which can silently fail |
| Agent pool keying | `scheduler.py:34-40` | `_agents: dict[str, list[AgentSlot]]` pre-seeded with role names |
| Role default | `task_graph.py:59` | `task.get("assigned_to") or "developer"` — fixed this session; the `.get` default never fired on an explicit `None` |
| Logging style | `scheduler.py:72-75` | `logger.info("Assigned %s to %s (%s)", ...)` — the line that never printed |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/orchestrator/core/scheduler.py` | UPDATE | Instrument `get_assignments`, then fix per the finding |
| `agent/orchestrator/core/engine.py` | UPDATE (maybe) | `engine.py:306-313` may be consuming assignments before they are used |
| `agent/tests/unit/orchestrator/test_scheduler.py` | CREATE/UPDATE | A dispatch test that fails today |

## Tasks

### Task 1: Instrument, do not guess
- **Action**: One log line at the top of `get_assignments()` printing, at the moment of the
  call: the ready tasks with their `assigned_to`, the `_agents` dict keys, and for each slot
  its `busy` flag and `agent.state`. Two hypotheses remain and this separates them —
  **(a)** the role string does not match a pool key, **(b)** every slot is considered busy or
  in a non-IDLE state.
- **Why first**: three conditions gate availability and the failure is silent in all three.
  Changing code before knowing which is guessing.
- **Validate**: one `orchestrate-native.sh` run prints the state; the hypothesis is decided.

### Task 2: Fix the identified cause
- **If (a) role mismatch**: the manager emits a role the pool does not contain. Normalise at
  the boundary — `task_graph.add_task` is the single funnel — and make an unknown role a
  loud rejection rather than a silent non-match.
- **If (b) slots never available**: an agent is left `busy` or in `THINKING`/`ERROR` from a
  previous iteration without release. `scheduler.release_agent` is called in
  `engine.py:326` only inside the `if assignments:` branch, so a slot marked busy by a
  *failed* assignment path is never released — check that path specifically.
- **Mirror**: keep `get_assignments`'s shape; this is a correctness fix, not a redesign.
- **Validate**: `grep -c "Assigned " <log>` ≥ 1.

### Task 3: A test that would have caught it
- **Action**: Unit-test `get_assignments` directly: a graph with one READY task assigned to
  `developer`, one registered idle developer agent, assert exactly one assignment. Add the
  negative cases — unknown role, busy slot, non-IDLE state — each asserting zero assignments
  **and** a log line saying which condition blocked it.
- **Why**: the defect survived because zero assignments is indistinguishable from no work.
- **Validate**: the positive test fails on `HEAD~` and passes after Task 2.

### Task 4: Prove it end to end
- **Action**: `scripts/orchestrate-native.sh "<small goal>"` must reach a task actually
  executed by a developer agent — not merely assigned.
- **Gotcha from prior work**: `OrchestratorState.load_or_create` resumes stale state from
  `<workspace>/.auton/`, and silently ran a June goal while reporting the new one. Clear
  `.auton/` before each run, or fix the resume to refuse a goal mismatch.
- **Validate**: the run log shows a `[dev-01]` line, and the target tree has a diff.

## Validation

```bash
rm -rf <target>/.auton                       # stale state hijacks the goal
scripts/orchestrate-native.sh "add a comment above arp_input" --timeout 600
grep -c "Assigned " .artifacts/orchestrator/*.log     # expect >= 1
grep -E "\[dev-01\]" .artifacts/orchestrator/*.log    # expect the developer to have run
cd agent && python -m pytest tests/unit/orchestrator -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Root cause is in the engine, not the scheduler | **M** | Task 1 instruments the call site; if the state is correct there, the caller is consuming assignments |
| Fixing dispatch reveals the next blocker immediately | **H** | Expected. Task 4 requires an executed task, not just an assignment, so the next wall is found in the same run |
| Stale `.auton/` state masks the fix | **M** | Documented gotcha; clear it, and consider refusing a resumed goal that differs from the requested one |
| A generated kernel diff lands unreviewed | **M** | `kernels/` is gitignored, so nothing reaches the repo by accident. Human review before anything is committed |

## Acceptance
- [ ] The blocking condition is named from instrumentation, not inferred
- [ ] `get_assignments()` returns ≥1 assignment for a ready task with an idle agent of its role
- [ ] Unit tests cover the positive case and all three negative conditions
- [ ] A real run shows a developer agent executing, and produces a diff in the target tree
- [ ] An unknown role is a loud rejection, not a silent non-match
