# The generation queue

Every run that is waiting only for a model, with the command to start it and the gate that
decides it. Each is a single command; none needs a decision first.

**Qualify the model before spending a run on it:**

```bash
.venv/bin/python scripts/model-probe.py ollama_chat/qwen3.5:27b
```

Four checks, each a way a local model has actually failed this loop: does it call a tool at
all, does file content survive the round trip, does it still work with a 25 000-character spec
in the prompt, and does it move on after a tool result. Measured 2026-09-22 on an M4 Pro:

| Model | Checks | Slowest call | Note |
|---|---|---|---|
| `ollama_chat/qwen3.5:27b` | **4/4** | 492 s | configured; reached the development phase and merged agent-written code |
| `ollama_chat/qwen3.5:9b` | 4/4 | 285 s | faster; untried on a full run |
| `ollama/gemma4:latest` | 3/4 | 50 s | fails the long-prompt check; four runs produced nothing |

A run's wall-clock is dominated by the per-call time, so budget hours and set `ORCH_TIMEOUT`
accordingly. `[llm].request_timeout` must exceed the slowest call or an agent is killed
mid-thought.

## The protocol, once per run

Defined in `w13-factory-f6-rerun.plan.md` and unchanged since:

1. **Pre-register** before starting: model, budget, goal text, and the gates *in order*, into
   `.claude/PRPs/reports/<run>-preregistration.md`. Predictions are stated in advance so a
   result cannot be reinterpreted afterwards.
2. **Run once.** A second attempt is a different experiment and is labelled as one.
3. **Archive** the transcript, timing, goal, config and branch diffs to `.artifacts/authorship/`.
4. **Gates decide**, in the pre-registered order. Exit 2 means not generated; exit 1 means
   generated wrong. These are different results and are never merged into "failed".
5. **Injected bugs** against whatever was produced, scored beside the human references.
6. **Report** either way, including what the model did instead.

## The queue

| # | Run | Command | Gate that decides it |
|---|---|---|---|
| 1 | **TFTP service** (F6) | `ORCH_CONFIG=<cfg> scripts/orchestrate-native.sh "$(cat goal.txt)"` | `KERNEL_TREE=<ws> tests/kernel/run_tftp_test.sh` (31 checks, frozen) |
| 2 | **Memory manager** (F3/B2) | same, mm goal | `run_mm_test.sh`, then `run_vmm_test.sh`, then the `[MM]` boot line |
| 3 | **Storage** (F7) | same, storage goal | `run_virtio_blk_test.sh`, `run_fat32_test.sh`, then `scripts/run-storage-acceptance.sh <ws>` |
| 4 | **File server** (F8) | build after 3 | `run_fileserver_test.sh`, then `run-storage-acceptance.sh <ws> --service fileserver` |
| 5 | **KV store** (F9) | build after 3 | `run_kvstore_test.sh`, then `--service kvstore` (two boots, redis-cli) |
| 6 | **Email** (F11) | build after 3 | `run_smtp_test.sh`, then `--service smtp` (two boots, smtplib) |
| 7 | **Repo server** (I2) | build after 3 | `run_host_repo_test.sh`, then `run_host_repo_test.sh --clone`, then the intent probe |
| 8 | **SSH** (F12) | build after 3 | `run_ssh_test.sh` (28 checks); the crypto gate already returned **GO** |
| 9 | **VirtIO console** (V8) | same, console goal | `run_virtio_console_gate_test.sh` (29 checks, frozen before the run) |
| 10 | **aarch64 arch layer** (D2) | same, aarch64 goal | `run_dtb_test.sh` in tree mode, `[gate: hal]`, then `scripts/e2e.sh --arch aarch64` |
| 11 | **F00F mitigation** (H7) | after 2 (needs `vmm_protect`) | the mitigation's own `verify`; steps 1–2 can pass under QEMU, step 3 needs a family-5 Pentium |
| 12 | **Doom** | after 3 | a non-blank frame and accepted input, via QEMU's monitor. **Building is unblocked; distributing is not** — `kernel_spec/decisions/doom-engine-licence.md` |

## What every gate already refuses

Each suite distinguishes *absent* from *wrong*, and both from *passing*:

- **exit 2** — the component was not generated. A suite that did not run has found nothing, and
  is never counted as a pass.
- **exit 1** — it exists and is wrong, with the expected value printed beside the observed one.
- **exit 0** — it passes, and the injected-bug score for that suite says what passing is worth.

The loop itself refuses more than it used to, and every refusal came from a real failure:

- C that does not compile never reaches a reviewer (`syntax_gate.py`).
- A driver record the validator rejects never reaches a reviewer either.
- An architect's design is merged only if it compiles.
- Work left uncommitted on a branch is committed to that branch, not lost.
- A branch identical to main is "no output", not a silent success.
