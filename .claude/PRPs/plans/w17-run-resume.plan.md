# Plan: Run Resume — a cut-off run keeps its work and continues

## Summary
R1 ran for exactly `ORCH_TIMEOUT=18000` and was killed. One task of six was approved, and
`pmm.c` (13,982 bytes) was on disk and **never committed**. The next run would re-plan from
nothing, because `OrchestratorState` saves counters but not the task graph, and `engine.run()`
always starts at Phase 1. The R1 report calls wall-clock "the binding constraint". This plan
makes wall-clock a pause instead of a loss: a timeout commits pending work, the task graph is
persisted, and `--resume` continues from the last completed iteration.

## User Story
As the operator running the completion PRD's R phases on one Mac, I want a run that hits its
time budget to resume where it stopped, so that a 20-hour generation task can be run as four
5-hour sessions without re-planning, re-designing or losing uncommitted files.

## Problem → Solution
Timeout = SIGTERM → the process dies mid-task → uncommitted files are orphaned, the graph is
lost, the next run re-decomposes the goal (and may decompose it differently) →
SIGTERM/SIGINT commit pending work on each busy agent's branch, the graph is saved every
iteration, and `run --resume` reloads the graph, requeues IN_PROGRESS tasks as READY, and
skips planning and design.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-completion.prd.md`
- **PRD Phase**: enabling work for R1–R12 (Open Question 2 "how many turns is enough?" and 3 "is the faster model enough?")
- **Estimated Files**: 7

---

## UX Design
```
Before                                               After
$ ORCH_TIMEOUT=18000 orchestrate-native.sh "$GOAL"   $ ORCH_TIMEOUT=18000 orchestrate-native.sh "$GOAL"
ORCHESTRATOR: TIMEOUT after 18000s                   ORCHESTRATOR: PAUSED after 18000s — 1/6 merged,
  (pmm.c on disk, uncommitted, graph gone)             pmm-002 committed WIP on agent/dev-01/mm/pmm
                                                       resume: orchestrate-native.sh --resume
                                                     $ orchestrate-native.sh --resume
                                                     Resuming run 3f2a9c1e at iteration 41: skipping
                                                       planning and design; pmm-002 READY (WIP kept)
```

### Interaction Changes
| Touchpoint | Before | After | Notes |
|---|---|---|---|
| Timeout / Ctrl-C | process killed | handler commits WIP on each busy branch, saves graph, exits 75 (`EX_TEMPFAIL`) | `orchestrate-native.sh` sends SIGTERM first and escalates to SIGKILL only after a grace period |
| `.auton/state.json` | counters only | + `graph` (every `TaskNode`), + `design_adopted`, + `resume_count` | versioned with a `format` field |
| `run --resume` | n/a | refuses if no state, if the goal differs, or if the workspace HEAD moved since the save | each refusal names what differs |
| Pre-registration | one run = one session | one run = N sessions, and the report lists every session's wall-clock | protocol step 2 "run once" still holds: a resume is the same run |

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/orchestrator/core/engine.py` | 234-345 | `run()`: state created at `:242`, always plans (`:252`), designs (`:285`), then the dev loop |
| P0 | `agent/orchestrator/core/state.py` | 1-60 | `OrchestratorState` — says "crash recovery" and persists no graph |
| P0 | `agent/orchestrator/core/task_graph.py` | 11-60, 101-160 | `TaskState`, `TaskNode`, `requeue`, readiness |
| P0 | `scripts/orchestrate-native.sh` | 25-80 | `auton_timeout` → rc 124 → "TIMEOUT" |
| P1 | `agent/orchestrator/comms/git_workspace.py` | 319-347 | `commit_pending(branch, message)` — the engine already uses it so work is never orphaned by a checkout |
| P1 | `scripts/lib/toolchain.sh` | 87-120 | `auton_timeout` fallback; which signal it sends |
| P1 | `.claude/PRPs/reports/w15-mm-qwen-report.md` | all | the run this exists for |
| P2 | `agent/orchestrator/cli.py` | all | where `--resume` is added |

## External Documentation
No external research needed. `asyncio` `loop.add_signal_handler` is stdlib (POSIX only; see Risks).

---

## Patterns to Mirror

### ERROR_HANDLING (a refusal that names what differs)
// SOURCE: agent/orchestrator/comms/git_workspace.py:97-104
Refusals say what was refused and what to do instead: `refusing to overwrite 'x', which this
workspace has not read ... read_file('x') first`. `--resume` refusals do the same:
`refusing to resume: saved goal "…" differs from "…"; start a new run or pass the saved goal`.

### PERSISTENCE
// SOURCE: agent/orchestrator/core/state.py:32-50
`save()` writes JSON with `asdict`; `load()` rebuilds with `cls(**data)`. Extend, do not replace.
Add `format: int = 2`; `load()` of a format-1 file (no graph) refuses to resume and says why.

### TEST_STRUCTURE
// SOURCE: agent/tests/unit/orchestrator/test_scheduler_dispatch.py
A fake agent, a scripted client, the defect named in the docstring with the report that found it.

---

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/orchestrator/core/task_graph.py` | UPDATE | `to_dict()` / `from_dict()`; `TaskNode` round-trips including feedback and review round |
| `agent/orchestrator/core/state.py` | UPDATE | `graph`, `design_adopted`, `resume_count`, `head_at_save`, `format` |
| `agent/orchestrator/core/engine.py` | UPDATE | `run(goal, resume=False)`; save graph each iteration; skip phases 1–2 on resume; signal handler |
| `agent/orchestrator/cli.py` | UPDATE | `run --resume` |
| `scripts/orchestrate-native.sh` | UPDATE | `--resume`; SIGTERM then grace (`ORCH_GRACE`, default 120 s) then SIGKILL; exit 75 → "PAUSED" |
| `agent/tests/unit/orchestrator/test_run_resume.py` | CREATE | the tests below |
| `docs/GENERATION-QUEUE.md` | UPDATE | "Protocol" step 2: a resumed run is the same run; sessions are listed in the report |

## NOT Building
- Mid-LLM-call checkpointing. A task interrupted mid-conversation restarts that task's conversation; the files it wrote survive as a WIP commit, which is what was lost in R1.
- Automatic re-launch. The operator decides whether to resume, because a model or budget change between sessions is a different experiment and must be pre-registered as one.
- Windows signal handling (see Risks).

---

## Step-by-Step Tasks

### Task 1: Regression tests first (RED)
- **ACTION**: `test_run_resume.py` with: (a) graph round-trips through `state.json` byte-for-byte on the fields that matter; (b) a SIGTERM delivered while a fake developer has written an uncommitted file leaves that file committed on its branch; (c) `run(resume=True)` with a saved graph does **not** call `decompose_goal` or `design_subsystem`; (d) an IN_PROGRESS task is READY after resume and keeps its branch; (e) resume refuses on a different goal, on a moved HEAD, and on a format-1 state file.
- **VALIDATE**: `cd agent && ../.venv/bin/python -m pytest tests/unit/orchestrator/test_run_resume.py` fails for the stated reasons.

### Task 2: The graph persists
- **ACTION**: `TaskGraph.to_dict/from_dict`; `OrchestratorState.graph`; save inside the dev loop where `state.save` already runs (`engine.py:312`).
- **GOTCHA**: `from_dict` must re-run readiness so a MERGED dependency unblocks its dependants.

### Task 3: A signal pauses instead of killing
- **ACTION**: install SIGTERM/SIGINT handlers in `run()` that set a flag; the dev loop checks it between iterations *and* cancels in-flight `gather`; on cancel, for each busy slot call `commit_pending(branch, "WIP: paused at iteration N")`, save state, exit 75.
- **GOTCHA**: `commit_pending` must run after the agent coroutine is cancelled, not concurrently with a tool call writing the same file.

### Task 4: `--resume`
- **ACTION**: `run(resume=True)` loads state; validates goal, HEAD, format; requeues IN_PROGRESS → READY with feedback `{"resumed": true, "branch": …}` so the agent's prompt says the branch already holds its earlier work; increments `resume_count`; jumps to Phase 3.

### Task 5: The script says PAUSED, not TIMEOUT
- **ACTION**: send TERM at the budget, wait `ORCH_GRACE`, then KILL. rc 75 → `ORCHESTRATOR: PAUSED … resume: …`; rc 124 (killed after grace) stays `TIMEOUT` and says the WIP may be lost.

### Task 6: Proof on a real cut
- **ACTION**: scripted-model run with `ORCH_TIMEOUT=30` over a two-task goal; confirm PAUSED, a WIP commit, then `--resume` reaches MERGED on both without a second decomposition (count manager calls in the log).

## Testing Strategy
Unit tests above; one scripted-model end-to-end pause/resume. No live model needed.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/orchestrator -q
ORCH_TIMEOUT=30 ORCH_CONFIG=<scripted cfg> scripts/orchestrate-native.sh "<two-task goal>"; echo rc=$?
ORCH_CONFIG=<scripted cfg> scripts/orchestrate-native.sh --resume
```

## Acceptance Criteria
- [ ] A timed-out run exits 75 with every busy agent's files committed on its branch.
- [ ] `--resume` makes zero manager decomposition calls and zero architect design calls.
- [ ] Resume refuses a changed goal, a moved HEAD and a format-1 state, each with its reason.
- [ ] The whole orchestrator unit suite still passes.

## Risks
| Risk | Likelihood | Mitigation |
|---|---|---|
| `add_signal_handler` is POSIX-only | certain on Windows | fall back to `signal.signal` + flag; document that Windows gets pause-between-iterations only (same boundary as `SIGKILL is POSIX-only`, commit 7c8c018) |
| A WIP commit of half a file fails `syntax_gate` at review | high | expected: the resumed agent sees its branch and finishes; the gate is unchanged |
| Operators resume with a different model | medium | `state.json` records the model; resume refuses a model change unless `--new-session-model` is passed, and the report must list it |

## Notes
This does not change what a gate accepts. It changes how many hours a run may use before a gate is asked.
