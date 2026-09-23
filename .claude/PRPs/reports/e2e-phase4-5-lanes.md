# Phases 4 & 5 — Control-Plane and Operator E2E Lanes

**Recorded**: 2026-09-12
**Branch**: `feat/cp-e2e-lane` (2 commits)

## Summary

Both host-side lanes now run as one flow and as spine stages. The spine is 10 stages, GREEN
in 88 s.

| Lane | Command | Stage | Result |
|---|---|---|---|
| Control plane | `scripts/cp-e2e.sh` | `[8/10] cplane` | ALL PASS (46 s) |
| Operator | `scripts/operator-e2e.sh` | `[9/10] operator` | ALL PASS (18 s) |

Suites: 181 controlplane passed / 8 skipped, 800 agent, 93 SLM, `run-acceptance` exit 0.

## Phase 4 — Control-plane lane

12 new tests in `controlplane/tests/test_e2e_surfaces.py`:

- **Cross-surface continuity at the ChatEngine level**, not just `SessionStore`. A turn
  written by the terminal is visible to `ui` and `desktop` over one database, each turn
  correctly attributed, and order preserved when surfaces interleave.
- **Backend honesty.** Every discovered capability answers without raising and without an
  empty message. The backend layer's premise is that it never pretends, so a silent failure
  is a worse bug here than a crash — hence an explicit assertion rather than "no exception
  escaped".
- **Entry points.** `repl.run` over explicit streams, the FastAPI app serving a turn another
  surface recorded, desktop guarded by import, and all four console scripts declared.

### Docker down is a passing case, not a blocked run

The daemon is stopped on this host, and that is the *interesting* path:

```
docker      handled=True  'docker list failed: failed to connect to the docker API at unix:///var/run/docker.sock…'
```

It names the daemon. `cp-e2e.sh` prints which path was exercised, because "all backends
honest" means something different with Docker up than down and a reader should not have to
assume the stronger reading.

### Two findings — recorded, not fixed

The plan is explicit that this lane asserts current behaviour and that fixing backends is out
of scope.

| Backend | Finding |
|---|---|
| `kubernetes` | Surfaces `kubectl` stderr verbatim — the same connection error four times with timestamps and goroutine detail. Honest but unusable, and exactly the shape the `CAP_ROADMAP` convention exists to avoid. |
| `status` | Aggregates the other backends, so it inherits the above. **One root cause, not two.** |

Both sit in `RAW_DUMP_KNOWN_GAPS`, guarded from both directions: one test fails if any *other*
backend starts dumping raw tool output, and another fails once a tracked gap is fixed — so
the exemption cannot outlive the defect.

**A wrong first heuristic, corrected.** The initial check flagged `os` and `status` on output
length. That was wrong: `os` lists five environments and `status` reports several tools, both
deliberately. Length is not the signal; log-formatted lines (`E0…`, `W0…`, `Traceback`,
`goroutine`) are.

## Phase 5 — Operator lane

Most of the scenario coverage already existed. The genuine gaps were the safety properties.

- **`TestApprovalDefaults`.** `always_allow` exists for `--yes` and for tests. A regression
  making it the default would be **silent** — every existing scenario would still pass — and
  would mean the OS performs irreversible actions without consent.
  `ToolExecutor` turned out to be stronger than a safe default: `approval` is a *required*
  argument, so a caller cannot construct one without deciding. The test asserts that property
  rather than a default that does not exist.
- **`TestWorkspaceContainment`.** Relative, absolute, and nested escapes, plus a download
  attempting to write outside the sandbox. Driven through `execute()`, the boundary a brain
  actually uses; the bare methods raise `ToolError`.
- **`TestBrainProvenance`.** `TaskResult.brain` is the only proof of which path ran. The
  scenario succeeding is not enough — `auto` silently falls back to the rule engine, so a
  broken LLM path is indistinguishable from a working one. The lane therefore drives
  `--brain llm` explicitly and asserts provenance.

The live-brain scenario ran against `ollama/gemma4:latest` and really called
`download_file → update_spreadsheet → send_email`, with the edited attachment (B2=1234)
captured by a real `aiosmtpd` sink. `operator-e2e.sh` reports whether Ollama was reachable,
because a skipped live path must not read as a verified one.

## Acceptance

**Phase 4**
- [x] A turn is visible across all three surfaces via one session DB
- [x] Every backend either works or refuses with a reason naming what's missing
- [x] All three entry points start, answer, and exit cleanly (or skip loudly)
- [x] `scripts/cp-e2e.sh` green standalone and as an `e2e.sh` stage
- [x] Docker-down is a passing test case, not a blocked run

**Phase 5**
- [x] Excel scenario green on the deterministic-planner path
- [x] Same scenario green on the live-brain path, asserted via `TaskResult.brain`
- [x] Approval gate provably blocks a denied irreversible action
- [x] Default approval is not `always_allow` — it is a required argument
- [x] Workspace escape attempts rejected (relative, absolute, nested, download)
- [x] `scripts/operator-e2e.sh` green standalone and as a stage

## Follow-up worth doing

The kubernetes raw-dump gap is small and self-contained: one refusal string instead of piping
`kubectl` stderr through. Fixing it also fixes `status`. Out of scope here by design, but it
is the most visible honesty wart left in the host plane.
