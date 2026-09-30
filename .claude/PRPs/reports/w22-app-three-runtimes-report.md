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

## Findings so far

1. **The index needs a kind for language packages** (`pypi:`, `npm:`). Without one, an
   Analyst's most natural claim is refused. It is ablatable (uninstall, then probe). Not added
   during w22: a vocabulary change is a reviewed edit, not an experiment variable.
2. **"It works inside the container" is not evidence.** The probe was the only check standing
   outside, and it was the only one that caught the defect. It now runs before review.
