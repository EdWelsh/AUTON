# Implementation Report: Derive a microVM Target (D3)

## Summary

A microVM's device set is not discovered — it is decided by the hypervisor and machine type
before anything boots. So `--derive-microvm firecracker` emits a complete, valid target and asks
nothing. The PRD's hypothesis, that elicitation is a fallback rather than the main road, holds
here.

Deriving it also found two errors in the hand-written example D1 shipped.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | The hypervisor table | Complete | 3 hypervisors, 2 transports, absences per entry |
| 2 | Derivation | Complete | round-trip resolved 6 differences |
| 3 | Prove it needs no questions | Complete | 0 questions, 1 assumption, justified |

## What the derivation found

**The ids were PCI ids on a machine with no PCI bus.** `firecracker.md` listed `1af4:1000` and
`1af4:1001` — virtio's *PCI* vendor:device pairs — two rows below its own table saying "PCI bus:
no". Over virtio-MMIO there is no vendor:device pair anywhere in the transport; the guest reads a
device type number out of a register.

The error was not carelessness, it was the format. D1's id grammar was `vvvv:dddd` and nothing
else, so the wrong id was the only writable one. **A format that admits one id shape does not
merely fail to express the other — it makes the wrong answer the only writable one.** The grammar
now admits `virtio-mmio:<type>`, resolved against the VIRTIO 1.2 §5 type table.

**The machine type was borrowed from a different hypervisor.** `machine: microvm` is QEMU's name
for its machine type. Firecracker has none. Two D6 test fixtures carried the same stale value and
were caught by the table lookup.

**Absences were being filed as assumptions.** The first derivation emitted "absent: PCI bus" under
`assumptions`, which marks a known fact as a guess. `absent:` is now a field. D1's own prose had
noted the gap — "a target that can only list what is present cannot say 'there is no PCI bus
here'" — and the derivation is what forced it into the open.

**Naming a platform does not always pin a device set.** D6's rule allowed `microvm` to leave
`devices` empty because the platform implies them. QEMU's `microvm` machine type declares MMIO
slots and says nothing about what occupies them, so a target naming it and listing nothing is
still blank. `pins_devices: false` records this, and both the derivation and the validator refuse
it with the same reason — a hand-written target gets the same answer as a derived one.

## Task 1: the table

| Hypervisor | Machine | Transport | Devices | Absences |
|---|---|---|---|---|
| firecracker | default | virtio-mmio | 2 | 4 |
| cloud-hypervisor | default | **virtio-pci** | 3 | 2 |
| qemu-microvm | default | virtio-mmio | 0 (slots) | 3 |

Cloud Hypervisor is in the table deliberately: a microVM *with* a PCI bus. If absence were a
property of the class rather than of the entry, that row could not be written and the format
would be wrong.

Each entry records `describes_version` and `reference`. The header states the evidence class
plainly: these are transcribed from hypervisor documentation, not ingested from a vendor document
under `.cache/`, which makes them weaker than a `pci.ids` lookup. D4's probe is the check, and a
probe that contradicts an entry is a finding about the table.

## Task 3: the measurement

| | |
|---|---|
| Questions asked | **0** |
| Facts emitted | 14 (class, arch, firmware, silicon×5, platform×5, devices×2) |
| Facts carrying `source: derived` | all except silicon |
| `assumptions` entries | **1** — silicon |
| Validates under D6 | yes, exit 0 |

The single assumption is the one fact derivation genuinely cannot supply: a guest does not choose
its CPU and the hypervisor config does not state it. It stays `source: assumed` until D4 probes a
running instance.

## Task 2: the round-trip

`firecracker.md` is kept as a hand-written control rather than regenerated, so the derivation has
something independent to check against. Six differences, all resolved in writing:

| Difference | Resolution |
|---|---|
| `machine: microvm` vs `default` | Derivation right — `microvm` is QEMU's name |
| `transport` absent from control | Derivation right — added; it is load-bearing |
| `console` absent from control | Derivation right — a platform fact, added |
| PCI ids vs MMIO ids | Derivation right — control corrected |
| "input: serial console" assumption | Split: `platform.console` + `absent: display` |
| `source: user-stated` vs `derived` | **Both right** — same value, two ways of knowing it |
| `stated_at` vs `describes_version` | Both right — a derivation cites the table and its version; a timestamp would make the output non-deterministic |

A test asserts the two agree on class, firmware, transport, console, every device id and role, and
the whole absence list.

## Validation

28 + 20 = 48 tests pass. Mutation-tested; every mutation caught:

| Mutation | Tests failed |
|---|---|
| derived device facts claim `source: probed` | 2 |
| derived platform facts claim `source: probed` | 3 |
| `pins_devices` ignored (slots treated as occupants) | 1 |
| absences folded back into `assumptions` | 3 |
| MMIO ids replaced with PCI ids in the table | 2 |

One mutation appeared to survive and did not: the `sed` had failed to match, so nothing was
mutated. Re-applied with an exact replacement, it failed 2 tests.

## Files

| File | Action | Lines |
|---|---|---|
| `agent/kernel_spec/targets/hypervisors.yaml` | CREATED | 107 |
| `agent/tests/unit/test_target_derivation.py` | CREATED | 20 tests |
| `agent/tools/target_spec.py` | UPDATED | id grammar, `absent`, derivation |
| `agent/kernel_spec/targets/firecracker.md` | UPDATED | corrected; now the control |
| `agent/kernel_spec/targets/README.md` | UPDATED | rules 2, 5, 6; derivation section |
| `agent/tests/unit/test_target_spec.py` | UPDATED | stale machine name in 2 fixtures |

## Acceptance

- [x] A hypervisor table stating present *and* absent devices, versioned
- [x] Firecracker derives a complete, valid target with no questions asked
- [x] Derived facts carry `source: derived`; `assumptions` holds one justified entry
- [x] A round-trip against the hand-written example resolves every difference in writing
