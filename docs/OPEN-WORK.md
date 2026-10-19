# Open work

Every piece of AUTON that is not finished, what blocks it, and the exact next step. All 102
completed plans and all original PRDs are closed (`.claude/PRPs/plans/completed/`,
`.claude/PRPs/prds/completed/`), and
[`auton-completion.prd.md`](../.claude/PRPs/prds/completed/auton-completion.prd.md) carries what is left
of that work, phase by phase, with the gate that decides each one.

One PRD of **new** scope was opened on 2026-09-24:
[`auton-application-to-environment.prd.md`](../.claude/PRPs/prds/completed/auton-application-to-environment.prd.md)
— give AUTON an application repository that already exists and a machine, and have an Analyst
agent work out what it needs and hand the existing swarm a manifest. Its phases are not listed
in the blocker tables below, because they are unstarted rather than blocked: nothing stands in
their way but the decision to begin. Its **three** owner decisions are in [decide](#decide).

Nothing here is blocked on something unnamed. Three kinds of blocker:

- **run** — a generation run. The spec, the gate and the pre-registration exist; it is one
  command. See `GENERATION-QUEUE.md`.
- **decide** — a person has to choose. The question is written down, with what it depends on.
- **hardware** — a machine this project does not have.

## State 2026-10-19

- **The campaign restarted on a local model** (`ollama_chat/qwen3-coder:30b`; no subscription), attempts
  counting from 1; its record is in `reports/w25-campaign-attempt3-preregistration.md` (amendment
  2026-10-19). R13, the `cpu` subsystem, joined it: its frozen host suite scores 13/13 on injected
  bugs (`tests/kernel/run_cpu_test.sh`).
- **w26 closed in code:** the kernel-tree default is `.artifacts/kernels/x86_64` (C5); the `slm_spec`
  bodies match what ships (C7); `scripts/e2e.sh --rung 3b` trains `chat_tiny` on the kernel set (C3);
  the vendor agents have write roots, the SLM roles have no shell, `auton run` exits 1 on failure.
  SLM chat quality (C1) has a first measurement and a decision (train on `os_chat` alone until
  `cpu_has()` exists); the 10% garbage bar needs a person's `--review`.

## State 2026-10-17

- **R1 attempt 3 stopped by the owner** before a result, to save subscription usage. It ran
  on a Linux x86_64 cloud host (amendment in
  `reports/w25-campaign-attempt3-preregistration.md`); its directory is archived as
  `.artifacts/campaign-stopped-by-owner-2026-10-17/`. Both R1 attempts of this experiment
  remain unspent.
- **Harness fixes found getting there:** `boot-marker.sh` used BSD-only `mktemp -t` (every
  boot gate would have read "not generated" on Linux); new workspaces now start on `main`
  whatever the host's default branch is; `campaign.py` refuses to start without the session
  interpreter or `auton.toml` (a fresh clone spent both attempts in a minute).
- **A changed experiment from here on.** The example config now enables the 24 specialists,
  and `run_gate`-era prompts differ from the 2026-10-10 campaign's. The next campaign
  attempt needs its own pre-registration saying so.

**Drift audit (w26):** [`w26-drift-and-slm-readiness`](../.claude/PRPs/plans/w26-drift-and-slm-readiness.plan.md)
lists 20 places where docs, specs and code disagreed, with evidence; 10 are fixed, the rest
have a next step. The SLM swarm could not have run a single tool before it.
Its Part D reviews the w26 changes themselves: 51 confirmed findings, the fixes, and what is
still open (the corpus's per-id vendor names, `vendor_fetch.py`'s redirects, per-role write
roots for the vendor agents, the SLM roles' `shell`, `auton run`'s exit code).

New work, none of it blocked:

| What | Next step | Where |
|---|---|---|
| Vendor coverage | 5,146 of 5,164 registry vendors have no inventory record. Run the Vendor Scout, CPU vendors first (`vendor_queue`) | `scripts/vendor_research.py start` |
| Verify the instruction exceptions | 9 rows in `exceptions.yaml` are `verified: false`; each names the vendor document to check. Spec Reader | `agent/hardware/isa/exceptions.yaml` |
| IBM | POWER is in the inventory (`ibm-openpower`, Power ISA); IBM Z has instruction tables (LLVM) but no inventory record. Scout both | `vendors.yaml` |
| `cpu` subsystem | Specified (`subsystems/cpu.md`): baseline ISA only, everything else behind `cpu_has()`. Needs a frozen host suite (fake `cpuid()`), then a generation run | `tests/kernel/` |
| SLM chat quality | Best kernel model: 78% correct-or-honest, 22% garbage (bar: <10%). Train on the kernel set (`os_chat` + `hardware_kernel`, 929 words; 90 of the 1,019 word slots left) with `scripts/slm_run.py`; add phrasings for what the eval fails | `SLM/DATA.md` |
| Kernel tokenizer | Word-level, 1,024 words. Subword would let the 2.8M words of fetched domain text help; it is a kernel change. **Owner decision** | `SLM/DATA.md` |
| Hardware reference corpus | 30,848 rows; does **not** fit the kernel tokenizer (15% `<unk>`). For a host-side model only | `SLM/datasets/hardware_reference.jsonl` |

## run

**State 2026-10-07** (`scripts/campaign.py --status` is the source of truth): R8 passed. R1, R2
and R3 failed both attempts and their dependants continued on the last good tree; R6 attempt 2 is
running. R4, R5, R7 and R9–R12 have not started. The table below lists what each run is and the
gate that decides it, not whether it has run.

Generation works: on 2026-09-22 `qwen3.5:27b` wrote a 430-line TFTP server that passes all 31
checks of a suite it never saw (`.claude/PRPs/reports/w14-f6-qwen-report.md`). Each row below is
the same shape of task, and each is one command.

| What | Blocked because | Gate that decides it |
|---|---|---|
| Memory manager (F3/B2) | not yet run on a qualified model | `run_mm_test.sh`, `run_vmm_test.sh`, the `[MM]` boot line |
| Storage: virtio-blk + FAT32 (F7) | not yet run | `run_virtio_blk_test.sh`, `run_fat32_test.sh`, `run-storage-acceptance.sh` |
| File server (F8) | needs storage first | `run_fileserver_test.sh`, then `--service fileserver` |
| KV store (F9) | needs storage first | `run_kvstore_test.sh`, then `--service kvstore` (two boots, redis-cli) |
| Email (F11) | needs storage first | `run_smtp_test.sh`, then `--service smtp` (two boots, smtplib) |
| Repo server (I2) | needs storage first | `run_host_repo_test.sh --clone`, then `run-intent-probe.sh host-repo` |
| SSH (F12) | needs storage first; **the crypto gate already said GO** | `run_ssh_test.sh` (28 checks) |
| VirtIO console (V8) | not yet run | `run_virtio_console_gate_test.sh` (29 checks, frozen before any run) |
| aarch64 arch layer (D2) | not yet run | `run_dtb_test.sh` in tree mode, `[gate: hal]`, `e2e.sh --arch aarch64` |
| F00F mitigation (H7) | needs the memory manager's `vmm_protect` | the mitigation's own `verify` |
| Conformance in every image (H10c) | needs a generated tree to put it in | `conformance_select.py` already chooses the checks |

## decide

| Question | Who | Written up in | What turns on it |
|---|---|---|---|
| The Doom engine's licence | owner | `agent/kernel_spec/decisions/doom-engine-licence.md` | **Distributing** a Doom image. Building and probing one locally is not blocked |
| Where a fleet conformance report goes, if anywhere | owner | `agent/kernel_spec/decisions/fleet-endpoint.md` | Nothing else: the format, the consent flow and the local aggregator are built, and the tool has no network code at all |
| Push this branch | owner | — | **Done 2026-09-23.** CI now runs; what it found is tracked above |
| First substrate for application-to-environment: container or microVM | owner | [`decisions/first-substrate.md`](../agent/kernel_spec/decisions/first-substrate.md) | Phase A5 of the application-to-environment PRD. Everything before A5 is substrate-agnostic, so this can wait until A4 |
| How far to go on syscalls and seccomp | owner | [`decisions/syscall-scope.md`](../agent/kernel_spec/decisions/syscall-scope.md) | Whether that PRD attempts syscall extraction at all. A seccomp profile that is *almost* right is an outage with a confusing error message |
| Is a subject application repository trusted? | owner | [`decisions/subject-trust.md`](../agent/kernel_spec/decisions/subject-trust.md) | Phase A5. An Analyst agent reads files AUTON did not write and feeds them to a model, then runs the application to observe it. A README saying "ignore previous instructions" is a live injection vector into a task graph other agents execute |

## the validation scenarios — the swarm's exam, not its backlog

Six sentences, each one `AUTON train` invocation graded by a probe **outside** the image.
Passing one means the whole chain worked: intent → manifest → spec → generation → gates → boot
→ external proof. They are not features to implement; they are how we find out whether the
swarm works.

| # | Scenario | Probe | Runnable when |
|---|---|---|---|
| C1 | *"I want to play Doom"* | a non-blank frame, and input that changes it | the Doom run (R12) |
| C2 | *"host this repo"* | `git clone` the served URL; tree matches HEAD | the repo-server run (R6) |
| C3 | *"be an email server"* | smtplib delivers; a reboot keeps it | the email run (R5) |
| C4 | *"a database with RBAC and OAuth"* | OAuth round-trip; a low-privilege query refused | **needs TLS** — no phase, deliberately |
| C5 | *"interact with yedgi.com"* | page title matches; a form submits | **needs TLS** |
| C6 | *"my laptop won't connect to wifi"* | the right driver on real silicon; association succeeds | real hardware, and a wifi driver |

C4 and C5 rest on **TLS**, which has no phase on purpose: a TLS stack invented inside a
scenario plan is the mistake `DEFERRED.md` exists to prevent. It needs its own phase with the
SSH crypto gate's rule — reuse or port, never synthesize. The second half of C3 ("receive all
my emails") needs IMAP, which F11 says plainly it does not provide.

## hardware, and the documents behind a paywall of clicks

Each row, as one command and one gate: [`ACQUIRE.md`](ACQUIRE.md).

| What | Needs | Already done |
|---|---|---|
| Driver ↔ erratum join (V10) | **One Intel NIC specification update.** `curl` gets 403 from Intel's CDN and from Mouser's mirror; a person downloads it and `vendor_fetch.py --from-file` ingests it. The nearest real pair is the 82574 (`8086:10d3`), which `e1000e` binds | the join, the record format, and the rule that a field is added only when a real pair needs it |
| Errata lineage (H9) | **Six more Intel spec updates**, one per generation, same download problem | `lineage.py`, `retrodict.py`, the class taxonomy, and tests. Both tools refuse below two documents |
| Real-silicon conformance | an x86 machine to run on | the harness, the oracle, and `CONFORMANCE-HARDWARE.md` stating what emulation cannot answer |
| Proxmox / WSL2 / bare metal | those hosts | `HOST-MATRIX.md` says exactly what each would newly prove |

## What "done" already means here

Every item above has its verification built and passing *before* the thing it verifies exists.
That is deliberate: a suite written after the code tends to agree with it. The suites are
scored by injecting bugs into a known-good implementation and checking each is caught —
including, in one case, bugs injected into an agent's code, which found a gap in a human
suite (`tftp.md` ACK rule 4).

| Area | Suite | Injected-bug score |
|---|---|---|
| TFTP (F6) | 33 checks | 5/5 |
| FAT32 (F7) | 34 checks + mtools oracle + `fsck.fat` | 5/5 |
| KV store (F9) | 31 checks | 9/9 |
| Email (F11) | 32 checks | 9/9 |
| File server (F8) | 29 checks | 8/8 |
| Repo server (I2) | 28 checks + a real `git clone` | 7/7 |
| SSH wire (F12) | 28 checks | 8/8 |
| VirtIO console (V8) | 29 checks | 8/8 |
| Device tree (D2) | 21 checks | 9/9 |
| Allocator (R1) | 29 checks, incl. double free and end-of-RAM | 9/9 |
| Conformance (H10) | 28 clause-cited entries, SoftFloat oracle | 23/23 match bit-for-bit |
