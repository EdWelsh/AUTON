# Generation Campaign

Twelve generation runs, R1 to R12, each one subsystem or service the swarm must write and a
frozen gate must pass. The campaign is data ([`docs/campaign/runs.yaml`](https://github.com/EdWelsh/AUTON/blob/HEAD/docs/campaign/runs.yaml))
and `scripts/campaign.py` runs it unattended.

## The runs

| Run | What | Gate |
|---|---|---|
| R1 | memory manager (PMM + VMM) | `run_mm_test.sh`, `run_vmm_test.sh`, `[MM]` boot line |
| R2 | storage: VirtIO block + FAT32 | `run_virtio_blk_test.sh`, `run_fat32_test.sh`, storage acceptance |
| R3 | file server | `run_fileserver_test.sh`, `--service fileserver` |
| R4 | KV store | `run_kvstore_test.sh`, two boots and redis-cli |
| R5 | email (SMTP) | `run_smtp_test.sh`, two boots and smtplib |
| R6 | repo server | `run_host_repo_test.sh --clone`, `git clone` probe |
| R7 | SSH | `run_ssh_test.sh` (28 checks), crypto gate GO |
| R8 | VirtIO console | `run_virtio_console_gate_test.sh` (29) — **passed** |
| R9 | aarch64 arch layer | `run_dtb_test.sh`, HAL gate |
| R10 | F00F mitigation | the mitigation's own verify |
| R11 | conformance in every image | `conformance_select.py` |
| R12 | Doom | `run_play_doom_test.sh`, the QMP frame probe |

Order: R1 → R2 → R3–R7 → R9 → R10–R12. A dependant runs on its base run's tree only if that
run passed (or its pre-registered fallback tree), and never on a tree with no source for what
it extends.

## Running it

```bash
.venv/bin/python scripts/campaign.py --status
.venv/bin/python scripts/campaign.py --only r1-mm      # one run
```

Each run's sessions (5 h each, `--resume` between them) and gates land in
`.artifacts/campaign/<run>-attempt<k>/` (the tree is `ws/`). The campaign refuses to start
without its session interpreter (`.venv/bin/python`) or `agent/config/auton.toml`. Killing it
loses nothing; re-running resumes. **It spends model calls for hours**: start one run.

## Stop rules

1. At most two attempts per run; attempt 2 may change the model or budget, never the gate.
2. Exit 2 twice: the phase falls back to human-authored code, labelled, and the ladder continues.
3. Exit 1 twice: the same, and the report quotes the failing assertions.
4. Exit 0: score the generated code against injected bugs beside the reference.
5. A gate defect found mid-run is fixed and re-scored; it is not an attempt.

## History

| Campaign | Result |
|---|---|
| Campaign 1–2 (to 2026-10-10) | **1 of 12** passed (R8). Eleven failures investigated one by one ([w24](https://github.com/EdWelsh/AUTON/blob/HEAD/.claude/PRPs/plans/w24-campaign-failure-investigations.plan.md)): suites using names no spec declared, git plumbing, timeouts, a gate that wrote into the tree. Fixed and tested |
| R1 attempt 3 (2026-10-17) | pre-registered and started on a Linux host; stopped by the owner before a result to save usage; not counted |

The next attempt must be pre-registered as a new experiment: the example config now enables
the 24 specialists.
