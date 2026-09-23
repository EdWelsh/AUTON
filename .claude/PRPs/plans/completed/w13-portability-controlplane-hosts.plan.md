# Plan: Control Plane on Linux and Windows (windows-linux C1)

## Summary
The host half of the chat OS (`controlplane/`) has only run on macOS. Its desktop backend picks
an adapter from `sys.platform` (`backends/desktop/launcher.py:103, 179-190`), and the Windows and
Linux branches have never executed. GitHub provides both `ubuntu-latest` and `windows-latest`
runners, so C1's success signal (*"suite green on both; all three surfaces smoke-tested per
host"*) is reachable in CI with no hardware.

## User Story
As a Linux or Windows user, I want the AUTON control plane to launch, list and close apps from
chat on my OS, so that the chat OS's host half is not Mac-only.

## Problem → Solution
The suite runs on the Mac only; the Windows/Linux adapters are unexecuted → a CI matrix running
`controlplane/tests` on all three OSes, a smoke test per surface (terminal, UI, desktop) per host
that launches a real, harmless app (`gedit`/`xdg-open` headless alternatives, `notepad`, `TextEdit`),
and fixes for every path/process assumption found (`~/.auton`, `start` builtin, path separators).

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-windows-linux.prd.md`
- **PRD Phase**: C1
- **Estimated Files**: 5 + fixes found
- **Depends on**: nothing (the PRD: A1 ∥ C1)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `controlplane/src/controlplane/backends/desktop/launcher.py` | 95-200 | per-OS branches; `start` as a shell builtin on Windows (`:102-103`) |
| P0 | `controlplane/src/controlplane/backends/desktop/adapters_windows.py` | all | pure argv builders: unit-testable anywhere, and executed only on Windows |
| P0 | `controlplane/tests/` | `test_desktop.py`, `test_e2e_surfaces.py` | what exists; which tests are Mac-gated |
| P1 | `controlplane/pyproject.toml`, `INSTALL.md` | all | install per OS |

## Patterns to Mirror
### PURE_ARGV_ADAPTERS
// SOURCE: controlplane/src/controlplane/backends/desktop/adapters_windows.py:1: "pure argv builders for launch/close/list", testable without the OS.
### SHELL_BUILTIN_CARE
// SOURCE: launcher.py:102-103: `start` needs `cmd /c` on Windows. This is also the one place injection care applies: argv only, never an interpolated string (the w0 H0 rule).

## Files to Change
| File | Action | Justification |
|---|---|---|
| `.github/workflows/controlplane.yml` | CREATE | matrix `macos-14, ubuntu-latest, windows-latest`; install; pytest; smoke per surface |
| `controlplane/tests/test_platform_smoke.py` | CREATE | per OS: launch → list shows it → close; skips only when no GUI session exists, and says so |
| `controlplane/src/…` | UPDATE (as found) | path handling (`Path.home()` not `~`), encodings, process listing |
| `controlplane/INSTALL.md` | UPDATE | per-OS install and what each surface needs |
| `docs/HOST-MATRIX.md` | UPDATE | the control-plane columns per host |

## NOT Building
- The KVM OS profiles (C2, needs Proxmox).
- New surfaces.

## Step-by-Step Tasks
### Task 1: CI matrix running the existing suite (RED shows the real failures)
- **GOTCHA**: CI runners have no interactive desktop on Linux (use `xvfb-run`) and a non-interactive session on Windows. A launch that cannot show a window must still launch a process. Assert on the process, not on a window.
### Task 2: Fix each failure with a regression test on the adapter level
### Task 3: Smoke per surface per host
### Task 4: Docs and matrix

## Validation Commands
```bash
cd controlplane && python -m pytest -q
gh workflow run controlplane.yml && gh run watch
```

## Acceptance Criteria
- [ ] Suite green on macOS, Linux, Windows in CI
- [ ] Each surface smoke-tested per host, with a real process launched and closed
- [ ] Every fix pinned by a test

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Headless CI hides GUI-only bugs | M | M | stated in the matrix; a manual check on a real desktop per OS when available |
| A Windows argv/quoting injection | L | H | argv-only, the H0 tests extended to the Windows adapter |
