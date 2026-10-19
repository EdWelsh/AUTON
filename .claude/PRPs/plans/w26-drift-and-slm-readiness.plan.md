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
| A2 | SLM integration | "Copy SLM model to kernel workspace" | Copied a **GGUF** to `kernels/<arch>/` relative to the orchestrator's cwd; the kernel loads only the AUTON flat format | `_integrate_slm`; `subsystems/slm.md: MODEL_FORMAT_AUTON` | **FIXED** `3a1b185` (refuses GGUF/ONNX; places `models/auton-slm.bin` in the workspace). Corrected in the review (Part D, #32/#44): the workspace of an `slm_training` run has no kernel, so the model now goes to `[slm] kernel_tree`, and a file is checked by its AUTON magic |
| A3 | SLM prompts | BPE/WordPiece/SentencePiece tokenization; x86_64 → 150M model; "perplexity thresholds" | Word-level tokenizer, 1,024 words; the shipped model is 6M (`chat_tiny`); the bar is the chat eval (≥70% correct-or-honest, <10% garbage) | `prompts.py`, `neural_backend.c: slm_neural_tokenize`, rung-3b report | **FIXED** `3a1b185` |
| A4 | SLM task graph | Quantize "using GPTQ"; "Export to GGUF"; no parity, no chat eval; tasks name no outputs | `quantize.py` is symmetric per-tensor; the kernel needs `export_auton`; parity and the eval are the gates | `task_graph.create_slm_training_tasks` | **FIXED** `3a1b185` (same 7 ids; parity and eval in evaluation; every task has `produces` and criteria) |
| A5 | SLM agents | constructible like every role | Crashed on a `None` arch profile (`.display_name`) | `data_scientist_agent.py` and two siblings | **FIXED** `3a1b185` |
| A6 | SLM workflow tests | "SLM workflow tested" | Tested only the task graph's shape; no tool was ever run | `tests/integration/test_slm_workflow.py` | **FIXED** `3a1b185` (`test_slm_tools_run.py` runs build → budget → tokenize for real) |
| A7 | `agent/slm_spec/*` | GGUF export and loading (export.md: 42 mentions, integration.md: 29), BPE (data_preparation.md), corpora of 100M–50B tokens of Linux source, Stack Overflow and Reddit, model sizes up to 500M | AUTON flat format, word-level 1,024-word tokenizer, ~1,500 ground-truth pairs, 6M model | `slm_spec/*.md` vs `SLM/DATA.md` | **FIXED** 2026-10-19: all seven bodies rewritten to the AUTON format, word-level tokenizer, 65-prompt eval and real commands (C7) |
| A8 | `subsystems/slm.md` overview | "neural backend (GGUF/ONNX model loading)" | `MODEL_FORMAT_AUTON` is the required format; GGUF/ONNX are aspirational (the same file, line 182) | `slm.md:13` vs `slm.md:179-186` | **FIXED** this commit |
| A9 | Hardware reference corpus | (w26 morning) "training data for the SLM" | 13,401 distinct words (13,718 after the review's table fixes); 15% of answer tokens `<unk>` at the kernel's vocabulary; mixing it in pushes the chat corpus to 15% `<unk>` | `SLM/tools/vocab_budget.py` | **FIXED** `a49e90e` (reclassified host-side; a kernel CPU corpus that fits was added) |
| A10 | e2e spine | trains "the SLM" | Trains on the 12-row `os_tasks.jsonl` with `tiny_10M` (rung 3a, a pipeline proof), not the chat corpus | `scripts/e2e.sh:209-210` | **FIXED** 2026-10-19: `scripts/e2e.sh --rung 3b` trains `chat_tiny` on the kernel set (1,024-word vocabulary, 4,000 steps): train, export, parity (ALL PASS), ISO and boot pass; the `[MM]` marker fails only because the base kernel has no memory manager (R1's product) (C3) |
| A11 | Tokenizer parity | Python and kernel tokenize alike | Python `str.split()` splits on any whitespace; the kernel splits on spaces only | `tokenizer.py:122`, `neural_backend.c` | **FIXED** 2026-10-19: `split_words` splits on spaces only, as the kernel does (`SLM/tools/tokenizer.py`); vocabulary unchanged (929 words, 0% `<unk>`); parity must be re-run on the next export |
| A12 | `scripts/eval.sh` | `KERNEL_TREE` selects the tree | The rule-engine fingerprint hashed `kernels/x86_64` whatever `KERNEL_TREE` said; `session.sh` had no override at all | `eval.sh:72`, `session.sh:43-52` | **FIXED** `3a1b185` |
| A13 | Default kernel paths | Kernels live in testing areas (owner rule, `CLAUDE.md`) | 34 script/test references default `KERNEL_TREE` to `kernels/x86_64` at the repo root (gitignored, but not a testing area); docker compose expects it | `grep -rn kernels/x86_64 scripts tests` | **FIXED** 2026-10-19: every script and gate suite, the README, CONTRIBUTING, the issue template and the Rust/Python tool defaults now use `.artifacts/kernels/x86_64`; `kernel-base.sh` still reads the `kernels/x86_64` path inside git revisions, which is history, not a default (C5) |
| A14 | `.amazonq/rules/memory-bank/` | `PHASES.md`, `kernels/` as committed output, the original agent list | None of that exists; it predates every PRD | `structure.md`, `tech.md`, `guidelines.md` | **BANNERED** this commit; **OPEN**: regenerate or delete (owner's IDE config) |
| A15 | `agent/tests/STRUCTURE_COMPLETE.md` | "34 passing placeholders" | 2,084 real unit and integration tests | the file vs `pytest agent/tests` | **BANNERED** this commit as historical |
| A16 | `docs/OPEN-WORK.md` | "All 90 plans … are closed" | 102 plans in `completed/`, 5 open (w18, w23, w24, w25, w26) | `ls plans/completed` | **FIXED** this commit |
| A17 | Campaign experiment | the next attempt is w25 attempt 3 as pre-registered | The example config now enables 24 specialists, so the next attempt differs from what was pre-registered | `auton.toml.example: specialists = "all"` | **OPEN**: pre-register the next attempt with specialists named as the change (B1) |
| A18 | `subsystems/cpu.md` | the kernel answers CPU questions with `cpu_has()` | No kernel implements it; `hardware_kernel.jsonl` assumes one that does | `cpu.md`, `kernel-base-v5` | **OPEN**: frozen host suite, then a generation run (C4) |
| A19 | Vendor coverage | "vendor spec agents built" | Built and tested; never run, so 5,146 of 5,164 registry vendors (5,060 of 5,077 before the review's registry fix, Part D #4) still have no inventory record and all 9 `exceptions.yaml` rows are `verified: false` | `vendor_registry.py --coverage` | **OPEN** (C2): run the Scout and the Reader, small goals first |
| A20 | VirtIO device names | the corpus mirrors what the kernel prints | `device_drivers.py` (the source the factory and `build_corpus.py` read) names 1af4:1000/1001 "Virtio network/block device (transitional)"; `kernel-base-v5`'s `slm.c` still prints the names without "(transitional)". The committed `os_chat.jsonl` had been built before the table changed; regenerated in the review (24 rows) | `device_drivers.py:23-24`, base `slm.c:29-30`, `SLM/tests/test_chat_corpus.py` | **OPEN**, low: the deterministic PCI handler answers these ids before the model, so only the neural fallback differs; the next generated base takes the table's names |

## Part B — the swarms, and what each is set up to do

| Swarm | Roles | Launcher (output in a testing area) | State |
|---|---|---|---|
| Kernel build | manager, architect, developers, **24 specialists**, reviewer (+ checklists), tester, integrator | `scripts/campaign.py` → `.artifacts/campaign/<run>-attempt<k>/ws` | Ready; next attempt needs pre-registration (A17) |
| Hardware research | Vendor Scout, Spec Reader | `scripts/vendor_research.py` → `.artifacts/hardware/<run>/ws` | Ready; never run (A19) |
| SLM | data scientist, model architect, training ×2, integrator | `scripts/slm_run.py` → `.artifacts/slm/<run>/ws` + a base tree for parity and eval | **Ready as of `3a1b185`**; never run |
| Application to environment | analyst, packager | `scripts/app_to_env.py` | Ready (w18–w23) |

The roles the manager assigns work to are constructed, registered and advertised together,
each with a test of all three: the Analyst (`test_analyst_loop.py`), the Packager
(`test_packager_wiring.py`), the Vendor Scout and Spec Reader (`test_vendor_research.py`; a
count of 0 advertises nothing, `test_swarm_wiring.py`) and the specialists
(`test_specialists.py`). The fixed kernel roles are checked for registration
(`test_scheduler_dispatch.py`). The SLM roles are constructed and registered
(`test_dual_workflow.py`; an `slm_training` run end to end in `test_swarm_wiring.py`) but not
advertised: their tasks come from the fixed SLM task graph. (Corrected in the review, #42:
this paragraph said every role, citing `test_slm_workflow.py`, which checks neither.)

## Part C — remaining work, ordered

| # | Task | Gate | Cost |
|---|---|---|---|
| C1 | **2026-10-19 first measurement (OPEN).** `chat_tiny` on the kernel set (4,000 steps, perplexity 1.03): parity ALL PASS; 16 of 65 prompts auto-graded: 12 correct, 4 honest-roadmap, 0 garbage; **49 free-form answers await a person** (`--review`; the raw answers are in `reports/w26-c1-chat-tiny-kernelset-eval.json`). Reading them, about 11 of the 49 are clearly off-topic, e.g. `which roles are available?` → `No. This CPU does not report xop.`, `how long have you been running` → `Yes. This CPU reports msr.`, `ip a`/`lsmod`/`meminfo` → the SSH-role roadmap line. That is over the 10% bar, and the cause is visible: the `hardware_kernel` CPU rows (628, "Yes. This CPU reports X") capture unrelated short prompts. Next: add grounded phrasings for these intents and rebalance CPU rows against chat rows within the 90 free words, then re-measure. **SLM chat quality.** The best kernel model is 78% correct-or-honest, 22% garbage; the bar is <10% garbage. Add ground-truth phrasings for the intents the eval fails (from `.artifacts/eval/` results), within the vocabulary budget (90 words left: 1,024 − 5 special tokens − 929; this said 95 until the review, #10/#40) | `scripts/eval.sh` on `scripts/slm_run.py`'s model; `vocab_budget.py` 0% `<unk>` | one SLM run (CPU training + model calls) |
| C2 | **Vendor coverage.** Scout: CPU vendors first (Cyrix, National Semiconductor, Transmeta, Centaur, DM&P, Hygon, Zhaoxin), then IBM Z. Reader: the 9 unverified exceptions. Their documents with no `fetch_url` (Intel's) must be cached by an operator first, `vendor_fetch.py --vendor <v> --id <doc_id> --from-file <path>`; the Reader's `unverified_exceptions` tool says which | `vendor_research.py collect` PASS; a person merges | model calls; small goals |
| C3 | **DONE 2026-10-19** — **e2e spine on the real corpus** (A10) | `scripts/e2e.sh` parity stage on `chat_tiny` + the kernel set | CPU |
| C4 | **`cpu` subsystem** (A18): `tests/kernel/run_cpu_test.sh` with a fake `cpuid()`, scored by injected bugs, then a generation run | the suite's `--inject` score, then the run's gate | one generation run |
| C5 | **DONE 2026-10-19** — **Default kernel paths** (A13) | every script, docker compose and CI green with the new default | code only |
| C6 | **Decide: word-level or subword kernel tokenizer** (`SLM/DATA.md`). Subword lets the 2.8M words of fetched domain text help an in-kernel model; it changes `slm_neural_tokenize`, the model file and parity | owner decision, then `neural_parity.sh` | owner |
| C7 | **DONE 2026-10-19** — Rewrite the `slm_spec` bodies (A7) to match `SLM/DATA.md` | `grep -c GGUF agent/slm_spec/*.md` only in "host tools" context | docs |
| B1 | Pre-register the next campaign attempt (A17) | the pre-registration exists before the run | docs |

## What is not drift

- `os_chat.jsonl` pinned to QEMU's defaults (IP 10.0.2.15, the e1000 at 8086:100e): that
  is the machine every gate boots, and the corpus says so.
- GGUF/ONNX export tools exist: for host tools, labelled as such.
- `hardware_reference.jsonl` exists: for a host-side model, labelled as such.

## Part D: review of the w26 changes (2026-10-17)

A review of everything w26 changed (`0e6c1ee..c2ae3ea`) confirmed **51 findings**: 6 high,
25 medium, 20 low. Each was reproduced before it was fixed, and each code fix comes with a
test that was run against the old code and failed there. Nothing here was checked by a model-backed run; none was started.

| Group | Findings | What was wrong | What changed |
|---|---|---|---|
| Hardware tables | #1, #3, #6, #7, #9 | RISC-V tables dropped each part's profile base and every `Zvl*b`, so 9 parts lacked I/M/A/C/64bit. `qemu_cpu` took CPUID names from C comments and kept leaf prefixes. Hygon `c86` parts were attributed to Intel. `Geode by NSC` was missing. A `BUG word` header overwrote Transmeta word 2 | `RISCVProfiles.td` is in the inventory and read. The TableGen reader handles `foreach`, and an undefined feature is an error. Comments are stripped. `vendor_of` is an explicit table (unknown → none). Every `.c_ident` is read. `BUG` headers are skipped. Features: x86 236, aarch64 364, riscv 344; 0 unresolved; 29 QEMU models corrected |
| Vendor registry | #4 | Unrelated companies merged (two unknown vendors under `""`) | Only legal-form words are dropped, a hand-checked `SAME_COMPANY` table remains, and each id keeps its own name: 5,164 vendors, 18 covered |
| SLM corpus | #5, #29 | Questions about features no table lists ("is pwr9 64bit": No). `os_chat.jsonl` was stale against `device_drivers.py` | Only listed features are asked. All three generated datasets are regenerated, each with a test that it equals its generator (30,848 reference rows, 13,718 words) |
| Vendor research security | #2, #8, #11, #27, #46, #47 | `resolve()` took absolute refs, so a Spec Reader could cite a document it wrote itself. Redirects left the host allowlist. Fetches had no size cap. A string `page` skipped the quote check | A ref must be `<vendor>/<doc_id>` inside the cache, and its payload must hash to its provenance sha256. Every redirect and the final URL are checked. 128 MiB cap. `page` must be an integer |
| Engine and swarms | #12, #45, #15, #20, #43, #44, #32, #13, #49, #14, #51, #16, #17, #18, #48, #50 | Specialist tasks skipped design. SLM and research runs always ended in a kernel build of an empty workspace, so they always failed. SLM tasks were MERGED unchecked. The model went to a workspace with no kernel. The SLM swarm was told to read files it could not reach, and its outputs could overwrite tracked files. Roles with count 0 were advertised. Branch names collided. The Spec Reader could not see its queue. Hardware records skipped the syntax gate | Specialists are designed. Runs with no kernel end on their own tasks. `produces`, `must_pass` and `must_run` are checked before MERGED. The model goes to `[slm] kernel_tree`, checked by its AUTON magic. Inputs are seeded read-only under `slm/`. Outputs stay in the workspace. Only roles with agents are advertised. Branches use the whole task id. New `unverified_exceptions` tool. `hardware_errors()` runs in the syntax gate |
| Launchers and campaign | #19, #24, #25, #26, #21, #22, #23, #30 | Ctrl-C left the orchestrator running unbounded, and the launchers needed coreutils `timeout`. They ignored `auton.toml`. `collect` counted a file once per branch. R8 was set to re-run. R1's fallback named an unjudged attempt. `wiki.py check` never compared Home's numbers | `run_bounded()` (SIGTERM to the group, SIGKILL after 60 s, exit 124/130). The operator's config is the template. `collect` dedupes by blob. R8 has `skip`, and R1's fallback is `none`, both as dated amendments. A fallback tree must have changed. `check` compares Home |
| Documentation | #10, #40, #28, #29, #31, #32, #33, #34, #35, #36, #37, #38, #39, #41, #42 | Vocabulary headroom given as 95 (it is 90 once the 5 special tokens count). Vendor agents described as confined to their output directory. The architecture diagram still showed 4 trainers, quantize/export agents and GGUF. `cpu.md` claimed a table CPUID bit for `INVARIANT_TSC`. `app_to_env.py` was documented without `--out`. The default `auton run` workspace was wrong. The eval was called 50 prompts (65). Inventory counts and the `--fetch-plan` output were stale. The wiki's campaign order and gates were wrong. The `CAMPAIGN.md` status rows contradicted each other. Every role was said to be tested for advertising | Each doc now states what the code does, re-measured on 2026-10-17: 90 words left; what the file tools enforce; the real SLM pipeline; `0x80000007` EDX bit 8; `--out`; `[workspace].path`; 65 prompts (baselines on 50); 37 vendors and 76 documents; the real refusal text; the runs.yaml order and gates; campaign 1 and 2 labelled; which roles are tested for what. The wiki is rebuilt, and `wiki.py check` is clean |

**Not fixed, and what each needs:**

| # | What remains | Where | Needs |
|---|---|---|---|
| 4 | **DONE** (`vendor_rows` uses each id's own name). Was: the hardware reference corpus still answers every id with the vendor's first name (`e["names"][0]`), not that id's own `name`, so e.g. `AuthenticAMD` can get a PCI spelling | `SLM/tools/build_hardware_corpus.py: vendor_rows` | use `i["name"]` per id, regenerate `SLM/datasets/` |
| 47 | **DONE 2026-10-19** `fetch_url` ran synchronously inside the async tool executor | `agent/orchestrator/agents/base_agent.py` | now `asyncio.to_thread` |
| 47 | `vendor_fetch._download` follows redirects anywhere, with no host check and no size cap | `agent/tools/vendor_fetch.py` | reuse `vendor_research._AllowedRedirects` and `MAX_BYTES` |
| 11, 28 | **DONE 2026-10-19** (write roots: `Agent.write_roots`; Scout `hardware/proposals`, Reader `hardware/derived`; `test_vendor_write_roots.py`). Was: the Scout and the Reader can write anywhere in their workspace, not only `hardware/proposals/` and `hardware/derived/`. `GitWorkspace._resolve` prints the absolute workspace path in a refusal | `vendor_research_agents.py`, `git_workspace.py` | a per-class write root on `write_file` and `edit_file`. Docs now say what is enforced; the `scripts/vendor_research.py` docstring still says "and nowhere else" |
| 43 | **DONE 2026-10-19** (exit 1; `orchestrate-native.sh` reads the log, not the code). Was: `auton run` exits 0 on a failed run | `agent/orchestrator/cli.py` | decide together with `scripts/` callers that read the exit code |
| — | **DONE 2026-10-19** (dropped from the three SLM roles). Was: the SLM roles keep the allowlisted, unsandboxed `shell` (`python`, `cat`), which can write outside the workspace | `tools.py` / role tool lists | drop it, or sandbox it |
| — | **DONE** (`fallback: none`, dated in `runs.yaml`). Was: `r2-storage` still names `tree:r2-storage-attempt2`, campaign 2's tree. `tree_changed` guards it, but there is no dated amendment. The pre-registration says a dependant runs only on a green base; with `none`, dependants run on the last good tree | `docs/campaign/runs.yaml`, pre-registration | an amendment, or an owner decision on the policy |
| — | **DONE 2026-10-19** (`_scout` skipped). Was: `vendor_fetch.cached()` builds `Provenance(**…)` from `_scout` provenance files, which lack vendor, title and form, so `vendor_fetch --list` can crash once a scout fetch exists | `agent/tools/vendor_fetch.py` | skip `_scout`, or filter keys |
| 36 | **DONE** (65). Was: the training agent's prompt still says "50-prompt eval" | `agent/orchestrator/llm/prompts.py:240` | 65 |
| — | Stale figures in code docstrings: `vocab_budget.py` (13,401 words), `vendor_fetch.py` ("43 documents") | those files | **FIXED** (13,718; 76) |
| — | **DONE 2026-10-19** (the cause was `tree_changed` reading the cwd's repo when a result named no base; fixed in `campaign.py`). Was: `test_campaign_fallback.py::test_a_failed_phase_with_a_tree_fallback_is_the_base` fails. Its fixture uses an empty non-git `ws/` as the fallback, which `base_for` now correctly refuses as unchanged | `agent/tests/unit/test_campaign_fallback.py` | a git fixture with a base commit plus one model commit, as in `test_campaign_w25_amendments.py` |
| — | Generated kernels under `.artifacts/` still print "Virtio network device" without "(transitional)" | runtime output, not tracked | none; a kernel generated now matches the corpus |
| — | The documentation fixes have no tests of their own, except Home's numbers (`wiki.py check`) and the dataset regeneration tests | `scripts/wiki.py` | generate the vocabulary headroom, the inventory counts and the campaign table from their sources, as Home's numbers are |
