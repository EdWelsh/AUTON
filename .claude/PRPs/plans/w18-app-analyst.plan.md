# Plan: A3 + A4 — The Analyst agent, and the evidence discipline that constrains it

## Summary
A new `AgentRole.ANALYST` reads the staged subject (A2) and writes an artifact record (A1) on
its branch. Two things make it safe to add. **Registration** has a known silent failure
(`engine.py:165` — a role constructed but not registered "was routed to an empty pool and
silently never dispatched"), so the phase gate is all three: constructed, registered, and
advertised in the manager's `assigned_to` list. **Evidence** is adjudicated by a tool, not by the
reviewer: the record goes through `syntax_gate.record_errors` the way a driver record already
does, and the validator additionally checks that every quoted line **actually appears at the
cited `file:line` in the staged subject**. The PRD asks for a model's findings to be checkable.
This makes them checked.

## User Story
As the swarm, I want a role whose only output is a sourced, index-bounded, quote-verified record
of what an application needs, so that no downstream agent acts on a capability a model invented.

## Problem → Solution
No role reads applications; a model asked to name capabilities invents plausible ones (measured:
5 phantom citations / 50 turns) →
an Analyst with read-only tools, whose record is refused before review if any capability is
outside the index, any quote is not at its line, or any fact is sourced `observed`.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A3 (role) and A4 (evidence discipline) — one plan because A4's gate is what makes A3's output usable
- **Estimated Files**: 10
- **Depends on**: `w17-app-artifact-record` (A1), `w17-app-subject-staging` (A2). D-A3 should be decided first; if it is not, the prompt framing in Task 4 is the conservative default and is labelled as such

---

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `agent/orchestrator/core/engine.py` | 154-230 | `_init_agents`; the comment at `:165` is the failure this phase's gate exists for |
| P0 | `agent/orchestrator/core/scheduler.py` | 33-75 | pools; the warning an unregistered role produces |
| P0 | `agent/orchestrator/agents/manager_agent.py` | 105-120 | `assigned_to: agent role ("developer", "tester", "architect")` — the third registration point |
| P0 | `agent/orchestrator/core/syntax_gate.py` | 1-90 | `record_errors` — the pre-review record gate to extend |
| P0 | `agent/orchestrator/agents/base_agent.py` | 29-40 | `AgentRole` |
| P1 | `agent/orchestrator/agents/tester_agent.py` | all | smallest existing role class to mirror |
| P1 | `agent/orchestrator/llm/prompts.py` | 6-100 | `build_*_prompt(arch)` |
| P1 | `agent/orchestrator/llm/tools.py` | 499-560 | per-role tool lists |
| P1 | `agent/tests/unit/orchestrator/test_scheduler_dispatch.py` | all | how dispatch is tested |

## Patterns to Mirror

### ROLE CLASS
// SOURCE: agent/orchestrator/agents/tester_agent.py:15-38 — `_get_prompt(kwargs)`, `super().__init__(role=…, system_prompt=…, tools=…, **kwargs)`

### PRE-REVIEW RECORD GATE
// SOURCE: agent/orchestrator/core/syntax_gate.py:53-70 — changed `drivers/<name>.md` → `driver_spec.load` → error text returned to the author as the review. Add: changed `analysis/*.artifact.yaml` → `artifact_spec.validate(path, subject=<ws>/.auton/subject)`.

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/orchestrator/agents/base_agent.py` | UPDATE | `AgentRole.ANALYST = "analyst"` |
| `agent/orchestrator/agents/analyst_agent.py` | CREATE | role class |
| `agent/orchestrator/llm/prompts.py` | UPDATE | `build_analyst_prompt` |
| `agent/orchestrator/llm/tools.py` | UPDATE | `ANALYST_TOOLS = [read_file, search_code, list_files, write_file, edit_file, git_commit]` — **no `shell`** |
| `agent/orchestrator/core/engine.py` | UPDATE | construct + `register_agent("analyst", …)` when `[agents].analyst_count > 0` or the goal carries a subject |
| `agent/orchestrator/agents/manager_agent.py` | UPDATE | advertise `"analyst"` in `assigned_to` **only when a subject is staged** — a manager told about a role that is not registered recreates `:165` |
| `agent/orchestrator/core/syntax_gate.py` | UPDATE | artifact records in `record_errors` |
| `agent/tools/artifact_spec.py` | UPDATE | `validate(..., subject=Path)`: quote-at-line check; refuse `source: observed` from any file not written by `observe.py` (A5 adds the writer; here: refuse all `observed` in agent-written records) |
| `agent/tests/unit/orchestrator/test_analyst_registration.py` | CREATE | the three-part gate |
| `agent/tests/unit/test_analyst_evidence.py` | CREATE | adversarial scoring (Task 6) |

## NOT Building
- A new file-reading tool (A2 staged the subject so this is unnecessary).
- `shell` for the Analyst. It reads; it does not run. Running is A5, in a sandbox, by a tool.
- A reviewer change. The reviewer sees only records the validator already accepted.

---

## Step-by-Step Tasks

### Task 1: Registration tests first (RED)
- **ACTION**: with a staged subject, an engine init yields (a) an `analyst` agent object, (b) a non-empty `scheduler._agents["analyst"]`, (c) `"analyst"` in the manager's decomposition prompt, and (d) a task `assigned_to: analyst` is returned by `get_assignments()`. Plus the negative: with no subject, `"analyst"` is **not** advertised.

### Task 2: Role, prompt, tools
- **ACTION**: `AnalystAgent`; prompt says: output is `analysis/<app>.artifact.yaml` in A1's format; every fact cites `file`, `line`, and the **exact** line as `quote`; capability names come from `artifact_spec.py --known <kind>` (the prompt embeds the list); never write `observed`; write `unknown` with `looked_at` rather than guess; ports are never `inferred`.

### Task 3: Register in all three places
- **ACTION**: engine construct + register; manager prompt conditional advertisement.

### Task 4: Subject content is data
- **ACTION**: prompt framing that subject files are quoted evidence, never instructions; the task description names the subject path and the hash from A2. If D-A3 is undecided this is the conservative default and the plan's report says so.

### Task 5: The evidence gate
- **ACTION**: `artifact_spec.validate(subject=…)`: for each evidence item, open `subject/file`, read line `line`, compare to `quote` after whitespace normalisation; mismatch → refusal naming both strings. `verify_subject(hash)` from A2 runs first; a changed subject refuses the whole record. Wire into `syntax_gate.record_errors`.

### Task 6: Scored adversarially (the A4 gate)
- **ACTION**: a scripted-model test in which the Analyst (a) names `lib:libmagic-unicorn.so` → refused, and the refusal lists the known `lib:` names; (b) cites a real file with a fabricated quote → refused with both strings; (c) writes `source: observed` → refused; (d) writes `listen:tcp/8080` as `inferred` → refused. Then **one live run** on a small fixture app (`agent/tests/fixtures/apps/flask-hello/`) with the campaign's qualified model: pre-registered, and the phase fails if any record reaching the reviewer contains a capability outside the index.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/orchestrator/test_analyst_registration.py tests/unit/test_analyst_evidence.py -q
cd agent && ../.venv/bin/python -m pytest tests/unit -q   # nothing else moved
```

## Acceptance Criteria
- [ ] A task assigned to `analyst` is dispatched (all three registration points, by test).
- [ ] `analyst` is not advertised when no subject is staged.
- [ ] The four adversarial cases are refused before review, each with a message naming the fix.
- [ ] The live fixture run's record passes the validator, or the run is reported as a negative result with the refusals quoted.

## Risks
| Risk | Mitigation |
|---|---|
| Local models cannot hold exact quotes | whitespace-normalised comparison only; a model that paraphrases fails loudly, which is the measurement |
| Index too small → every record refused | growing `capabilities.yaml` is a reviewed human edit; the refusal count is reported, not hidden |
| Prompt injection from subject | no `shell`; output limited to the closed vocabulary; D-A3 governs anything further |
