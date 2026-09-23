# Local Review: foundation MVP (finish-codebase-local-os-on-docker)

**Reviewed**: 2026-06-14
**Branch**: feat/finish-codebase-local-os-on-docker (uncommitted)
**Scope**: 33 files, +1100 / -7 (18 kernel C/asm, Docker/compose/scripts, orchestrator Python)
**Decision**: APPROVE with comments

## Summary
A focused, well-scoped MVP: a from-scratch x86_64 kernel that boots in QEMU via a
GRUB Multiboot2 ISO and prints the acceptance markers, plus the orchestrator
validator-wiring fix. No security issues, no secrets, no injection. Boot and
Python tests pass (verified). Findings are MEDIUM/LOW only — mostly deliberate
seed-stage simplifications and one behavior-change worth a config opt-out.

## Findings

### CRITICAL
None.

### HIGH
None.

### MEDIUM
1. **Final-success gate has no opt-out** — `engine.py run()` now always runs a real
   `make` build + QEMU boot and folds the result into `success`. In an environment
   without the cross toolchain/QEMU, a run with all tasks completed will report
   `success=False`. This is the intended verification gate, but there is no
   `[validation].enabled=false` escape hatch the way `composition_checks` has one.
   *Suggest*: add a `validation.enabled` flag (default true) to skip build/test
   gating when the toolchain is intentionally absent.
2. **CompositionValidator is not arch-aware** — `CompositionValidator(workspace_path)`
   constructs its internal `BuildValidator`/`TestValidator` with x86_64 defaults
   (its constructor takes no `arch_profile`). For aarch64/riscv64 runs the
   composition step would use the wrong toolchain/QEMU. Pre-existing design, but
   now reachable since the validator is wired in. *Suggest*: thread `arch_profile`
   into `CompositionValidator`.
3. **Redundant rebuilds in the final phase** — `run()` builds, then tests, then
   `composition_validator.validate()` builds + tests **again** (up to ~3 builds).
   Gated behind `composition_checks`, so opt-out exists, but worth a comment or
   reusing the prior build artifact.

### LOW
4. **`boot_info.c` tag walk is unbounded** — the Multiboot2 tag loop trusts the
   bootloader's terminating type-0 tag; a malformed info struct could loop. Trust
   boundary is the bootloader (GRUB), so low risk. *Optional*: bound by `total_size`.
5. **compose mounts repo as root** — `os`/`acceptance` write `build/` artifacts as
   root via the bind mount. Harmless on Docker Desktop (uid mapping); could leave
   root-owned files on a Linux host. *Optional*: run as the host uid.
6. **`.note.GNU-stack` missing on .S files** — caused a linker exec-stack warning.
   **Fixed in this review** (added the marker to `boot.S` and `multiboot_header.S`).

## Validation Results

| Check | Result | Notes |
|---|---|---|
| Kernel build | Pass | clean; exec-stack warning fixed in-review |
| Boot in QEMU (acceptance) | Pass | `docker compose run acceptance` → ALL PASS (12/12 markers) |
| Python unit + wiring tests | Pass | 772 passed (native venv), incl. 5 new wiring tests |
| Rust clippy/test | Skipped | Rust tools not implemented this pass (Phase 3.1–3.3) |

## Positive Notes
- Sound boot-protocol pivot (Multiboot2+ISO) correctly handles QEMU's ELF64
  `-kernel` rejection; long-mode markers stay truthful.
- Clean separation: arch HAL (`io.h`), portable libk, drivers, subsystems —
  matches `architecture.md` layout.
- Validator wiring includes regression tests; previously-dead code now exercised.
- Real repo bug fixed: phantom submodule gitlinks removed.

## Files Reviewed (33)
Kernel sources (18, Added) · Dockerfile/.dockerignore/docker-compose.yml (Added) ·
scripts/{auton-boot,run-acceptance,build-iso}.sh (Added) ·
engine.py/cli.py/validation `__init__`.py (Modified) ·
test_engine_validation_wiring.py (Added) · README/.gitignore (Modified) ·
kernels/{x86_64,aarch64,riscv64} gitlinks (Deleted).
