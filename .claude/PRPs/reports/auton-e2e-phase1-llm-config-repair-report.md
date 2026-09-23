# Implementation Report: LLM Config Repair — AUTON E2E Phase 1

**Plan**: `.claude/PRPs/plans/completed/auton-e2e-phase1-llm-config-repair.plan.md`
**Branch**: `feat/cp-os-images`
**Date**: 2026-09-10

## Summary

Replaced the dead configured model with one qualified empirically against the operator's
real tool-calling scenario, removed every live copy of the dead model string, added an
Ollama model-availability preflight that fails at construction naming the real options, and
fixed the resolver's unawaited-coroutine path.

The most consequential finding was not in the plan: removing `brain.py`'s hardcoded fallback
exposed that `_REPO_ROOT = Path(__file__).resolve().parents[5]` was **off by one**, resolving
to `/Users/edwelsh/source/repos` instead of the repo root. The operator's `LLMBrain` had
therefore *never read `auton.toml` at all* — every call silently fell through to the
hardcoded `ollama/llama3.1:8b`. The hardcoded fallback was not merely a second source of
truth; it was the only one in effect, and it was masking a broken config path.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Small (fix) / Medium (qualifying a model) | Small fix, **Small** qualification — first candidate passed |
| Confidence | — | High; both consumers verified against the live model |
| Files Changed | 6 | **10** (4 more: a latent path bug plus doc/help copies of the dead string) |

## Task 1 — Qualify a replacement model

Decided empirically. Both installed candidates were probed with the operator's real
scenario (`download_file → update_spreadsheet → send_email`) through `ollama_chat/`, with
the real tool schemas and a full multi-turn loop.

| Model | Size | Result | Wall time |
|---|---|---|---|
| **`gemma4:latest`** | 9.6 GB | **PASS** — correct 3-tool sequence, correct args, clean summary | **18.9 s** |
| `qwen3.6:27B` | 17 GB | PASS — same correct sequence | 235.1 s (12× slower) |

`llama3.1:8b` was **not** re-pulled: 4.7 GB against 7.1 GiB free would have left the host
under any sane disk floor (the Phase 0 risk the plan flagged), and an installed model
qualified on the first attempt.

**Chosen: `ollama/gemma4:latest`.** qwen3.6 is correct but 12× slower — the config comment
claiming it "returns empty" was only partly right, so it was corrected to record the real
measurement rather than the old assumption.

## Tasks Completed

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Qualify a replacement model | Complete | gemma4:latest, measured against both candidates |
| 2 | Single source of truth for the model string | Complete | **Deviated** — see below |
| 3 | Model-availability preflight | Complete | **Deviated** — scoped to Ollama only |
| 4 | Fix the unawaited coroutine | Complete | Explicit `coro.close()` on both non-awaited exits |
| 5 | Smoke both consumers | Complete | Both drove the live model, neither fell back to `rule` |

## Deviations from Plan

**1. `brain.py` config path was broken (not in the plan).**
`parents[5]` overshot the repo root by one level. Replaced the fixed index with
`_find_agent_config()`, which walks up looking for `agent/config/auton.toml` — index-
independent and survives a src-layout move. Without this, Task 2 would have converted a
silent wrong-model bug into a hard failure on every operator run.

**2. `resolve_model()` moved inside the try in `runner.py`.**
Making `_config_model()` raise `BrainUnavailable` (instead of returning a hardcoded string)
meant `resolve_model()` could now raise. It sat *outside* `_drive`'s try block, so an
unreadable config would have propagated even in `auto` mode, breaking the documented
neural→rule degradation. Moved inside the try.

**3. Preflight scoped to Ollama; the cloud API-key check was not duplicated.**
The plan said "for cloud providers keep the existing API-key check". An early draft added a
key check to `preflight_model` too — that both broke existing mock-based `LLMClient` tests
(which construct with the anthropic default and no key) and recreated in `client.py` the
exact two-sources-of-truth problem this phase exists to remove. `cli.py:81-107` remains the
single place cloud keys are checked.

**4. Four more copies of the dead model string than the plan listed.**
Plan named `auton.toml` and `brain.py:61`. Also found and updated: `test_intent.py:143`
(a live default — now reads config via `resolve_model()`), `resolver.py:162` (docstring),
`intent/__init__.py:8` (usage example), `operator/README.md:22`, and `operator/cli.py:20`
(`--model` help text).

**5. Coroutine tests target `_resolve_via_llm` directly.**
`make_resolver()` has no client-injection seam. Testing through it would have required
widening the production API; testing the private function that actually holds the bug does
not. No production signature was changed.

**6. `agent/config/auton.toml` is gitignored.**
The model change is local-only. `auton.toml.example` (the tracked file a fresh clone gets)
defaults to a cloud model, so it needed no model change — but a note documenting the new
preflight was added so the behavior is discoverable.

## Validation Results

| Level | Status | Notes |
|---|---|---|
| Static analysis (ruff) | Pass | All changed files clean. 52 pre-existing errors remain elsewhere in `orchestrator/` and 5 in untouched controlplane lines — none introduced here, none in files this phase changed |
| Unit tests | Pass | 793 agent + 168 controlplane (8 skipped); **14 new tests** |
| `-W error::RuntimeWarning` | Pass | `controlplane/tests/test_intent.py` exit 0 |
| Live-model tests | Pass | `test_operator.py` live-brain test ran unskipped (6 passed) |
| Integration smoke | Pass | Both consumers, real servers, live model |
| Edge cases | Pass | Missing model, unreachable endpoint, empty tag list, cloud passthrough, cache, `ollama_chat/` prefix |

### Task 5 — Smoke results

**Operator** (`auton-do`, real HTTP file server + real aiosmtpd sink):
```
[brain: llm:ollama/gemma4:latest]
  • download_file  → budget.xlsx, 4865 bytes
  • update_spreadsheet → B2 = 1234
  • send_email → boss@example.com, status: sent
```
Reported `llm:ollama/gemma4:latest`, **not** the `rule` fallback.

**Orchestrator** (real config → `LLMClient` → live model → tool call):
```
config model: ollama/gemma4:latest
preflight: passed
tool calls made: [('write_file', {'path': 'boot/hello.txt', 'contents': 'hello auton'}), ...]
```
Preflight passed and the live model drove the tool with correct arguments. The kernel-
building `auton run` path was deliberately not exercised — the plan forbids changes to the
kernel tree.

### Preflight, verified against the real endpoint
```
ModelUnavailableError: Model 'ollama/llama3.1:8b' is not installed on the Ollama host at
http://localhost:11434. Available: gemma4:latest, qwen3.6:27B, qwen3.6:35B, qwen3.6:latest.
Either run `ollama pull llama3.1:8b`, or set [llm].model in config/auton.toml to one of the
available names.
```
A correct model name is silent.

## Files Changed

| File | Action | Change |
|---|---|---|
| `agent/config/auton.toml` | UPDATED | model → `ollama/gemma4:latest`; comments record the measurement (gitignored) |
| `agent/config/auton.toml.example` | UPDATED | +5 — documents the preflight |
| `agent/orchestrator/llm/client.py` | UPDATED | +69 — `ModelUnavailableError`, `preflight_model`, `_installed_ollama_tags`, `preflight` ctor flag |
| `agent/tests/unit/llm/test_preflight.py` | CREATED | +139 — 11 tests |
| `controlplane/src/controlplane/operator/brain.py` | UPDATED | +101/-9 — path discovery fix, raising `_config_model`, `preflight_ollama` |
| `controlplane/src/controlplane/operator/runner.py` | UPDATED | +5/-2 — `resolve_model` inside the try |
| `controlplane/src/controlplane/intent/resolver.py` | UPDATED | +22/-8 — coroutine lifecycle + docstring |
| `controlplane/tests/test_intent.py` | UPDATED | +97 — 3 coroutine tests, 1 routing test, config-derived live default |
| `controlplane/src/controlplane/intent/__init__.py` | UPDATED | example model string |
| `controlplane/src/controlplane/operator/README.md` | UPDATED | example model string |
| `controlplane/src/controlplane/operator/cli.py` | UPDATED | `--model` help text |

## Tests Written

| Test File | Tests | Coverage |
|---|---|---|
| `agent/tests/unit/llm/test_preflight.py` | 11 | Missing model names the available list and remedy; installed model silent; unreachable endpoint does not raise; empty tag list; cloud not probed; `ollama_chat/` prefix; per-process cache; default endpoint; `LLMClient` construction fails/succeeds; `preflight=False` escape hatch |
| `controlplane/tests/test_intent.py` | 3 new | No `RuntimeWarning` leaks inside a running loop, on the error path, or synchronously — GC forced inside the capture block, since "never awaited" is emitted at finalisation |
| `controlplane/tests/test_intent.py` | 1 new | A dead LLM model still routes via the deterministic backstop |

Preflight tests use a real local HTTP server serving `/api/tags`, matching the repo's
no-mocks convention (`test_operator.py`). The absent-model fixture uses an obviously
fictional tag (`not-a-real-model:v9`) rather than `llama3.1:8b`, so the repo-wide grep
for dead model strings stays genuinely clean and the test's intent is unmistakable.

## Issues Encountered

1. **`parents[5]` off-by-one** — found because removing the hardcoded fallback turned a
   silent fallthrough into a visible test failure. Fixed with an upward search.
2. **Preflight broke existing `LLMClient` tests** — caused by the out-of-scope cloud key
   check; resolved by removing it (see Deviation 3).
3. **`make_resolver` has no client seam** — resolved by testing the private function rather
   than widening the API (see Deviation 5).

## Observation for a Later Phase (not actioned)

`brain.py` rewrites `ollama/` → `ollama_chat/` because that has "the most reliable
tool-calling support in LiteLLM". The orchestrator's `LLMClient` does **not** do this
rewrite, and in the smoke test the model emitted a duplicate `write_file` call after the
observation. This is a real behavioral difference between the two lanes, but changing the
orchestrator's provider prefix is a behavior change beyond this plan's scope. Recommend
addressing in **Phase 8 (orchestrator lane)**.

## Acceptance

- [x] A named local model verifiably drives real tool-calling — `gemma4:latest`, both consumers
- [x] The dead model string exists nowhere as a live default — `grep` returns nothing repo-wide
- [x] Wrong model name fails at preflight with the available list, never mid-run — verified live
- [x] No `RuntimeWarning` from the resolver's LLM path — `-W error::RuntimeWarning` green, 3 targeted tests
- [x] Operator and orchestrator both report `llm:<model>`, not `rule`
- [x] No changes to kernel, SLM pipeline, or the E2E harness

## Next Steps

- [ ] Code review via `/code-review`
- [ ] Commit (note: `agent/config/auton.toml` is gitignored — the model change is local-only,
      so any other machine must set `[llm].model` itself; the preflight now makes that
      failure loud instead of silent)
- [ ] Phase 8: align the orchestrator's Ollama provider prefix with `brain.py`'s
