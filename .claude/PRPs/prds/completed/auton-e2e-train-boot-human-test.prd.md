> **COMPLETE** — all 12 phases (0, 1, 2, 3a–3d, 4–8) implemented, each with an archived plan
> in `plans/completed/` and a report in `reports/`.
>
> **Two of its results were later superseded, and the record should say so:**
>
> 1. **Phase 6's 22% garbage figure was measured with a broken harness.** `eval.sh` sent
>    prompts open-loop and scored undelivered ones as garbage, so a slower model read as a
>    worse one. Fixed in `reports/e2e-intent-scoped-corpus.md`; the harness is now closed-loop
>    and refuses to score a truncated run.
> 2. **The garbage rate is now 12.3%, not 22%** — and not by the route this PRD assumed.
>    Growing the corpus moved it to 21.5% while trading classes against each other; moving
>    retrieval ahead of generation took it to 12.3% (`reports/w5-over-refusal-fix.md`).
>
> Neither invalidates the phases. Both mean a reader should take the *methods* from here and
> the *numbers* from the later reports.

# AUTON End-to-End: Train, Boot, and Talk To It

**Status**: **COMPLETE** — all 12 phases delivered (2026-09-12). Historical record; do not plan from it.

> **Reading note.** This PRD built the verification spine, the graded eval, the session
> harness, and the training pipeline, and it succeeded at that. Two things about it are now
> historical rather than current:
>
> **Its kernel work was hand-written, which contradicts the repo's premise.** Phases 3b–3d
> added +285/−66 lines of kernel C by hand. `README.md:11` says *"We don't write the kernel.
> The agents do."* Those capabilities have since been folded into `agent/kernel_spec/` as
> contracts so agents generate them, and `kernels/` is now gitignored as generated output
> (reference at tag `kernel-reference-v1`, structure at
> `agent/kernel_spec/reference/x86_64/`).
>
> **Its path references are stale.** `kernels/x86_64/tests/` moved to `tests/kernel/`, and
> the spine takes `--target <dir>` rather than assuming `kernels/<arch>`.
>
> What it delivered and that still stands: `scripts/e2e.sh` (10 stages), `scripts/eval.sh`
> (65 graded prompts), `scripts/session.sh`, `scripts/cp-e2e.sh`,
> `scripts/operator-e2e.sh`, the SLM training pipeline, and the recorded baselines in
> `.claude/PRPs/reports/`.
>
> Forward-looking work lives in
> [`auton-service-kernel-factory.prd.md`](../auton-service-kernel-factory.prd.md) (generation)
> and [`auton-intent-to-os-compiler.prd.md`](../auton-intent-to-os-compiler.prd.md) (intent).

## Problem Statement

AUTON has a working chat-OS stack — an in-kernel SLM, a real network stack, a host
control plane, and an operator agent — but every part of it was verified once, by hand,
in a different host state (June 2026), and never again. There is no single command that
takes a model from training to a booted VM a human can talk to, and the one boot path
that exists (Docker-emulated amd64 running QEMU) is currently unavailable on this host.
The cost of not solving it: the project cannot answer "does AUTON still work?" without a
multi-hour archaeology session, and it cannot answer "is the OS any good to talk to?" at all.

## Evidence

- `docker compose run acceptance` — the only automated E2E today — cannot run: the Docker
  daemon is not listening on `/var/run/docker.sock` as of 2026-09-10.
- `/System/Volumes/Data` is **98% full (11 GiB free)**. The same condition previously
  corrupted an `auton-os` containerd blob mid-session and blocked the ~1.5 GiB emulated
  amd64 image build, twice.
- `agent/config/auton.toml` sets `model = "ollama/llama3.1:8b"`. `ollama list` shows only
  `qwen3.6:27B`, `qwen3.6:35B`, `gemma4:latest`. The configured model is **gone**, and the
  file's own comment records that qwen3.6 "burns the whole token budget thinking on long
  agent prompts and returns empty." Both the orchestrator and the operator brain route
  through this config.
- `qemu-system-x86_64` is **not installed on the host** — the kernel can only be booted
  through double emulation (Docker amd64 → QEMU x86) today.
- `SLM/datasets/os_tasks.jsonl` is **1687 bytes**; `SLM/work/vocab.json` is **677 bytes**
  (word-level). The exported `auton-slm.bin` is a 56 MB fp32 model trained on that. It is
  sufficient to prove the export/inference contract and insufficient for free-form human chat.
- Last verified state is recorded only in session memory, not in a runnable artifact:
  "Phase G/H DONE and VERIFIED end-to-end in Docker/QEMU (2026-06-16)". Three months of
  host drift since, zero re-verification.

## Proposed Solution

Build a native-host E2E spine: install the macOS cross-toolchain (`x86_64-elf-gcc`,
`i686-elf-grub`, `xorriso`, `qemu`) so the ISO builds and the VM boots with no Docker and
no double emulation, then wrap the whole chain — train → export → host-parity → ISO →
boot → assert → chat — behind one script that emits a pass/fail and an artifact directory.
On top of that spine, run four verification tiers (markers, scripted transcript, graded
rubric eval, live human session) and climb a four-rung training ladder, each rung a
separately-planned phase so model ambition can be raised or stopped without re-planning
the harness. Chosen over the Docker path because Docker is the single largest source of
observed failure on this host (daemon down, disk exhaustion, blob corruption, emulation
tax) and none of it is essential: the Makefile already defaults `CC` to `x86_64-elf-gcc`.

## Key Hypothesis

We believe a one-command native E2E harness plus a graded chat eval will turn AUTON from
"verified once by hand" into "verifiable on demand" for its developer.
We'll know we're right when a cold `./scripts/e2e.sh` run — no Docker — goes from training
data to a booted VM answering a scripted human transcript in under 15 minutes, and a
graded 50-prompt eval produces a number that moves when the model changes.

## What We're NOT Building

- **Docker removal.** The Docker path stays as a documented fallback and for the OS-image
  backend, which genuinely needs it. Native just becomes the default for the kernel loop.
- **Proxmox / KVM-only OS profiles.** Windows-dockur, Android emulator, macOS-dockur need
  `/dev/kvm`; they are already honestly gated in `controlplane/backends/os/profiles.py`.
  Out of scope until the host loop is trustworthy.
- **A GUI for the OS.** Human interaction is the serial `auton>` REPL. No framebuffer, no
  terminal emulator inside the kernel.
- **Cloud LLM dependency.** Everything runs against local Ollama or the in-kernel SLM.
  Cloud providers stay as an explicit user opt-in ("use chatgpt") in the operator brain.
- **CI.** Single-developer, single-machine for now. The harness must be CI-*shaped* (exit
  codes, artifacts) but no runner is being set up.

## Success Metrics

| Metric | Target | How Measured |
|--------|--------|--------------|
| Cold E2E wall time (native, no Docker) | < 15 min train→boot→assert | `scripts/e2e.sh` self-timing, logged to artifact dir |
| E2E harness exit reliability | 5 consecutive green runs | Repeat runs, no flake quarantine |
| Acceptance markers | 12/12 existing + new chain markers, 100% | `agent/kernel_spec/tests/acceptance_tests.py` |
| Scripted transcript assertions | 100% of expected answers matched | New transcript runner vs expectation file |
| Graded chat eval score | Baseline recorded, then ≥ 70% correct-or-honestly-roadmapped | 50-prompt rubric, scored run |
| Garbage rate (incoherent neural output) | < 10% of prompts | Same rubric, "garbage" bucket |
| Live human session | ≥ 1 unscripted 20-min session per training rung, findings logged | Manual, written up in reports/ |
| Subsystem test suites still green | agent 767, controlplane 158, SLM 72 | Native venv pytest |

## Open Questions

- [ ] Does `i686-elf-grub-mkrescue` on macOS ship the `i386-pc` modules and cooperate with
      Homebrew `xorriso` to produce a BIOS-bootable El Torito ISO? **This is the single
      riskiest unknown in the native plan** — needs a 30-minute spike before Phase 0 commits.
- [ ] Which local model replaces `llama3.1:8b`? Re-pull it (~4.7 GB against 11 GiB free), or
      qualify `gemma4:latest` / a smaller pull for tool-calling reliability?
- [ ] What is the real target corpus for rung 3b? OS/hardware Q&A is a narrow domain with no
      obvious public dataset — synthesize from the kernel's own knowledge base, scrape man
      pages, or generate with a local LLM? TBD, needs research.
- [ ] Does a real tokenizer (BPE) change the `auton_format.py` host↔kernel byte contract, and
      therefore the kernel loader? Suspected yes — vocab is currently word-level.
- [ ] Is 11 GiB free enough to hold a training run's checkpoints + a second exported model +
      an Ollama pull simultaneously? Probably not. Disk budget needs a number.
- [ ] Should the operator agent be reachable from inside the booted OS chat, or does it stay
      host-only? Affects whether Phase 5 is in the VM's E2E path or beside it.

---

## Users & Context

**Primary User**
- **Who**: The AUTON developer (single operator, this machine) — building a chat-based OS
  with an on-device SLM, working in long agentic sessions across weeks.
- **Current behavior**: Verifies by hand — start Docker, hope disk holds, run compose,
  read serial output, pipe sentences into QEMU stdin, eyeball answers. Records the result
  in session memory rather than an artifact.
- **Trigger**: Returning to the project after a gap, or finishing a kernel/model change and
  needing to know whether the whole stack still boots and still answers.
- **Success state**: One command; a green/red answer; an artifact directory to read when red;
  and a number that says whether the model got better or worse.

**Job to Be Done**
When I've changed the kernel or retrained the SLM, I want to run the whole chain and talk to
the result, so I can tell whether AUTON is still a working chat OS and whether it's improving.

**Non-Users**
Not for end users of the OS — nobody is installing AUTON yet. Not for a team; no multi-user
CI, no shared test infrastructure, no onboarding docs for contributors. Not for cloud
deployment.

---

## Solution Detail

### Core Capabilities (MoSCoW)

| Priority | Capability | Rationale |
|----------|------------|-----------|
| Must | Native macOS build+boot (no Docker) | Docker is the top observed failure source; Makefile already defaults to the cross-compiler |
| Must | One-command E2E spine with artifact dir | The whole point — repeatable verification |
| Must | Local LLM config repair + preflight | Orchestrator and operator are both dead until fixed; a preflight stops silent drift recurring |
| Must | Scripted chat transcript runner | Catches regressions in what the OS *says*, not just that it booted |
| Should | Graded rubric eval (50 prompts) | The only measurement of model quality; without it "train the model" has no target |
| Should | Control-plane + operator E2E lanes | User scoped both in; they're the host half of the chat OS |
| Should | Training rung 3b (real dataset + tokenizer) | The rung that makes human chat actually good |
| Could | int8 quantization (rung 3c) | 56 MB → ~14 MB, faster load, lower RAM floor; format already reserves the field |
| Could | Orchestrator agent-loop E2E | Depends entirely on local-model quality; lowest confidence |
| Won't | KVM-only OS profiles, CI runner, kernel GUI | Explicitly deferred above |

### MVP Scope

Phases 0–2 plus training rung 3a: a native toolchain, a repaired LLM config, one script that
runs train(tiny) → export → parity → ISO → boot → 12 markers → scripted transcript, and exits
non-zero on any failure. That alone validates the hypothesis' first half; the eval and the
higher training rungs validate the second.

### User Flow

```
$ ./scripts/e2e.sh --rung 3a
  [0/7] preflight ....... toolchain ok, disk 11.2 GiB ok, ollama gemma4 ok
  [1/7] train ........... SLM/work/final.pt
  [2/7] export .......... auton-slm.bin (56 MB, fp32)
  [3/7] parity .......... token-for-token vs PyTorch: MATCH
  [4/7] iso ............. build/auton-neural.iso
  [5/7] boot+markers .... 12/12 PASS
  [6/7] transcript ...... 18/18 assertions PASS
  [7/7] eval ............ 74% correct, 8% garbage
  GREEN — artifacts in .artifacts/e2e/2026-09-10T14-02/
$ make -C kernels/x86_64 run-neural     # then just talk to it
  auton> what is my ip
  My IP is 10.0.2.15 (gateway 10.0.2.2, dns 10.0.2.3)
```

---

## Technical Approach

**Feasibility**: **HIGH** for the harness and native boot; **MEDIUM** for model quality;
**LOW-confidence** for the orchestrator lane.

**Architecture Notes**
- `kernels/x86_64/Makefile` already defaults `CC` to `x86_64-elf-gcc` and its `iso`/`run`
  targets shell out to `grub-mkrescue` and `qemu-system-x86_64`. Native support is a
  toolchain install plus a `GRUB_MKRESCUE` variable — **not** a Makefile rewrite.
- All required Homebrew formulae verified present in the tap on 2026-09-10: `qemu`,
  `xorriso`, `x86_64-elf-gcc`, `x86_64-elf-binutils`, `i686-elf-grub`.
- The E2E spine wraps existing verified pieces rather than replacing them:
  `SLM/scripts/train.py`, `SLM/scripts/export_auton.py`, `kernel/tests/neural_parity.sh`,
  `make iso-neural MODEL=...`, `agent/kernel_spec/tests/acceptance_tests.py`.
- The host↔kernel model contract is `SLM/tools/auton_format.py` (header + fixed tensor order
  + vocab). Any tokenizer change is a change to *that file and the kernel loader together*;
  `neural_parity.sh` is the guard.
- Chat input to the VM is serial stdin. Known cosmetic defect: QEMU `-serial stdio` drops the
  first stdin byte after UART init — the transcript runner must send a priming newline.
- Control plane and operator are pure host Python (`pip install -e controlplane`) sharing one
  SQLite session at `~/.auton/session.db`; their E2E lanes need no VM and can run in parallel
  with the kernel lane.

**Technical Risks**

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| `i686-elf-grub-mkrescue` can't produce a BIOS-bootable ISO on macOS | **M** | 30-min spike first (Phase 0 gate). Fallback: build ISO once in a slim amd64 container, boot natively — still removes the double-emulation tax |
| Disk exhaustion during training/export/pull | **H** | Preflight asserts a free-space floor and fails fast; artifact dir has a retention cap; document a disk budget before rung 3b |
| No local model gives reliable tool-calling JSON | **M** | Deterministic planner fallback already exists in `operator/planner.py`; orchestrator lane is marked Could, not Must |
| Tokenizer swap breaks the kernel loader | **M** | `neural_parity.sh` runs before every ISO build in the spine; contract change is one atomic commit across host+kernel |
| Trained model is coherent on host but garbage in-kernel | **M** | Parity check is token-for-token, already proven once; keep the rule-engine fallback wired in `slm_process_text` |
| Rung 3b has no viable corpus | **M** | Treated as an open question with its own research step, not assumed away; rung 3a is independently shippable |
| Native x86 QEMU on arm64 is still TCG (slow) | **L** | Accepted — single-layer emulation was already fast enough in the Docker-nested case |

---

## Implementation Phases

<!--
  STATUS: pending | in-progress | complete
  PARALLEL: phases that can run concurrently (e.g., "with 3" or "-")
  DEPENDS: phases that must complete first (e.g., "1, 2" or "-")
  PRP: link to generated plan file once created
-->

| # | Phase | Description | Status | Parallel | Depends | PRP Plan |
|---|-------|-------------|--------|----------|---------|----------|
| 0 | Native bench | Toolchain install + GRUB spike + disk floor; ISO builds and boots with no Docker | complete | - | - | [plan](../../plans/completed/auton-e2e-phase0-native-bench.plan.md) · [report](../../reports/auton-e2e-phase0-native-bench-report.md) |
| 1 | LLM config repair | Pick and qualify a local model; add a preflight that fails loudly on drift | **complete** | with 0 | `ollama/gemma4:latest` qualified | [plan](../../plans/completed/auton-e2e-phase1-llm-config-repair.plan.md) · [report](../../reports/auton-e2e-phase1-llm-config-repair-report.md) |
| 2 | E2E spine | `scripts/e2e.sh`: train→export→parity→iso→boot→markers→transcript, artifacts + exit codes | **complete** | - | 0, 1 | [plan](../../plans/completed/auton-e2e-phase2-e2e-spine.plan.md) · [report](../../reports/auton-e2e-phase2-e2e-spine-report.md) |
| 3a | Training rung: prove pipeline | Retrain tiny on existing corpus, re-verify parity + neural boot | **complete** | with 4, 5 | 2 | [plan](../../plans/completed/auton-e2e-phase3a-training-prove-pipeline.plan.md) · [baseline](../../reports/e2e-rung3a-baseline.md) |
| 3b | Training rung: real chat quality | Corpus research + build, real tokenizer, contract update, train to a quality bar | **complete (bar half met)** | - | 3a, 6 | [plan](../../plans/completed/auton-e2e-phase3b-training-chat-quality.plan.md) · [corpus plan](../../reports/e2e-rung3b-corpus-plan.md) · [attempts](../../reports/e2e-rung3b-training-attempts.md) |
| 3c | Training rung: int8 quantization | Quantize, extend flat format quant path, kernel dequant, re-parity | **complete** | - | 3b | [plan](../../plans/completed/auton-e2e-phase3c-training-int8-quant.plan.md) · [criterion](../../reports/e2e-rung3c-parity-criterion.md) · [results](../../reports/e2e-rung3c-int8-results.md) |
| 3d | Inference hardening | Load time, RAM floor, fallback behavior, garbage-output guards | **complete** | with 3c | 3a | [plan](../../plans/completed/auton-e2e-phase3d-inference-hardening.plan.md) · [results](../../reports/e2e-rung3d-hardening.md) |
| 4 | Control-plane E2E lane | Terminal + UI + desktop over one session; docker/k8s/os/server backends asserted honestly | **complete** | with 3a, 5 | 1 | [plan](../../plans/completed/auton-e2e-phase4-controlplane-lane.plan.md) · [report](../../reports/e2e-phase4-5-lanes.md) |
| 5 | Operator E2E lane | `auton-do` goal → real tools → approval gate, live-model and deterministic-planner paths | **complete** | with 3a, 4 | 1 | [plan](../../plans/completed/auton-e2e-phase5-operator-lane.plan.md) · [report](../../reports/e2e-phase4-5-lanes.md) |
| 6 | Graded chat eval | 50-prompt rubric (correct / honest-roadmap / garbage), scored runner, baseline recorded | **complete** | - | 2, 3a | [plan](../../plans/completed/auton-e2e-phase6-graded-chat-eval.plan.md) · [baselines](../../reports/e2e-eval-baselines.md) |
| 7 | Live human sessions | Unscripted 20-min session per rung; findings logged and fed back | **complete (automated stand-in)** | - | 6 | [plan](../../plans/completed/auton-e2e-phase7-live-human-sessions.plan.md) · [sessions](../../reports/e2e-human-session-all-rungs-2026-09-12.md) |
| 8 | Orchestrator lane (stretch) | Agent loop writes/extends the kernel against the local model | **complete (negative result)** | - | 1, 2 | [plan](../../plans/completed/auton-e2e-phase8-orchestrator-lane.plan.md) · [result](../../reports/e2e-orchestrator-lane.md) |

### Phase Details

**Phase 0: Native bench**
- **Goal**: Build and boot AUTON on macOS with no Docker in the loop.
- **Scope**: `brew install qemu xorriso x86_64-elf-gcc x86_64-elf-binutils i686-elf-grub`;
  a `GRUB_MKRESCUE` Makefile variable; `scripts/auton-boot-native.sh`; a preflight that
  checks toolchain presence and a free-disk floor; README truth-up for the native path.
- **Gate first**: 30-minute spike proving `i686-elf-grub-mkrescue -o test.iso` yields an ISO
  QEMU actually boots. If it fails, switch to the containerized-ISO fallback before writing
  anything else.
- **Success signal**: `make -C kernels/x86_64 run` prints `[BOOT] OK` and an `auton>` prompt
  on the host, Docker Desktop never started.

**Phase 1: LLM config repair**
- **Goal**: The orchestrator and operator brain both talk to a model that exists.
- **Scope**: Qualify a local model for tool-calling/JSON (candidates: re-pull `llama3.1:8b`
  if disk allows, else `gemma4:latest`); update `agent/config/auton.toml`; add a startup
  preflight that cross-checks the configured model against `ollama list` and errors with the
  available list rather than failing mid-run. Also fix the known
  `intent/resolver.py` "coroutine never awaited" RuntimeWarning on the LLM path.
- **Success signal**: one operator goal and one orchestrator smoke goal both complete
  against a live local model; a deliberately-wrong model name fails at preflight, not later.

**Phase 2: E2E spine**
- **Goal**: One command, one verdict, one artifact directory.
- **Scope**: `scripts/e2e.sh` with staged steps and per-step timing; `--rung` selector;
  extend `acceptance_tests.py` with chain markers (`[SLM] Loaded model`, `[SLM] Backend:`);
  a transcript runner (sentence list + expected-substring assertions) that handles the
  dropped-first-byte UART quirk; `.artifacts/e2e/<timestamp>/` with serial logs, model
  manifest, and a summary JSON; non-zero exit on any failure.
- **Success signal**: 5 consecutive green cold runs under 15 minutes, and a deliberately
  broken kernel produces a red run naming the failing step.

**Phase 3a: Training rung — prove pipeline**
- **Goal**: Establish that train→export→parity→boot is reproducible today, unchanged.
- **Scope**: Retrain tiny on `os_tasks.jsonl`, export, run `neural_parity.sh`, boot the
  neural ISO, confirm `[SLM] Backend: neural`. No corpus or format changes.
- **Success signal**: byte-comparable pipeline outcome to the June run; rung 3a is the
  regression baseline everything later is compared against.

**Phase 3b: Training rung — real chat quality**
- **Goal**: A human asking OS questions in their own words gets coherent, correct answers.
- **Scope**: (i) corpus research — decide the source (synthesize from the in-kernel knowledge
  base, man-page mining, or local-LLM generation) and build to a target size; (ii) replace
  word-level vocab with a real tokenizer; (iii) update `auton_format.py` **and** the kernel
  loader in one atomic change; (iv) train the tiny/small config to the eval bar; (v) re-parity.
- **Blocked on**: Phase 6 existing — do not train without the eval, or "better" is unmeasurable.
- **Success signal**: graded eval ≥ 70% correct-or-honest, garbage < 10%, and a live session
  where the developer is not embarrassed by the answers.

**Phase 3c: Training rung — int8 quantization**
- **Goal**: Shrink the boot module and the RAM floor without losing the eval score.
- **Scope**: Use `SLM/scripts/quantize.py`; populate the flat format's reserved quant field;
  add kernel-side dequant in `neural_backend.c`; re-run parity with a documented tolerance
  (exact token match may no longer hold — define the acceptable divergence first).
- **Success signal**: module ≈ 14 MB, boots at a lower `-m`, eval score within 5 points of 3b.

**Phase 3d: Inference hardening**
- **Goal**: The neural backend degrades honestly instead of emitting nonsense.
- **Scope**: Measure load time and RAM floor; verify the rule-engine fallback triggers
  correctly when the module is absent/corrupt/too large; add a guard for degenerate output
  (repetition loops, empty generations) that falls back rather than printing garbage.
- **Success signal**: every failure mode produces a stated fallback, never a garbage answer.

**Phase 4: Control-plane E2E lane**
- **Goal**: The host half of the chat OS is verified as one flow, not 158 unit tests.
- **Scope**: A scripted session hitting terminal (`auton-chat`), UI (`POST /api/chat`), and
  desktop surfaces against one shared `~/.auton/session.db`; assert session continuity across
  surfaces; assert each backend either does the real thing or returns an honest ROADMAP/
  unavailable answer (Docker being down is a *test case*, not a blocker).
- **Success signal**: one command exercises all three surfaces; backend honesty is asserted,
  so a missing tool never silently looks like success.

**Phase 5: Operator E2E lane**
- **Goal**: "Speak a goal, AUTON does the steps" is re-verified on the current host.
- **Scope**: Re-run the proven scenario (download xlsx → set B2=1234 → email via local
  aiosmtpd sink) on **both** the live-brain path and the deterministic-planner path; assert
  the approval gate blocks an irreversible action until confirmed; assert `always_deny` default.
- **Success signal**: both paths green with no mocks; the approval gate demonstrably refuses.

**Phase 6: Graded chat eval**
- **Goal**: A number that moves when the model changes.
- **Scope**: 50 prompts spanning the six intent classes plus out-of-domain; a three-bucket
  rubric (correct / honest-roadmap / garbage); a runner that boots the VM, sends all prompts,
  and scores; baselines recorded for both the rule engine and the rung-3a neural model.
- **Success signal**: two baselines on file; re-running an unchanged model reproduces its
  score within noise.

**Phase 7: Live human sessions**
- **Goal**: Catch what the rubric can't.
- **Scope**: One unscripted 20-minute session per training rung; findings written to
  `.claude/PRPs/reports/`; each finding becomes either a new eval prompt or a defect.
- **Success signal**: every session either produces new eval prompts or explicitly records
  that it found nothing new.

**Phase 8: Orchestrator lane (stretch)**
- **Goal**: The agent loop that writes the kernel runs again locally.
- **Scope**: `docker compose run orchestrate` equivalent, natively, against the Phase 1 model;
  one small real kernel change produced end to end.
- **Success signal**: a committed kernel diff authored by the loop that passes Phase 2.
- **Note**: lowest confidence in the plan — depends on local-model tool-calling quality that
  Phase 1 may not be able to deliver. Cut without regret if 1 lands weakly.

### Parallelism Notes

- **0 ∥ 1** — different subsystems (kernel toolchain vs. host Python config), no shared files.
- **3a ∥ 4 ∥ 5** — once the spine and config exist, the kernel lane, control-plane lane, and
  operator lane touch disjoint code and can be developed together. The control-plane and
  operator lanes need no VM at all.
- **3c ∥ 3d** — quantization is a format/loader change; hardening is a fallback-path change.
  Coordinate only on `neural_backend.c`.
- **Strictly serial**: 0/1 → 2 → 3a → 6 → 3b. The eval must exist before the quality training
  rung, or 3b has no target. This is the one ordering constraint worth defending.

---

## Decisions Log

| Decision | Choice | Alternatives | Rationale |
|----------|--------|--------------|-----------|
| VM target | Native QEMU on the Mac | Docker-hosted QEMU; Proxmox KVM; UTM | User selected; removes double emulation and the top observed failure source. All formulae verified available; Makefile already defaults to the cross-compiler |
| E2E scope | All four lanes (kernel, control plane, operator, orchestrator) | Kernel only | User selected all four. Orchestrator demoted to a stretch phase on feasibility grounds |
| Training ambition | A four-rung ladder, each rung its own phase | Pick one level up front | User asked for a plan for each. Lets ambition rise or stop without re-planning the harness |
| Pass bar | All four tiers (markers, transcript, rubric, human) | Automated only | User selected all four. Each catches a different failure class |
| Eval before quality training | Yes — Phase 6 blocks Phase 3b | Train first, measure later | Without a baseline, "the model got better" is unfalsifiable |
| Docker | Kept as fallback, not default | Remove entirely | The OS-image backend genuinely needs it; only the kernel loop moves off it |

---

## Research Summary

**Market Context**
Not researched — this is a single-developer research OS with no competitive set. The relevant
prior art is convention, not competition: OS kernels are verified by serial-marker acceptance
harnesses (the pattern already in `acceptance_tests.py`), and LLM quality is verified by
graded eval sets rather than assertions. Both conventions are adopted directly.

**Technical Context (verified on this host, 2026-09-10)**
- Homebrew present (6.0.18); `qemu`, `xorriso`, `x86_64-elf-gcc`, `x86_64-elf-binutils`,
  `i686-elf-grub` all available in the tap. `qemu-system-x86_64` not yet installed.
- `kernels/x86_64/Makefile`: `iso` → `grub-mkrescue`, `run`/`run-neural` → `qemu-system-x86_64`
  with `-serial stdio -display none`, `-m 128M`/`256M`. `CC` defaults to `x86_64-elf-gcc`.
- Docker daemon down; data volume 98% full (11 GiB free).
- Ollama up with `qwen3.6:27B/35B`, `gemma4:latest`; `agent/config/auton.toml` references the
  absent `llama3.1:8b`.
- Existing verified assets to wrap, not rebuild: `SLM/scripts/{train,export_auton,quantize}.py`,
  `SLM/tools/auton_format.py`, `kernel/tests/neural_parity.sh`, `make iso-neural`,
  `agent/kernel_spec/tests/acceptance_tests.py` (645 lines, 12 markers),
  `controlplane/` (14 test modules), `controlplane/operator/`.
- Known quirks carried into the plan: QEMU drops the first serial stdin byte after UART init;
  e1000 rings must stay `volatile`; poll loops must `hlt` or SLIRP starves under TCG;
  `net_bringup` must pre-resolve the gateway ARP.

---

*Generated: 2026-09-10*
*Status: DRAFT - needs validation*
