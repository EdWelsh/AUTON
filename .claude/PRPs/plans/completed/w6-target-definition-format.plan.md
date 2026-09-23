# Plan: Target Definition Format (D1)

**Source PRD**: `.claude/PRPs/prds/auton-hardware-definition.prd.md` — phase D1
**Complexity**: Small — a format plus two worked examples, mirroring the service-spec format
**Unblocks**: every other phase in the PRD, and the driver PRD entirely

## Summary

Agents build for hardware they cannot see, and the target is currently implicit: QEMU's
idealised PC, hardcoded everywhere. This defines the format that makes a target explicit, and
makes every fact in it carry where it came from.

## Evidence

- `SLM/tools/build_corpus.py` `BUS_DEVICES` — the device list is a hardcoded literal:
  `8086:1237 8086:7000 1234:1111 8086:100e`. Every corpus answer, every rule-engine fact and
  every eval expectation is written against that one machine.
- `SLM/tools/build_corpus.py` `PCI_KB` — 4 devices. `.cache` ingest has **21,564**
  (`reports/w2-hardware-ingestion.md`).
- `agent/kernel_spec/services/README.md` — the format to mirror: front-matter plus prose, every
  field justified, validated by a tool that names the offending field.
- `agent/kernel_spec/arch/hal.md` category 8 — `ident_source_t` (`IDENT_UNKNOWN`, `IDENT_READ`,
  `IDENT_FIRMWARE`) already distinguishes *how confidently* a fact is known. This generalises it.
- `agent/tools/intent_manifest.py` — records applied defaults in an `assumptions` list rather
  than defaulting silently. Same discipline, different subject.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Format shape | `kernel_spec/services/README.md` | Front-matter + prose; a rationale table per field; "a field is added when a second case cannot be expressed without it" |
| Confidence per fact | `hal.md` `ident_source_t` | Unknown is not zero, and a consumer must check before using |
| Refusal that names the field | `service_spec.py` | `INVALID: <file>: field 'x' ...` — never a bare "invalid" |
| Two examples that differ | `services/dhcp.md` + `fileserver.md` | A format proven against one case has not been tested |

## Tasks

### Task 1: The format
- **Action**: `agent/kernel_spec/targets/README.md` + the front-matter schema. Fields: `target`,
  `class`, `arch`, `silicon`, `devices`, `firmware`, `assumptions`, `provenance`.
- **Critical**: **`source` is mandatory per fact**, from `{user-stated, probed, derived,
  assumed}`. A driver decision made on an assumption must be reversible when the truth arrives,
  and that is impossible if the record cannot say which facts were assumed.
- **Validate**: the rationale table justifies every field; a field nothing needs is removed.

### Task 2: Two worked examples that differ structurally
- **Action**: a bare-metal target (real silicon, real errata, many devices) and a microVM target
  (virtio only, often no PCI at all, MMIO instead). Write the second **without adding a field**.
- **Why**: `fileserver.md` earned the service format its credibility by being written second and
  needing nothing new. The same bar applies here, and the two classes are far further apart.
- **Validate**: both parse; a test asserts they carry the same field set.

### Task 3: Parse and validate
- **Action**: `agent/tools/target_spec.py` — parse, validate, and refuse by field name. A device
  id must resolve against the ingested registry; a `source` outside the enum is an error.
- **Gotcha**: the ingested registry lives in `.cache/`, which may be absent. A missing registry
  must make identification *unavailable*, not make an unknown device *valid* — the same
  distinction `run_leakage_test.sh` draws between "not generated" and "clean".
- **Validate**: a target naming `ffff:ffff` is refused; the same target with no registry cached
  is reported unverifiable rather than accepted.

### Task 4: Say what is missing
- **Action**: A definition too thin to support a build is refused, naming the missing facts —
  never defaulted to the QEMU PC.
- **Why**: silently defaulting is how every image becomes an image for a machine nobody owns.
- **Validate**: `class: bare-metal` with no devices is refused; `class: microvm` with no devices
  is accepted, because the machine type implies them.

## Validation

```bash
python agent/tools/target_spec.py --validate agent/kernel_spec/targets/qemu-pc.md
python agent/tools/target_spec.py --validate agent/kernel_spec/targets/firecracker.md
python agent/tools/target_spec.py --validate <a target naming a device not in pci.ids>   # refuses
cd agent && python -m pytest tests/unit/test_target_spec.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The format fits bare metal and breaks on microVM | **H** | Task 2 writes the microVM example second and forbids adding a field |
| `source` is filled in as `user-stated` for everything | **M** | D4's probe path and D2/D3's derivation set it themselves; only D5 writes `user-stated` |
| It duplicates the capability manifest | **M** | A target says what the hardware *is*; a manifest says what the image is *for*. D7 joins them, and neither restates the other |
| A missing registry makes bad targets look valid | **M** | Task 3: unverifiable is a third state, not a pass |

## Acceptance
- [ ] Every field justified; `source` mandatory per fact with a four-value enum
- [ ] Two structurally different targets expressed without adding a field
- [ ] A device absent from the ingested registry is refused by name
- [ ] A missing registry yields *unverifiable*, never *valid*
- [ ] An underspecified target is refused with the missing facts named, never defaulted
