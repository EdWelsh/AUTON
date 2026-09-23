# Plan: Operator E2E Lane — Phase 5

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 5 — Operator E2E lane
**Complexity**: Medium

## Summary

Re-verify "speak a goal, AUTON does the steps" on the current host: the proven Excel scenario
on **both** the live-brain and deterministic-planner paths, plus proof that the approval gate
actually blocks irreversible actions. Depends on Phase 1 (a model that exists); runs parallel
with 3a and 4.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| No-mocks scenario | `controlplane/tests/test_operator.py:1-8` | Real HTTP server serves a real .xlsx; openpyxl really edits; aiosmtpd really captures |
| Brain selection | `operator/runner.py:52-63` | `_drive`: `rule` direct, `llm`/`auto` try `LLMBrain`, `auto` falls back to `RuleBrain` on `BrainUnavailable` |
| Brain provenance | `runner.py:23-25` | `TaskResult.brain` is `"llm:<model>"` or `"rule"` — the assertion hook |
| Approval | `operator/approval.py:8-27` | `terminal_approval` default; `always_deny`; `always_allow` for tests/`--yes` |
| Workspace containment | `operator/tools.py:57-63` | `_resolve()` rejects paths escaping the workspace |
| CLI | `operator/cli.py:18-31` | `goal`, `--brain {auto,llm,rule}`, `--model`, `--yes`, `--smtp-host/port` |

## Files to Change

| File | Action | Why |
|---|---|---|
| `controlplane/tests/test_operator.py` | UPDATE | Un-skip the live-brain test once Phase 1 lands; assert `TaskResult.brain` |
| `scripts/operator-e2e.sh` | CREATE | Drives both paths, callable as an `e2e.sh` stage |

## Tasks

### Task 1: Deterministic-planner path
- **Action**: Run the Excel scenario with `--brain rule`. This path needs no model and is the
  regression floor.
- **Mirror**: the existing no-mocks fixtures — real HTTP server, real aiosmtpd sink.
- **Validate**: mail captured with the edited attachment (B2=1234); `TaskResult.brain == "rule"`.

### Task 2: Live-brain path
- **Action**: Same scenario with `--brain llm` and the Phase 1 model. Must **not** silently
  fall back — that's what `--brain llm` (vs `auto`) is for: `runner.py:60` re-raises rather
  than falling back.
- **Validate**: `TaskResult.brain == "llm:<model>"`; the model really called
  `download_file → update_spreadsheet → send_email`.

### Task 3: Prove the approval gate blocks
- **Action**: Run an irreversible action with `always_deny` and assert it is refused and not
  performed. Then assert the default is `terminal_approval`, not `always_allow`.
- **Why**: `always_allow` exists for `--yes` and tests (`cli.py:28`). A regression that makes
  it the default would be silent and serious.
- **Validate**: denied action does not reach the tool; the mail sink stays empty.

### Task 4: Workspace containment
- **Action**: Assert `_resolve()` rejects `../` escapes and absolute paths outside
  `~/.auton/operator`.
- **Mirror**: `tools.py:57-63` — the check exists; this asserts it stays.
- **Validate**: escape attempts raise rather than write outside the workspace.

### Task 5: Wire into the spine
- **Action**: `scripts/operator-e2e.sh` in the repo's `check()`/`ALL PASS` style.
- **Validate**: green standalone and as an `e2e.sh` stage.

## Validation

```bash
python -m pytest controlplane/tests/test_operator.py -v      # both paths, live test unskipped
scripts/operator-e2e.sh                                      # expect ALL PASS
auton-do --brain rule "download <url>, set B2 to 1234, email boss@example.com"
auton-do --brain llm  "<same goal>"                          # expect brain=llm:<model>
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Phase 1 yields no tool-calling-capable model | **M** | Task 1 (rule path) still delivers; Task 2 skips loudly with the reason recorded |
| Live-brain test is nondeterministic | **H** | Assert the observable outcome (mail with edited attachment), not the model's token sequence |
| A silent `auto` fallback masks a broken llm path | **H** | Use `--brain llm` explicitly and assert `TaskResult.brain` — never accept `auto` as proof |
| aiosmtpd port conflicts | **L** | Ephemeral port from the existing fixture |
| Scenario mutates real state | **L** | Workspace-contained; SMTP goes to a local sink, never a real server |

## Acceptance
- [ ] Excel scenario green on the deterministic-planner path
- [ ] Same scenario green on the live-brain path, asserted via `TaskResult.brain`
- [ ] Approval gate provably blocks a denied irreversible action
- [ ] Default approval is `terminal_approval`, not `always_allow`
- [ ] Workspace escape attempts rejected
- [ ] `scripts/operator-e2e.sh` green standalone and as a stage
