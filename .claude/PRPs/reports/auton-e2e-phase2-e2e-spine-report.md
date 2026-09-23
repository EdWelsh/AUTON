# Implementation Report: E2E Spine — AUTON E2E Phase 2

**Plan**: `.claude/PRPs/plans/completed/auton-e2e-phase2-e2e-spine.plan.md`
**Branch**: `feat/e2e-spine` (6 commits, one per task)
**Date**: 2026-09-11

## Summary

`scripts/e2e.sh` runs preflight → train → export → parity → ISO → boot → markers →
transcript in one command, emits GREEN/RED plus an artifact directory, and exits non-zero on
the first failing stage. Built by wrapping the pieces that already worked; no train, export,
parity or ISO logic was reimplemented.

**5 consecutive cold runs, all GREEN, zero flakes, 28–29s each** — 142s for all five against
a 15-minute *per-run* budget. The budget was never the constraint; two fixed-timeout waits
were, and both are gone.

## Assessment vs Reality

| Metric | Predicted (Plan) | Actual |
|---|---|---|
| Complexity | Large (keystone) | Large — accurate |
| Runtime | "<15 min, QEMU boots are the long pole" | 29s. Boots *were* the long pole: 210s of the original 240s was two timeouts nothing was waiting on |
| Files changed | 6 | 9 |
| Training risk | **H** — "15-minute budget blown by training" | Wrong. Training is 6s; it could not run at all until its batch size was fixed |

## Tasks Completed

| # | Task | Commit | Notes |
|---|---|---|---|
| 1 | Resolve the duplicated marker list | `f6ed25d` | Found a real gate hole — see below |
| 2 | Stage runner skeleton | `ca3dc67` | |
| 3 | Wire the pipeline pieces | `f15b714` | Found rung 3a could not train at stock settings |
| 4 | Transcript runner | `d1e0c6b` | 18/18; matcher bug found by its own first run |
| 5 | Artifacts and verdict | `7aa09aa` | 5/5 green cold runs |
| 6 | Preflight integration | `bbc9fea` | Opt-in `CHECK_E2E=1`, floor 5→10 GiB |

## What the plan did not predict

**1. The marker lists had genuinely diverged (Task 1).**
The plan assumed the shell restated a list Python already owned. In fact `run-acceptance.sh`
checked `[BOOT] OK`, which **no AcceptanceTest defined** — the shell was the only thing
verifying it, so the Python gate had a real hole. The two also spelled the PCI pattern
differently (`[0-9]+` vs `\d+`). Python is now a genuine superset: `boot_ok` added, plus the
`slm_model_loaded` / `slm_backend_neural` chain markers Task 1 asked for. Both chain markers
were then confirmed against a real neural boot (`[SLM] Loaded model: auton-slm (fp32)`,
`[SLM] Backend: neural`).

**2. Rung 3a could not train at stock settings (Task 3).**
`os_tasks.jsonl` is 1.7 KB and tokenizes to ~61 tokens; `train.py` requires
`seq_len × batch_size` tokens and rejects the dataset outright at the default 64×32. The
chain had never been run unattended. Defaults are now seq_len=16, batch=2.

**3. Two fixed timeouts dominated the runtime.**
The kernel boots to an interactive prompt and never exits, so both the boot stage and the
transcript waited out their full timeouts — 90s and 120s — for nothing. Boot now polls for
`[BOOT] OK` (4s); the transcript drives QEMU through a fifo and stops it after drain (14s).

**4. A watchdog held the caller's stdout open.**
After fixing the transcript to stop early, it still blocked any caller reading its output
for the full 120s: the watchdog subshell's orphaned `sleep` inherited stdout. Detaching the
watchdog's own stdout fixed it. This would have silently reimposed the old runtime on
`e2e.sh` while the transcript itself looked fast.

**5. The transcript matcher's first run failed on two of its own checks.**
Matching expectations by bare substring found the wrong block: the boot banner (`Type a
request, or 'help'`) and the help listing both quote example commands, including `help` and
`what is pci 8086:100e`. Matching is now anchored to `auton> <sentence>`. Block scoping is
also what makes the stateful pair real — `set hostname web1` → `Hostname is web1.` cannot be
satisfied by the earlier `Hostname is auton.`

**6. One expectation was simply wrong.**
There is no `what is my gateway` command; it falls through to the generic reply. The gateway
is asserted inside the IP answer, where the kernel actually reports it. Also observed and
recorded: `be a web server` / `be a dns server` run until a keypress and swallow the first
byte of the next sentence, so both are excluded from the transcript and left to
`run-acceptance.sh`.

## Validation Results

| Level | Status | Notes |
|---|---|---|
| `e2e.sh --help` | Pass | Every stage and flag documented from the header |
| 5 consecutive cold runs | Pass | 5/5 GREEN, 0 flakes, 28–29s each, 142s total |
| Broken kernel → RED naming the stage | Pass | Corrupt ISO → `failed_stage: "boot"`, markers/transcript SKIPPED |
| Transcript catches a changed answer | Pass | One line fails, reports what the kernel actually said |
| `run-acceptance.sh` | Pass | Same 14 verdicts, ALL PASS, exit 0 |
| Marker list in one place | Pass | Mutation-verified: deleting a pattern fails the suite |
| Starved disk fails at stage 0 | Pass | `MIN_FREE_GB=99999` → exit 1, no training attempted |
| Unit tests | Pass | 800 agent (+7), controlplane green under `-W error::RuntimeWarning` |
| `bash -n` | Pass | All scripts clean |

### Timing breakdown (cold)

| Stage | Seconds |
|---|---|
| preflight | <1 |
| train | 6 |
| export | 2 |
| parity | 2 |
| iso | 0 |
| boot | 4 |
| markers | 0 |
| transcript | 15 |
| **total** | **29** |

## Files Changed

| File | Action |
|---|---|
| `scripts/e2e.sh` | CREATED — the spine |
| `scripts/transcript.sh` | CREATED — chat assertions |
| `scripts/lib/markers.sh` | CREATED — marker loader |
| `tests/transcripts/boot-basics.txt` | CREATED — 18 expectations |
| `agent/kernel_spec/tests/acceptance_tests.py` | UPDATED — `boot_ok`, 2 chain markers, `SERIAL_MARKER_SETS`, `--list-patterns` |
| `agent/tests/unit/test_acceptance_runner.py` | UPDATED — 7 guard tests |
| `scripts/run-acceptance.sh` | UPDATED — consumes `markers.sh` |
| `scripts/preflight.sh` | UPDATED — `CHECK_E2E=1` mode |
| `.gitignore` | UPDATED — `.artifacts/` |

## Deviations

**"Byte-identical" is not claimed.** One echoed line reads `\d+` where it read `[0-9]+` —
equivalent regex, same 14 verdicts, same exit code. Unifying on the Python spelling is the
point of Task 1; forcing Python to `[0-9]+` to preserve an echoed string would invert the
dependency. Flagged rather than glossed.

**Transcript runs against the rule-engine ISO,** not the neural one. Rung 3a trains only far
enough to prove the pipeline — its parity output is degenerate by design — so asserting
conversational answers against it would test nothing. Chat quality is graded in Phase 6.

**Preflight's e2e checks are opt-in.** Making clang and torch unconditional would break the
kernel-only loop for anyone who just builds and boots.

## Acceptance

- [x] One command runs all seven stages and emits GREEN/RED plus an artifact path
- [x] Marker list exists in exactly one place (mutation-verified)
- [x] 5 consecutive green cold runs, each under 15 minutes
- [x] A deliberately broken kernel produces RED naming the failing stage
- [x] Transcript assertions catch a changed kernel answer
- [x] `run-acceptance.sh` output unchanged (one echoed regex re-spelled; verdicts identical)
- [x] No reimplementation of train/export/parity/iso logic

## Next Steps

- [ ] Phase 3a can now consume the spine (`--rung 3a` is live; 3b/3c exit 2 naming their phase)
- [ ] Docker-path non-regression for the marker refactor is still unverified — daemon down,
      same gap Phase 0 left open
