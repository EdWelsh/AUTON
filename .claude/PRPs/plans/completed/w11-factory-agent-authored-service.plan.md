# Plan: Service #2, Agent-Authored (F6)

**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 6
**Depends on**: F4 (landed, the control), F5 (landed), w9 workspace safety (landed)
**This is the phase that tests `README.md:11`** — *"We don't write the kernel. The agents do."*

## Summary

Everything else in this repo is scaffolding for this experiment. F4 built a DHCP service by hand
and recorded what it cost. F5 built the pipeline and its gates. w9 fixed the thing that stopped
the loop being used. What has never happened is the loop drafting a service and someone measuring
what that cost instead.

**This plan specifies the experiment, not its result.** A plan that predicted the outcome would be
worthless; a plan that does not say precisely what is being measured, against what, and what counts
as failure is worse.

## Evidence

- `.claude/PRPs/reports/w3-factory-dhcp-service.md:120-127` — F4's cost, recorded explicitly *"for
  F6 to be compared against"*:

  | | |
  |---|---|
  | Spec | `services/dhcp.md`, 175 lines |
  | Implementation | `server.c` 320, `serve.c` 52, `dhcp.h` 60 |
  | Tests | `dhcp_test.c` 200 lines, 24 cases |
  | Defects caught by tests | 1 spec-conformance gap |
  | Defects caught by building | 1 spec bug |
  | Defects caught in tooling | 5 |
  | Not caught by anything | the client exchange — no test covers the QEMU network path |

- `agent/orchestrator/core/engine.py:225` `run(goal)` — the entry point, and `cli.py:71` the
  command. The loop runs until tasks complete, the budget is exhausted, or max iterations hit.
- `agent/orchestrator/core/scheduler.py:80` `get_assignments()` — the function wave 0 fixed. If
  it returns empty with a ready task and an idle agent, the run is over before it starts.
- `agent/orchestrator/comms/git_workspace.py` (w9) — `_resolve`, `_resolve_for_write`,
  `edit_file`. The architect can no longer overwrite a header it has not read, which is why this
  is attemptable at all.
- `agent/tools/build_service.py` — five gates the output must pass: spec, capabilities, drivers,
  link closure, leakage. **The agent does not get to choose whether it passes them.**
- `agent/kernel_spec/services/README.md` — the format the agent writes into, and rule 5: *"A spec
  must resolve."*

## Patterns to Mirror

- **Measure against a recorded control**: V6 did this against V5 and published the ratio
  including the unflattering parts.
- **The gates are the referee**: `build_service.py`'s existing gates decide pass/fail, not a
  judgement about whether the code "looks right".
- **Report what was not caught**: F4's cost table has a row for *"not caught by anything"*. That
  row is the most useful one in it.

## Tasks

### Task 1: Choose the service, and say why before running
- **Action**: Name the service F6 attempts, and record the choice and its reasoning **before** the
  run. Candidate: a second UDP service close enough to DHCP that the comparison is meaningful and
  different enough that the agent cannot copy it.
- **Why before**: choosing after seeing what the loop produced makes the measurement worthless.
- **Gotcha**: do not pick a service needing a capability with no source mapping — `gate_capabilities`
  will refuse and the experiment measures the gate rather than the agent.
- **Validate**: the chosen service's capabilities are all mapped; the choice is written down with
  a timestamp before any run.

### Task 2: A cost harness, so the comparison is not anecdote
- **Action**: `scripts/measure_authorship.sh` — for a given service, emit the same rows F4's table
  has: spec lines, implementation lines, test lines and cases, gates passed, defects found by
  each mechanism.
- **Why a harness and not hand-counting**: F4's numbers were counted by hand once. A second hand
  count is not comparable, and a third would not be either.
- **Gotcha**: it must be able to produce F4's row **from F4's own artifacts** and match the
  recorded numbers. A harness that cannot reproduce the control's figures is measuring something
  else.
- **Validate**: run against `services/dhcp.md` and its tree; the output matches
  `w3-factory-dhcp-service.md:120-127` or the difference is explained.

### Task 3: Run the loop, once, and record everything
- **Action**: `auton run "<goal>"` against a clean workspace, with the transcript, the task graph
  and the diff kept.
- **Why once**: a best-of-N run measures the operator's patience, not the loop. If N runs are
  needed to get one that passes, **that is the result** and the report says so.
- **Gotcha**: the run costs API budget. Set and record the budget before starting; an exhausted
  budget mid-run is a data point, not a failed experiment.
- **Gotcha**: w9's `write_file` now refuses an unread overwrite. If the loop trips that
  repeatedly, that is a finding about agent behaviour and belongs in the report rather than being
  worked around by loosening the guard.
- **Validate**: the transcript, the resulting tree and the gate output are all kept, pass or fail.

### Task 4: Let the gates decide
- **Action**: Run `build_service.py` on the output. The five gates are the verdict.
- **Why**: "the code looks reasonable" is how F4's client exchange shipped untested. The gates are
  mechanical and were built for exactly this.
- **Gotcha**: a gate failure is **not** an experiment failure. *Which* gate, and whether the agent
  could have known, is the interesting part.
- **Validate**: each gate's result is recorded by name.

### Task 5: Report the comparison, whichever way it falls
- **Action**: F4's table beside F6's, with the ratio, plus what each mechanism caught and what
  nothing caught.
- **Why this framing**: the PRD's question is not "can an agent write a service" but "what does it
  cost compared with a human". Both answers are useful and only one is flattering.
- **Gotcha**: if the loop cannot produce a passing service, say so plainly and name the step it
  failed at. A negative result here is worth more than a positive one obtained by helping.
- **Validate**: the report carries both columns and states what was not caught by anything.

## Validation

```bash
scripts/measure_authorship.sh --service dhcp           # reproduces F4's control row
auton run "Build a <service> service against kernel_spec/services/<name>.md"
python agent/tools/build_service.py <name> --tree <workspace tree>
scripts/measure_authorship.sh --service <name>
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The loop produces nothing and the phase reads as "not attempted" | **M** | Task 3: the transcript is kept pass or fail, and a negative result is the result |
| The measurement is helped until it succeeds | **H** | Task 3's one-run rule; Task 1's choose-before-running rule |
| A gate refuses for a reason unrelated to the agent | **M** | Task 1's gotcha — every capability mapped before starting |
| The harness cannot reproduce F4's own numbers | **H** | Task 2's gotcha makes that the acceptance test for the harness itself |
| w9's guards are loosened to make the run succeed | **H** | Task 3's second gotcha: that is a finding, not an obstacle |
| Budget exhausts mid-run | **M** | Recorded up front; an exhausted budget is a data point |

## Acceptance
- [ ] The service is chosen and justified in writing before any run
- [ ] A harness reproduces F4's recorded cost row from F4's own artifacts
- [ ] One run, with transcript, task graph and diff kept regardless of outcome
- [ ] The five gates decide, and each result is recorded by name
- [ ] F4's and F6's cost tables published side by side with the ratio
- [ ] What nothing caught is stated, as F4's table does
