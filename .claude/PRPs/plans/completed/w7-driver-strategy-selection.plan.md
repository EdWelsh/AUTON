# Plan: Strategy Selection (V4)

**Source PRD**: `auton-driver-development.prd.md` — phase V4
**Depends on**: V2 (landed), V3 (landed)
**Why first**: `strategy` is a field in every driver record and nothing decides it. V5 should be
the *output* of a decision, not a hand-wave that a record then documents.

## Summary

A driver record carries `strategy: reuse | port | synthesize`. V2 built the field and the rule
that each strategy must name its basis — a `source` with a licence, or a `specification`. What
does not exist is anything that *chooses*, or that can say no.

The PRD's security argument makes the ordering non-obvious in exactly one direction: **reuse >
port > synthesize**, because a synthesized driver is ring-0 DMA-capable code nobody has ever run.
So the selection must default to the least novel option that is actually available, and refuse
when none is.

## Evidence

- `auton-driver-development.prd.md:57-77` — the security argument, stated first. *"A synthesized
  DMA programming error is an arbitrary-write primitive"*, and *"synthesis must carry the
  heaviest verification burden rather than the lightest"*.
- `agent/kernel_spec/drivers/README.md` — `strategy`, `source` (mandatory for reuse/port, **with
  its licence**) and `specification` (mandatory for synthesize). The fields a decision must fill.
- `agent/tools/driver_spec.py` `STRATEGY_REQUIRES` — the mapping strategy → required basis. A
  selector must produce a record that passes this, or it has selected something unwritable.
- `agent/hardware/vendors.yaml` — **44 documents across 25 vendors**, the inventory H1 built.
  This is what answers "is there a specification to synthesize from" for a given device class.
- `agent/tools/vendor_inventory.py:80` `load()`, `:54` `Document` — the loader and the record
  shape, including licence and `form`.
- `agent/tools/device_registry.py` `identify()` — V3. A device id yields a vendor and a title,
  deterministically, with provenance. That vendor is the join key into the inventory.
- **The gap this will surface**: `drivers/virtio-net.md` cites *"VIRTIO 1.2 §5.1"*, and **there
  is no VIRTIO specification in `vendors.yaml`**. The record's basis is a document the tree
  cannot fetch, has not ingested, and does not know the licence of. A selector that consults the
  inventory will refuse `synthesize` for virtio-net, which is the correct and inconvenient
  answer.

## Patterns to Mirror

- **Three-valued outcome**: `target_spec.Identification`, `errata_table.Verdict`. "No defensible
  option" is a value, not an exception in disguise.
- **Refusal explains what to do next**: `build_service.GateFailure`.
- **Provenance travels with the fact**: `vendor_ingest.Record`. A selection cites the inventory
  entry that justified it.
- **Data, not logic**: `source_map.yaml`, `hypervisors.yaml`, `pci-classes.yaml`. Licence
  compatibility is a table, not a function.

## Tasks

### Task 1: The criteria, written down before the code
- **Action**: `agent/kernel_spec/drivers/STRATEGY.md` — what makes each strategy available, and
  what makes it preferred, each justified by the PRD's security argument rather than by taste.
- **Why a document**: a selector whose criteria live only in code cannot be argued with, and this
  is a decision about ring-0 code where being argued with is the point.
- **Gotcha**: *available* and *preferred* are different questions. Synthesize is almost always
  *available* (there is usually some document); it is preferred almost never. Conflating them is
  how "we had a datasheet" becomes a justification.
- **Validate**: each rule cites either the PRD's security table or a licence fact, and none cites
  convenience.

### Task 2: Licence compatibility as a table
- **Action**: `agent/kernel_spec/drivers/licences.yaml` — per licence, whether reuse and port are
  permissible for this project, and what obligation each carries.
- **Why data**: the mapping is a fact with a citation, not a rule to compute, and it is the field
  most likely to be wrong in a way nobody notices until distribution.
- **Gotcha**: *do not encode legal advice.* The table records what a licence requires
  (attribution, source disclosure, same-licence derivative works) and refuses to characterise
  what is "safe". Where the answer depends on how the code is combined, the entry says so and the
  selector refuses rather than guessing.
- **Validate**: an entry exists for GPL-2.0, BSD-3-Clause, MIT and "unknown"; the `unknown` entry
  makes reuse and port unavailable rather than assumed-fine.

### Task 3: Select, and record why
- **Action**: `agent/tools/driver_strategy.py --device <id>` — identify the device (V3), look up
  what the inventory offers for that vendor, apply the criteria, and emit a decision with its
  rationale and the inventory entry that justified it.
- **Mirror**: `errata_join.Join` — a result object carrying what could and could not be
  established, never a bare value.
- **Gotcha**: the selector must produce something `driver_spec.load` accepts. A decision of
  `synthesize` with no ingestable specification produces a record that fails validation, so the
  selector must check the basis *before* choosing, not after.
- **Validate**: `8086:100e` selects a strategy and names the document behind it; the decision
  round-trips into a record that validates.

### Task 4: Refuse rather than guess
- **Action**: When no strategy is defensible — no reusable driver, no portable source with a
  workable licence, no ingestable specification — refuse, naming each option and why it is
  unavailable.
- **Why**: this is the PRD's stated behaviour, and the alternative is a record asserting
  `synthesize` against a document nobody can fetch. That record validates structurally and is a
  lie.
- **Gotcha**: "no document in the inventory" and "a document exists but is not ingested" are
  different states, and the second is actionable — `vendor_fetch.py` exists. Say which.
- **Validate**: `1234:1111` (QEMU's Bochs VGA, in no registry and no inventory) is refused with
  all three options named; the refusal for virtio's ids says the VIRTIO spec is not inventoried.

### Task 5: The inventory gap this exposes
- **Action**: Add the VIRTIO specification to `agent/hardware/vendors.yaml` — it is the document
  `virtio-net.md` already cites, and V5 cannot honestly proceed while its basis is uninventoried.
- **Why here and not in V5**: the gap is *found* by this phase's selector, and the fix belongs
  with the thing that found it. V5 then consumes an inventory entry rather than asserting a
  citation.
- **Gotcha**: `vendor_inventory.fetch_plan` refuses a tracked destination and `.cache/` is
  gitignored — the VIRTIO specification is freely available but this repo still does not commit
  vendor documents. Inventory it; do not vendor it.
- **Validate**: `vendor_inventory.py --coverage` lists VIRTIO; `fetch_plan` produces a plan whose
  destination is untracked.

## Validation

```bash
python agent/tools/driver_strategy.py --device 8086:100e
python agent/tools/driver_strategy.py --device virtio-mmio:1
python agent/tools/driver_strategy.py --device 1234:1111        # refuses, names all three
python agent/tools/vendor_inventory.py --coverage | grep -i virtio
cd agent && python -m pytest tests/unit/test_driver_strategy.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `synthesize` is selected because it is always technically available | **H** | Task 1 separates *available* from *preferred*; Task 3 checks the basis is ingestable before choosing |
| The licence table becomes legal advice | **H** | Task 2 records obligations and refuses to characterise safety; ambiguity is a refusal, not a judgement |
| A decision cites a document nobody can fetch | **H** | Task 4 distinguishes "not inventoried" from "not ingested", and Task 5 closes the one real instance |
| The selector duplicates `driver_spec`'s validation and drifts | **M** | Task 3 emits a record and validates it through `driver_spec.load`; one validator |
| It selects for devices nothing will ever drive | **L** | Input is a device id from a target, so the set is bounded by what a target actually has |

## Acceptance
- [ ] Criteria written down and justified by the security argument, not convenience
- [ ] *Available* and *preferred* are separate questions, and the document says so
- [ ] Licence compatibility is a table; `unknown` makes reuse and port unavailable
- [ ] A selection cites the inventory entry that justified it
- [ ] No defensible option produces a refusal naming all three and why each fails
- [ ] "Not inventoried" and "not ingested" are distinguished
- [ ] The VIRTIO specification is inventoried, and not committed
