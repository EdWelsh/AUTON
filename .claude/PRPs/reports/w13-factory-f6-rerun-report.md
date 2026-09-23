# Report: F6 Re-run (service #2, agent-authored)

**Plan**: `plans/completed/w13-factory-f6-rerun.plan.md`
**Pre-registration**: `w13-factory-f6-rerun-preregistration.md`, 12:35:19Z, before the run
**Artifacts**: `.artifacts/authorship/2026-09-22-f6-rerun/` (transcript, timing, goal, config,
task graph, branch diffs, and the diagnostic transcript)

## Result: nothing written. This time the loop was not the cause

| | F4 (human control) | F6, w11 | **F6, w13** |
|---|---|---|---|
| Implementation | 401 lines (graph) | 0 | **0** |
| Tests | 255 lines, 24 cases | 0 | **0** |
| Gate suite (31 checks, frozen at `0fa2589`) | n/a | n/a | **exit 2: not generated** |
| Where it stopped | n/a | iteration 1, the loop's review path | **the developer's 20-turn cap** |
| Cause | n/a | four loop defects | **model: tool-use confusion** |

The loop behaved as designed: the manager planned 2 tasks with deliverables (dropping a reader
task), the developer got its task and its own branch, the spec was read through `read_spec`, and
the run ended in a named state (`tftp-002 failed (no output: branch … identical to main)`). The
run took about 2 minutes of a 60-minute budget.

## Why: a diagnostic run, labelled as such

The measured run's transcript could not say what the developer's 20 calls were (tool calls were
not logged). A **diagnostic** run on identical inputs, with tool-call logging added, is not a
second attempt at the experiment and is not scored. It showed:

```
read_spec(services/tftp) → spec          ×6   (re-reading, never acting)
tftp_server_init(...)    → Unknown tool  ×8   (a C function from the spec, called as a tool)
hit max turns (20)
```

gemma4 (8B, Q4_K_M) confused the **specification's functions with its own tools**, and never
called `write_file`. This is a capability limit of the model, not a plumbing defect.

## Loop improvements that came out of it (follow-ups, not in-run patches)

- Every tool call is now logged at INFO: tool, arguments with bodies elided, and the result.
  An archived run can now say what an agent did.
- An unknown tool's reply lists the agent's real tools and says how to create a file. The bare
  "Unknown tool" gave the model nothing to correct against.

## The finding that matters for the next steps

**With the loop repaired, the bottleneck is the model.** An 8B local model cannot yet drive this
loop to a written service. The same is expected of every generation plan in w13–w14 (memory
manager, storage, drivers, Doom, services) on gemma4, and each will be run once and reported
honestly. A capable model is the lever: `[llm].model` accepts any LiteLLM provider, and the key
check in `cli.py` covers Anthropic and others. **That choice is the owner's** (it has a cost), and
is recorded as a gate for re-running the authorship experiments.

## Harness note

`authorship.yaml`'s `tftp` entry still pointed at a `spec/` copy in the workspace (the w11
layout). It now reads the spec from the repo (`in_repo: true`), and lists the human gate tests
separately from the agent's.
