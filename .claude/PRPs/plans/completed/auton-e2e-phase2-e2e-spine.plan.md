# Plan: E2E Spine — AUTON E2E Phase 2

**Source PRD**: `.claude/PRPs/prds/auton-e2e-train-boot-human-test.prd.md`
**Selected Milestone**: Phase 2 — E2E spine
**Complexity**: Large (this is the keystone; every later phase consumes it)

## Summary

One command that runs train → export → parity → ISO → boot → markers → transcript, emits a
verdict and an artifact directory, and exits non-zero on any failure. Built by *wrapping*
the pieces that already work rather than reimplementing them, and by resolving the
duplicated marker list that Phase 0 deliberately left alone.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Staged shell harness | `kernels/x86_64/tests/neural_parity.sh:1-45` | Header comment with a `Usage:` line, `set -uo pipefail`, `${1:?model.bin}` required-arg idiom, `PASS [x] -> y` per case, `fail=1` accumulator |
| Check/report | `scripts/run-acceptance.sh:19-27, 95-101` | `check()` → `PASS`/`FAIL`, `ALL PASS`/`FAILURES` + `exit 1` |
| Venv resolution | `neural_parity.sh:14-16` | `PY="${PYTHON:-$ROOT/.venv/bin/python}"`, absolutized before any `cd` |
| Structured markers | `agent/kernel_spec/tests/acceptance_tests.py:23,34+` | `expected_serial_patterns: list[str]` per case — the canonical source |
| Serial-input quirk | `run-acceptance.sh:57` | `printf '\nbe a web server\n'` — the leading blank line absorbs the dropped first byte |
| Background QEMU + probe | `run-acceptance.sh:56-78` | Launch in background, poll with `/dev/tcp`, `kill`+`wait`, capture to a temp log |
| Toolchain resolution | `scripts/lib/toolchain.sh` (Phase 0) | Source it; never hardcode `CC` |

## Files to Change

| File | Action | Why |
|---|---|---|
| `scripts/e2e.sh` | CREATE | The spine: staged, timed, `--rung` selectable, artifact-emitting |
| `scripts/lib/markers.sh` | CREATE | Read marker sets from the Python source of truth so the list exists once |
| `agent/kernel_spec/tests/acceptance_tests.py` | UPDATE | Add chain markers (`[SLM] Loaded model`, `[SLM] Backend:`); expose the pattern list for shell consumption |
| `scripts/run-acceptance.sh` | UPDATE | Consume `lib/markers.sh` instead of its 12 inline `check` calls |
| `scripts/transcript.sh` | CREATE | Send a sentence list to the booted VM, assert expected substrings |
| `tests/transcripts/boot-basics.txt` | CREATE | The first expectation file (sentence → expected substring) |

## Tasks

### Task 1: Resolve the duplicated marker list
- **Action**: `run-acceptance.sh:29-41` hardcodes 12 markers that `acceptance_tests.py:34+`
  already holds as structured `expected_serial_patterns`. Make the Python file the single
  source; add a small emit mode (e.g. `--list-patterns <case>`) and have `lib/markers.sh`
  consume it.
- **Mirror**: `acceptance_tests.py`'s existing dataclass shape — extend, don't replace.
- **Validate**: `scripts/run-acceptance.sh` behaviour is byte-identical to today; deleting a
  pattern from the Python file changes the shell run's output.

### Task 2: Stage runner skeleton
- **Action**: `scripts/e2e.sh` with numbered stages (`[n/7] name ....... detail`), per-stage
  timing, `--rung {3a,3b,3c}` selecting the training rung, `--skip-train` for iteration, and
  a stage-failure short-circuit that still writes artifacts.
- **Mirror**: `neural_parity.sh`'s header/usage/`set -uo pipefail`/accumulator shape.
- **Validate**: `--help` documents every stage; a forced failure in stage 3 reports stage 3
  and exits non-zero.

### Task 3: Wire the existing pipeline pieces
- **Action**: Call, don't reimplement — `SLM/scripts/train.py --config --dataset --output
  --max-steps` (`train.py:107-113`), `SLM/scripts/export_auton.py --checkpoint --vocab
  --output` (`:108-110`), `kernels/x86_64/tests/neural_parity.sh <model.bin> <ckpt.pt>
  <vocab.json>`, `make -C kernels/x86_64 iso-neural MODEL=...`.
- **Mirror**: `scripts/build-iso.sh:5-6` — "mirrors the Makefile target rather than
  reimplementing it."
- **Note**: parity needs `clang` and a torch-capable Python; the preflight must check both.
- **Validate**: each stage produces the artifact the next consumes; no stage duplicates
  logic living in the script it calls.

### Task 4: Transcript runner
- **Action**: `scripts/transcript.sh` reads an expectation file (sentence + expected
  substring), pipes sentences into the booted VM's serial stdin, and asserts per line.
- **Mirror**: `run-acceptance.sh:56-60` for the background-QEMU pattern **and the leading
  blank line** — QEMU drops the first stdin byte after UART init.
- **Validate**: 18/18 on a known-good build; a changed kernel answer fails the specific line.

### Task 5: Artifacts and verdict
- **Action**: `.artifacts/e2e/<ISO-8601>/` holding serial logs per boot, the model manifest
  (`export_auton.py` already writes `.manifest.json`), per-stage timings, and `summary.json`.
  Print `GREEN`/`RED` plus the artifact path. Add a retention cap.
- **Mirror**: `.claude/PRPs/reports/` report style for the human-readable summary — Summary
  section then an "Assessment vs Reality" table.
- **Validate**: 5 consecutive green cold runs under 15 minutes; artifacts present each time.

### Task 6: Preflight integration
- **Action**: Stage 0 calls `scripts/preflight.sh` (Phase 0) extended with `clang`, the torch
  venv, and the disk floor sized for a training run **plus** a second exported model.
- **Validate**: starved disk fails at stage 0, before training burns 10 minutes.

## Validation

```bash
scripts/e2e.sh --help
scripts/e2e.sh --rung 3a                 # expect GREEN, <15 min, artifacts written
scripts/e2e.sh --skip-train              # fast path for iteration
for i in 1 2 3 4 5; do scripts/e2e.sh --rung 3a || echo "FLAKE run $i"; done
scripts/run-acceptance.sh                # unchanged behaviour after Task 1
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| 15-minute budget blown by training | **H** | `--skip-train` reuses the last checkpoint; rung 3a's corpus is 1.7 KB, so training is not the long pole — QEMU boots are |
| Transcript flakes on serial timing | **H** | Leading blank line (proven in `run-acceptance.sh`); poll-with-timeout rather than fixed sleeps; quarantine and report, never silently retry |
| Marker refactor breaks the Docker path | **M** | Byte-identical output is Task 1's acceptance criterion; verify with the daemon up |
| Parity needs clang + torch not present on all hosts | **M** | Preflight names the gap; parity stage skippable with a loud `SKIPPED`, never a silent pass |
| Artifact directory grows unbounded | **L** | Retention cap in Task 5 |
| Spine grows into a build system | **M** | Hard rule: `e2e.sh` calls existing entry points only. Any logic it needs belongs in the tool it calls |

## Acceptance
- [ ] One command runs all seven stages and emits GREEN/RED plus an artifact path
- [ ] Marker list exists in exactly one place
- [ ] 5 consecutive green cold runs, each under 15 minutes
- [ ] A deliberately broken kernel produces RED naming the failing stage
- [ ] Transcript assertions catch a changed kernel answer
- [ ] `run-acceptance.sh` output unchanged
- [ ] No reimplementation of train/export/parity/iso logic
