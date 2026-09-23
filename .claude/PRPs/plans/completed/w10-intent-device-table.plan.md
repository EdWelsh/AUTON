# Plan: Device Table in the Model File (intent-I)

**Source PRD**: `auton-intent-to-os-compiler.prd.md` — phase I
**Depends on**: D (landed), H2 (landed)
**Why it is the only eligible phase**: see `.claude/PRPs/prds/ELIGIBILITY.md`

## Summary

The shipped model knows four device ids. `SLM/tools/build_corpus.py` `BUS_DEVICES` is QEMU's
default PC, and everything else the model says about hardware it invents — measured at **5 phantom
citations per 50 novel turns**, against 0 from a lookup.

Meanwhile `.cache/vendor/` holds **21,564 PCI and 20,537 USB** ingested records that the running
image cannot reach, because they live on the build host and the image ships a model file.

This puts the table *inside the model file*, as a section: one artifact, one version contract, no
way for model and table to drift.

## Evidence

- `.claude/PRPs/prds/auton-intent-to-os-compiler.prd.md:223` — the design, already decided:
  *"sorted identity keys plus a string pool, binary-searchable as mapped bytes, shipped as a
  section inside the model file — one artifact, one version contract, no way for model and table
  to drift. Scoped by manifest."*
- `.claude/PRPs/prds/auton-intent-to-os-compiler.prd.md:119` — the metric: 4 entries today,
  **≥30,000 PCI + ≥5,000 USB** target. See the Risks table: PCI is measured at 21,564.
- `SLM/tools/auton_format.py:9-41` — the layout, and `VERSION = 2` at `:53` with the comment
  explaining why a version bump is mandatory when a section is added: a v2 kernel reading a v3
  file *"would feed it an id that means something else entirely — a silently wrong model rather
  than a load error."*
- `SLM/tools/auton_format.py:241-276` — `validate()`, which re-reads a written file and refuses
  trailing bytes. A new section must be parsed there or it reads as corruption.
- `agent/kernel_spec/subsystems/slm.md:197-214` — `flat_header_t` in the kernel spec, the other
  half of the contract. Both sides must change together or the format has two definitions.
- `agent/tools/vendor_ingest.py:95-130` `parse_ids_registry` — where the records come from, with
  `document_revision` per record.
- `agent/tools/device_registry.py` — the host-side lookup this mirrors in-kernel. Same three
  outcomes; the kernel's `UNAVAILABLE` is "no table section in this model".
- `SLM/tools/build_corpus.py:28-49` — `BUS_DEVICES`, `UNKNOWN_DEVICES` and the comment recording
  the phantom-citation measurement: *"An id that is not on the bus must never appear in a
  response."*
- `agent/kernel_spec/subsystems/slm.md:389` — *"the same retrieval-not-generation rule already
  applied to device facts"*. This is that rule given something to retrieve from.

## Patterns to Mirror

- **One definition of a format**: `auton_format.py` and `slm.md` already mirror each other field
  for field. A section added to one and not the other is the drift the phase exists to prevent.
- **Exact-match versioning**: `VERSION = 2`'s comment. Not a minimum — an exact match, because a
  mismatched parse is silently wrong rather than loudly broken.
- **Provenance travels**: `vendor_ingest.Record` carries `document_revision`. A table that cannot
  say which pci.ids it came from cannot be re-checked.
- **Scoped by manifest**: `capability_slice`, `build_corpus.py --manifest`. A Doom image needs
  display and input entries, not every NIC ever made.

## Tasks

### Task 1: The section layout, written down before it is written
- **Action**: Extend the format docstring in `auton_format.py` and `flat_header_t`'s section in
  `slm.md` with the device-table layout, in the same voice.
- **Layout**: a count, then sorted fixed-width identity keys, then a string-pool offset per entry,
  then the pool. Binary-searchable in place; no allocation on lookup.
- **Gotcha**: the kernel maps the model file from a boot module and runs it **in place**. Anything
  requiring relocation or alignment beyond what the header already promises breaks that, and the
  docstring says so at `:5-7`.
- **Gotcha**: the id is not a string. `8086:100e` is two `uint16`s; storing it as text costs nine
  bytes per entry and makes the binary search a `strcmp`.
- **Validate**: the layout is stated in both files and they agree field for field.

### Task 2: Bump the version, on both sides
- **Action**: `VERSION = 3`, with the comment saying what changed and why an exact match matters.
- **Why mandatory**: a v2 kernel reading a v3 file would parse the table's bytes as tokenizer
  entries. That is the *silently wrong model* the v1→v2 comment already warns about, and the
  warning was written for exactly this situation.
- **Gotcha**: `validate()` refuses trailing bytes. A v3 file read by v3 code that does not know
  about the section fails there, which is correct — but the failure message must name the section
  rather than say "trailing bytes".
- **Validate**: a v2 file is refused by v3 code naming the version; a v3 file round-trips.

### Task 3: Build the table from the ingested registries
- **Action**: `SLM/tools/build_device_table.py` — read `pci-sig/pci-ids` and `usb-if/usb-ids`
  through `vendor_ingest`, sort by identity key, emit the section.
- **Gotcha**: **do not re-parse the raw files.** `vendor_ingest.parse_ids_registry` already counts
  what it skips so an extraction rate can be reported honestly, and a second parser would drift
  from the first — the same defect V6 found in the shared virtio reference.
- **Gotcha**: a duplicate key is possible (the same id in both registries is not, but a malformed
  registry could repeat one). Binary search over a list with duplicates returns an arbitrary
  match. Refuse rather than pick.
- **Validate**: 21,564 PCI + 20,537 USB entries; the section round-trips through `validate()`;
  keys are strictly ascending.

### Task 4: Scope it by manifest
- **Action**: `--manifest` filters the table the way `build_corpus.py` filters the corpus. A Doom
  image gets display and input classes; a DHCP image gets network.
- **Why**: the PRD's premise is per-image scoping, and a 42,000-entry table in an image that
  drives one NIC is the opposite. It is also the difference between a table that fits in a boot
  module and one that does not.
- **Gotcha**: scoping must never drop a device the *target* actually has. The manifest says what
  the image is for; the target says what the machine is. A scoped table missing `1234:1111` on a
  QEMU PC makes the image unable to name a device it can see.
- **Validate**: a Doom manifest yields a measurably smaller table than a full one, and both
  contain every id in `qemu-pc.md`.

### Task 5: Report what it cost, and what it cannot do
- **Action**: Record entry counts, section bytes, and the resulting model-file size.
- **Why**: the PRD's metric is entry count, and `auton_format.py`'s whole design premise is that
  the file is mapped and run in place. A table that doubles the file is a real trade and the
  number decides it.
- **Gotcha**: the in-kernel lookup is **not** implemented by this phase — `kernel/slm/neural/
  loader.c` does not exist, and no tree does. This phase ships the table and the host-side
  writer/reader; the kernel side is spec. Say so rather than implying the image can use it.
- **Validate**: the report states the counts, the bytes, and that the kernel consumer is specified
  and unwritten.

## Validation

```bash
python SLM/tools/build_device_table.py --out /tmp/devices.bin
python SLM/tools/build_device_table.py --manifest <a Doom manifest> --out /tmp/doom.bin
python SLM/tools/auton_format.py --validate <a model file carrying the section>
cd agent && python -m pytest tests/unit/test_device_table.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| **The PRD's ≥30,000 PCI target is not reachable** | **H** | Measured: `parse_ids_registry` yields **21,564** device records, because it counts devices and skips subsystem entries. The target was set before ingestion existed. Report the real number and say the target was wrong rather than inflating the count by including subsystems |
| A second registry parser drifts from the first | **H** | Task 3 reuses `vendor_ingest`; no re-parsing |
| The format changes on one side only | **H** | Task 1 changes `auton_format.py` and `slm.md` together; Task 2 bumps the version both places |
| The table makes the model file too large to boot as a module | **M** | Task 4 scopes it; Task 5 measures it |
| Scoping drops a device the machine actually has | **M** | Task 4's gotcha — the target's ids are always included |
| It is read as making the image able to answer device questions | **H** | Task 5's gotcha: the kernel consumer is specified and unwritten, and the report must say so |

## Acceptance
- [ ] The section layout is stated in `auton_format.py` and `slm.md`, agreeing field for field
- [ ] `VERSION = 3` on both sides; a v2 file is refused naming the version
- [ ] The table is built through `vendor_ingest`, never by re-parsing
- [ ] Keys strictly ascending; a duplicate is refused, not arbitrated
- [ ] `--manifest` scopes the table, and never drops an id the target has
- [ ] Entry counts, section bytes and file size reported
- [ ] The PRD's ≥30,000 target is reported against the measured 21,564, with the reason
- [ ] The report says the in-kernel consumer is specified and unwritten
