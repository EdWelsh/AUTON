# Report: The Control Plane on Linux and Windows (C1)

**Plan**: `plans/completed/w13-portability-controlplane-hosts.plan.md` · **Commit**: `175be36`

## Where it runs now

| Host | Suite | Terminal | UI | Desktop | Evidence |
|---|---|---|---|---|---|
| macOS, Apple Silicon | 189 passed, 5 skipped | yes | yes | real launch (TextEdit) | run here, 2026-09-22 |
| Linux (arm64 container on this Mac) | 178 passed, 13 skipped | yes | yes | process only | `python:3.12-slim` under Docker, 2026-09-22 |
| Linux x86_64 (real host) | — | — | — | — | **wired, unrun** |
| Windows | — | — | — | — | **wired, unrun**: no Windows host here |

The matrix job (`.github/workflows/controlplane.yml`, `macos-14 / ubuntu-latest /
windows-latest`) runs the suite and the surface smoke on each. It has not run: this branch is
not pushed (the auth gate).

## What running it on Linux actually found

1. **A real product bug.** `what oses are running` raised `FileNotFoundError` on any host with
   no Docker CLI: `OSManager.running()` and `.stop()` ran `docker` unguarded. It now answers
   "Docker isn't installed on this host…". Two tests pin it, and they run on every host
   (`OSManager(docker="no-such-docker-cli-auton")`).
2. **A repo-layout assumption**: a test read `<repo>/controlplane/pyproject.toml`; a CI runner
   or container that has only the package fails. It now reads its own package's file.
3. **An environment-dependent test**: the tracked kubernetes raw-dump gap reproduces only with
   kubectl installed and no reachable cluster. It now skips with that reason. (Found twice: in
   the container, and on the Mac once Rancher Desktop was started and brought up a cluster.)

## The smoke test, and what it cannot prove

`controlplane/tests/test_platform_smoke.py`: the terminal surface answers on a pipe; the UI
surface serves HTTP from a real process on a free port; the desktop launcher's own runner
executes a process (on Windows through `cmd /c`, where `start` is a builtin).

It asserts on **processes, not windows**: a headless runner has no desktop session. So "the
desktop surface works on Windows" is not proved by a green matrix, and `docs/HOST-MATRIX.md`
says so. A real desktop check per OS is still owed — that is the owner's machine, not CI.

## Left open
- The matrix has never executed (push gate). Its first run may find Windows-specific failures;
  that is what it is for.
- C2 (KVM OS profiles) needs Proxmox: owner-gated, as planned.
