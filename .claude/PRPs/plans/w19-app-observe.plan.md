# Plan: A5 — `observe.py`, the only writer of `observed`

## Summary
Static reading misses what an application reaches for at run time: a `dlopen` of a name read
from config, a subprocess on first request, a CA bundle, `/dev/urandom`. `observe.py` runs the
subject inside a disposable, network-less sandbox under a tracer and records what it opened,
loaded, exec'd, bound and dialled — each as a fact with `source: observed`. It is **the only
tool that may write that word**, mirroring `probe_ingest.py`'s monopoly on `probed`. The phase
gate is a fixture whose only dependency is `dlopen`ed: A5 must catch it and A4's static read must
miss it. If both catch it, or neither does, one of the two is not doing its job.

## User Story
As the manifest builder (A6), I want run-time facts that no model wrote, so that an environment
derived from them fails only on paths nobody exercised — and says which paths were exercised.

## Problem → Solution
Every fact so far is `declared` or `inferred` → a traced run in a sandbox produces `observed`
facts plus a **coverage statement** (the exercise script that ran, its exit, duration), merged
into the artifact record by a tool, never by an agent.

## Metadata
- **Complexity**: Large
- **Source PRD**: `prds/auton-application-to-environment.prd.md`
- **PRD Phase**: A5
- **Estimated Files**: 9
- **Depends on**: A1 (record format). **Hard gates**: `decisions/subject-trust.md` (D-A3) and `decisions/first-substrate.md` (D-A1) must have verdicts — this phase executes code AUTON did not write. `decisions/syscall-scope.md` (D-A2) decides whether the `syscalls` kind is recorded at all; default until decided: not recorded

---

## Sandbox (the default this plan assumes, pending D-A3)
- Linux container via the host's `docker` (the control plane's backend already shells to it: `controlplane/src/controlplane/backends/docker/client.py:152`), image pinned by digest.
- `--network none`, `--read-only` root with a tmpfs `/tmp`, `--cap-drop ALL` plus `SYS_PTRACE` for the tracer only, no host mounts except the staged subject **read-only**, no environment passed through, `--pids-limit`, `--memory`, wall-clock cap.
- If D-A1 chooses microVM, the same contract is met by QEMU `microvm` and only `sandbox.py` changes.

## What is traced
| Fact kind | Mechanism (inside the container) |
|---|---|
| `lib:` | `strace -f -e trace=openat` on `*.so*` that returned ≥0, plus `LD_DEBUG=libs` for the loader's view |
| `path:` | `openat`/`stat` results, successful and **failed** (a failed open of `/etc/ssl/certs/…` is a need the image lacks) |
| `exec:` | `execve` |
| `listen:` / `dial:` | `bind`+`listen`, `connect` (network is off, so dials fail — recorded as `dial:` with `result: refused-by-sandbox`) |
| `syscalls:` | only if D-A2 says so; with coverage |

## Mandatory Reading

| Priority | File | Why |
|---|---|---|
| P0 | `agent/tools/probe_ingest.py` | the "only tool that may write `probed`" docstring and structure: parse raw tool output → facts |
| P0 | `agent/tests/unit/test_probe_ingest.py:232-260` | the two-direction guarantee test to mirror |
| P0 | `agent/tools/artifact_spec.py` (A1) | the record observe merges into |
| P1 | `controlplane/src/controlplane/backends/docker/client.py:140-170` | how this repo runs `docker` as argv |
| P1 | `agent/kernel_spec/decisions/subject-trust.md`, `first-substrate.md` | the verdicts this plan must obey |

## Files to Change

| File | Action | Justification |
|---|---|---|
| `agent/tools/observe.py` | CREATE | `observe(subject, record, exercise) -> record'`; CLI |
| `agent/tools/observe_sandbox.py` | CREATE | the docker argv, isolated so D-A1 changes one file |
| `agent/tools/observe_parse.py` | CREATE | strace / LD_DEBUG text → facts; pure functions, tested on captured output |
| `agent/app_spec/observe.Dockerfile` | CREATE | tracer image (strace, pinned) |
| `agent/tools/artifact_spec.py` | UPDATE | an `observed` fact must carry `observation: <id>`, and `observations/<id>.json` must exist with a matching sha256 |
| `agent/tests/unit/test_observe_parse.py` | CREATE | parsers on recorded output |
| `agent/tests/unit/test_observed_monopoly.py` | CREATE | no module other than `observe.py` emits `source: observed` (source scan + A4's record gate refuses it) |
| `agent/tests/fixtures/apps/dlopen-only/` | CREATE | a C program whose only dependency is `dlopen(getenv("LIB") ?: "libz.so.1")`, plus its exercise script |
| `agent/tests/integration/test_observe_dlopen.py` | CREATE | the phase gate; skips with a reason when docker is absent |

## NOT Building
- Seccomp generation (D-A2; the PRD: "an almost-right profile is an outage").
- Network access for the subject. Dials are recorded as attempts.
- Exercise-script authoring by a model. The exercise is `declared` by the operator or the subject's own test command, and coverage is stated as exactly that.

---

## Step-by-Step Tasks

### Task 1: Parsers first
- **ACTION**: capture real strace/LD_DEBUG output from the fixture once, commit it as test data, write `observe_parse` against it. Every emitted fact has `source: observed` and an `observation` id.

### Task 2: The monopoly test
- **ACTION**: scan `agent/` for the literal `"observed"` assigned to a `source`; only `observe.py`/`observe_parse.py` may match. Mirror `test_probe_ingest.py:232`'s docstring about both directions.

### Task 3: Sandbox
- **ACTION**: `observe_sandbox.argv(subject, image, exercise, limits)`; tests assert `--network none`, `--read-only`, `--cap-drop ALL`, the subject mount is `:ro`, and no `-e` of host environment.

### Task 4: Observe and merge
- **ACTION**: run, parse, write `observations/<id>.json` (raw trace hash, exercise, exit code, duration, image digest), merge facts into the record: an `observed` fact **supersedes** an `inferred` one for the same capability and the record keeps both evidence lists.

### Task 5: The gate
- **ACTION**: fixture `dlopen-only`: A4's scripted Analyst on the fixture must *not* produce `lib:libz.so.1` from the source alone (the name is in an env default, and the scripted run is given only the static read); `observe.py` must produce it `observed`. Assert both. Then the reverse check on a fixture with a static `-lz` link: both find it.

## Validation Commands
```bash
cd agent && ../.venv/bin/python -m pytest tests/unit/test_observe_parse.py tests/unit/test_observed_monopoly.py -q
cd agent && ../.venv/bin/python -m pytest tests/integration/test_observe_dlopen.py -q   # needs docker
.venv/bin/python agent/tools/observe.py --subject <ws>/.auton/subject --record analysis/app.artifact.yaml --exercise ./exercise.sh
```

## Acceptance Criteria
- [ ] The dlopen fixture is caught by A5 and missed by the static read, by test.
- [ ] No module but `observe*.py` can produce `source: observed`, by test in both directions.
- [ ] Every observation states its exercise and exit; a record with `observed` facts and no observation file is refused.
- [ ] Sandbox flags are asserted by test, not by convention.

## Risks
| Risk | Mitigation |
|---|---|
| Rancher/Docker Desktop on macOS: ptrace in containers | `SYS_PTRACE` cap; integration test skips with the reason if the runtime refuses, and CI's Linux leg runs it |
| Coverage is partial by construction | stated in every observation; A9's ablation is the check on what it missed |
| Executing an untrusted subject | D-A3 is a hard precondition; this plan does not start without a verdict |
