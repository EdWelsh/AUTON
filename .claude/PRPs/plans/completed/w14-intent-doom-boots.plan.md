# Plan: I1 Doom Boots and Plays (intent-G, part 2)

## Summary
w11 took Doom as far as specification allows: `play-doom.md` written, the i8042 accepted by
recorded decision, `module-asset` specified. It named what remains: a generated tree with
`framebuffer`, `input` and `module-asset`, and a **human licence decision** on doomgeneric
(GPL-2.0) before any image is distributed. This plan generates the three capabilities, ports the
engine *outside* the repo, and grades the image with the PRD's external probe: **a non-blank
frame, and input accepted**. Both are checked by QEMU's monitor, not by reading serial.

## User Story
As a user who runs `AUTON train "I want to play Doom" --output ./Doom`, I want an image that
boots into Doom and responds to keys, so that the headline intent is real.

## Problem → Solution
The package is INCOMPLETE at `[gate: sources]` → a generated tree with `fb`, `ps2`, `pkg_module_asset`;
doomgeneric fetched at build time from a pinned commit (never committed); a boot where QMP
`screendump` shows a non-uniform frame and `sendkey` changes the next frame.

## Metadata
- **Complexity**: Large
- **Source PRD**: `auton-intent-to-os-compiler.prd.md`
- **PRD Phase**: G, I1 Doom
- **Estimated Files**: 3 generated drivers + probe + engine fetch + report
- **Depends on**: `w12-loop-review-repair`, `w12-kernel-base`, protocol from `w13-factory-f6-rerun`; **GATE**: the doomgeneric licence decision recorded in `agent/kernel_spec/decisions/doomgeneric-licence.md`

---

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/reports/w11-intent-doom-report.md` | all | what is done, what blocks |
| P0 | `agent/kernel_spec/services/play-doom.md` | all | contract: six `DG_*` functions, the memory-backed WAD class, markers, the licence section |
| P0 | `agent/kernel_spec/subsystems/drivers.md` | 617-705 | framebuffer (Multiboot2 tag, pitch) and PS/2 sections; markers `[FB] mode set 1024x768x32`, `[FB] pitch 4096 bytes`, `[INPUT] keyboard ready` |
| P0 | `tests/kernel/run_display_test.sh` | 1-40 | the host gate for pitch and scancode arithmetic (21 checks) |
| P1 | `agent/kernel_spec/drivers/ps2-keyboard.md`, `platform-devices.yaml` | all | the accepted-without-spec record; stays `specified` until an observed pass |
| P1 | `agent/kernel_spec/subsystems/pkg.md` | *Module assets* | `pkg_module_asset` |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| doomgeneric | github.com/ozkl/doomgeneric (GPL-2.0) | platform = `doomgeneric_<plat>.c` implementing `DG_*`; needs a small libc subset (string, `malloc`, `snprintf`, math) |
| GRUB gfx mode | GRUB manual: `gfxpayload`, `set gfxmode=1024x768x32` | the kernel receives a linear framebuffer only if `grub.cfg` requests it |
| QEMU monitor | QEMU docs: QMP `screendump`, HMP `sendkey` | an external probe for "non-blank frame" and "input accepted" |
| Freedoom | freedoom.github.io (BSD-3) | a WAD the project may use in CI; commercial WADs never |

GOTCHA: the base `grub/grub.cfg` requests no graphics mode. Without `set gfxpayload=keep` and a
`gfxmode`, the Multiboot2 framebuffer tag is text mode and `play_doom_serve` halts, correctly,
per the spec. The scaffold template (`agent/kernel_spec/templates/x86_64/grub/`) needs a
graphics variant for this service.

## Patterns to Mirror
### HOST_SUITE_TREE_MODE
// SOURCE: tests/kernel/run_display_test.sh:28 (exit 2 = not generated, exit 1 = wrong).
### ASSET_BY_NAME
// SOURCE: agent/tools/package_image.py: assets recorded by name, never embedded.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/kernel_spec/decisions/doomgeneric-licence.md` | CREATE (human decision) | the gate. Options: (a) distribute images with GPL-2.0 obligations met (source offer); (b) local builds only, never distribute; (c) do not ship Doom |
| `agent/kernel_spec/templates/x86_64/grub/grub-gfx.cfg` | CREATE | `gfxmode=1024x768x32`, `gfxpayload=keep`, `module2 /boot/doom.wad doom.wad` |
| `scripts/fetch-doomgeneric.sh` | CREATE | clone a **pinned** commit into `.cache/third_party/doomgeneric` (gitignored); record its sha in `PROVENANCE.json`; refuses without the decision file |
| `<ws>/kernel/drivers/fb/framebuffer.c`, `kernel/drivers/input/ps2.c`, `kernel/pkg/module_asset.c` | GENERATED | the three capabilities |
| `<ws>/kernel/services/play_doom/*` | GENERATED or human (labelled) | the `DG_*` layer and the WAD class |
| `scripts/run-intent-probe.sh` | UPDATE | `doom`: boot with the Freedoom WAD, QMP `screendump` at t=20 s → the PPM is not a single colour; `sendkey up` ×10 → the second screendump differs from a no-key control |
| `agent/kernel_spec/source_map.yaml` | UPDATE, after gates | `framebuffer`, `input`, `module-asset` → generated paths, per-tree note |

## NOT Building
- Sound, music, networking, savegames (the spec excludes them).
- Committing doomgeneric or any WAD.

## Step-by-Step Tasks
### Task 1: The licence decision (human, first)
- **ACTION**: Draft the decision record with the three options and their obligations. The **owner decides**. Nothing past Task 2 runs without it.
- **VALIDATE**: `fetch-doomgeneric.sh` refuses when the decision file is absent or says (c).

### Task 2: Probe first
- **ACTION**: `run-intent-probe.sh doom`, with the QMP socket (`-qmp unix:…,server,nowait`) and a Python helper to send `screendump` / `human-monitor-command sendkey`.
- **GOTCHA**: A frame that is uniformly black is "blank", and so is a frame showing only the text console. Assert more than N distinct colours, not merely non-zero.
- **VALIDATE**: against the base (text mode) it reports **failed: blank frame**. That is the honest current state.

### Task 3: Generate the three capabilities (protocol)
- **GATES**: `run_display_test.sh` tree mode; the boot markers `[FB] mode set 1024x768x32`, `[FB] pitch 4096 bytes`, `[INPUT] keyboard ready`; `pkg_module_asset("doom.wad")` returns the module span (a marker with its length).

### Task 4: Port the platform layer
- **ACTION**: `DG_*` per `play-doom.md`; a libc shim limited to what doomgeneric calls, listed from its undefined symbols (`nm -u`), each implemented or refused at link time.
- **GOTCHA**: doomgeneric's `I_Error` calls `exit`. Map it to a logged halt, never a return.

### Task 5: Probe, grade, record
- **ACTION**: `package_image.py "I want to play Doom" --output …` then the probe. Record worked / honestly refused / failed. Promote `ps2-keyboard` / `framebuffer` to `implemented` only via V9's observed pass.

## Validation Commands
```bash
KERNEL_TREE=<ws> tests/kernel/run_display_test.sh
scripts/fetch-doomgeneric.sh
.venv/bin/python agent/tools/package_image.py "I want to play Doom" --output /tmp/doom --target agent/kernel_spec/targets/qemu-pc.md
scripts/run-intent-probe.sh doom /tmp/doom
```

## Acceptance Criteria
- [ ] The licence decision recorded by the owner before any engine fetch
- [ ] Probe: a non-blank frame, and a keypress changes the next frame
- [ ] No doomgeneric source or WAD in git
- [ ] The package has no `blocked_by`

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The decision is (c) | M | the plan ends at Task 1 | an honest outcome; the report says Doom is cut and why |
| The libc surface is larger than expected | M | M | enumerate from `nm -u` before writing any shim |


---

## Closed 2026-09-23

The licence question is now a written decision record, and `run-intent-probe.sh doom` grades a built image from outside via QEMU's monitor. Building needs a generation run; distributing needs the decision.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
