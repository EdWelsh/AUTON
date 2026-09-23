# Plan: Join a Target to the Capability Manifest (D7)

**Source PRD**: `auton-hardware-definition.prd.md` — phase D7
**Depends on**: D1 (landed), intent-B (landed)
**Why first among the remaining**: D1–D3 built target definitions that nothing reads. This is the
phase where a target starts changing what gets built.

## Summary

`e1000` is hardcoded into three intent rules. Every network image AUTON can build is built for an
Intel 82540EM, whatever machine it is going to run on — including a Firecracker microVM that has
no PCI bus at all.

An intent should say what the image is *for*. A target says what the machine *is*. The driver is
the join of the two, and right now the intent decides it alone.

## Evidence

- `agent/tools/intent_manifest.py:80,87,94` — `requires=("e1000", ...)` in `host-repo`,
  `serve-dhcp` and `serve-files`. Three of the five rules name a specific NIC.
- `agent/kernel_spec/targets/firecracker.md` — `transport: virtio-mmio`, `absent: "PCI bus —
  enumeration finds nothing"`. An `e1000` driver on this machine binds to nothing.
- `agent/tools/build_service.py` `gate_capabilities` (w6, landed) — **will not catch this.**
  `e1000` has a source mapping, so the slice resolves, the gate passes, and the image builds with
  a driver for a NIC that is not there. V1 catches *required but unimplementable*; this is
  *implemented but not on this machine*, which is the mirror case and currently invisible.
- `SLM/tools/build_corpus.py:28-33` `PCI_KB` — the only table in the tree tying device ids to
  driver names (`8086:100e → e1000`, `1af4:1000 → virtio-net`).
- `SLM/tools/build_corpus.py:351-354` `DRIVER_CAPS` — driver names to capabilities
  (`virtio-net → {net}`, `virtio-blk → {fs}`).
- `agent/tools/intent_manifest.py:117-119` `DEFAULTS["input"]` — assumes a serial console because
  nothing could say otherwise. `firecracker.md` records `absent: display` as a fact, which makes
  the assumption unnecessary rather than merely better-guessed.
- `agent/tools/target_spec.py` `Device.role` — every device already carries `network`, `storage`,
  `display` or `console`. The join key exists; nothing consumes it.

## Patterns to Mirror

- **Refusal style**: `build_service.py` `gate_capabilities` — `[gate: <name>]`, names the thing,
  says what to do next.
- **Three-valued outcome**: `target_spec.Identification` — where "cannot tell" is possible it is
  a value, never folded into a pass.
- **Recorded, never silent**: `intent_manifest.py:113-115` — the comment above `DEFAULTS` is the
  house rule. A default that is applied is written into `assumptions`.

## Tasks

### Task 1: Roles, not drivers, in the intent rules
- **Action**: Drop `e1000` from the three rules' `requires`. Add a separate `roles` field to
  `IntentRule` (`intent_manifest.py:47`) naming what the image needs *hardware* for —
  `("network",)` for all three. The driver is selected later, from the target.
- **Why a new field rather than reusing `requires`**: `requires` names capabilities from the
  subsystem index, and a role is not one. **Verified**: `net` is a *subsystem* name, not an index
  capability — `capability_slice(["boot", "net"])` and `capability_slice(["boot", "udp"])` both
  resolve to the same six subsystems, so putting `net` in `requires` would be an alias for `udp`
  and would violate `services/README.md` rule 2 ("`requires` names capabilities, not subsystems").
  The two lists answer different questions and must not be merged.
- **Gotcha**: `requires` is validated against the index at `intent_manifest.py:212-217` and drives
  both `derive_excludes` (`intent_manifest.py:168`) and `capability_slice`. `roles` must be
  excluded from all three, or a role name will be reported as an unknown capability.
- **Validate**: `build("hand out addresses")` with no target still resolves, its `requires` no
  longer contains a driver name, and its slice is unchanged from today's.

### Task 2: Select the driver from the target
- **Action**: `build(sentence, target=<Target>)` maps each required role to a driver, using the
  target's devices and `PCI_KB`/`DRIVER_CAPS`.
- **Why measured this way**: the selection is a table lookup joined on `Device.role`, not an
  inference. The same rule H2 set — device facts come from tables.
- **Gotcha**: `PCI_KB` lives in `SLM/tools/build_corpus.py`, which is corpus tooling, not factory
  tooling. Importing the factory's device knowledge from the corpus generator inverts the
  dependency. Move the table to `agent/tools/` and have the corpus read it, or the next change to
  the corpus will silently change what gets built.
- **Gotcha**: `virtio-mmio:1` is a role-carrying device with no PCI id. The join must be on
  `role`, not on id — a lookup keyed on `vvvv:dddd` cannot see a microVM's devices at all.
- **Validate**: the same sentence against `qemu-pc.md` yields `e1000`; against `firecracker.md`
  yields `virtio-net`. The manifest records which target chose it.

### Task 3: A machine that cannot serve the intent is refused
- **Action**: An intent requiring `net` against a target with no network device refuses, naming
  the target and the role.
- **Why**: this is the mirror of `gate_capabilities`, and the more likely failure of the two. The
  guest derived from a Doom host (D2) has no network device *by construction* — building a DHCP
  server for it produces an image that cannot work, and nothing today would say so.
- **Gotcha**: refuse on the *role*, not on the driver. "No driver for e1000" is a different and
  less useful sentence than "this machine has no network device".
- **Validate**: deriving a guest from the Doom host package (D2) and asking for a DHCP server is
  refused, naming the absent role.

### Task 4: A target replaces an assumption rather than improving it
- **Action**: Where the target states a fact the manifest was assuming, the assumption is dropped
  and the fact recorded with its `source`.
- **Why**: the PRD's metric is *facts carrying a source*, not *better defaults*. An assumption
  that survives as a better guess is still a guess.
- **Validate**: `build("hand out addresses")` alone carries the `input:` assumption;
  `build(..., target=firecracker)` carries none, because `absent: display` settles it. Measured
  as a count, before and after.

### Task 5: The join is recorded, not just applied
- **Action**: The manifest records, per driver, which device and which target chose it.
- **Why**: `package_image.py` writes the target into `PROVENANCE.json` (D2, landed). A reviewer
  can then see *why this image has this driver* without re-deriving it.
- **Validate**: a packaged image's provenance names the device id behind each driver.

## Validation

```bash
python agent/tools/intent_manifest.py "hand out addresses" \
    --target agent/kernel_spec/targets/qemu-pc.md      # e1000
python agent/tools/intent_manifest.py "hand out addresses" \
    --target agent/kernel_spec/targets/firecracker.md  # virtio-net
python agent/tools/intent_manifest.py "hand out addresses" \
    --target <a guest derived from the Doom host>      # refuses: no network device
cd agent && python -m pytest tests/unit/test_intent_manifest.py tests/unit/test_target_join.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The factory imports device knowledge from the corpus generator | **H** | Task 2 moves `PCI_KB` to `agent/tools/` first; the corpus becomes the consumer |
| Removing `e1000` from the rules breaks every existing test and fixture | **H** | The three rules are the blast radius; `test_intent_manifest.py` and the corpus expectations both assert on `e1000` today. Expect to update both, and treat a surprised test as a finding |
| A target with no devices silently produces a driverless image | **M** | Task 3 refuses on the role. A microVM with an empty device list is already refused by D6 unless its platform pins one |
| The join duplicates `gate_capabilities` | **L** | They answer different questions — *can this tree implement it* versus *is it on this machine*. Both must fire |
| Targets become mandatory and every existing call site breaks | **M** | `target=None` keeps today's behaviour and records that no target was stated, matching `package_image.py`'s `target.stated: false` |

## Acceptance
- [ ] No intent rule names a driver
- [ ] The same sentence yields `e1000` on the QEMU PC and `virtio-net` on Firecracker
- [ ] An intent whose role the target cannot supply is refused, naming the role and the target
- [ ] A stated target reduces the assumption count; measured before and after
- [ ] The manifest records which device chose each driver, and provenance carries it
- [ ] `PCI_KB` lives in factory tooling; the corpus reads it rather than owning it
