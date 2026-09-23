# AUTON Completion

**Status**: canonical for all remaining work. The five PRDs it consolidates are in
[`completed/`](./completed/) — their phases are done, and every phase that was not is a phase
below, carried over with its evidence.

This document exists because the project stopped being a design problem. Ninety plans are
closed, every specification has a host suite scored by injected bugs, and on 2026-09-22 an agent
wrote a 430-line TFTP server that passed all 31 checks of a suite it never saw
([report](../reports/w14-f6-qwen-report.md)). What is left is **running the swarm, taking three
decisions, and acquiring four things this project does not have.**

## Problem Statement

The kernel does not exist yet, and by design nobody here is going to write it. Everything that
*judges* a kernel exists: specs, gates, oracles, acceptance harnesses, and a loop that refuses
what it should. The remaining question is not "can we build this" but **"can the swarm build it,
and how do we know?"**

The second half of that sentence is what this PRD protects. A generation run that produces code
nobody checked is worth nothing, so every phase below names the gate that decides it *before*
the run happens.

## Evidence this is the right shape

| Fact | Where |
|---|---|
| An agent-authored service passed a frozen human suite it never saw | [w14 F6 report](../reports/w14-f6-qwen-report.md) |
| Four earlier runs on an unqualified model produced zero working lines | [w13 F6](../reports/w13-factory-f6-rerun-report.md), [mm](../reports/w13-generate-mm-report.md), [storage](../reports/w13-generate-storage-report.md), [V8](../reports/w13-driver-v8-rerun-report.md) |
| The difference was measured, not assumed | `scripts/model-probe.py`, four checks a local model has actually failed |
| Two harness defects hid a working result for a day | the TFTP stub shadowed libk; the engine orphaned uncommitted work |

That last row is why the phases below each carry a gate **and** a note on what the gate cannot
see. A suite that cannot fail is not evidence.

## What we are NOT building

- **TLS.** Two scenarios need it (C4, C5 below). It is named here as a dependency and nothing
  more: a TLS stack invented inside a scenario plan is exactly the mistake `DEFERRED.md` exists
  to prevent. It needs its own phase, with the SSH crypto gate's rule — reuse or port, never
  synthesize.
- **IMAP.** F11 receives and stores mail and says so plainly. "Receive all my emails" is
  unmet scope, not an oversight.
- **A wifi driver.** C6 needs one and no hardware here has wifi worth driving.
- **Anything to replace a decision.** Three questions below are the owner's, and a default
  chosen by an agent would be a decision taken quietly.

## Success Metrics

| Metric | Now | Target |
|---|---|---|
| Services generated and passing their gate | 1 of 7 (TFTP) | 7 |
| Generation runs whose result was decided by a pre-registered gate | 5 | every one |
| Validation scenarios passing their external probe | 0 of 6 | 4 of 6 (C4, C5 need TLS) |
| CI workflows that have ever run | 0 | all 4 |
| Suites scored by injected bugs | 10 | stays 10; each new one scored before use |

## Implementation Phases

Three kinds of phase, distinguished because they fail differently: **R** runs the swarm,
**D** needs a person to decide, **X** needs something acquired.

| # | Phase | Gate that decides it | Depends on |
|---|---|---|---|
| R1 | Memory manager (was F3, B2) | `run_mm_test.sh`, `run_vmm_test.sh`, the exact `[MM]` boot line | — |
| R2 | Storage: virtio-blk + FAT32 (was F7) | `run_virtio_blk_test.sh`, `run_fat32_test.sh`, `run-storage-acceptance.sh` | R1 |
| R3 | File server (was F8) | `run_fileserver_test.sh`, then `--service fileserver`: curl retrieves bytes `mcopy` put on the disk | R2 |
| R4 | KV store (was F9) | `run_kvstore_test.sh`, then `--service kvstore`: redis-cli values survive a reboot | R2 |
| R5 | Email (was F11) | `run_smtp_test.sh`, then `--service smtp`: smtplib mail survives a reboot | R2 |
| R6 | Repo server (was I2/H) | `run_host_repo_test.sh --clone`, then `run-intent-probe.sh host-repo` | R2 |
| R7 | SSH (was F12) | `run_ssh_test.sh`; the crypto gate already returned **GO** | R2 |
| R8 | VirtIO console (was V8) | `run_virtio_console_gate_test.sh`, 29 checks frozen before any run | — |
| R9 | aarch64 arch layer (was D2) | `run_dtb_test.sh` in tree mode, `[gate: hal]`, `e2e.sh --arch aarch64` | — |
| R10 | F00F mitigation (was H7) | the mitigation's own `verify`; step 3 needs a family-5 Pentium | R1 |
| R11 | Conformance in every image (was H10c/H10d) | the in-kernel runner passes `run_fault_harness_test.sh` in tree mode | R1 |
| R12 | Doom (was I1/G) | `run-intent-probe.sh doom`: a non-blank frame, and input that changes it | R1, D1 for distribution only |
| D1 | The Doom engine's licence | a written verdict in `decisions/doom-engine-licence.md` | owner |
| D2 | Where a fleet report goes, if anywhere | a written verdict in `decisions/fleet-endpoint.md` | owner |
| D3 | Push the branch | CI runs; four workflows stop being theoretical | owner |
| X1 | Driver ↔ erratum join (was V10) | `errata_join.py` finds a real pair for `e1000e` | one Intel NIC spec update |
| X2 | Errata lineage (was H9) | `retrodict.py` scores a real cutoff against the baseline | six Intel spec updates |
| X3 | Real-silicon conformance (was J/I6) | `run_conformance.sh` does not SKIP, on metal | an x86 machine |
| X4 | Proxmox, WSL2, bare metal (was 0, A3, B1, B4, B5, C2) | each host's row in `HOST-MATRIX.md` stops saying "No" | those hosts |

### The validation scenarios

The intent corpus is **the swarm's exam, not its backlog.** Each scenario is one
`AUTON train` invocation graded by a probe outside the image, and passing one means the whole
chain worked: intent → manifest → spec → generation → gates → boot → external proof.

| # | Scenario | Probe | Runnable when |
|---|---|---|---|
| C1 | *"I want to play Doom"* | non-blank frame; input changes it | R12 |
| C2 | *"host this repo"* | `git clone` the served URL; tree matches HEAD | R6 |
| C3 | *"be an email server"* | smtplib delivers; a reboot keeps it | R5 |
| C4 | *"a database with RBAC and OAuth"* | OAuth round-trip; a low-privilege query refused | **needs TLS** — no phase yet, deliberately |
| C5 | *"interact with yedgi.com"* | page title matches; a form submits | **needs TLS** — no phase yet |
| C6 | *"my laptop won't connect to wifi"* | correct driver for real silicon; association succeeds | X3 plus a wifi driver |

C1–C3 are reachable with what exists. C4 and C5 are the honest edge of the project: they were
written as scenarios and never became phases, and they stay that way until TLS has a phase of
its own.

## Open Questions

1. **Does the swarm's own verification hold up?** The TFTP run produced an implementation but
   never reached its test task. Until an agent writes tests that catch injected bugs, "the swarm
   can build a service" means *the swarm can write code a person's suite approves of*.
2. **How many turns is enough?** 20 ended a run mid-task with working code; 60 is a guess with
   one data point behind it.
3. **Is the faster model enough?** `qwen3.5:9b` also qualifies 4/4 and is roughly twice as fast.
   Nobody has run it on a full task.
4. **What does the architect's scope creep cost?** It rewrote a 709-line unrelated header on a
   TFTP goal. It compiled, so it merged. That is a gate working and a prompt failing.

## Decisions Log

| Decision | Why |
|---|---|
| Consolidate five PRDs into one | Their phases are done. Keeping five documents whose open rows all said "waiting on a generation run" spread one fact across five files |
| Scenarios are validation, not features | They test the chain end to end. Treating them as a backlog produced a row (C4) that would have been "done" by shipping a KV store with no RBAC, no OAuth and no TLS |
| Phases keep their old identifiers in the title | `was F7` costs one phrase and saves a reader who has the old PRD open |
| TLS gets no phase here | Naming a dependency is honest; inventing a crypto stack inside a scenario plan is not |
