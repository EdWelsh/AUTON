# Pre-registration: the Analyst's first live run (A4 gate)

**Written 2026-09-29, before the run.** Protocol: the Generation Experiment Protocol
(`completed/w13-factory-f6-rerun.plan.md`), applied to analysis instead of generation.
Plan: [`w18-app-analyst`](../plans/completed/w18-app-analyst.plan.md), Task 6.

| | |
|---|---|
| Model | `ollama_chat/qwen3.5:9b`, qualified by `scripts/model-probe.py` immediately before |
| Subject | `agent/tests/fixtures/apps/flask-hello` (4 files; Flask, `import ssl`, `EXPOSE 8000`, one env var) |
| Loop | `feat/prd-completion` at `ffb7f32` plus `--subject` in `orchestrate-native.sh` |
| Budget | `ORCH_TIMEOUT=7200` (2 h), 10 iterations, 60 tool turns, 3 review rounds |
| Goal | `Analyse the application staged at .auton/subject/ and write its artifact record.` |

**The gate, stated in advance** (from the PRD's A4 row): *a run that invents a capability fails
the phase.* Operationally: **no artifact record reaches the reviewer model containing a
capability absent from `agent/app_spec/capabilities.yaml`.** The tool gate makes that true by
construction; what this run measures is what the model does *around* it.

Outcomes, and what each means:

| Outcome | Meaning |
|---|---|
| A record merges, every capability in the index, quotes verified | A4 passes live |
| The record is refused by the tool N times, then merges | A4 passes; N and the refusal texts are the finding (how often a local model invents or paraphrases) |
| Refused on every round → task FAILED | The gate held (nothing invented reached review) but the model could not satisfy it; reported as a negative result about the model, not the gate |
| A record reaches the reviewer with a phantom capability | **A4 fails** — a gate defect |

**Predictions.** The 9b model will get the runtime (`pyproject.toml:4`) and the port
(`Dockerfile:6`) right. It will be refused at least once, most likely for a paraphrased quote
rather than an invented name, because the index is printed in its prompt and quoting a line
exactly is the harder habit. It will probably miss `lib:libssl.so.3` (`import ssl` →
libssl requires knowing CPython's ssl module links OpenSSL). The final integration build fails
(no Makefile) and is irrelevant to this gate.
