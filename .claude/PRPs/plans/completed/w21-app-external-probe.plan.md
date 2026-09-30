# Plan: A10 — The external probe for applications

## Summary
`scripts/run-intent-probe.sh` grades a built kernel image from outside it (`git clone` for
host-repo, a framebuffer dump for Doom), with a three-way verdict: `WORKED`, `HONESTLY REFUSED`,
`FAILED`. This phase adds an `app` intent that does the same for a packaged application: start
the artifact from A8 in its substrate, run a **probe declared per application** from the host
side (an HTTP request and an expected response, a CLI invocation and an expected exit), and
return the same verdicts. A log line saying "started" is the image grading itself, and the PRD
names that as the failure this rubric exists to prevent.

## User Story
As the ablation score (A9) and as the owner, I want one command whose exit status says whether
the packaged application actually did its job, judged from outside it.

## Problem → Solution
The probe knows two intents → `run-intent-probe.sh app <package dir>` reads
`package/probe.yaml` (declared by the operator, never by an agent), runs the artifact
network-isolated with only the declared ports published, executes the probe, grades.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A10
- **Estimated Files**: 5
- **Depends on**: A8

---

## Probe declaration (`probe.yaml`, operator-written)
```yaml
format: 1
start_timeout_s: 60
checks:
  - {kind: http, port: 8000, path: /health, expect_status: 200, expect_body_contains: "ok"}
  - {kind: http, port: 8000, path: /items/1, expect_status: 200}
refusal_markers: ["AUTON-REFUSED:"]   # a line the app prints when it knowingly lacks a capability
```
Kinds in v1: `http`, `tcp` (connect + optional send/expect), `exec` (a command inside the
container, expected exit). `probe.yaml` is `declared` evidence of what "works" means, and it is
written by a person because a model-written success criterion is the image grading itself one
step removed.

## Mandatory Reading

| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `scripts/run-intent-probe.sh` | all (esp. 1-60 rubric, 83-140 dispatch) | the rubric, `worked`/`refused`/`failed`, cleanup trap, `free_port` |
| P0 | `agent/tools/package_gate.py` (A8) | — | where the image tag comes from |
| P1 | `scripts/lib/toolchain.sh` | 87-120 | `auton_timeout` |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `scripts/run-intent-probe.sh` | UPDATE | `app)` branch; usage line; unknown-intent message lists `app` |
| `agent/tools/app_probe.py` | CREATE | parse `probe.yaml`, run checks, print one verdict line; bash branch delegates to it (HTTP/TCP in bash is fragile) |
| `agent/tests/unit/test_app_probe.py` | CREATE | each check kind against a local stub server; each verdict |
| `agent/tests/integration/test_app_probe_flask_hello.py` | CREATE | end to end on A8's fixture |
| `agent/tests/fixtures/apps/flask-hello/probe.yaml` | CREATE | the fixture's declaration |

## NOT Building
- Probes written by agents.
- Load or soak testing. One probe run is one verdict.

---

## Step-by-Step Tasks

### Task 1: Verdict tests (RED)
- **ACTION**: stub HTTP server returns expected → `WORKED` exit 0; wrong status → `FAILED` exit 1 naming check and observed value; container exits early printing a `refusal_markers` line → `HONESTLY REFUSED` exit 2 with the line; container exits early silently → `FAILED` ("exited 1 after 0.4 s; no refusal marker"); no `probe.yaml` → exit 2 "probe could not run: no declaration".

### Task 2: `app_probe.py`
- **ACTION**: `docker run --rm -d --network <isolated bridge> -p 127.0.0.1:<free>:<port>` for declared ports only; wait for port or timeout; run checks; capture container logs on failure; always stop the container.

### Task 3: Wire into the script
- **ACTION**: `app)` → `"$PY" agent/tools/app_probe.py "$PKG"`; map exit codes 0/1/2 to the existing helpers so output is uniform.

### Task 4: Fixture
- **ACTION**: flask-hello → `WORKED`; flask-hello with `flask` removed from the recipe → `FAILED` (this is A9's first ablation step, done by hand here to prove the probe can fail).

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_app_probe.py -q
scripts/run-intent-probe.sh app agent/tests/fixtures/apps/flask-hello/package; echo $?
```

## Acceptance Criteria
- [ ] All three verdicts reachable, each by test, with the reason printed.
- [ ] A probe that passes on the full fixture fails when a required dependency is removed.
- [ ] The two existing intents are unchanged (their tests pass).

## Risks
| Risk | Mitigation |
|---|---|
| Port readiness races | wait for TCP accept, then retry the first check for `start_timeout_s` |
| Container left running on Ctrl-C | the existing `trap cleanup EXIT` pattern plus `--rm` and a named container |
