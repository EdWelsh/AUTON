# Implementation Report: Join a Target to the Capability Manifest (D7)

## Summary

`e1000` was hardcoded into three of the five intent rules. Every network image AUTON could build
was built for an Intel 82540EM whatever machine it was going to run on. The driver now comes from
the target's own devices, joined on `role`.

Doing that surfaced a fact the tree had been hiding: **AUTON can build a network image for
exactly one kind of machine.**

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Roles, not drivers, in the intent rules | Complete | new `roles` field, not merged into `requires` |
| 2 | Select the driver from the target | Complete | table moved to `agent/tools/device_drivers.py` |
| 3 | A machine that cannot serve the intent is refused | Complete | three distinct refusals, not one |
| 4 | A target replaces an assumption rather than improving it | Complete | measured |
| 5 | The join is recorded, not just applied | Complete | reaches `spec/manifest.json` |

## The finding

`drivers.md` `provides` lists exactly one network driver: `e1000`. `virtio-net` appears in that
file only as a `#define` inside the *block device* section and in a comment at `:444`. It is not
a capability.

So a Firecracker target — whose network device is `virtio-mmio:1` — cannot be served at all:

```
MISMATCH: target 'firecracker' needs 'virtio-net' for its network device virtio-mmio:1, and no
subsystem spec provides it. `virtio-net` is not in the capability index — see
kernel_spec/subsystems/drivers.md `provides`. A driver record and an implementation are needed
first (auton-driver-development.prd.md, V2 then V5)
```

That was invisible while the driver came from the intent rule: the rule said `e1000`, `e1000` is
mapped, `[gate: capabilities]` passed, and the image built. It would have had a driver for a NIC
the machine does not have, on a bus the machine does not have.

This is V5's justification stated as a measurement rather than an intention. A test asserts the
count — if a second network driver ever appears in the index, that test fails and is deleted.

## Design decisions the work forced

**`roles` is a separate field, not a value in `requires`.** The obvious move is to require `net`
instead of `e1000`. Measured and rejected: `net` is a *subsystem* name, and
`capability_slice(["boot","net"])` and `capability_slice(["boot","udp"])` resolve to the **same six
subsystems**. Putting it in `requires` would make it an alias for `udp` and would break
`services/README.md` rule 2. The two lists answer different questions — what the image does, and
what it runs on.

**The default stayed, and became visible.** Dropping `e1000` entirely would break every caller
that states no target. It is now `DEFAULTS["network"]`, alongside the input default, and it is
recorded as an assumption on every manifest built without a target. The rule the file already
states — *"Applied when the sentence does not say. Recorded, never silent"* — now covers the NIC.

**Three refusals, not one.** They are different problems and the reader needs to know which:

| Case | Message |
|---|---|
| No device for the role | `has no device with role 'network'`, quoting the recorded absence |
| Device present, no driver known | names the device id, points at `kernel_spec/drivers/` |
| Driver known, not in the index | names the driver and points at V2 then V5 |

The third deliberately does **not** raise through the existing index check, which would have
printed *"The rule table and the specs disagree"* — blaming a file that no longer names a driver
at all.

## Task 4: the measurement

| Intent | Target | Assumptions | Decisions |
|---|---|---|---|
| what hardware is this | none | 1 | 0 |
| what hardware is this | firecracker | **0** | 1 |
| hand out addresses | none | 2 | 0 |
| hand out addresses | qemu-pc | **1** | 1 |

The remaining assumption on `qemu-pc` is correct and not a gap: that machine *has* a display
device (`1234:1111`) and no framebuffer driver, so the serial-console assumption is still a real
assumption. Firecracker records `absent: display`, which settles it as a fact.

## Task 2: the table moved

`PCI_KB` and `DRIVER_CAPS` lived in `SLM/tools/build_corpus.py` — corpus tooling. The factory read
its device knowledge from the corpus generator, so a change made to improve a training set would
silently change what got built. They are now `agent/tools/device_drivers.py` and the corpus
imports them; `build_corpus.py:389` already reached into `agent/tools`, so the direction was
already established.

The move added what the old table could not express: `virtio-mmio:<type>` ids, and modern
virtio-pci ids computed as `0x1040 + device type` rather than enumerated.

## Validation

1213 unit tests pass (was 1184), 111 SLM tests. 26 new tests in `test_target_join.py`, 3 in
`test_package_image.py`. Mutation-tested:

| Mutation | Tests failed |
|---|---|
| `e1000` put back in a rule | 1 |
| no device for the role silently ignored | 2 |
| a driver absent from the index used anyway | 2 |
| a target no longer suppresses the assumption | 1 |
| the decision record drops the device source | **0 → 2** |
| MMIO ids no longer resolve | 2 |

The fifth survived on first run: the test asserted `device_source == "probed"` against a fixture
whose device *was* probed, so hardcoding `"probed"` passed. Widened to parameterise over all three
sources; it now fails the mutation.

## Deviations

The plan's Task 2 validation expected *"against `firecracker.md` yields `virtio-net`"*. It yields
a refusal, because `virtio-net` is not in the capability index. The selection mechanism is tested
against an injected capability set — `_drivers_from_target` takes it as an argument for exactly
that reason — so the mechanism is proven apart from what the tree provides today.

The plan predicted a large blast radius from removing `e1000`. Measured: no test asserted that
`e1000` came from an intent rule, and the generated/hand-written round-trip compares *subsystems*,
which are unchanged. The four failures that did appear were the D2 packaging tests pairing
Firecracker with a DHCP intent — a pairing that is now correctly impossible.

## Files

| File | Action |
|---|---|
| `agent/tools/device_drivers.py` | CREATED |
| `agent/tests/unit/test_target_join.py` | CREATED — 26 tests |
| `agent/tools/intent_manifest.py` | UPDATED — `roles`, `TargetMismatch`, the join |
| `agent/tools/package_image.py` | UPDATED — target loaded before the intent is matched |
| `SLM/tools/build_corpus.py` | UPDATED — imports the moved table |
| `agent/tests/unit/test_package_image.py` | UPDATED — 3 tests added, 6 repointed |

## Acceptance

- [x] No intent rule names a driver
- [x] The same sentence yields `e1000` on the QEMU PC; on Firecracker it is refused, naming why
- [x] An intent whose role the target cannot supply is refused, naming the role and the target
- [x] A stated target reduces the assumption count; measured above
- [x] The manifest records which device chose each driver; it reaches `spec/manifest.json`
- [x] `PCI_KB` lives in factory tooling; the corpus reads it
