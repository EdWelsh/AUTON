# Plan: Driver Errata Join, with a Real Erratum/Driver Pair (V10)

## Summary
V10 was deferred on a data gap: *"Nothing links a device or a driver to an erratum. Every errata
document in `vendors.yaml` is a CPU or SoC errata sheet."* V2's rule forbids adding a field to
driver records until a real case needs it. A real case almost certainly exists and has not been
ingested: Intel publishes **specification updates for its Ethernet controllers**, and the 8254x
family document covers the **82540EM** (`8086:100e`), the device the base's `e1000` driver binds.
This plan inventories and ingests that document, keys its errata by **PCI id + revision ID**
(the device-level analogue of CPUID stepping), and only then adds the join and the field V2's
rule now justifies.

## User Story
As an image with an `e1000` driver, I want the errata that apply to the NIC it drives reported,
and a workaround applied where one exists, so that "is this machine safe?" covers devices, not
just CPUs.

## Problem → Solution
No device errata ingested; the join has nothing to join → the 8254x spec update ingested with
`applies_to: {pci: 8086:100e, revision: …}`; `errata_join.py` joins driver records to device
errata by PCI id (revision when the probe knows it); the `e1000` record gains `errata:` only
because a real erratum now requires it; `mitigation_registry` accepts device-level workarounds.

## Metadata
- **Complexity**: Medium
- **Source PRD**: `auton-driver-development.prd.md`
- **PRD Phase**: V10
- **Estimated Files**: 7
- **Depends on**: H4, H6, D8 (landed)

## Mandatory Reading
| Priority | File | Lines | Why |
|---|---|---|---|
| P0 | `.claude/PRPs/plans/DEFERRED.md` | "V10" row | why it was deferred, and the rule |
| P0 | `.claude/PRPs/reports/w6-target-errata-join-report.md` | all | D8 hit the same wall one level up |
| P0 | `agent/tools/vendor_ingest.py` | 39-70, 148-257 | `Record.applies_to` identity keys; the Intel PDF parser to extend for a controller document |
| P0 | `agent/tools/errata_join.py` | all | the CPU-level join to generalise |
| P0 | `agent/kernel_spec/drivers/e1000.md`, `README.md` | all | the record; "a field is added when a second record cannot be expressed without it" |
| P1 | `agent/tools/mitigation_registry.py` | 128-160 | `assess()` |

## External Documentation
| Topic | Source | Key Takeaway |
|---|---|---|
| Intel 8254x family specification update | intel.com (8254x Family of Gigabit Ethernet Controllers Specification Update) | errata per controller and stepping, usually with software workarounds in the driver. **Verify the document number and that the 82540EM is covered before inventorying** |
| PCI revision ID | PCI Local Bus Spec §6.2.1 (config offset 0x08) | the device's stepping analogue; QEMU's e1000 reports a fixed revision |

GOTCHA: if the downloaded document does not cover the 82540EM, the gap stands. Record that and
pick the nearest real pair (e.g. an `e1000e` part a Phase 0 machine carries). Never attach
another controller's erratum to `8086:100e`.

## Patterns to Mirror
### FIELD_ONLY_WHEN_NEEDED
// SOURCE: agent/kernel_spec/drivers/README.md: "A field is added when a second driver genuinely cannot be expressed without it, not in anticipation."
### PROVENANCE
// SOURCE: agent/tools/vendor_ingest.py:57-66.

## Files to Change
| File | Action | Justification |
|---|---|---|
| `agent/hardware/vendors.yaml` | UPDATE | the Intel Ethernet spec update, `kind: errata`, `key: pci-id+revision` |
| `agent/tools/vendor_ingest.py` | UPDATE | `parse_intel_controller_update`, with fixture tests from the real PDF layout |
| `agent/tools/errata_join.py` | UPDATE | device errata by `(vendor:device[, revision])` from the target's devices |
| `agent/kernel_spec/drivers/README.md` + `e1000.md` | UPDATE | the `errata:` field (erratum ids + the workaround each needs), justified by the real pair |
| `agent/tools/driver_spec.py` | UPDATE | validate `errata:` ids exist in ingested records (a phantom erratum id is refused, like a phantom device) |
| `agent/tests/unit/test_driver_errata.py` | CREATE | join finds the 82540EM errata for `qemu-pc`; a phantom id refused; revision-specific errata not applied when the revision is unknown, and reported as "revision unknown" |

## NOT Building
- Implementing the workarounds in a tree. That is the e1000 driver's owner; the record states them.
- CPU errata changes.

## Step-by-Step Tasks
### Task 1: Acquire + verify coverage (a person downloads; `vendor_fetch --from-file`)
### Task 2: Parser + fixtures
### Task 3: The join
- **GOTCHA**: QEMU's emulated 82540EM reports one revision and has none of the silicon's bugs. The join reports what *applies to the device id*; whether the emulated device exhibits it is H10's question.
### Task 4: The field, and its validation
### Task 5: `machine_safety` + package `spec/errata.json` include device errata

## Validation Commands
```bash
.venv/bin/python agent/tools/vendor_ingest.py --vendor intel --id <controller-doc>
.venv/bin/python agent/tools/errata_join.py --target agent/kernel_spec/targets/qemu-pc.md
cd agent && ../.venv/bin/python -m pytest tests/unit/test_driver_errata.py tests/unit/test_errata_join.py -q
```

## Acceptance Criteria
- [ ] A real erratum linked to a real driver, cited to the page
- [ ] The `errata:` field exists because that pair needs it
- [ ] Unknown revision reported, never assumed
- [ ] Or, if no pair is found, the gap restated with what was searched

## Risks
| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| The document does not cover the 82540EM | M | V10 stays deferred | the gotcha: record it; pick the nearest real pair |
| Controller PDFs parse differently from CPU ones | H | M | a separate parser with fixtures |


---

## Closed 2026-09-23

Blocked on one Intel NIC specification update that a person must download (Intel's CDN refuses scripted fetches). The join and the field rule are ready for it.

Remaining work for this phase is tracked in `docs/OPEN-WORK.md`, which is in the repository rather than here: it names the blocker and the next command for every unfinished piece.
