# Plan: Control-Plane E2E Lane — Phase 4

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 4 — Control-plane E2E lane
**Complexity**: Medium

## Summary

Verify the host half of the chat OS as one flow rather than 158 isolated unit tests: one
scripted session crossing terminal, UI, and desktop surfaces over a single shared session
database, asserting that every backend either does the real thing or refuses honestly.
Needs no VM; runs parallel with 3a and 5.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| No-mocks testing | `controlplane/tests/test_operator.py:1-8` | Real HTTP server, real openpyxl, real aiosmtpd — "no mocks" is the house rule |
| Guarded live tests | same | Skip when the real tool is unreachable; never substitute a mock and call it a pass |
| Honest capability status | `backends/os/profiles.py:19-25` | `REAL` / `NEEDS_KVM` / `EXPERIMENTAL` / `EXTERNAL` — the project's honesty vocabulary |
| Capability contract | `core/` (frozen) | `Capability(name, keywords, status WORKING/ROADMAP, note, handler)`; `Registry` discovers plugins |
| Shared session | `core/session.py:21,44-47` | SQLite WAL at `~/.auton/session.db`; multiple surface processes coexist |
| Testable REPL | `surfaces/terminal/repl.py:25` | `run(engine, in_stream, out_stream)` — explicit streams for testing |
| UI surface | `surfaces/ui/app.py:57-92` | `build_app(db_path)` accepts an isolated temp DB for tests |

## Files to Change

| File | Action | Why |
|---|---|---|
| `controlplane/tests/test_e2e_surfaces.py` | CREATE | The cross-surface flow test that doesn't exist yet |
| `scripts/cp-e2e.sh` | CREATE | One command driving the lane, consumable by `scripts/e2e.sh` |
| `controlplane/tests/test_status.py` | UPDATE | Assert honest refusal when a tool is absent (Docker daemon down is a *case*, not a blocker) |

## Tasks

### Task 1: Cross-surface session continuity
- **Action**: Drive terminal → UI → desktop against one `db_path`; assert a turn written by
  one surface is visible to the next, with the correct `surface` attribution.
- **Mirror**: `repl.py:25`'s explicit streams; `build_app(db_path)`'s temp-DB hook;
  `test_session_continuity.py` already covers part of this — extend rather than duplicate.
- **Validate**: history from `GET /api/history` contains the terminal's turn and vice versa.

### Task 2: Backend honesty assertions
- **Action**: For each backend (desktop, docker, kubernetes, server, status, os), assert the
  response is either a real result or an honest refusal naming what's missing. **Docker
  being down must produce a stated refusal, not an exception or a false success.**
- **Mirror**: `profiles.py:19-25` status vocabulary; `roles.c`'s `CAP_ROADMAP` note convention.
- **Why this matters most**: the backend layer's entire design premise is that it never
  pretends. A silent failure is a worse bug here than a crash.
- **Validate**: with Docker stopped, the docker backend refuses with a reason; with it
  running, it really lists containers.

### Task 3: The three surfaces actually start
- **Action**: Smoke each entry point — `auton-chat` (terminal), `auton-ui` (FastAPI on
  `127.0.0.1:8765`), `auton-desktop` (pywebview window config). Desktop may be
  display-guarded; skip loudly if headless.
- **Validate**: each starts, answers one message, exits cleanly.

### Task 4: Wire into the spine
- **Action**: `scripts/cp-e2e.sh` with the repo's `check()`/`ALL PASS` convention, callable
  as a stage from `scripts/e2e.sh`.
- **Mirror**: `scripts/run-acceptance.sh:19-27, 95-101`.
- **Validate**: green standalone and as an `e2e.sh` stage.

## Validation

```bash
python -m pytest controlplane/tests -q                      # expect 158+ passing
python -m pytest controlplane/tests/test_e2e_surfaces.py -v
scripts/cp-e2e.sh                                           # expect ALL PASS
# honesty check with the daemon deliberately down:
pkill -f "Docker Desktop" 2>/dev/null; scripts/cp-e2e.sh    # expect honest refusals, not errors
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Desktop surface needs a display | **H** | Guarded skip with a loud reason — the repo already has 6 such skips |
| Cross-surface test races on SQLite | **M** | WAL is already enabled; use distinct temp DBs per test and one shared DB only in the continuity test |
| "Honest refusal" is asserted too loosely and passes on an exception | **M** | Assert the *message content* names the missing tool, not merely that no exception escaped |
| Port 8765 already bound | **L** | `AUTON_UI_PORT` override already exists |
| Lane drifts into fixing backends | **M** | This phase asserts current behaviour. Real gaps become findings, not in-scope fixes |

## Acceptance
- [ ] A turn is visible across all three surfaces via one session DB
- [ ] Every backend either works or refuses with a reason naming what's missing
- [ ] All three entry points start, answer, and exit cleanly (or skip loudly)
- [ ] `scripts/cp-e2e.sh` green standalone and as an `e2e.sh` stage
- [ ] Docker-down is a passing test case, not a blocked run
