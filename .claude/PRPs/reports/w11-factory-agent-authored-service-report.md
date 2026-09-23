# Implementation Report: Service #2, Agent-Authored (F6)

## Summary

**The loop produced nothing, and it failed before the agent was tested.** One pre-registered
run on local gemma4 (8B, Q4_K_M) lasted **81 seconds and one iteration** and wrote **zero
lines**. It did not fail because gemma4 could not write TFTP. It failed because the loop never
asked it to: the first task was "read a spec", review rejected that task over code that did not
exist, and a rejection is terminal.

So `README.md:11` has still **not been tested**. What F6 did establish is why it cannot be yet,
down to three lines of the engine, and it built the harness a real test will need.

| | F4 (human, control) | F6 (agent) |
|---|---|---|
| Spec | 175 lines (F2's text) | 200 lines, **human-written** before the run, so not part of the agent's cost |
| Implementation | 401 lines (graph); hand count 372 | **0** |
| Tests | 255 lines, 24 cases | **0** |
| Gates passed | all five, then the boot | **none reached with agent output**. See *Gates* |
| Defects caught | 1 by tests, 1 by building, 5 in tooling | none. Nothing was produced to catch anything in |
| Not caught by anything | the client exchange under QEMU | **a reviewer approving or rejecting an empty diff**. No gate looks at the loop itself |

The ratio F6 was meant to publish is 0/401. It means nothing about authorship, because no
authorship happened.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Choose the service before running | Complete | `tftp` (RFC 1350 read-only), spec written and pre-registered at 17:28:38Z. See `w11-authorship-preregistration.md` |
| 2 | A cost harness that reproduces F4 | Complete, with published differences | `agent/tools/measure_authorship.py` + `scripts/measure_authorship.sh`. See below |
| 3 | Run the loop once | Complete | 17:29:30Z–17:30:51Z. Transcript, task graph and branch diffs in `.artifacts/authorship/2026-09-21-f6/` |
| 4 | Let the gates decide | Complete | nothing to gate; the base tree's own gate result recorded below |
| 5 | Report whichever way it falls | Complete | this file |

## What happened in the run

```
Planning   manager: 7 tasks
             tftp-001 "Read Architecture Specification"      subsystem: architecture
             tftp-002 "Read Relevant Subsystem Specifications" (dep 001)
             tftp-003..007 header, server.c, serve.c, test, runner (a chain)
Design     architect "designs" subsystems named architect, architecture, tftp
Iter 0     tftp-001 → architect → success on branch `main`
           reviewer: review `main` against `main` (an empty diff)
             → "implements basic TFTP client functionality … use of malloc is incorrect"
           → BLOCKED
Iter 1     no task ready (all six depend on 001), manager "assessment" suggests a retry
           that nothing acts on → loop exits
Final      build of the unchanged base tree: OK. "Orchestration failed: unknown"
```

## Why: three engine defects, each necessary for this outcome

| # | Where | What |
|---|---|---|
| 1 | `agent/orchestrator/agents/base_agent.py:133` | `TaskResult.branch = self._current_branch()`. For any non-developer agent that is `main`, so a task that wrote nothing still names a branch |
| 2 | `agent/orchestrator/core/engine.py:343`, `_trigger_review` (`:427`) | any result with a branch goes to review, and nothing checks for an empty diff. gemma4, asked to review nothing, invents code to reject. In V8 it invented `struct page` handling |
| 3 | `engine.py:446-447` | a non-approve is `TaskState.BLOCKED`, and the comment reads *"Send feedback to developer for fixes"*. Nothing sends it. BLOCKED is terminal, so one bad review halts a linear task chain |

A fourth made it certain: **the manager plans "read the spec" as tasks.** A task with no
deliverable can only be reviewed as nothing. It happened in both runs (F6: 2 of 7 tasks; V8:
2 of 7).

V8's run reproduced 1–3 exactly, with a different goal, workspace and subject. That makes it a
property of the loop, not of one run.

## The harness, and what re-counting the control found

`measure_authorship.py` counts the same way for every subject (`agent/tools/authorship.yaml`).
Acceptance for the harness was reproducing F4's recorded row from F4's own artifacts:

| F4 figure | Recorded | From artifacts | Why they differ |
|---|---|---|---|
| Spec lines | 175 | **175** ✓ | at F2's commit (`2b1b1f4`); it grew +5 (intent-C) and +4 (F4) afterwards |
| Test cases | 24 | **24** ✓ | |
| Test lines | 200 | **255** | at F4's own commit (`530f9c5`). **The recorded figure was wrong when written** |
| Implementation | 372 (320 + 52) | **401** (350 + 51) | the text is gone because `kernels/` was gitignored. The only surviving artifact is the structural graph at `9571384`, and it disagrees with the hand count |

The same exercise on V5 and V6 is in the V8 report. Of four controls, **none reproduces
completely**, and one (H6) never recorded a row at all. That is the case for a harness.

## Gates, and a setup error of mine that did not change the result

Run on the workspace after the loop, `build_service.py tftp` refused at
`[gate: link closure] no stub signature for: dhcp_run`. **That refusal was mine, not the
agent's:** I seeded the workspace from the tag `kernel-reference-v1`. F4's own static-IP branch
in `setup.c` and weak `service_main` in `kernel_main.c` (+31 lines) were committed after that
tag. The right base is the last tracked tree, `5fb2777^`. On that base an empty TFTP attempt
fails only at `undefined: tftp_serve`, which is the agent's job.

It did not affect the outcome: the loop died in iteration 1 without writing a file or reaching
a build. I did **not** re-run. The one-run rule exists so the operator's judgement does not pick
the result, and a re-run would have hit defects 1–3 regardless. V8 ran on the corrected base.

## Deviations

- **Spec supplied inside the workspace** (`spec/tftp.md`). The agent `read_spec` tool reads only
  `subsystems/`, `arch/` and `architecture.md`, so **no agent can read a service spec, a driver
  record or a mitigation.** Found before the run and recorded in the pre-registration.
- **Iteration cap 30** instead of the repo default of 10, pre-registered. It was irrelevant:
  the run used 1.

## For the next PRD session

The agent-authorship question is blocked on the loop, not the model. Before any re-run of F6,
V8 or H7:

1. A result with an empty diff is not reviewable. Either skip review or fail it as "no output"
   (`engine.py:_trigger_review`).
2. `request_changes` must return the task to its author with the feedback, with a bounded retry
   count, instead of blocking it forever (`engine.py:446`).
3. The manager must not emit tasks with no deliverable, or the engine must execute them without
   review.
4. `read_spec` must reach `services/`, `drivers/` and `mitigations/`.
5. Then re-run F6 once, pre-registered, on base `5fb2777^`, with `measure_authorship.py` as the
   meter.
