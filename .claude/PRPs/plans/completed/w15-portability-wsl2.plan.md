# Plan: WSL2 Windows Bench (windows-linux A3)

## Summary
The PRD decided *WSL2 only*: `grub-mkrescue` has no supported native-Windows path. A3 makes that
decision usable and unmissable: a setup script for WSL2 (Ubuntu), the repo on the ext4 side (not
`/mnt/c`, which is slow and breaks permissions), KVM inside WSL2 where nested virtualisation is
available and TCG otherwise, and a green e2e. A2's selector already treats WSL2 as Linux
(`uname -s` = Linux), which `docs/HOST-MATRIX.md` states. GitHub's Windows runners do not provide
WSL2 with nested virtualisation reliably, so the run needs a real Windows 11 machine. This plan
marks that gate plainly and lets CI verify only what it can: the setup script's Linux half, on the
Ubuntu runner.

## User Story
As a Windows developer, I want one documented path to build and boot AUTON, so that I don't
spend a week discovering that native Windows cannot build it.

## Problem → Solution
No Windows path; nothing says why → `scripts/setup-wsl2.sh` (in-WSL: apt toolchain, a repo-location
check, a `/dev/kvm` check), `docs/WINDOWS.md` (WSL2 required, and why; enabling nested
virtualisation), the HOST-MATRIX WSL2 row exercised on a real machine with its timings.

## Metadata
- **Complexity**: Small
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: A3
- **Estimated Files**: 4
- **GATE**: a Windows 11 machine with virtualisation enabled (the owner's, or a contributor's)
- **Depends on**: `w12-portability-linux-bench` (the apt list and the Linux e2e job)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `scripts/lib/toolchain.sh` | 15-30, accelerator section | Linux branch; `/dev/kvm` usability check |
| P0 | `docs/HOST-MATRIX.md` | WSL2 row | "kvm if nested virtualisation exposes /dev/kvm, else tcg" |
| P0 | `.github/workflows/portability.yml` (after w12) | linux-e2e | the apt list to reuse verbatim |

## Patterns to Mirror
### PREFLIGHT_NOTES_NOT_FAILS
// SOURCE: scripts/preflight.sh accelerator NOTE: TCG is slow, not broken.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `scripts/setup-wsl2.sh` | CREATE | detect WSL (`/proc/version` contains `microsoft`); refuse a repo under `/mnt/[a-z]/` with the reason; apt install; run preflight |
| `docs/WINDOWS.md` | CREATE | WSL2 required; native unsupported (the `grub-mkrescue` reason); `.wslconfig` `nestedVirtualization=true`; expected timings |
| `scripts/preflight.sh` | UPDATE | on WSL, a NOTE naming WSL and the repo filesystem |
| `docs/HOST-MATRIX.md` | UPDATE | the WSL2 row exercised, with the date, machine and timings |

## NOT Building
- Native Windows builds (MSYS2/mingw). Ruled out by the PRD.

## Step-by-Step Tasks
### Task 1: `setup-wsl2.sh`, with its Linux half exercised in CI (the WSL detection mocked by a fixture `/proc/version`)
### Task 2: `docs/WINDOWS.md`
### Task 3: On a real Windows 11 machine: setup → preflight → `e2e.sh --skip-train` → `time-boot.sh`; record in the matrix

## Validation Commands
```bash
bash -n scripts/setup-wsl2.sh
# on Windows 11, inside WSL2:
scripts/setup-wsl2.sh && scripts/e2e.sh --target <ws> --skip-train
```

## Acceptance Criteria
- [ ] E2E green under WSL2 on a real machine, timings recorded
- [ ] The docs make the WSL2 requirement unmissable, with the reason
- [ ] A repo on `/mnt/c` is refused with an explanation

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| No Windows machine available | M | A3 stays open | stated as the gate; everything else is prepared |
| Nested virtualisation off | M | L | TCG fallback via A2's selector, NOTE in preflight |


---

## Closed 2026-09-23

Blocked on a Windows machine. The control-plane CI matrix already covers windows-latest and is unrun only because the branch is unpushed.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
