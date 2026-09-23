# Plan: Leakage Enforcement (intent-E)

**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase E
**Depends on**: intent-C (landed), F5 (landed)

## Summary

F5 wired leakage as a gate in `build_service.py`. That covers a *service* build. The PRD's
claim is broader: **capability leakage is a build failure**, for any image, with a target of
**0**. Two things are missing — the general `auton build` path has no gate at all, and nothing
records a leakage measurement over time.

## Evidence

- `tests/kernel/run_leakage_test.sh` exists, takes `--excludes` and `--stubs`, and distinguishes
  a generated stub from a real implementation (`w3-factory-dhcp-service.md`).
- `build_service.py` calls it as a gate; nothing else does.
- The PRD's success metric table: *Capability leakage — n/a → **0***.
- `.claude/PRPs/reports/w2-factory-dependency-audit.md`: the full image leaks 68 net symbols
  when net is excluded, so the check has a known non-zero case to regress against.

## Tasks

### Task 1: A leakage report, not just a gate
- **Action**: `--report` emits the measurement as data: image, excludes, symbols checked,
  leaked, stubbed. The PRD tracks a number; a pass/fail cannot be tracked.
- **Validate**: the report is machine-readable and records zero for the DHCP image.

### Task 2: Enforce on every image, not only services
- **Action**: A manifest-built image (intent-B/C path) gets the same gate. An image with no
  declared excludes is a finding, not a pass — `excludes` is mandatory in every manifest.
- **Validate**: building without excludes is refused with the reason.

### Task 3: Regress against the known leak
- **Action**: The 68-symbol case is a fixture: a full image with `--excludes net` must still
  report leakage. A check that has stopped detecting is worse than none.
- **Validate**: a test asserts the detector fires on the general image and not on the scoped one.

## Acceptance
- [ ] Leakage is reported as a number, not only pass/fail
- [ ] Every manifest-built image is gated, not only services
- [ ] A manifest with no excludes is refused
- [ ] The known 68-symbol leak is a regression fixture the detector must still catch
