# Phase 8 — Orchestrator Lane: Negative Result

**Phase**: 8 — Orchestrator lane (stretch)
**Recorded**: 2026-09-12
**Outcome**: **The loop does not produce a kernel change.** Recorded as the plan's explicitly
permitted negative result — and the blocker is *not* the one the plan predicted.

## The prediction was wrong in an interesting way

The plan expected local-model tool-calling to be the binding constraint, citing `auton.toml`'s
own note that a reasoning model "burns the whole token budget thinking on long agent prompts
and returns empty."

Measured against the developer agent's real tool set (`DEVELOPER_TOOLS`), through the
orchestrator's own `LLMClient`, on eight realistic kernel tasks:

```
TOOL   Read kernel/net/arp.c and report what arp_input does.   -> read_file
TOOL   Add a bounds-check comment above arp_input …            -> search_code
TOOL   List the files under kernel/net/.                       -> list_files
TOOL   Search the codebase for the symbol e1000_init.          -> search_code
TOOL   Read the spec for the net subsystem.                    -> read_spec
TOOL   Write a one-line comment at the top of kernel/lib/kmath.c -> write_file
TOOL   Find where kprintf is defined.                          -> search_code
TOOL   Show me the contents of kernel/include/slm.h.           -> read_file

tool calls: 8/8 (100%)   prose: 0   errors: 0
```

**100%, with correct tool selection every time.** The Phase 1 model qualification paid off
here. The gate at Task 2 passes decisively, so the phase continued — and then failed for
entirely different reasons.

## What actually blocks it

The loop runs natively, reaches a terminal phase, and never hangs (Task 1 met). It decomposes
the goal into tasks. Then **no task is ever dispatched**: the developer, reviewer and tester
agents never execute. Nine iterations report an identical progress line, and the run ends
"Orchestration failed: unknown" with one task still `ready`.

Three defects, in the order they were found:

### 1. Stale run state silently hijacks a new goal

`OrchestratorState.load_or_create` resumes a previous run from `<workspace>/.auton/`. The
first runs of this lane were executing a goal from **15 June** — `state.json` held
`"Add an interactive chat console to the x86_64 kernel…"` while carrying the current run's
iteration count, and the task files on disk were three months old.

Nothing reports this. A new goal is accepted on the command line, printed in the banner, and
then quietly ignored in favour of the resumed one. `.auton/` had to be deleted by hand to get
a run against the goal actually requested.

### 2. `assigned_to` is `None`, so no task can match an agent

`TaskGraph.add_task` used `task.get("assigned_to", "developer")`. The manager emits the key
with a **null value** when the model omits a role, and `dict.get(key, default)` returns that
`None` rather than the default — the default only applies when the key is absent.

`Scheduler.get_assignments` then calls `get_available_agent(None)`, which matches nothing, so
the task sits `ready` forever. No error is raised; the loop simply spins until the iteration
cap with no work done.

**Fixed** in this commit (`or` instead of a `.get` default, applied to `subsystem`,
`assigned_to`, `priority` and `dependencies`). Verified: loading the persisted tasks now
yields `net-001 assigned_to='developer' state=READY`.

### 3. Still zero assignments after the fix — not isolated

With roles resolving correctly at the graph level, a clean run still logs **0 assignments**.
`get_ready_tasks()` returns a task, a `developer` agent is registered, and agents initialise
`IDLE` — the three conditions `get_available_agent` checks — yet `get_assignments()` returns
empty. The gap between the graph state I can reproduce in isolation and the engine's runtime
behaviour was not closed.

This is where the lane stopped. I did not want to keep changing engine internals on a stretch
phase to chase it.

## Delivered anyway

- **`scripts/orchestrate-native.sh`** — the loop without Docker, the native equivalent of
  `docker compose run orchestrate`. Sources the Phase 0 toolchain (the validators shell out to
  it), reports the model and iteration cap, forces plain output so the log is greppable, and
  distinguishes a timeout from a terminal phase.
- **`[orchestrator].max_iterations`** is now configurable (was hardcoded at 50). A local model
  that cannot dispatch will otherwise spend fifty iterations discovering that.
- **`python -m orchestrator.cli` now works.** It previously exited 0 having done nothing — the
  module imported, defined the click group, and returned, with no `__main__` guard. Silent
  success is the worst failure mode for an entry point.
- **The `.get`-vs-`None` fix** above, which is a real correctness bug regardless of whether it
  unblocks this lane.

## Acceptance

- [x] Loop runs natively and reaches a terminal phase
- [x] Tool-calling reliability measured and recorded — **100% (8/8)**
- [x] A written negative result explaining what blocked it
- [ ] A human-reviewed kernel change that passes the spine — **not achieved**
- [x] No unreviewed generated code merged — the loop produced no kernel diff at all, and the
      kernel tree is untouched

## If this is picked up again

Start at defect 3 with a debug log inside `Scheduler.get_assignments` printing the ready
tasks, their roles, and the agent pool keys at the moment of the call. That single line should
separate "the role string does not match a pool key" from "every slot is considered busy" —
the two remaining hypotheses.

The security note from the plan still stands and is untouched: `_run_shell` interpolates tool
arguments into `create_subprocess_shell`. This lane was run only against a local model on a
goal written by hand. It belongs in the security PRD before the loop is pointed at anything
untrusted.
