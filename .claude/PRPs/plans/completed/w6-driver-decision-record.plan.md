# Plan: Driver Decision Record Format (V2)

**Source PRD**: `auton-driver-development.prd.md` — phase V2
**Depends on**: D1 (landed — this is what unblocked it)
**Unblocks**: V4 (strategy selection), V5 (virtio-net), and with V5 the whole driver ladder

## Summary

A target says a device is present. The capability index says whether the tree can drive it. What
neither says is **how this driver came to exist and how anyone would know it works** — reused
from an existing implementation, ported from another OS, or synthesized from a specification.

The PRD's demand is that `verification` is mandatory and executable. A driver record that cannot
say how its claim was checked is an assertion, and an assertion about hardware is the most
expensive kind to be wrong about.

## Evidence

- `agent/kernel_spec/mitigations/README.md:24-34` — the nearest precedent, and a good one. Per-item
  records with a "Why each field exists" table, `cost` **mandatory** ("a mitigation with unstated
  cost gets applied everywhere"), `verify` **"mandatory, and mechanical"**, and `status` with
  `unmitigatable` as a real answer. A driver record wants the same three properties under
  different names.
- `agent/kernel_spec/services/README.md:29-41` — the field-justification table, and the rule that
  closes it: *"Nothing else. A field is added when a second service genuinely cannot be expressed
  without it, not in anticipation."* D1 followed that rule and it held: two structurally different
  targets, no field added.
- `agent/kernel_spec/services/README.md:45,49` — *"Do not restate a subsystem spec"* and *"Cite
  protocols normatively"*. Both bind here hard: `subsystems/drivers.md` already carries register
  layouts for AHCI (`:50`), NVMe (`:113`), VirtIO Block (`:163`), e1000 (`:216`) and VESA
  (`:279`). A driver record that repeats them creates a second source of truth that will drift.
- `agent/kernel_spec/targets/README.md` (w6/D1, landed) — the format doc to mirror in shape:
  numbered rules, each justified by the failure it prevents, plus an exit-code table.
- `agent/tools/device_registry.py` `identify()` (w6/V3, landed) — a record naming a device id
  resolves against the ingested registry, with the same three outcomes.
- `agent/tools/target_spec.py` `PCI_ID` / `MMIO_ID` — **two** id forms. A microVM's devices have
  no PCI pair at all, and a driver record format admitting only `vvvv:dddd` would be unable to
  describe a virtio-mmio driver — which is precisely the driver V5 is about to write.
- `.claude/PRPs/reports/w6-driver-capability-honesty-report.md` — 27 capabilities have no
  implementation. These records are where a decision to change that gets written down.

## Patterns to Mirror

- **Mandatory-with-a-reason**: `mitigations/README.md:32-34`. Each mandatory field's row says what
  goes wrong when it is absent, not that it is required.
- **A third state that is a real answer**: `status: unmitigatable`. The driver equivalent is a
  device that cannot be driven from an open specification and has no documentation — saying so is
  more useful than an empty record.
- **Two structurally different examples**: D1's `qemu-pc.md` / `firecracker.md`, where the second
  was written deliberately second and **without adding a field**. Same bar here.
- **Refusal names the field**: `target_spec.TargetError`.

## Tasks

### Task 1: The fields, each justified by the failure it prevents
- **Action**: `agent/kernel_spec/drivers/README.md` — the format. Start from what V4 and V5 will
  actually need and justify each field against a failure, in the voice of
  `mitigations/README.md:24`.
- **The candidate set, and why each earns its place**:
  - `driver` — identity, matches the filename, as services and mitigations do.
  - `devices` — the ids it binds to, in either form (`vvvv:dddd` or `virtio-mmio:<type>`).
  - `provides` — capabilities, joining to the index and therefore to `source_map.yaml`.
  - `strategy` — `reuse` / `port` / `synthesize`. V4 selects it; this is where it is recorded.
  - `source` — for `reuse`/`port`, what it came from **and its licence**. A ported driver with an
    unrecorded licence is a legal defect that surfaces at distribution, long after the decision.
  - `specification` — for `synthesize`, the normative document and section.
  - `verification` — **mandatory and executable**. How the claim was checked.
  - `status` — `implemented` / `specified` / `undrivable`.
- **Gotcha**: resist `author`, `date`, `version`. Git records them, and a field git already owns
  goes stale in the file while staying correct in the history.
- **Validate**: every field's row says what goes wrong without it. A field whose row says "useful
  for reference" is cut before the format ships.

### Task 2: `verification` is mandatory and executable
- **Action**: `verification` names a command or an observable marker, not a description.
- **Why**: this is the PRD's stated demand and the format's whole point. `mitigations/README.md:33`
  puts it exactly: *"An image that claims a mitigation it did not apply is worse than one that
  declines it, because the claim is the part a user acts on."* A driver claiming to work is the
  same shape of claim.
- **Gotcha**: for a driver that is `specified` but not `implemented`, `verification` states how it
  *would* be checked. Allowing it to be empty until implementation is how it ends up empty
  afterwards — the mitigations registry already refuses that trade.
- **Validate**: a record whose `verification` is prose with no command and no marker is refused,
  naming the field.

### Task 3: Two structurally different examples, second written without adding a field
- **Action**: `virtio-net.md` (`strategy: synthesize`, from the open VIRTIO 1.2 specification,
  `virtio-mmio:1` **and** `1af4:1041` — the same driver on two transports) and `e1000.md`
  (`strategy: port` or `reuse`, a documented register set, a single PCI id, `status: implemented`
  — it is the one driver the tree actually has).
- **Why these two**: they differ on every axis the format claims to express — strategy, id form,
  transport count, status. If the format survives both, it is a format; if the second needs a new
  field, the first one taught it the wrong shape. This is D1's test, and D1 passed it.
- **Gotcha**: `virtio-net.md` is a *record*, not the driver. V5 writes the driver. A record that
  quietly becomes a specification duplicates `subsystems/drivers.md:163-215` and will drift from it.
- **Validate**: `e1000.md` is written second and adds no field. Any field it needs is a finding
  about `virtio-net.md`, resolved in writing.

### Task 4: Validate and refuse
- **Action**: `agent/tools/driver_spec.py --validate` — parse, refuse by field name, resolve every
  device id against the registry.
- **Mirror**: `target_spec.py` exactly — same refusal style, same three-valued identification,
  same "unverifiable is not valid" exit-code discipline.
- **Gotcha**: a driver record naming a device absent from `pci.ids` cannot appeal to `source:
  probed` the way a target can — there is no machine here to have observed it. An unlisted device
  id in a driver record is refused unless the record names the specification that defines it, the
  way `virtio-mmio:<type>` resolves against the VIRTIO type table rather than against `pci.ids`.
- **Validate**: both examples validate; a record naming `ffff:ffff` is refused by name; with the
  registry absent the result is unverifiable, not valid.

### Task 5: Join to the capability index
- **Action**: A record's `provides` must name capabilities the index defines, and a driver whose
  `provides` has no `source_map.yaml` mapping is reported — not refused.
- **Why reported and not refused**: a record for a driver that does not exist yet is the point.
  `status: specified` with no mapping is the normal state before V5 runs; refusing it would make
  the format unusable for the thing it exists to plan.
- **Gotcha**: `gate_capabilities` (w6/V1) refuses a *build* on the same condition. The two must
  not be confused — a record is a plan, a build is a claim.
- **Validate**: `virtio-net.md` with `status: specified` validates and reports the unmapped
  capability; the same record with `status: implemented` and no mapping is refused, because that
  combination is a false claim.

## Validation

```bash
python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/virtio-net.md
python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/e1000.md
python agent/tools/driver_spec.py --validate <a record naming ffff:ffff>   # refuses
python agent/tools/driver_spec.py --all
cd agent && python -m pytest tests/unit/test_driver_spec.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The record restates `drivers.md`'s register layouts | **H** | Task 3's gotcha; `services/README.md:45` is the existing rule and it is cited in the format doc |
| `verification` becomes prose nobody can run | **H** | Task 2 refuses prose-only; the mitigations registry already set this bar and held it |
| Fields added in anticipation of V4 | **M** | Task 1's cut rule and Task 3's no-new-field test, both taken from D1 where they worked |
| A ported driver's licence goes unrecorded | **M** | `source` carries the licence for `reuse`/`port`; a record without one is refused |
| The format is designed around virtio and breaks on real hardware | **M** | `e1000.md` is the second example precisely because it is the unlike one |

## Acceptance
- [ ] Every field justified by the failure its absence causes; no field git already owns
- [ ] `verification` mandatory and executable, including for `status: specified`
- [ ] Two structurally different records, the second adding no field
- [ ] Both id forms admitted; a device absent from every registry is refused by name
- [ ] A missing registry yields unverifiable, never valid
- [ ] `status: implemented` with no source mapping is refused; `status: specified` is reported
