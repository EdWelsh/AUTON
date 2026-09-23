# Plan: LLM Config Repair — AUTON E2E Phase 1

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 1 — LLM config repair
**Complexity**: Small (the fix), Medium (qualifying a model that actually works)

## Summary

The configured local model does not exist on this host, and the failure is silent until an
agent run is already underway. Repair the config, add a preflight that cross-checks it
against `ollama list` and fails with the available options, remove the second hardcoded copy
of the dead model name, and fix the resolver's unawaited-coroutine path. Runs parallel with
Phase 0 — no shared files.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Config load | `agent/orchestrator/cli.py:28-47` | `_load_config()` with `tomllib`/`tomli` fallback, explicit missing-file message |
| Missing-key guidance | `cli.py:98-107` | On absence, print the exact remedy: the config key *and* the env var name |
| Provider env map | `cli.py:81-85` | `PROVIDER_ENV_VARS` dict keyed by provider prefix |
| Model-string resolution | `operator/brain.py:36-61` | `resolve_model(request, default)` → config → hardcoded fallback |
| Ollama tool-calling | `brain.py:79-83` | `ollama/` rewritten to `ollama_chat/` — "most reliable tool-calling support in LiteLLM" |
| Graceful degradation | `brain.py:32`, `runner.py:52-63` | `BrainUnavailable` → `_drive` falls back `auto` → `llm` → `rule` |
| Tests | `controlplane/tests/test_operator.py:1-8` | No mocks; real servers; live-model tests guarded and skipped when unreachable |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/config/auton.toml` | UPDATE | `model = "ollama/llama3.1:8b"` names a model absent from this host |
| `controlplane/src/controlplane/operator/brain.py` | UPDATE | `:61` hardcodes the same dead model as the config fallback — a second source of truth |
| `agent/orchestrator/llm/client.py` | UPDATE | Add the model-availability preflight at client construction |
| `controlplane/src/controlplane/intent/resolver.py` | UPDATE | `:224-245` creates a coroutine that is never awaited when `asyncio.run` raises |
| `controlplane/tests/test_intent.py` | UPDATE | Assert no `RuntimeWarning` escapes the LLM-reachable path |
| `agent/tests/unit/` (new test) | CREATE | Preflight: wrong model name fails fast with the available list |

## Tasks

### Task 1: Qualify a replacement model
- **Action**: Decide empirically, not by preference. Candidates: re-pull `llama3.1:8b`
  (~4.7 GB against 11 GiB free — check the floor first) or qualify `gemma4:latest` (9.6 GB,
  already present). Test each against the actual requirement: **structured tool-calling
  through `ollama_chat/`**, using the operator's real Excel scenario as the probe.
- **Mirror**: `test_operator.py`'s no-mocks live-brain test — it already exercises exactly
  this path end to end.
- **Note**: `auton.toml`'s own comment records that qwen3.6 "burns the whole token budget
  thinking on long agent prompts and returns empty." Treat the two qwen models as
  disqualified unless the probe says otherwise.
- **Validate**: the chosen model drives `download_file → update_spreadsheet → send_email`
  to completion via `LLMBrain`, not the rule fallback.

### Task 2: Single source of truth for the model string
- **Action**: Update `auton.toml`, and change `brain.py:61`'s hardcoded
  `return "ollama/llama3.1:8b"` so the fallback cannot silently diverge from config again —
  either derive it from a shared constant or fail explicitly when config is unreadable.
- **Mirror**: `brain.py:36-61` `resolve_model` structure; keep the "use chatgpt" override.
- **Validate**: `grep -rn 'llama3.1:8b' --include=*.py --include=*.toml` returns only
  intentional documentation references.

### Task 3: Model-availability preflight
- **Action**: Before the first completion, verify the configured model is reachable. For
  `ollama/*`, query the endpoint from `[llm.endpoints].ollama` and compare against the
  installed tags; on mismatch raise with the configured name **and the available list**.
  For cloud providers keep the existing API-key check.
- **Mirror**: `cli.py:98-107` — name the exact remedy, both config key and env var.
- **Why**: today the failure surfaces as an empty completion or a connection error deep in
  an agent run. `client.py:165` already special-cases ollama errors, which is where the
  symptom currently lands.
- **Validate**: a deliberately wrong model name fails at construction naming the real
  options; a correct one is silent.

### Task 4: Fix the unawaited coroutine
- **Action**: `resolver.py:224` builds a coroutine and passes it to `asyncio.run`; when that
  raises (already inside a running loop, `:233`), the coroutine object is discarded
  unawaited → `RuntimeWarning`. Construct the coroutine only inside the branch that will
  actually await it, or close it explicitly on the fallback path before delegating to
  `_resolve_via_llm_threaded` (`:246`).
- **Mirror**: the existing threaded-fallback shape at `:246-258`; don't restructure it.
- **Validate**: `pytest -W error::RuntimeWarning controlplane/tests/test_intent.py` passes.

### Task 5: Smoke both consumers
- **Action**: One operator goal (`auton-do`) and one orchestrator goal against the live
  model. Record which brain actually served each — `TaskResult.brain` is already
  `"llm:<model>"` or `"rule"` (`runner.py:23-25`).
- **Validate**: both report `llm:<model>`, not the rule fallback. A silent fallback to `rule`
  means Task 1 has not really succeeded.

## Validation

```bash
ollama list                                            # ground truth for what exists
grep -rn 'llama3.1:8b' --include=*.py --include=*.toml . | grep -v '\.venv'
python -m pytest controlplane/tests/test_intent.py -W error::RuntimeWarning -q
python -m pytest controlplane/tests/test_operator.py -q          # live-brain test unskipped
auton-do "download <url> set B2 to 1234 and email boss@example.com"   # expect brain=llm:*
cd agent && python -m pytest tests/unit -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| No installed model does reliable tool-calling | **M** | Rule-brain fallback already exists and is tested. If none qualify, record it: Phase 8 (orchestrator) is cut, Phase 5 runs planner-only |
| Re-pulling llama3.1:8b exhausts disk | **M** | Check the Phase 0 disk floor before pulling; prefer qualifying an installed model |
| Preflight adds latency to every run | **L** | Cache per process; it's one HTTP call to localhost |
| Ollama reachable but model unloaded → long first-token delay | **M** | Generous timeout on the preflight probe; don't mistake a cold start for absence |

## Acceptance
- [ ] A named local model verifiably drives real tool-calling
- [ ] The dead model string exists nowhere as a live default
- [ ] Wrong model name fails at preflight with the available list, never mid-run
- [ ] No `RuntimeWarning` from the resolver's LLM path
- [ ] Operator and orchestrator both report `llm:<model>`, not `rule`
- [ ] No changes to kernel, SLM pipeline, or the E2E harness
