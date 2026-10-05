# Plan: w23 — everything the two open PRDs still need, after w17–w22

## Summary

Eleven of the twelve w17–w22 plans are complete and in `completed/`. What is left falls into
four groups, and they differ in who can move them:

- **A. The larger model:** a local run you can start now.
- **B. The generation campaign (R1–R12)**, carried over from `w18-generation-campaign`, with Doom
  (R12) now testable. Machine time: weeks on this Mac.
- **C. Application-to-environment gaps** found in w22. Code.
- **D. Yours:** decisions and acquisitions no code can close.

The first row of each group is where to start. This plan is to be reviewed with the owner
before execution.

## Metadata
- **Source PRDs**: `auton-completion.prd.md` (R, D, X rows), `auton-application-to-environment.prd.md` (headline metric, D-A1 second substrate)
- **Carries over**: `w18-generation-campaign.plan.md` (not started; remains the campaign's operating procedure)
- **Evidence it rests on**: [w18 live Analyst report](../reports/w18-analyst-live-report.md), [w22 report](../reports/w22-app-three-runtimes-report.md)

---

## A. The larger model

The w22 finding: on this machine `qwen3.5:9b` *packages* reliably (three of three) and does not
*analyse* (0 of 3 within budget). Its failure modes were never writing, running out of budget
while rewriting, and a missing vocabulary kind. The owner has about 42 GB of unified memory
available for a model.

| # | Task | Gate |
|---|---|---|
| A1 | `qwen3.5:27b-coding-mxfp8` (MLX, 30 GB, coding-tuned 27B dense at 8-bit; chosen as the largest that leaves ~12 GB for context). Downloaded 2026-09-30; the older models were removed at the owner's request. | `scripts/model-probe.py`, 4/4 |
| A2 | The fixture Analyst run again: flask-hello, same goal and budget, a pre-registered new experiment | a record merges, and the reviewer, not only the tool, reads it. Watch whether it rejects "needed because the base has it" (run 4's pattern) |
| A3 | **w22 fully agent-driven, again** on A1's model: the three pinned subjects and their frozen probes, no human record | the PRD headline: applications compiled to a running minimal environment, *fully agent-driven*. Today 0 of 3 |

**If A3 is still 0 of 3,** that answers whether local models on this machine can do the
analysis at all. The report says so, and the next lever is the prompt and vocabulary (C1, C2),
not a still-larger model.

## B. The generation campaign, R1–R12

The procedure is unchanged: `docs/CAMPAIGN.md` for order, budgets and stop rules;
`w18-generation-campaign.plan.md` for the tasks. What changes:

| # | Change | Why |
|---|---|---|
| B1 | **Model:** A1's model replaces 9b and 27b in the campaign table, after qualification | the owner asked for the largest model that fits |
| B2 | **R1 attempt 2** runs first, as pre-registered (`reports/w18-r1-mm-9b-preregistration.md`), amended for the model change *before* it starts | a model change after pre-registration is a different experiment and is labelled as one |
| B3 | Sessions of 5 h with `--resume`; each run from a pinned copy of the wrapper; the wall-clock timeout (`3f85080`) | the lessons of w18 runs 2–4 |

### R12 — Doom, now testable end to end

Built this session (`2c9e324`):
- **The gate suite:** `tests/kernel/run_play_doom_test.sh` over the new REQUIRED host-test
  interface in `services/play-doom.md` (key queue, set-1 → doomgeneric translation, centred
  pitch-aware blit, bounded WAD read). Self-test passes; **10/10 injected bugs caught**; runs
  in CI.
- **The probe:** `run-intent-probe.sh doom` via `qmp_probe.py`. It now checks the whole frame,
  and measures idle change as a control, so an animating demo is *inconclusive*, not WORKED.
  Seven tests drive every verdict through a fake QMP monitor.

Still to do for R12:

| # | Task | Gate |
|---|---|---|
| R12.1 | **DONE 2026-09-30** (`test_qmp_probe_live.py`): the crash was the full disk, not macOS; the probe runs live. Against GRUB's menu it reports WORKED with Escape and not-WORKED with no key; `MIN_EXTRA` was calibrated there (1% → 0.2%). Original text: **Fix or characterise the QEMU screendump failure on macOS.** On this Mac, `qemu-system-x86_64 -vga std -display none` crashed on the first QMP `screendump` (`qemu_memfd_alloc … failed to allocate shared memory`). That was seen while the disk was full, so re-test first. If it reproduces with space free, find a display backend that works (`-display vnc=127.0.0.1:N`, `-vga virtio`), or run the probe's QEMU in the Linux container. Validate live against GRUB's menu (a real guest that animates, a countdown, and responds to Escape) before trusting it on Doom | `qmp_probe.py` against a live GRUB menu: exit 0 with Escape, and exit 4 or 3 without it |
| R12.2 | Assets, local only and never committed: doomgeneric (cloned to `.cache/third_party/doomgeneric`, `dcb7a8d`, GPL-2.0) and **Freedoom** (BSD) as `doom.wad` | the build stages them; `package_image.py` records them by name, never embeds them |
| R12.3 | Pre-register, then run R12 after R1 (the allocator). Gates in order: `run_play_doom_test.sh` → build and leakage (`net`/`fs`/`sched`/`ipc` absent) → `run-intent-probe.sh doom` | WORKED: a non-blank frame, and Escape changes it beyond idle animation |
| R12.4 | Scenario C1, *"I want to play Doom"*, end to end through `AUTON train` | the same probe |

Distribution stays blocked on D1. Building and probing locally is not.

## C. Application-to-environment gaps (from w22)

| # | Task | Gate |
|---|---|---|
| C1 | **A capability kind for language packages** (`pypi:`, `npm:`, `go:` modules) in `capabilities.yaml`, with an ablation removal (uninstall, then probe). It is the first thing an Analyst reaches for (`lib:flask`, refused in w22). A reviewed vocabulary edit, not an experiment variable | validator refusal/acceptance tests; one ablation on the fixture |
| C2 | Analyst prompt: say that a line proves only what it says (no "needed because the base has it"), and cap rewrites. Or measure first with A2 and change only what A2 shows | A2's record |
| C3 | **The microVM substrate** (D-A1: "both, container first"): a Packager recipe for Firecracker or QEMU `microvm`, and `app_probe` over the guest's network | the fixture WORKED on a microVM, and ablation runs there too |
| C4 | Leftover review items, LOW: SIGINT handler restoration after `run()` (the asyncio Runner's), `observe.merge` upgrading `declared` → `observed` without keeping the original source, the integrator agent spending 60 turns on `git log` in application runs | a test each |

## D. Yours (the owner's)

| Row | What | Where |
|---|---|---|
| D1 | Doom engine licence: distribution only | `agent/kernel_spec/decisions/doom-engine-licence.md` |
| D2 | Fleet report endpoint, if any | `decisions/fleet-endpoint.md` |
| D3 | Push `feat/prd-completion`, about 60 commits, so CI runs the new suites (the Doom self-test and injected score, the Docker integration tests) | — |
| X1–X4 | Intel NIC and generation spec updates; an x86 machine; Proxmox, Windows 11, bare metal | `docs/ACQUIRE.md`, one command each |

## Found on the w18 campaign (2026-10-03)

| ID | Item | Evidence |
|---|---|---|
| G1 | The mm suite misses two injected bugs, before and after the repair: an absorbed double free (its header claims to catch it; testing an abort needs a fork) and an off-by-one at the end of RAM in `pmm_alloc_contiguous` | [R1 report](../reports/w18-r1-mm-report.md) |
| G2 | The host mm suite can't model `dma_alloc` zeroing through its identity-mapped physical return. Decide whether the suite maps it, or the spec requires zeroing via `phys_to_virt` | R1 diagnostic |
| G3 | `scripts/e2e.sh`'s parity stage fails on `kernel-base-v5`: the current SLM model doesn't load in the base kernel's runtime. Every e2e-based check is blind until this is fixed | R1 gate defect 1 |
| G4 | The swarm's reviewer and tester never run the frozen suites that judge a run. R1's two deviations were one line each, and mm.md's hook paragraph names them | R1 reading |
| G6 | drivers.md must name `tests/kernel/virtio_reference/include/virtio_ref.h`'s `vnr_*` ring API as normative (fs.md does that for `fat32.h`), and goals that build a VirtIO driver should seed it, as R8's did. Until then the ring suite is advisory for R2 | R2 gate review, 2026-10-05 |
| G7 | Host sleep: `caffeinate -s` can't hold off sleep on battery, and a sleep mid-call failed a task. Transient errors are now retried, but long unattended runs need AC power, which `campaign.py` could check and log | R2 `fs-004` |
| G5 | Subscription spend limits: R1 waited about 6.25 h of its 6.7 h on them. Report wait time separately from work time in RESULT.json | R1 metrics |

## Suggested order

1. **A1 → A2** (hours). Does the larger model analyse?
2. **R12.1** (an hour). A probe that crashes on the host is no probe.
3. **A3** (a day). The PRD headline.
4. **B2 (R1)**, then the campaign in `docs/CAMPAIGN.md` order, with **R12** as soon as R1 has
   passed or fallen back.
5. **C1–C4** interleaved while the model is busy (they need no model).
6. **D** whenever you have the time; D3 first, it costs a minute.
