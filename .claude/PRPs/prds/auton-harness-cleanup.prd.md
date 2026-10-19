# AUTON Kernel Harness Cleanup: What We Take From Harness²

**Status**: draft
**Created**: 2026-10-19
**Depends on**: nothing open. H1–H3 touch only the orchestrator and need no model run.
**Sources**: the Harness² paper (arXiv 2610.14224, Xu et al., Google Research, 2026) and
`google-research/harness2` (Apache-2.0, read at `main` on 2026-10-19). AUTON side:
`agent/orchestrator/`, `docs/CAMPAIGN.md`, `.claude/PRPs/plans/w24-campaign-failure-investigations.plan.md`.

## Problem Statement

The first full generation campaign passed 1 of 12 runs. The w24 investigation traced the other
eleven to causes in the **harness**, not the model: a frozen suite that used names the agent was
never shown (F-1), an engine verdict that could never pass, git faults that killed runs at
checkout, local timeouts, a role the manager could assign work to that nobody had registered
(w12), and a read-only role that called `write_file`. Each was found by reading logs after a
multi-hour run, and each was fixed as a one-off patch.

The harness is hard to reason about, which is why those faults stayed hidden:

- **A role is defined in five places.** Its prompt is a function in `llm/prompts.py`; its tool
  list is a constant in `llm/tools.py`; its construction, registration and advertisement are
  separate statements in `OrchestrationEngine._init_agents` (`core/engine.py:233`, about 180
  lines); the manager's description of it is a string passed to `advertise_role`; its checklist
  is in `kernel_spec/specialists.yaml`. Forgetting one produces a role that exists but never
  runs, with no error. That is the w12 empty-pool fault, and it is guarded today only by tests
  written after the fact.
- **Tools are defined twice and dispatched by name.** A tool's JSON schema is in `llm/tools.py`
  and its implementation is a `case` in `Agent._execute_tool` (30 cases, `agents/base_agent.py:241`).
  `_all_tool_names()` finds schemas by scanning `vars()` of the module for dicts. Adding a tool
  means editing both files and a role list, and nothing checks they agree.
- **Two files are over the 800-line limit** in the repository's own coding rules:
  `core/engine.py` (1,251 lines) and `agents/base_agent.py` (999 lines, which also holds the SLM
  and hardware tool bodies).
- **A run does not record which harness produced it.** `CLAUDE.md` and the campaign hold that "a
  changed harness is a changed experiment", but that is enforced by a person remembering to
  pre-register. `RESULT.json` records work seconds and limit waits, not a fingerprint of the
  prompts, tools and checklists in force.
- **Nothing learns from a failed attempt except a person.** w24 is a good document, but its
  lessons live in prose. The next attempt's agents do not see them unless someone edits a spec.

## What Harness² Is, and What It Is Not

Harness² treats the system around a fixed model as an editable thing and improves it in two
loops.

**Task level: Propose–Probe–Compose.** It runs the current harness once as a reference. It then
proposes two edited copies, one for weaknesses that recur across domains ("invariant": planning,
tool use, delegation) and one for the current domain's knowledge. It runs each copy on the same
task and builds a *behavioural contrast* against the reference. A composer reads the reference,
both candidates, their diffs and the evidence, and merges, revises, adopts one, or keeps the
original. It does this **without a ground-truth verifier**, which is the problem it was built for.

**Harnessing level: the experience library.** After each task a reflector keeps only lessons
the contrast supports, as a full harness tree plus an `EXPERIENCE.md` (cue, lesson, evidence).
Later tasks in the same domain read it on demand.

The harness is eight files-on-disk components: system prompt, guardrails, memory, skills, tool
guidance, scripts, subagents, and a middleware plugin. In the code, an edit may touch only paths
a `SurfaceSpec` allows (`core/tree.py`: `is_allowed`, size caps, name rules); a proposal states
only what it changes (omitted is inherited); an invalid proposal gets one retry and then
inherits the current harness; every stage is recorded in a ledger.

**Paper evidence (k=1, Gemini 3.5 Flash on OpenCode, its Table 3).** Removing the library cost
3.1 points on WorkBuddy and 1.8 on JobBench; removing scoping (the invariant/domain split), 2.9
and 3.7; removing composition, 1.6 and 1.9. Refining without reference runs, probes or the
library hurt more than refining with them (WB-Code 73.4 → 63.2). Gains grow with budget (k=1 to
k=5: roughly +3 to +4 more on WorkBuddy and JobBench).

**What it is not, for us.**

- Its benchmarks are professional documents (legal, office, web). None involves compiling code or
  booting a machine. We have no evidence it helps a kernel generation run.
- Its probes are noisy and, by the authors' own account, "inform composition but do not verify
  correctness". **We have a verifier it was designed to do without**: frozen gates with injected
  bugs. Using the gate as the judge is strictly stronger than its contrast, and it removes the
  main weakness the authors list.
- It runs OpenCode or Codex as the executor on Linux with Vertex credentials. We own the engine
  and run `claude -p` as a pure model on macOS. Its `claude_cli` channel is used only for its
  proposer and selector, not as an executor. Adopting it as a dependency means a bridge for no
  gain, and its executors run with network access unrestricted and (Codex) the sandbox off,
  against our per-role tool allowlists.
- Its cost is large. Its own docstring puts one step at four executor rollouts and three
  improvement stages per task. Our unit of budget is five-hour, usage-limited subscription
  sessions, and R1's first attempt closed one task of six in one.

So the decision is **to borrow its structure, not its code.** The parts worth taking are the
declarative harness surface, the ledger, the scoped experience library, and, last and gated, a
gate-judged version of the improvement loop.

## Goals

1. A role, a tool and a harness edit each have **one definition** that the engine, the tests and
   the docs all read.
2. A run's result states **which harness produced it**, so a changed harness is detected by a
   machine and not by memory.
3. `engine.py` and `base_agent.py` are each under 800 lines with no change in behaviour.
4. The campaign's lessons reach the next attempt's agents as evidence-backed entries, not as prose.
5. Whether a gate-judged improvement loop helps is **measured once, cheaply, before anything
   depends on it.**

## Non-Goals

- Depending on `harness2`, OpenCode or Codex, or running Vertex models.
- Changing the model (`claude-cli/claude-sonnet-5-5`), the gates, the frozen suites, the
  specs of record, or the SHELL_ALLOWLIST.
- Letting any loop edit tool *code*, gates, tests or specs of record. The editable surface is
  text the agents read (see H4).
- Re-running the campaign. A re-run is a changed experiment and needs its own pre-registration.
- Judging improvements without a gate. Where no gate exists, nothing is adopted.

## Phases

H1–H3 are cleanup: deterministic, no model spend, each independently shippable. H4–H5 need an
owner decision on spend (`CLAUDE.md`: model runs spend the owner's subscription).

### H1. One definition per role (data-driven roster)

Replace the five scattered definitions with one row per role.

- Add `agent/orchestrator/harness/roles.py` (or `roles.yaml` plus a loader). A row holds: role
  id, pool, class, prompt builder, tool list, count config key, `advertised` text or `None`,
  and the extras the engine currently sets by hand (`probe_path`, `manifest`, gates).
- `_init_agents` becomes a loop over rows. **Constructed, registered and advertised** become one
  operation, so a role cannot be one without the others. The advertised-but-empty and
  registered-but-unadvertised cases become unrepresentable, not merely tested.
- Keep `test_swarm_wiring.py`, `test_specialists.py`, `test_scheduler_dispatch.py` and
  `test_analyst_loop.py` passing unchanged. They are the regression net.

**Done when:** `_init_agents` is under 60 lines; every pool in the roster has at least one agent
and every advertised role has a registered pool, asserted by one parametrised test over the
rows; no existing wiring test is edited.

### H2. One definition per tool (registry)

- Add `harness/tools.py`: a `Tool` record of name, JSON schema, handler, and the roles that may
  hold it. A role's tool list is derived from it (`MANAGER_TOOLS` etc. become views).
- Split the `_execute_tool` match by family into handler modules (files, git, build/test, SLM,
  hardware), registered into the one table. `Agent._execute_tool` keeps the per-role check
  (refuse a tool the role was not given, and list the tools it has) and dispatches by table.
- `_all_tool_names()` reads the registry instead of scanning `vars()`.
- Deliver `base_agent.py` under 800 lines and `engine.py` under 800 (the phase machinery in
  `_run_phases`, pause/resume and result handling are the natural seams).

**Done when:** a test asserts every tool schema has a handler and every handler has a schema;
adding a tool is one entry; both files are under 800 lines; the full unit suite passes with
no test changes other than imports; rendered tool schemas for every role are byte-identical to
a golden snapshot taken before the change.

### H3. A harness fingerprint and a stage ledger

Borrowing the idea of Harness²'s `Ledger`/`Stage` records and its saved run configuration that
refuses incompatible resumes.

- Define the **harness surface** as: system prompts (all roles), tool schemas and descriptions,
  specialist checklists and knowledge (`kernel_spec/specialists.yaml`), the task-prompt template,
  and the role roster. Compute a stable hash over their rendered text, and a per-component
  manifest so a difference names what changed.
- Write `harness_fingerprint` and the manifest into every `RESULT.json` and the run state. On
  `--resume`, refuse a different fingerprint, as `_resume_refusal` already does for goal and model.
- `scripts/campaign.py` compares the fingerprint of a run with the one in its pre-registration
  and refuses to start on a mismatch, so "a changed harness is a changed experiment" is checked.
- Record per-task stage data in `RESULT.json`: attempts, work seconds, limit-wait seconds,
  review rounds, and whether a task fell back or was returned to its agent.

**Done when:** two runs from an unchanged tree produce identical fingerprints; editing one word
of one prompt changes it and the manifest names that component; a campaign start with a stale
pre-registered fingerprint exits non-zero with the differing components listed.

### H4. A declared editable surface (the guard for any loop)

Before any automated edit is possible, say what may be edited, as Harness² does with
`SurfaceSpec` and `is_allowed`.

- Add `agent/kernel_spec/harness_surface.yaml`: the allowed paths (role prompt text, tool
  *guidance* strings, specialist `focus`/`checklist`, the task template, experience entries),
  size caps, and the name rules. Everything else, including `tests/kernel/`, gate scripts, the
  SHELL_ALLOWLIST, `tools.py` code, `kernel_spec/` specs of record and `docs/campaign/runs.yaml`,
  is explicitly outside it.
- To make the surface editable by text, move the prompt bodies out of Python f-strings into
  files under `agent/orchestrator/harness/prompts/<role>.md` with `{arch}`-style slots. H1's
  rows point at them. Output is byte-identical to today's (golden test).
- A validator, `is_allowed(path)` and `validate(tree)`, reused by H5. It rejects path escapes,
  files off the surface, and oversize files, as `normalize_rel` and `is_allowed` do in Harness².

**Done when:** every role prompt renders identically from its file; the validator rejects a
write to a gate script, a suite, a spec of record and `../` escapes (one test each, run against
a deliberately broken input to confirm the test can fail).

### H5. Gate-judged improvement spike, then the experience library

Only after H1–H4, and only with the owner's go-ahead for the spend.

**H5a. Spike.** Adapt Propose–Probe–Compose with the gate as judge, on **one task that already
passes**: the TFTP server (w14), because a known pass makes an effect, or a regression, visible.

1. Reference: run the current harness on the task; record the gate result.
2. Propose an invariant candidate and a domain candidate (edits limited to the H4 surface; a
   proposal states only what it changes; an invalid one retries once, then inherits).
3. Probe: run each candidate on the same task and the same gate.
4. Compose: adopt a candidate only if its **gate score does not fall** against the reference
   and the contrast evidence supports the change. Otherwise keep the reference. No gate result,
   no adoption.

Pre-register before running: model, k=1, the surface, the task, the number of repeats, and the
decision rule. Because one run is noisy (the paper says so), the spike runs the reference **at
least three times** to measure its own variance, and a candidate must beat that spread to count.

**Decision after H5a:** proceed to H5b only if the spike shows a change larger than the
reference's own variance. If not, record the null result in `docs/OPEN-WORK.md` and stop. A
clean negative is an acceptable outcome of this PRD.

**H5b. Experience library.** Independent of H5a and cheaper, because it needs no new runs: turn
the w24 findings into entries in the Harness² shape (`cue`, `lesson`, `evidence`), one
directory per specialist domain, indexed, and read on demand by the matching specialist and
reviewer. An entry without evidence (a gate log line, a file and line) is rejected by the
validator, as `has_experience` does. Entries are written by a person or by an agent from a
failed attempt's logs, and are part of the harness fingerprint, so adding one is a visible,
pre-registered change.

**Done when (H5a):** a written report with the three reference scores, both candidates' scores,
the decision and its justification. **(H5b):** every confirmed w24 finding with a lasting
lesson has an entry; the validator rejects an entry with no evidence; the entries change the
fingerprint.

## Success Metrics

| Metric | Today | Target | How measured |
|---|---|---|---|
| Places a role is defined | 5 | 1 | grep for the role id across the harness |
| `_init_agents` length | about 180 lines | under 60 | `wc` of the function |
| `engine.py`, `base_agent.py` | 1,251 / 999 lines | each under 800 | `wc -l` |
| Wiring faults reachable (registered ≠ advertised ≠ constructed) | caught by tests after the fact | unrepresentable | the roster test |
| Runs that state their harness | 0 | 100% | `RESULT.json` has `harness_fingerprint` |
| Pre-registered harness mismatch detected at start | no | yes | stale-fingerprint test |
| Unit suite | passing | passing, no assertion edited | CI |
| H5a decision | none | recorded, positive or null | the report |

## Risks

| Risk | Mitigation |
|---|---|
| A refactor of the engine changes behaviour in a way the suites do not catch | Golden snapshots of rendered prompts, tool schemas and the roster before each phase; no test assertion edited; H1 and H2 land as separate commits so a revert is cheap |
| The fingerprint makes every harmless wording fix look like a changed experiment | That is the intent. The manifest names the component so the owner can judge; pre-registration notes the change |
| An improvement loop learns to weaken a gate | Gates, suites, specs of record and the allowlist are outside the surface (H4) and the validator is tested against exactly those paths |
| The loop overfits one task | The decision rule needs a gain beyond the reference's own measured variance; the library is scoped by domain, as in the paper |
| Spend | H1–H4 cost nothing. H5a is a handful of subscription sessions and does not start without the owner's confirmation |
| Gains in the paper do not transfer | The paper tested documents, not code. We treat its numbers as a reason to run the spike, not as a forecast |
| Prompt files drift from the code that fills their slots | A test renders every role with a sample `ArchProfile` and fails on an unfilled slot |

## Open Questions (owner decisions)

1. Is H5a worth a few sessions of subscription time now, or after the next campaign attempt?
2. Should the fingerprint also cover the specs the agents read (`kernel_spec/`), or only the
   harness proper? Covering them is more honest and makes every spec fix a new fingerprint.
3. Should H5b entries be written by an agent from failed-attempt logs, or only by a person?

## Order and Sizing

H1 → H2 (H2 depends on the roster) → H3 → H4 → H5a ∥ H5b. H1–H3 are the cleanup the request
asks for and are worth doing whether or not H5 ever runs. Each phase gets its own plan under
`.claude/PRPs/plans/` when it is picked up; none is written yet.

## Not Verified

Read: the Harness² README, setup and experiment guides, `core/spec.py`, `core/library.py`,
`core/tree.py`, `core/recursion.py` (the head of each) and the paper's pages as far as they were
retrievable; the final third of the paper's text, including its limitations appendix, was not
read. No Harness² code was run. The AUTON figures (line counts, 30 cases, 5 places) were counted
on `feat/prd-completion` at `3ba720d`.
