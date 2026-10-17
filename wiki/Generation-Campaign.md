# Generation Campaign

Twelve generation runs, R1 to R12, each one subsystem or service the swarm must write and a
frozen gate must pass. The campaign is data ([`docs/campaign/runs.yaml`](https://github.com/EdWelsh/AUTON/blob/HEAD/docs/campaign/runs.yaml))
and `scripts/campaign.py` runs it unattended.

## The runs

In the order `scripts/campaign.py` runs them, which is the order of
`docs/campaign/runs.yaml`. A gate decides the run; an advisory suite is recorded and does not.

| Run | What | Base | Gates |
|---|---|---|---|
| R1 | memory manager (PMM + VMM) | `kernel-base-v5` | `run_mm_test.sh`, `run_vmm_test.sh`, the `[MM] PMM initialized` boot line |
| R8 | VirtIO console | `kernel-base-v5` | `run_virtio_console_gate_test.sh`. **Passed** on 2026-10-10; `skip` in this experiment, its verdict stands |
| R2 | storage: VirtIO block + FAT32 | R1 | `run_fat32_test.sh`, `run-storage-acceptance.sh`; advisory: `run_virtio_blk_test.sh` |
| R3 | file server | R2 | `run_fileserver_test.sh`, storage acceptance `--service fileserver` |
| R6 | repo server | R2 | `run_host_repo_test.sh`, then with `--clone` |
| R5 | email (SMTP) | R2 | `run_smtp_test.sh`, storage acceptance `--service smtp` |
| R4 | KV store | R2 | `run_kvstore_test.sh`, storage acceptance `--service kvstore` |
| R7 | SSH | R2 | `run_ssh_test.sh` |
| R12 | Doom | R1 | `run_play_doom_test.sh`, `make iso`, the doom intent probe |
| R11 | conformance in every image | R1 | `run_fault_harness_test.sh` |
| R10 | F00F mitigation | R1 | the boot line `F00F … applied` or `verified` |
| R9 | aarch64 arch layer | `kernel-base-v5` | `run_dtb_test.sh` |

Order: R1 → R8 → R2 → R3 → R6 → R5 → R4 → R7 → R12 → R11 → R10 → R9. A dependant builds on
its base run's tree if that run passed. If it failed, the base run's pre-registered
`tree:<attempt>` fallback is used only when that attempt generated something and its tree
differs from the one it started on (only R2 still names one); otherwise the dependant builds
on the failed run's own base, down to `kernel-base-v5`.

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
