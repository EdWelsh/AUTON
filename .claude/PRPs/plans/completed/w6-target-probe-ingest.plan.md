# Plan: Probe Ingest (D4)

**Source PRD**: `auton-hardware-definition.prd.md` — phase D4
**Depends on**: D1 (landed), H2 (landed)
**Unblocks**: D5, the last phase in the PRD

## Summary

D2 and D3 derive a target for machines whose device set is *decided* — an AUTON host, a
hypervisor machine type. Bare metal is the class where nothing is decided and nothing can be
derived: the only honest source is the machine itself.

So a user pastes `lspci -nn`, `/proc/cpuinfo` and `dmidecode` output into chat, and that becomes
a target definition with `source: probed` on every fact it supports.

## Evidence

- **Nothing in the tree parses probe output.** Searched with quoted globs across `agent/`,
  `scripts/` and `SLM/tools/`: the only mentions of `lspci`, `dmidecode` or `cpuinfo` are
  *specifications* of in-kernel behaviour — `subsystems/slm.md:401` (the shell-idiom table),
  `subsystems/fs.md:583` (`/proc/cpuinfo`), `slm_spec/evaluation.md:107`. This is a new parser,
  not an extension of one.
- `agent/tools/vendor_ingest.py:95-130` `parse_ids_registry` — the parser pattern to mirror:
  line-oriented, counts what it skips rather than dropping it silently, so an extraction rate can
  be reported honestly.
- `agent/tools/device_registry.py` `identify()` (w6, landed) — the join. A probed id resolves to
  a name with document provenance, or `UNKNOWN`, or `UNAVAILABLE`.
- `agent/tools/errata_table.py:54` `Signature.from_cpuid` — folds family/model exactly as
  `arch/x86_64.md` specifies. **The trap**: `/proc/cpuinfo` reports `cpu family`, `model` and
  `stepping` already folded, in decimal. Feeding those through `from_cpuid` folds them twice.
- `agent/kernel_spec/targets/qemu-pc.md:53-57` — "these ids were read from a running instance via
  `[DEV] PCI scan`, not stated by a person". That file is hand-written but claims `source:
  probed`; D4 is the tool that makes the claim true rather than asserted.
- `agent/tests/unit/test_target_derivation.py::test_nothing_derived_claims_to_have_been_probed` —
  D3 forbids the derivation writing `probed`. D4 is the only tool that may.

## Patterns to Mirror

- **Parser honesty**: `parse_ids_registry` counts skipped subsystem lines. A probe parser must
  report what it could not parse, not silently produce a shorter device list.
- **Three-valued identity**: `device_registry.Outcome` — a probed device absent from `pci.ids` is
  accepted (D1 rule 3: `source: probed` outranks the registry) and reported as unlisted.
- **Refusal names the field**: `target_spec.TargetError`.

## Tasks

### Task 1: Parse `lspci -nn`
- **Action**: `agent/tools/probe_ingest.py` — extract `vvvv:dddd` pairs and the class string from
  each line, map class to a target `role`.
- **Why the class string and not the name**: `lspci -nn` prints both a human name and a numeric
  class. The name is the *host's* `pci.ids`, which may be a different revision from the ingested
  one; using it would put an unattributed second source of truth into the record. Take the ids
  and the class, look the name up here.
- **Gotcha**: `lspci -nn` output varies by version and locale. Parse defensively and report the
  lines that did not match, with their text — a device silently dropped becomes a driver nobody
  builds.
- **Gotcha**: role mapping is from the PCI class code (`02xx` network, `01xx` storage,
  `03xx` display). That is a table, and it belongs next to the virtio type table in
  `hypervisors.yaml` or its own file — not inline in the parser.
- **Validate**: real `lspci -nn` output from a laptop and from a QEMU guest both parse; the
  unparsed-line count is zero or the lines are shown.

### Task 2: Parse `/proc/cpuinfo` into silicon
- **Action**: `vendor_id`, `cpu family`, `model`, `stepping` → the target's `silicon` block with
  `source: probed`.
- **Gotcha (the important one)**: these values are **already folded**. `Signature.from_cpuid`
  exists for a raw CPUID `eax`, and applying it here would fold extended family/model a second
  time — silently producing a different machine. A Core i7-8650U (family 6, model 142) would
  become something else, and `errata_table` would then answer about the wrong silicon
  confidently. Take the values as-is; use `from_cpuid` only where a raw signature is the input.
- **Validate**: a known `/proc/cpuinfo` yields family 6 / model 142 / stepping 10, cross-checked
  against `Signature.from_cpuid(0x806EA, ...)` producing the same triple by the other route.

### Task 3: Parse `dmidecode`, and refuse to guess the class
- **Action**: Firmware (`uefi`/`bios`) from the BIOS type; `class` from the system manufacturer
  where it is unambiguous — `QEMU`, `KVM`, `VMware`, `Amazon EC2` mean `vm`.
- **Why refuse rather than default**: a manufacturer this parser does not recognise might be a
  real vendor or a hypervisor it has not seen. Guessing `bare-metal` would make D6's
  bare-metal-specific requirements fire wrongly; guessing `vm` would suppress them. Leave `class`
  unset and let D6 refuse, naming it.
- **Gotcha — privacy**: `dmidecode` output carries the system **UUID**, **serial number** and
  asset tag. None of that is needed to build an image, and a target definition is a file that gets
  committed. Strip them at parse time and say in the record that they were stripped, so a reader
  knows the omission was deliberate. This mirrors the disclosure rule already enforced in
  `agent/tools/disclosure.py` — the tree already refuses to write private data to tracked paths.
- **Validate**: pasted `dmidecode` output containing a serial number produces a target with no
  serial number anywhere in it; an unrecognised manufacturer leaves `class` unset and the target
  is refused by D6 naming `class`.

### Task 4: Partial input is partial, not wrong
- **Action**: Any one of the three inputs may be absent. What it would have supplied is left
  unstated, never defaulted, and the resulting target is refused by D6 if the remainder is too
  thin.
- **Why**: a user pastes what they have. `lspci` without `dmidecode` is common — the devices are
  real and the firmware is unknown, and that is a better record than a guessed firmware.
- **Validate**: `lspci` alone produces a target with devices and no `firmware`, refused by D6
  naming `firmware`; adding `dmidecode` makes it valid.

### Task 5: Probed facts are the only ones that may say `probed`
- **Action**: Every fact this tool emits carries `source: probed`; every fact it could not
  observe is absent rather than filled from another source.
- **Why**: D3 asserts no derivation writes `probed`. If D4 writes `probed` for anything it
  inferred, that test's guarantee becomes meaningless from the other direction.
- **Validate**: a round-trip against `qemu-pc.md` — probing a QEMU guest reproduces its four
  devices, and every difference is resolved in writing, as D3 did against `firecracker.md`.

## Validation

```bash
lspci -nn | python agent/tools/probe_ingest.py --lspci - --name my-laptop
python agent/tools/probe_ingest.py --lspci lspci.txt --cpuinfo cpuinfo.txt \
    --dmidecode dmi.txt --name my-laptop > agent/kernel_spec/targets/my-laptop.md
python agent/tools/target_spec.py --validate agent/kernel_spec/targets/my-laptop.md
cd agent && python -m pytest tests/unit/test_probe_ingest.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| `dmidecode` serial numbers reach a committed file | **H** | Task 3 strips them and says so. Test asserts the absence, using output that contains one |
| `/proc/cpuinfo` values double-folded | **H** | Task 2's gotcha; the test cross-checks both routes to the same triple |
| `lspci` format variation drops devices silently | **M** | Task 1 reports unparsed lines with their text; zero-tolerance in the test |
| The class guess is wrong and D6's bare-metal rules misfire | **M** | Task 3 refuses to guess; D6 already refuses an unset class by name |
| Probe output is pasted from a machine the user does not have | **L** | `source: probed` is a claim like any other; D8's errata join will often contradict a wrong one |

## Acceptance
- [ ] `lspci -nn`, `/proc/cpuinfo` and `dmidecode` each parse, and unparsed lines are reported
- [ ] Device ids join to the ingested registry; an unlisted probed device is accepted, not refused
- [ ] Silicon is taken already-folded; a test proves both routes agree
- [ ] Serial numbers, UUIDs and asset tags never appear in the output
- [ ] An unrecognised manufacturer leaves `class` unset rather than guessing
- [ ] Partial input yields a partial target, refused by D6 naming what is missing
- [ ] Every emitted fact says `probed`; nothing inferred does
