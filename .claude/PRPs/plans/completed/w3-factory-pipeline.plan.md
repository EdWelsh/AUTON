# Plan: Factory Pipeline + Gates (F5)

**Source PRD**: `auton-service-kernel-factory.prd.md` — phase 5
**Depends on**: F4 (landed)
**Unblocks**: F6 (the agent-authored service), intent-E, intent-F

## Summary

F4 built a service image by hand: resolve the manifest, generate stubs, invoke `make` with an
explicit `CSRC`, build the ISO, boot it. Every step was a hand-typed command with arguments
that had to agree with each other.

This turns it into `auton build-service <name>` and wires the gates, so a step that disagrees
fails the build rather than producing a wrong image quietly.

## Evidence

- `.claude/PRPs/reports/w3-factory-dhcp-service.md` records the walked path, and five of the
  seven defects found were **disagreements between steps** — the generator compiled without the
  build's defines; the source list and the appended extras duplicated a file; the stub list and
  the leakage check were separate hand-maintained things.
- `agent/tools/build_manifest.py`, `gen_absent.py`, `service_spec.py` all exist and all take
  the same manifest.
- `agent/kernel_spec/tests/acceptance_tests.py` has `SERIAL_MARKER_SETS` and a per-set
  accessor; a service's `markers` field is the same shape and nothing consumes it.
- `tests/kernel/run_leakage_test.sh` exists and takes `--excludes` and `--stubs`.

## Tasks

### Task 1: One command
- **Action**: `auton build-service <name> --tree <dir>` runs spec → slice → stubs → build →
  ISO. Defines are computed once and passed to every step that needs them.
- **Why**: the defines disagreeing between the generator and the build is a defect that already
  happened. A pipeline that derives them once cannot reproduce it.
- **Validate**: DHCP rebuilds end to end from one command, producing the same image size.

### Task 2: The gates
- **Action**: Wire the checks that already exist, and fail the build on each:
  - the spec validates and resolves (`service_spec.py`)
  - no excluded capability leaks (`run_leakage_test.sh`, with the generated stub list)
  - the service's markers appear on a booted image
- **Gotcha**: a spec still carrying intent-C's `GENERATED STUB` marker must be refused. It
  validates — the front-matter is real — but its body is empty, and an agent will implement it
  confidently and wrongly.
- **Validate**: each gate fails the build when violated, demonstrated by violating it.

### Task 3: Markers as data
- **Action**: The service's `markers` feed the acceptance harness rather than being restated.
  `acceptance_tests.py` gains a per-service set built from the spec.
- **Validate**: a marker changed in the spec changes what the harness asserts, with no shell edit.

### Task 4: Prove a gate catches something real
- **Action**: Inject a defect — exclude a capability the service needs — and confirm the
  pipeline fails at the right gate with a legible message, rather than at boot.
- **Validate**: the failure names the gate and the capability.

## Acceptance
- [ ] `auton build-service dhcp` reproduces F4's image from one command
- [ ] Defines are derived once and shared; no step can disagree with another
- [ ] A spec carrying the generated-stub marker is refused
- [ ] Leakage is a build gate, using the generated stub list
- [ ] A service's markers drive the harness, not a restatement
- [ ] An injected defect fails at a named gate, not at boot
