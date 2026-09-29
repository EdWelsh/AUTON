# The Analyst's first live run: the harness failed, not the model

**Pre-registration**: [w18-analyst-live-preregistration.md](./w18-analyst-live-preregistration.md), written before the run.
**Run 1**: 2026-09-29 18:12:47Z → 18:18:42Z (6 minutes), `ollama_chat/qwen3.5:9b` (qualified 4/4 that
afternoon; slowest call 617 s). Archive: `.artifacts/authorship/2026-09-29-analyst/`.

## Verdict against the pre-registered gate

The gate was *"no artifact record reaches the reviewer containing a capability absent from the
index."* That held, but only in a way that does not count: **no Analyst task ever existed.** The
run ended in planning with `Manager produced no tasks`. This is not an A4 pass. It is a run that
never reached the thing being measured.

## What happened

The manager was given a read-only tool set (`read_spec`, `list_files`, `read_file`,
`search_code`). It read the staged subject, and then **called `write_file` and wrote
`analysis/flask-hello.artifact.yaml` itself**: 2,640 bytes, straight into the workspace, with no
branch, no gate and no review. After that it answered with prose instead of a task list
(`Failed to parse tasks: substring not found`), and planning ended.

The record it wrote is not an artifact record at all. It has `metadata:`, `description:`,
`application:`, `dependencies:`, and a `created: "2024-01-01"` nobody observed. It has no
`facts`, no `source` and no citation. `artifact_spec` would have refused it on every count.
Nothing asked `artifact_spec`, because nothing expected the manager to write.

## The defect: tool lists were advisory

`Agent._execute_tool` dispatched on the tool *name*. Every role shares one dispatcher, so any
agent could invoke any tool any role has, provided the model named it. The tool list sent to the
model was a suggestion, not a boundary. The same hole meant the Analyst's "no shell"
(`ANALYST_TOOLS`) was a comment rather than a rule, and the injection surface A2 and A3 reason
about was larger than written.

**Fixed** in the commit after this report. A tool not in the agent's own list is refused, and the
refusal names the tools the agent does have. Four tests in `tests/unit/agents/test_tool_boundaries.py`
cover it: the manager cannot write, the Analyst cannot run a shell, a given tool still works,
and an invented tool is still told what exists. Two existing test files called tools on agents
built with `tools=[]` and relied on the hole; they now pass the developer tool set explicitly.

## What this does not tell us

- **Whether the 9b model can write a valid record.** It never got an Analyst task.
- **Whether the manager would plan an analyst task** once it cannot do the work itself. Its
  prose answer may have been caused by the write: having "done" the job, there was nothing left
  to plan.

## Next

Run 2 is a **new experiment**, labelled as one. Same model, subject, goal and budget; the loop
changes only by the tool-boundary fix. Pre-registration addendum below.

### Pre-registration addendum, run 2 (written before it)

Unchanged except: loop at the tool-boundary commit. Additional prediction: the manager now
emits one `analyst` task. If it again answers in prose, that is a manager-prompt finding for
local models, reported separately from A4.

## Run 2 (tool boundary fixed): stopped by the operator in design

**2026-09-29 19:59:55Z → 20:22Z.** Archive: `.artifacts/authorship/2026-09-29-analyst-run2/`.

- The boundary held live. The manager tried `write_file` again, was refused, and then planned.
- **Prediction missed.** The manager did not make ONE analyst task, as its prompt asks. It made
  four (`analyst-001`…`004`: analyse source, dependencies, build config, then generate the
  record), and labelled them with the kernel subsystems `sys` and `pkg`.
- **Second harness defect.** Because of those labels, the design phase asked the architect to
  design kernel interfaces for `sys` and `pkg`. After 15 minutes the Analyst had not been
  reached. **Fixed** in `70a6485`: design covers only subsystems of developer/tester/architect
  tasks.
- The operator stopped the run with SIGTERM. The w17 pause worked live, mid-model-call: exit 75,
  `PAUSED`, graph saved. It was not resumed. The loop had changed, so continuing would be a
  different experiment presented as the same one.

Run 3 is a fresh run on the fixed loop (`.artifacts/authorship/2026-09-29-analyst-run3/`), with
the same model, subject, goal and budget.
