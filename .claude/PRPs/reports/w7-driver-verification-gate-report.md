# Implementation Report: Verification Harness (V9)

## Summary

V2 made `verification` mandatory and mechanical. Nothing ran it. A field that is mandatory and
unchecked is worse than an absent one, because it reads as a guarantee.

`driver_verify.py` runs what each record promises, as a build gate beside leakage, and writes the
result into every targeted package.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Which records apply to this image | Complete | joined from the target, reusing D7's resolution |
| 2 | Run what can be run, say what cannot | Complete | `cmd:` executed, `marker:` observed |
| 3 | Three outcomes, unverified is not passed | Complete | through to the package |
| 4 | `implemented` must be verified, not verifiable | Complete | bound to the record's hash |
| 5 | Report per driver, in the package | Complete | `spec/drivers.json` |

## The third state is the whole phase

| Situation | Outcome |
|---|---|
| command runs, exits 0 | **verified** |
| command exits 2 — *nothing to check* | unverified |
| command named but absent (`status: specified`) | unverified |
| command boots an image, skipped without `--slow` | unverified |
| marker with no boot log to observe it in | unverified |
| marker absent from a boot log that exists | **failed** |
| command exits non-zero, non-2 | **failed** |

`virtio-net.md` names `tests/kernel/run_virtio_net_test.sh`, which does not exist because the
driver does not exist. Treating that as a failure would block every build touching a planned
driver; treating it as a pass is the lie the field was created to prevent.

A driver's outcome is **the worst of its checks** — it is not verified because most of it was.

## Task 4: what `status: implemented` now costs

`driver_spec` already refuses `implemented` when `provides` has no source mapping — the driver
claims to be in an image that does not contain it. This closes the other half: the driver is
mapped, and nobody has checked it works.

```
[gate: drivers] record(s) claim status 'implemented' with no observed pass:
    e1000: cmd: scripts/run-acceptance.sh — skipped: boots an image; pass --slow to run it
  'implemented' is a claim about this tree. Run the verification, or set status to 'specified'
  until it is written.
```

Evidence is bound to the **sha256 of the record it passed against**, and lives in `.cache/`
alongside the other build artefacts. A pass against a different record is not evidence: the
verification may have been rewritten since, and the old result says nothing about the new claim.
Per-checkout on purpose — a recorded pass copied between machines would be a claim about a run
that never happened here.

## A gate people turn off verifies nothing

`scripts/run-acceptance.sh` boots an image under QEMU and takes minutes. Making every service
build pay that is how a gate gets disabled, so slow commands are skipped by default and reported
as *unverified* — never as verified, and never silently. `--slow` runs them.

## What the join found

Firecracker has a storage device. `device_drivers` resolves `virtio-mmio:2` to `virtio-blk`.
**No record exists for it.** The gate reports it as undeclared rather than passing over it:

```
  no record: virtio-blk (for virtio-mmio:2)
```

That is V6's justification, surfaced by machinery rather than asserted in a phase table. A device
the image needs that nothing describes is exactly the gap this join exists to find. Devices
nothing binds to — QEMU's host bridge — are *not* reported, because a list that includes them
trains a reader to ignore it.

## One correction during implementation

The driver report was first written only when a build succeeded, so a package that was INCOMPLETE
— which every DHCP package currently is, for want of a service spec — carried no driver
verification at all. Which drivers an image needs follows from the machine it is built for, not
from whether the image linked, so it is now written whenever a target is stated, beside
`spec/errata.json`.

## Validation

1393 unit tests pass (was 1364), 111 SLM tests. 29 new tests. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| an absent command counts as verified | 1 |
| a driver is verified if any check passed | 1 |
| implemented-with-no-pass no longer refused | 2 |
| a specified driver is refused too (too strict) | 1 |
| evidence not bound to the record hash | 1 |
| exit 2 read as a pass | **0 → 1** |
| a device with no record is silently ignored | 1 |

The sixth survived: nothing exercised the exit-2 convention, because no verification command in
the tree exits 2 yet. V5's will, so the test was added now rather than after it mattered.

## Files

| File | Action |
|---|---|
| `agent/tools/driver_verify.py` | CREATED |
| `agent/tests/unit/test_driver_verify.py` | CREATED — 29 tests |
| `agent/tools/build_service.py` | UPDATED — `[gate: drivers]`, `BuildResult.driver_report` |
| `agent/tools/package_image.py` | UPDATED — `_record_drivers`, `spec/drivers.json` |
| `agent/kernel_spec/drivers/README.md` | UPDATED — the verification section |

## Acceptance

- [x] The gate verifies only the drivers this image contains, joined from the target
- [x] `cmd:` runs; `marker:` is observed where a run exists and reported where not
- [x] Three outcomes, and unverified never counts as verified — through to the package
- [x] `status: implemented` with no observed pass is refused, naming the alternative
- [x] Recorded evidence is bound to the record it passed against
- [x] `spec/drivers.json` carries the per-driver result
