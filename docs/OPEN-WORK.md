# Open work

Every piece of AUTON that is not finished, what blocks it, and the exact next step. One file,
because the work left is no longer *design* — the plans that designed it are in
`.claude/PRPs/plans/completed/`, and what remains is running commands and taking decisions.

Nothing here is blocked on something unnamed. Three kinds of blocker:

- **run** — a generation run. The spec, the gate and the pre-registration exist; it is one
  command. See `GENERATION-QUEUE.md`.
- **decide** — a person has to choose. The question is written down, with what it depends on.
- **hardware** — a machine this project does not have.

## run

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
| Push this branch | owner | — | 90 commits have never reached CI. Every workflow here is unrun: the Linux e2e, the 3-OS control-plane matrix, the x86 conformance venues |

## not yet scoped

Two rows of the intent PRD's scenario corpus have no phase, no plan and no code, and should not
be planned until what they rest on does:

| Scenario | What it needs that does not exist |
|---|---|
| *"a database for user info with RBAC and OAuth"* (I4) | **TLS**, OAuth, and a permission model. The KV store is not this, and the SSH gate's primitives (X25519, Ed25519, ChaCha20-Poly1305) are not a TLS stack |
| *"I want to interact with yedgi.com"* (I5) | **TLS**, an HTTP client, and a browser-shaped framebuffer surface |
| *"receive all my emails"* (the second half of I3) | **IMAP**. F11 receives and stores mail and says it has no IMAP; that is scope, not an oversight |

The common blocker is TLS, which deserves its own PRD phase with a gate like the SSH crypto
one — reuse or port, never synthesize — rather than being invented inside a scenario plan.

## hardware, and the documents behind a paywall of clicks

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
| Conformance (H10) | 28 clause-cited entries, SoftFloat oracle | 23/23 match bit-for-bit |
