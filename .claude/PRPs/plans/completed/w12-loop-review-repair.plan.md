# Plan: Loop Review Repair: a task chain can complete

## Summary
Both w11 authorship runs (F6, V8) wrote zero lines. The model was never the reason: the loop
sent an empty diff to review, the reviewer invented code to reject, and rejection is terminal.
This plan fixes those four defects and widens `read_spec`, so the loop can complete a task chain.
The acceptance test is a scripted-model run that reaches `MERGED` for a two-task chain.

## User Story
As the AUTON operator, I want a goal's task chain to either complete or fail for a stated reason,
so that an authorship experiment measures the model and not the loop's plumbing.

## Problem → Solution
Read-only tasks go to review with `branch=main`; an empty diff is "reviewed"; `request_changes`
blocks forever; agents cannot read service/driver/mitigation specs →
empty diffs are not reviewable, rejections return to the author with feedback under a retry
bound, no-deliverable tasks complete without review, and `read_spec` reaches every spec kind.

## Metadata
- **Complexity**: Medium
- **Source PRD**: none. A cross-PRD blocker recorded in `prds/ELIGIBILITY.md` §1, a wave-0-class fix
- **PRD Phase**: blocks factory F6, driver V8, hardware-truth H7, and every generation phase
- **Estimated Files**: 8

---

## UX Design
Internal change. The visible difference is in the transcript:

```
Before                                        After
Iter 0 tftp-001 → review main..main           Iter 0 tftp-001 (no deliverable) → MERGED, no review
  → "malloc is incorrect" → BLOCKED           Iter 1 tftp-003 → dev branch → review diff (37 lines)
Iter 1 nothing ready → exit                     → request_changes → back to dev-01 with feedback (1/3)
                                              Iter 2 tftp-003 → revised → approve → MERGED
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Review of a task with no changes | reviewer hallucinates | skipped, logged `no changes to review` | a task with a deliverable and no diff FAILS instead |
| `request_changes` | terminal `BLOCKED` | back to `READY` with feedback, max `[orchestrator].max_review_rounds` (default 3) | then `FAILED` with the last review as the reason |
| `read_spec("services/tftp")` | "Specification not found" | the spec | also `drivers/<name>`, `mitigations/<name>` |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/orchestrator/core/engine.py` | 297-360, 419-455 | dev loop, result handling (`:343` review trigger), `_trigger_review`, the terminal BLOCKED at `:446` |
| P0 | `agent/orchestrator/agents/base_agent.py` | 95-140, 293-313, 454-459 | `execute_task` returns `branch=self._current_branch()` (`:133`); `_read_spec` |
| P0 | `agent/orchestrator/agents/reviewer_agent.py` | 41-105 | review prompt; the verdict parse |
| P0 | `agent/orchestrator/core/task_graph.py` | 11-19, 88-114 | `TaskState`; readiness only cascades on `MERGED` |
| P1 | `agent/orchestrator/agents/manager_agent.py` | 47-108 | the decomposition prompt that produced "Read Architecture Specification" tasks |
| P1 | `agent/orchestrator/comms/git_workspace.py` | 135-160, 262-266 | `create_branch`, `checkout_main`, `diff(branch)` |
| P1 | `agent/orchestrator/llm/tools.py` | 215-229 | `read_spec` schema; its description lists the subsystems |
| P2 | `agent/tests/unit/orchestrator/test_scheduler_dispatch.py` | 1-50 | the test style for a loop defect: a fake agent, the defect named in the docstring |
| P2 | `.artifacts/authorship/2026-09-21-{f6,v8}/transcript.plain.log` | all | the two failing runs, the evidence this fixes |

## External Documentation
No external research needed. The fix uses established internal patterns.

---

## Patterns to Mirror

### NAMING_CONVENTION
// SOURCE: agent/orchestrator/core/task_graph.py:11-19
```python
class TaskState(str, Enum):
    PENDING = "pending"
    READY = "ready"       # All dependencies met, can be scheduled
    ...
    BLOCKED = "blocked"
    FAILED = "failed"
```

### ERROR_HANDLING (a refusal that names itself)
// SOURCE: agent/orchestrator/core/scheduler.py (w0: an unsatisfiable role logs "no registered agents")
The loop's rule since w0: silence is the defect. Every new branch logs one line naming the task,
the reason, and the counter.

### LOGGING_PATTERN
// SOURCE: agent/orchestrator/core/engine.py:447-450
```python
logger.info(
    "Review requested changes for %s: %s",
    task_node.task_id, review_result.get("summary"),
)
```

### TEST_STRUCTURE
// SOURCE: agent/tests/unit/orchestrator/test_scheduler_dispatch.py:20-44
```python
class _FakeAgent:
    def __init__(self, agent_id: str, state: AgentState = AgentState.IDLE): ...

def _graph(role: str = "developer") -> TaskGraph:
    g = TaskGraph()
    g.add_task({"task_id": "t-1", "title": "do a thing", "assigned_to": role, "dependencies": []})
    return g
```

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/orchestrator/agents/base_agent.py` | UPDATE | `TaskResult.branch` is `None` unless the agent created a branch; `_read_spec` reaches `services/`, `drivers/`, `mitigations/` |
| `agent/orchestrator/core/engine.py` | UPDATE | no-branch → merge without review; empty diff → review skipped or task failed; `request_changes` → retry with feedback, bounded |
| `agent/orchestrator/core/task_graph.py` | UPDATE | `review_rounds` and `feedback` on `TaskNode`; `requeue(task_id, feedback)` |
| `agent/orchestrator/agents/manager_agent.py` | UPDATE | prompt: reading is part of a task, never a task; each task names a file it produces |
| `agent/orchestrator/agents/developer_agent.py` | UPDATE | include prior review feedback in the task prompt on a retry |
| `agent/orchestrator/llm/tools.py` | UPDATE | `read_spec` description lists the new kinds |
| `agent/tests/unit/orchestrator/test_review_path.py` | CREATE | the four defects as regression tests |
| `agent/tests/unit/orchestrator/test_loop_completes.py` | CREATE | a scripted-model engine run reaching MERGED |

## NOT Building
- Re-running F6 or V8. Those are separate plans (`w13-*-rerun`) and stay one-run experiments.
- Any change to what a reviewer checks for.
- Parallel review, or reviewer ensembles.
- Loosening w9's workspace guards.

---

## Step-by-Step Tasks

### Task 1: Regression tests first (RED)
- **ACTION**: Create `test_review_path.py`, one test per defect, each docstring quoting the w11 transcript line.
- **IMPLEMENT**: (a) an architect task returning success with no branch is MERGED without calling the reviewer; (b) a developer branch with an empty diff against main is not sent to review, and the task FAILS with `no output`; (c) `request_changes` sets the task READY with `feedback`, and after `max_review_rounds` it goes FAILED; (d) `_read_spec("services/dhcp")` returns `dhcp.md`.
- **MIRROR**: TEST_STRUCTURE. Use `AsyncMock` for `reviewer.review_branch` and assert `await_count == 0` for (a) and (b).
- **GOTCHA**: `update_state` only cascades readiness on MERGED (`task_graph.py:110`), so (a) must assert that dependents become READY. That dependents stayed PENDING is the real symptom in w11.
- **VALIDATE**: `pytest tests/unit/orchestrator/test_review_path.py` fails 4/4 for the stated reasons.

### Task 2: A branch means changes
- **ACTION**: `base_agent.execute_task` returns `branch=None` when the agent did not create one. Only `DeveloperAgent.implement_task` (`developer_agent.py:58`) creates branches.
- **IMPLEMENT**: Replace `branch=self._current_branch()` at `base_agent.py:133` with `branch=self._task_branch` (set by `create_branch`, cleared on `checkout_main`), defaulting to `None`.
- **GOTCHA**: The architect's `design_subsystem` *does* create branches (`agent/architect-01/arch-*`). Keep that, because those branches may carry headers. Then the empty-diff rule (Task 3) decides.
- **VALIDATE**: test (a) passes.

### Task 3: Empty diffs are not reviewable
- **ACTION**: In `engine.py` result handling (`:340-346`): no branch → `MERGED`. Branch with `workspace.diff(branch)` empty against main → `FAILED` with reason `no output`, logged by task id.
- **IMPLEMENT**: Put a `_has_changes(branch) -> bool` helper beside `_trigger_review`, using `git_workspace.diff`. Diff against main explicitly: `diff(f"{main}...{branch}")`.
- **GOTCHA**: `GitWorkspace.diff(branch)` diffs the working tree against `branch`, not main against branch. Call it as `main...branch`, or the result depends on what is checked out.
- **VALIDATE**: test (b) passes.

### Task 4: Rejection returns to the author
- **ACTION**: Replace `engine.py:445-450` with `task_graph.requeue(task_id, feedback=review)`, and fail after `max_review_rounds`.
- **IMPLEMENT**: `TaskNode.review_rounds: int = 0`, `TaskNode.feedback: list[dict]`. `requeue` increments the round count, appends the feedback and sets READY. `max_review_rounds` comes from `self.config["orchestrator"].get("max_review_rounds", 3)`, beside `max_iterations` (`engine.py:294`).
- **MIRROR**: LOGGING_PATTERN. Log `Review round %d/%d for %s: %s`.
- **GOTCHA**: The developer must *see* the feedback. `developer_agent.implement_task` builds the prompt from `task` data, so put `feedback` into `task_node.data` or it retries blind.
- **VALIDATE**: test (c) passes; `test_developer_agent.py` still passes.

### Task 5: The manager plans deliverables, not reading
- **ACTION**: Amend the prompt at `manager_agent.py:57-77`: *"Reading specs is part of every task, not a task. Each task must name at least one file it creates or changes in `produces`."* Tasks without `produces` are dropped at `_parse_tasks`, with a warning.
- **GOTCHA**: Dropping a task breaks the dependency lists of later tasks. Remap each dependency on a dropped task to that task's own dependencies, transitively.
- **VALIDATE**: a unit test feeding the w11 F6 task JSON (in `.artifacts/.../task-graph/`) yields 5 tasks, with `tftp-003` having no dependencies.

### Task 6: `read_spec` reaches every spec kind
- **ACTION**: `_read_spec` in `base_agent.py:293-313` accepts `services/<n>`, `drivers/<n>` and `mitigations/<n>`, resolving under `kernel_spec_path` and refusing `..`.
- **MIRROR**: w9's path containment (`git_workspace._resolve`).
- **VALIDATE**: test (d) passes, and a traversal attempt returns the refusal string.

### Task 7: A loop that completes
- **ACTION**: `test_loop_completes.py` builds an `OrchestrationEngine` whose `LLMClient.send_with_tools` is scripted. The manager returns 2 tasks; the developer writes a file via `write_file`; the reviewer returns `request_changes` once, then `approve`.
- **VALIDATE**: both tasks reach MERGED, with `review_rounds == 1` on the first. This is the test w11 lacked.

---

## Testing Strategy

| Test | Input | Expected | Edge? |
|---|---|---|---|
| no-branch success | architect result, branch None | MERGED, dependents READY, reviewer not called | |
| empty diff | dev branch == main | FAILED `no output`, reviewer not called | yes |
| rejection | request_changes ×1 | READY, feedback present | |
| rejection bound | request_changes ×3 | FAILED, last review in reason | yes |
| read_spec kinds | `services/dhcp`, `drivers/virtio-net`, `mitigations/f00f-idt-remap` | file text | |
| read_spec traversal | `services/../../config/auton` | refused | yes |
| manager drops readers | w11 F6 task JSON | 5 tasks, dependencies remapped | yes |

---

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/orchestrator tests/unit/agents -q
cd agent && ../.venv/bin/python -m pytest -q          # 1551+ passing, no regressions
.venv/bin/ruff check agent/orchestrator agent/tests/unit/orchestrator
```

### Manual Validation
- [ ] `scripts/orchestrate-native.sh "Add a comment to kernel/include/serial.h describing the port"` on gemma4 either merges or fails naming the reason, and does not end with `Orchestration failed: unknown`.

## Acceptance Criteria
- [ ] The four w11 defects have regression tests, and they pass
- [ ] A scripted engine run reaches MERGED through one rejection
- [ ] `read_spec` reaches services, drivers, mitigations, with containment
- [ ] No `Orchestration failed: unknown`: every terminal state names its cause

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Retry turns into a loop that burns iterations | M | M | bounded rounds; FAILED with the reason |
| The empty-diff rule fails legitimately empty tasks | M | L | Task 5 removes no-deliverable tasks upstream |
| gemma4 still cannot write TFTP | H | — | That is the F6 re-run's result to report, not this plan's to prevent |

## Notes
This is the scheduler-dispatch fix one layer up: small, and it changes the cost of everything
downstream. Nothing in w13+ that says "generated by the loop" is meaningful before it lands.
