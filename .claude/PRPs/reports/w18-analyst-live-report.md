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

## Run 3 (design scoped): the gate held; the model could not write the format

**2026-09-29 20:21:59Z → 22:36Z.** Archive: `.artifacts/authorship/2026-09-29-analyst-run3/`. Loop `70a6485`.

- **Planning:** one Analyst task, as asked. No design phase.
- **First draft:** the model copied the index. Every library in the vocabulary, from `libpq` to
  `libjpeg`, was "inferred" from `FROM python:3.12-slim`, and every quote was accurate. The
  quote check cannot catch a true line that does not support the claim. That is what the
  reviewer and the ablation score are for.
- **Final draft:** six plausible facts with mostly correct lines (`import ssl` at `app.py:2`,
  `app.run(...)` at `:20`). They were written in flow-style YAML with unquoted strings that
  contain `"` and `:`, so the file does not parse.
- **The gate held.** Round 1 was refused by the tool, which quoted the YAML error, and the
  reviewer model was never asked. Round 2 produced the same shape. **No record reached review;
  A4's gate is satisfied, but no record passed either.**
- **Partly the harness's fault.** The prompt's own example used flow mappings with unquoted
  placeholders, and the model could only learn a record was invalid after its task ended.
  **Fixed** in `a3b2acc`: a block-YAML example with single-quoted quotes, and a `check_record`
  tool that runs the gate's own validation on demand.
- **Budget.** The run ran past 2 h of wall time. macOS `sleep` does not count time the machine
  spends asleep, so the timeout shim fires late across a system sleep. The operator enforced
  the budget with SIGTERM at 2 h 14 min. The pause worked, the graph and the round-2 work were
  committed, and it was not resumed.
- **Operator error.** `orchestrate-native.sh` was edited while it was running. bash reads
  scripts incrementally, so the wrapper died with a syntax error after the pause (rc 2). The
  engine had already paused cleanly; only the wrapper's summary line was lost. The rule: never
  edit a script a run is executing.

Run 4 is a fresh run on `a3b2acc`, with the same model, subject, goal and budget.

## Run 4 (block-YAML example, check_record): a record passes the gate

**2026-09-29 22:39Z → 00:35Z**, paused by its own 2 h budget (`PAUSED`, exit 75). Archive:
`.artifacts/authorship/2026-09-29-analyst-run4/`. Loop `e3763e3`, run from a pinned copy of the
wrapper, with a wall-clock watchdog.

- **The format problem is gone.** The model wrote block YAML with single-quoted quotes, as the
  new example shows.
- **check_record worked.** Five calls. Each returned the gate's exact refusal (a line past the
  end of the file; `app.py:19 reads 'if __name__…'`), and the model corrected against it. The
  one refusal that reached round 1 was a line number; round 2 fixed it.
- **The final record passes every mechanical check:** valid YAML, every name in the index,
  every quote on its cited line (`app.run(...)` at `app.py:20`; `ssl.OPENSSL_VERSION` at `:16`).
  **This is the first agent-written artifact record to pass the gate.** A4's pre-registered
  gate (no invented capability reaches review) held on every run. The budget ended before a
  reviewer model read the record.
- **It over-claims massively: 36 facts for a 20-line application.** Twenty-six of them are
  libraries or programs "inferred" from `FROM python:3.12-slim`, despite the prompt saying a
  base image containing a library is not a reason to need it. Every quote is true, so the quote
  check cannot catch it; the capability names are real, so the index cannot either.

### What the pipeline does with an over-claiming record

`scripts/app_to_env.py` was run on run 4's record with the human reference recipe
(`.artifacts/authorship/2026-09-29-analyst-run4/pipeline/`). It stopped at the package gate:
the manifest requires `libcurl.so.4`, `libjpeg.so.62`, `libxml2.so.2`, `git`, `curl` and others
that the application never uses and the base does not contain.

That is the gate working, and it shows where the design's weight sits:

- An over-claim of something **present** reaches ablation, which proves it unneeded. The fixture
  runs showed this for `libsqlite3` and `/etc/ssl/certs`.
- An over-claim of something **absent** forces a bloated package or stops at the gate. Ablation
  never sees it.

So the **reviewer** is the stage that must reject "needed because the base image has it". It
reads evidence, and a line saying `FROM python:3.12-slim` is not evidence for `libjpeg`. The next
Analyst run should reach review; its verdict on this pattern is the finding to watch.

## Summary across four runs

| Run | Reached | Harness defect found and fixed |
|---|---|---|
| 1 | planning | tool lists were advisory; the manager wrote the record (`4a7b964`) |
| 2 | design (stopped) | kernel design ran for analysis tasks (`70a6485`) |
| 3 | gate × 2, refused | the prompt's example led to invalid YAML; no early check (`a3b2acc`); timeout shim ignored system sleep (`3f85080`) |
| 4 | **gate passed** | none; the remaining problem is the model's over-claiming |
