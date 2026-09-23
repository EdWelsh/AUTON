# Plan: Verification Harness (V9)

**Source PRD**: `auton-driver-development.prd.md` — phase V9
**Depends on**: V2 (landed), F5 (landed)
**Why before V5**: V5 is the first driver whose verification must actually run. Building the gate
after the driver is how a `verification` field becomes decorative.

## Summary

V2 made `verification` mandatory and mechanical — every driver record names commands and markers
rather than prose. Nothing runs them.

A field that is mandatory and unchecked is worse than an absent one, because it reads as a
guarantee. This wires driver verification into the factory pipeline as a gate, the way leakage
already is.

## Evidence

- `agent/kernel_spec/drivers/README.md` — *"`verification`: **Mandatory, and mechanical.** A
  command to run or a marker to observe. An image that claims a driver works is making the claim
  a user acts on."* The bar is set; this is what enforces it.
- `agent/tools/driver_spec.py` `VERIFICATION_PREFIXES` — entries are `cmd:` or `marker:`. Two
  kinds, checked two ways.
- `agent/tools/build_service.py` `gate_leakage`, `gate_capabilities` — the gate pattern:
  `[gate: <name>]` prefix, raises `GateFailure`, explains what to do next. `gate_capabilities`
  was added in V1 and is the closest precedent — it consumes a report rather than recomputing it.
- `agent/tools/build_service.py` `build()` — where gates are sequenced, and the comment recording
  why the capabilities gate runs *before* the stub generator.
- `tests/kernel/run_leakage_test.sh` — exit 2 (*nothing to check*) distinct from exit 0
  (*clean*). The same three states apply: a driver whose verification could not be run is not a
  driver that passed.
- `agent/kernel_spec/drivers/e1000.md` — `cmd: scripts/run-acceptance.sh`, a command that
  actually exists. `virtio-net.md` — `cmd: tests/kernel/run_virtio_net_test.sh`, which does not,
  because `status: specified`. The gate must tell those apart.
- `agent/tools/device_drivers.py` `driver_for_device` — how a target's device becomes a driver
  name, which is how the gate knows which records apply to this image.

## Patterns to Mirror

- **Gate shape**: `[gate: drivers]`, `GateFailure`, a message saying what to do next.
- **Three states, not two**: `run_leakage_test.sh`'s exit 2; `target_spec`'s `UNVERIFIABLE`.
- **Consume, do not recompute**: `gate_capabilities` reads `resolve()`'s report.

## Tasks

### Task 1: Which records apply to this image
- **Action**: From the target's devices, resolve each to a driver (`device_drivers`), then load
  that driver's record. Drivers with no record are reported.
- **Why from the target**: an image contains drivers for the machine it is built for. Verifying
  every record in `kernel_spec/drivers/` would check drivers this image does not contain, and
  the pass would mean nothing.
- **Gotcha**: D7 already does this join for the *manifest*. Reuse it — `intent_manifest`'s
  `decisions` list already records which device chose which driver, with its source. A second
  join would drift.
- **Validate**: a qemu-pc target yields `e1000.md`; a firecracker target yields `virtio-net.md`.

### Task 2: Run what can be run, and say what cannot
- **Action**: `cmd:` entries are executed. `marker:` entries are checked against the image's
  serial output where a run exists, and reported as *not yet observed* where it does not.
- **Why split**: a command can be run at build time; a marker can only be observed at boot. A
  gate that pretends otherwise either blocks every build or verifies nothing.
- **Gotcha**: `scripts/run-acceptance.sh` boots an image under QEMU and takes minutes. The gate
  must not make every service build pay that cost — it runs a driver's commands only when that
  driver's record or the image's device set has changed, or when explicitly asked.
- **Validate**: the gate on an unchanged tree is fast; `--verify-drivers` forces the full run.

### Task 3: Three outcomes, and unverified is not passed
- **Action**: `verified` / `unverified` / `failed`. A `status: specified` driver whose command
  does not exist is **unverified**, not failed and certainly not verified.
- **Why**: `virtio-net.md` names `tests/kernel/run_virtio_net_test.sh`, which does not exist
  because the driver does not exist. Treating that as a failure blocks every build that touches a
  planned driver; treating it as a pass is the lie the field was created to prevent.
- **Gotcha**: the distinction must survive into the package. `PROVENANCE.json` already carries
  `leakage`; driver verification belongs beside it, with the three states intact rather than
  flattened to a boolean.
- **Validate**: an image with `virtio-net` reports unverified and builds; an image whose `e1000`
  verification *fails* is refused.

### Task 4: `status: implemented` must be verified, not merely verifiable
- **Action**: A driver record claiming `implemented` whose verification has never been observed
  to pass is a gate failure.
- **Why this is the whole phase**: `status: implemented` is a claim about this tree, and V2
  already refuses it when `provides` has no source mapping. This closes the other half — the
  driver is mapped, and nobody has checked it works.
- **Gotcha**: do not require a fresh run on every build. A recorded pass with the record's hash
  and the image's hash is evidence; a recorded pass against a *different* record is not.
- **Validate**: flipping `virtio-net.md` to `implemented` without a passing verification is
  refused, naming the missing evidence.

### Task 5: Report per driver, in the package
- **Action**: `spec/drivers.json` in every targeted package: each driver, its strategy, its
  verification entries and each one's outcome.
- **Why**: the PRD's metric is *"drivers shipped without executable verification: 0"*, and a
  metric with no artifact behind it is an intention. D8 set the precedent with `spec/errata.json`.
- **Validate**: a packaged image carries the record, and the counts match the gate's own.

## Validation

```bash
python agent/tools/build_service.py dhcp --tree <tree> --target agent/kernel_spec/targets/qemu-pc.md
python agent/tools/driver_verify.py --target agent/kernel_spec/targets/qemu-pc.md
python agent/tools/driver_verify.py --target agent/kernel_spec/targets/firecracker.md  # unverified
cd agent && python -m pytest tests/unit/test_driver_verify.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Unverified quietly counts as verified | **H** | Task 3; three states through to the package, as D8 kept `unknown` separate from `not_applicable` |
| The gate makes every build slow enough to be disabled | **H** | Task 2 runs commands on change or on request; a gate people turn off verifies nothing |
| It verifies drivers the image does not contain | **M** | Task 1 joins from the target, reusing D7's decision list |
| A recorded pass outlives the record it passed against | **M** | Task 4 binds the evidence to the record's hash |
| `marker:` entries are unfalsifiable without a boot | **M** | Stated in Task 2 rather than papered over; a marker with no run is *not yet observed* |

## Acceptance
- [ ] The gate verifies only the drivers this image contains, joined from the target
- [ ] `cmd:` runs; `marker:` is observed where a run exists and reported where not
- [ ] Three outcomes, and unverified never counts as verified — through to the package
- [ ] `status: implemented` with no observed pass is refused, naming the missing evidence
- [ ] Recorded evidence is bound to the record it passed against
- [ ] `spec/drivers.json` carries the per-driver result
