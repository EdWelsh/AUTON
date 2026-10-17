# Plan: w26 — drift between docs, specs and code; SLM readiness for the kernel

**Written 2026-10-17**, from an audit of the whole repository after w25 and the hardware,
specialist and vendor-agent work of the same day. Each drift row says what a document or
spec claims, what the code does, the evidence, and whether it is fixed. Fixed rows cite the
commit; open rows name the next step and the gate that closes them.

**Source PRDs:** `prds/completed/auton-completion.prd.md`,
`prds/completed/auton-e2e-train-boot-human-test.prd.md` (the SLM rungs), and the owner's
request of 2026-10-17: every swarm and agent set up for the goal, correct data for a full SLM
in the kernel, a wiki.

## The goal, stated once

Agents write kernels; this repository holds the agents, the specs they are held to, the
gates that judge them and the data they learn from. Every kernel an agent writes lives in a
testing area (`.artifacts/…/ws`), never the tracked tree. The kernel's interface is an
on-device SLM whose facts come from lookups and whose phrasing comes from a model trained on
ground-truth data that fits the kernel's tokenizer.

## Part A — drift found

| # | Area | The doc or spec says | The code does | Evidence | Status |
|---|---|---|---|---|---|
| A1 | SLM swarm tools | `train_model` etc. run the SLM scripts | They ran `python SLM/...` with cwd = the agent workspace, where no `SLM/` exists: every SLM tool failed in a real run | `base_agent.py` SLM executors, `_run_argv` cwd | **FIXED** `3a1b185` |
| A2 | SLM integration | "Copy SLM model to kernel workspace" | Copied a **GGUF** to `kernels/<arch>/` relative to the orchestrator's cwd; the kernel loads only the AUTON flat format | `_integrate_slm`; `subsystems/slm.md: MODEL_FORMAT_AUTON` | **FIXED** `3a1b185` (refuses GGUF/ONNX; places `models/auton-slm.bin` in the workspace) |
| A3 | SLM prompts | BPE/WordPiece/SentencePiece tokenization; x86_64 → 150M model; "perplexity thresholds" | Word-level tokenizer, 1,024 words; the shipped model is 6M (`chat_tiny`); the bar is the chat eval (≥70% correct-or-honest, <10% garbage) | `prompts.py`, `neural_backend.c: slm_neural_tokenize`, rung-3b report | **FIXED** `3a1b185` |
| A4 | SLM task graph | Quantize "using GPTQ"; "Export to GGUF"; no parity, no chat eval; tasks name no outputs | `quantize.py` is symmetric per-tensor; the kernel needs `export_auton`; parity and the eval are the gates | `task_graph.create_slm_training_tasks` | **FIXED** `3a1b185` (same 7 ids; parity and eval in evaluation; every task has `produces` and criteria) |
| A5 | SLM agents | constructible like every role | Crashed on a `None` arch profile (`.display_name`) | `data_scientist_agent.py` and two siblings | **FIXED** `3a1b185` |
| A6 | SLM workflow tests | "SLM workflow tested" | Tested only the task graph's shape; no tool was ever run | `tests/integration/test_slm_workflow.py` | **FIXED** `3a1b185` (`test_slm_tools_run.py` runs build → budget → tokenize for real) |
| A7 | `agent/slm_spec/*` | GGUF export and loading (export.md: 42 mentions, integration.md: 29), BPE (data_preparation.md), corpora of 100M–50B tokens of Linux source, Stack Overflow and Reddit, model sizes up to 500M | AUTON flat format, word-level 1,024-word tokenizer, ~1,500 ground-truth pairs, 6M model | `slm_spec/*.md` vs `SLM/DATA.md` | **BANNERED** this commit (each file says what is current and points to `SLM/DATA.md`); **OPEN**: rewrite the bodies |
| A8 | `subsystems/slm.md` overview | "neural backend (GGUF/ONNX model loading)" | `MODEL_FORMAT_AUTON` is the required format; GGUF/ONNX are aspirational (the same file, line 182) | `slm.md:13` vs `slm.md:179-186` | **FIXED** this commit |
| A9 | Hardware reference corpus | (w26 morning) "training data for the SLM" | 13,401 distinct words; 15% of answer tokens `<unk>` at the kernel's vocabulary; mixing it in pushes the chat corpus to 15% `<unk>` | `SLM/tools/vocab_budget.py` | **FIXED** `a49e90e` (reclassified host-side; a kernel CPU corpus that fits was added) |
| A10 | e2e spine | trains "the SLM" | Trains on the 12-row `os_tasks.jsonl` with `tiny_10M` (rung 3a, a pipeline proof), not the chat corpus | `scripts/e2e.sh:209-210` | **OPEN**: point it at the kernel set with `chat_tiny` (C3) |
| A11 | Tokenizer parity | Python and kernel tokenize alike | Python `str.split()` splits on any whitespace; the kernel splits on spaces only | `tokenizer.py:122`, `neural_backend.c` | **OPEN**, low: tabs and newlines never reach the chat from the serial line; make Python split on `' '` and re-run parity before the next export |
| A12 | `scripts/eval.sh` | `KERNEL_TREE` selects the tree | The rule-engine fingerprint hashed `kernels/x86_64` whatever `KERNEL_TREE` said; `session.sh` had no override at all | `eval.sh:72`, `session.sh:43-52` | **FIXED** `3a1b185` |
| A13 | Default kernel paths | Kernels live in testing areas (owner rule, `CLAUDE.md`) | 34 script/test references default `KERNEL_TREE` to `kernels/x86_64` at the repo root (gitignored, but not a testing area); docker compose expects it | `grep -rn kernels/x86_64 scripts tests` | **OPEN**: move the default to `.artifacts/kernels/x86_64` in one change, with docker compose, README and CI together (C5) |
| A14 | `.amazonq/rules/memory-bank/` | `PHASES.md`, `kernels/` as committed output, the original agent list | None of that exists; it predates every PRD | `structure.md`, `tech.md`, `guidelines.md` | **BANNERED** this commit; **OPEN**: regenerate or delete (owner's IDE config) |
| A15 | `agent/tests/STRUCTURE_COMPLETE.md` | "34 passing placeholders" | 2,084 real unit and integration tests | the file vs `pytest agent/tests` | **BANNERED** this commit as historical |
| A16 | `docs/OPEN-WORK.md` | "All 90 plans … are closed" | 102 plans in `completed/`, 5 open (w18, w23, w24, w25, w26) | `ls plans/completed` | **FIXED** this commit |
| A17 | Campaign experiment | the next attempt is w25 attempt 3 as pre-registered | The example config now enables 24 specialists, so the next attempt differs from what was pre-registered | `auton.toml.example: specialists = "all"` | **OPEN**: pre-register the next attempt with specialists named as the change (B1) |
| A18 | `subsystems/cpu.md` | the kernel answers CPU questions with `cpu_has()` | No kernel implements it; `hardware_kernel.jsonl` assumes one that does | `cpu.md`, `kernel-base-v5` | **OPEN**: frozen host suite, then a generation run (C4) |
| A19 | Vendor coverage | "vendor spec agents built" | Built and tested; never run, so 5,060 of 5,077 registry vendors still have no inventory record and all 9 `exceptions.yaml` rows are `verified: false` | `vendor_registry.py --coverage` | **OPEN** (C2): run the Scout and the Reader, small goals first |

## Part B — the swarms, and what each is set up to do

| Swarm | Roles | Launcher (output in a testing area) | State |
|---|---|---|---|
| Kernel build | manager, architect, developers, **24 specialists**, reviewer (+ checklists), tester, integrator | `scripts/campaign.py` → `.artifacts/campaign/<run>-attempt<k>/ws` | Ready; next attempt needs pre-registration (A17) |
| Hardware research | Vendor Scout, Spec Reader | `scripts/vendor_research.py` → `.artifacts/hardware/<run>/ws` | Ready; never run (A19) |
| SLM | data scientist, model architect, training ×2, integrator | `scripts/slm_run.py` → `.artifacts/slm/<run>/ws` + a base tree for parity and eval | **Ready as of `3a1b185`**; never run |
| Application to environment | analyst, packager | `scripts/app_to_env.py` | Ready (w18–w23) |

Each role is constructed, registered and advertised together, each with a test of all three
(`test_analyst_loop.py`, `test_vendor_research.py`, `test_specialists.py`,
`test_slm_workflow.py`).

## Part C — remaining work, ordered

| # | Task | Gate | Cost |
|---|---|---|---|
| C1 | **SLM chat quality.** The best kernel model is 78% correct-or-honest, 22% garbage; the bar is <10% garbage. Add ground-truth phrasings for the intents the eval fails (from `.artifacts/eval/` results), within the vocabulary budget (95 words left) | `scripts/eval.sh` on `scripts/slm_run.py`'s model; `vocab_budget.py` 0% `<unk>` | one SLM run (CPU training + model calls) |
| C2 | **Vendor coverage.** Scout: CPU vendors first (Cyrix, Transmeta, Centaur, DM&P, Hygon, Zhaoxin), then IBM Z. Reader: the 9 unverified exceptions | `vendor_research.py collect` PASS; a person merges | model calls; small goals |
| C3 | **e2e spine on the real corpus** (A10) | `scripts/e2e.sh` parity stage on `chat_tiny` + the kernel set | CPU |
| C4 | **`cpu` subsystem** (A18): `tests/kernel/run_cpu_test.sh` with a fake `cpuid()`, scored by injected bugs, then a generation run | the suite's `--inject` score, then the run's gate | one generation run |
| C5 | **Default kernel paths** (A13) | every script, docker compose and CI green with the new default | code only |
| C6 | **Decide: word-level or subword kernel tokenizer** (`SLM/DATA.md`). Subword lets the 2.8M words of fetched domain text help an in-kernel model; it changes `slm_neural_tokenize`, the model file and parity | owner decision, then `neural_parity.sh` | owner |
| C7 | Rewrite the `slm_spec` bodies (A7) to match `SLM/DATA.md` | `grep -c GGUF agent/slm_spec/*.md` only in "host tools" context | docs |
| B1 | Pre-register the next campaign attempt (A17) | the pre-registration exists before the run | docs |

## What is not drift

- `os_chat.jsonl` pinned to QEMU's defaults (IP 10.0.2.15, the e1000 at 8086:100e): that
  is the machine every gate boots, and the corpus says so.
- GGUF/ONNX export tools exist: for host tools, labelled as such.
- `hardware_reference.jsonl` exists: for a host-side model, labelled as such.
