# w22 — three applications, three runtimes: results

**Pre-registration**: [w22-app-three-runtimes-preregistration.md](./w22-app-three-runtimes-preregistration.md).
Driver: `scripts/app_to_env.py`. Model `ollama_chat/qwen3.5:9b`, 2 h per agent stage.
Archives: `.artifacts/w22/<subject>/` (`STAGES.json`, logs, workspaces).

## Subject 1 — pallets/flask `examples/javascript` (Python)

### Attempt 1, fully agent-driven: stopped at `analyst`

Every refusal came from the tool; no record reached a reviewer. Three review rounds, then the
task failed.
- **Round 1: `lib:flask` is not in the index.** Flask is a Python *package*, and the index has no
  kind for language packages. This is a real vocabulary gap: it is the first thing an Analyst
  reaches for in a Python application. Not changed mid-experiment; see Findings.
- **Rounds 2 and 3:** the port `listen:tcp/5000` was marked `unknown` without saying where it
  looked.

### Attempt 1, from the manifest stage: human record (fallback, labelled), agent Packager

The fallback record is minimal: the runtime and port `unknown`, with the files read. Stages:

| Stage | Result |
|---|---|
| manifest | 1 requirement, 1 assumption |
| packager (**agent**) | recipe built, started, merged: `FROM <pinned python>`, `pip install -e .`, `CMD flask --app js_example run` |
| observe | 16 observed facts, 3 unindexed; exercise passed **inside** the container |
| regate | 16 requirements after observation, 0 missing |
| **probe** | **FAILED: connection refused on :5000 from outside** |

**The probe caught what nothing else did.** `flask run` binds `127.0.0.1` by default. The start
check, the in-container exercise, observation and the regate all ran inside the container, so
all passed. Only the probe connects from outside. The pre-registration's line for this outcome
reads: "the package builds and starts but does not work, judged from outside".

Two changes followed (`feat(package): the operator's probe runs inside the package gate`).
- The probe now runs in the package gate before review, so a Packager hears "connection
  refused from outside" and can fix it.
- Observation records a listener's bound address, and flags LOOPBACK ONLY.

Attempt 2 of the Packager stage runs on that gate, labelled as a new attempt.

### Attempt 2 of the Packager stage (on the probe-in-gate loop): **end to end, WORKED**

`.artifacts/w22/js-example-attempt2/`, 03:26Z → 04:18Z.

| Stage | Result |
|---|---|
| manifest | 16 requirements (see caveat) |
| packager (**agent**) | first recipe passed the gate, probe included: `pip install flask`, `flask --app js_example run --host 0.0.0.0 --port 5000` |
| observe / regate | 18 observed; 0 missing |
| probe | **WORKED**, from outside |
| ablate | **3 of 14 load-bearing**; 11 over-claimed, among them `libssl.so.3` and `libcrypto.so.3`: this app never uses TLS, and removing them changes nothing the probe can see |

- **The Packager chose `--host 0.0.0.0` unprompted this time.** The new in-gate probe never had
  to refuse anything, so this attempt does not show whether that feedback would have taught it.
  The loop test does (`test_the_gate_runs_the_operators_probe_before_review`).
- **Caveat.** `observe` merges into the record it is given, in place. Attempt 2's copy of the
  fallback record therefore already carried attempt 1's observed facts for the same subject:
  valid evidence, but not the 1-fact record attempt 1 started from. Hence 16 requirements.
- **Counting.** This is a full pipeline pass with a human-written record. It counts toward "the
  pipeline works on a real repository", not toward the PRD's agent-only metric.

## Subject 2 — heroku/node-js-getting-started (Node)

### Attempt 1, fully agent-driven: stopped at `analyst`, no output

04:18Z → 05:05Z. The Analyst read every file in the subject (`index.js`, `package.json`,
`Procfile`, `.env`, `README`, the licence, and more), then ended its turn **without writing a
record**. It never called `check_record`. The engine failed the task at once: a branch identical
to main was terminal, with no feedback and no second round. A *refused* record gets three
rounds with the reason attached.

**Fixed** (`fix(engine): an empty result is feedback`): an empty result now goes back to the
author, "you produced no change: this task must write <produces>", within the same round
limit, and is still never shown to a reviewer. Attempt 2 runs on that loop, labelled as a new
attempt.

### Attempt 2 (empty-result feedback): stopped at `analyst` again

05:08Z → 06:45Z. Three rounds of read, read, read; no record, and no `check_record` call. The
model's final replies were not logged, so *why* it stops is unknown. **Fixed for next time**:
every task's final reply is now logged (`f2aae8c`).

### Fallback (human record, agent Packager): stopped before the Packager

06:46Z → 07:10Z. The **manager** answered in prose and planned zero tasks (`Failed to parse
tasks`), so the Packager was never asked. This is the same failure as the first live Analyst
run.

**Fixed structurally** (`fix(engine): an application run's one task is seeded`). An
application run's plan is fixed, so the engine now seeds it through the A7 seed mechanism
instead of depending on a model to plan one task. A model-planned task for the same role is
dropped. The fallback is re-run on that loop.

### Fallback rerun (seeded loop): **end to end, WORKED**

`.artifacts/w22/node-getting-started-fallback2/`, 07:14Z → 08:11Z.

| Stage | Result |
|---|---|
| manifest | 2 requirements (the human record: `runtime:node-22`, `listen:tcp/5006`, `env:PORT`) |
| packager (**agent**) | first recipe passed the gate, probe included: `FROM <pinned node:22-slim>`, `npm install`, `node index.js` |
| observe / regate | 11 observed, 2 unindexed; 0 missing |
| probe | **WORKED** from outside |
| ablate | **7 of 9 load-bearing**; over-claimed `path:/etc/localtime` and `path:/etc/ssl/openssl.cnf` (read at start-up; the app does not need them) |

A human record again, so this counts toward "the pipeline works on a real repository", not the
agent-only metric.

## Subject 3 — traefik/whoami (Go, static, `scratch`)

### Attempt 1, fully agent-driven (seeded loop): stopped at `analyst`, budget

08:12Z → 10:20Z. The seeded analysis task ran, and the manager no longer mattered. **The best
content any agent has produced here**, with no index dumping:
- `runtime:static-elf` from `FROM scratch`
- `listen:tcp/80` from `EXPOSE 80`
- `path:/etc/ssl/certs` from the `COPY` of the CA bundle
- two `env:` vars cited to `app.go`

But the whole 2 h budget went inside the one task: 50 model calls and 13 rewrites of the file.
It ended with **two `facts:` sections** and never reached a gate.

**That exposed a real validator hole.** PyYAML keeps the last duplicate key silently, so the
first `facts:` list, the correct one, would have vanished without a word. **Fixed**
(`520cba2`): the loader refuses a duplicate key. The same commit fixes the driver, which
validated records against the raw clone while agents cite the staged export. The agent's
`tree_hash` was right; the driver's comparison was wrong.

### Fallback, Packager attempt 1: stopped at `packager`, budget

10:24Z → 12:24Z, three rounds, every refusal by the gate.
- **Round 1 was right:** `FROM golang:1-alpine` is not the pinned builder.
- **The Packager then deleted its builder stage instead of pinning it.** Rounds 2 and 3 refused
  `--from=builder` correctly, since no such stage existed. But the refusal repeated six times and
  never said how to fix it.
- **Fixed** (`7f3d2f6`): one refusal that names the listed builder to declare, and the
  Packager's task now lists the builders a build stage may use.

### Fallback, Packager attempt 2: **end to end, WORKED**

12:27Z → 13:46Z. The recipe passed the gate first time: `FROM <pinned golang> AS builder`, a
static `go build`, then `FROM scratch` with the binary alone.

| Stage | Result |
|---|---|
| packager (**agent**) | **0 extra libraries**; the image is **4.69 MB against upstream's own 4.95 MB** |
| observe / regate | 3 observed, 2 unindexed; 0 missing |
| probe | **WORKED** (2 checks: `/` shows "Hostname", `/health` → 200) |
| ablate | 0 of 1 load-bearing: `path:/etc/localtime` over-claimed (opened at start-up, absent, not needed) |

**The agent's package is smaller than upstream's, and just as correct by the probe.** Upstream
copies a CA bundle and the whole zoneinfo tree into `scratch`. The agent's package omits both,
and the operator's probe cannot tell the difference.

Ablation first came out `unprobeable` here. `scratch` has no shell, so no `RUN rm` can start.
**Fixed** (`28ee4e4`): the removal runs under a busybox copied in and deleted in the same step.

## Summary

| Subject | Agent Analyst | Agent Packager | Probe | Ablation |
|---|---|---|---|---|
| Flask `js_example` (Python) | failed: refused 3×, first for `lib:flask` | passed the gate first time (attempt 2) | **WORKED** | 3 of 14; 11 over-claims |
| Node starter | failed: no record, 2 attempts | passed first time | **WORKED** | 7 of 9; 2 over-claims |
| `whoami` (Go, scratch) | failed: budget, duplicate `facts:` | passed on attempt 2 | **WORKED** | 0 of 1; 1 over-claim |

**Against the PRD's metrics:**
- **Applications compiled to a running minimal environment:** 3 of 3 with a human-written
  record and an agent-written package. **0 of 3 fully agent-driven.** The pre-registration said
  the headline counts only the latter, so the headline is **0**.
- **Facts with no provenance reaching a manifest:** 0. Every refusal was by the validator.
- **Agent-asserted capabilities absent from the index:** refused every time (`lib:flask`,
  `lib:libmagic-unicorn.so` in tests). None reached a manifest.
- **`observed` written by anything but `observe.py`:** 0, held by test from both directions,
  and by the forger fixture.
- **Required capabilities proved load-bearing:** 10 of 24 across the three. **Over-claims
  caught: 14.** Reported, not zero, as the PRD requires.
- **Downstream files changed:** 0.

**Where the model stands.** On this machine `qwen3.5:9b` reliably *packages*: three of three,
twice first time. It does not yet *analyse*. Its three failure modes were a missing vocabulary
kind, never writing, and running out of budget while rewriting. The next experiment is the
larger model (w23).

**Harness defects found and fixed by w22, all committed with tests:**
- The probe now runs inside the package gate: a loopback-only server passed every in-container
  check.
- An empty result is feedback, not a terminal failure.
- An application run's one task is seeded, not left to the manager.
- A duplicate YAML key is refused, not silently dropped.
- One staged export is used everywhere.
- A missing build stage is named once, with the fix.
- Shell-less images can be ablated.

## Findings so far

## Findings so far

1. **The index needs a kind for language packages** (`pypi:`, `npm:`). Without one, an
   Analyst's most natural claim is refused. It is ablatable (uninstall, then probe). Not added
   during w22: a vocabulary change is a reviewed edit, not an experiment variable.
2. **"It works inside the container" is not evidence.** The probe was the only check standing
   outside, and it was the only one that caught the defect. It now runs before review.
