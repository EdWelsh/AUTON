---
driver: ps2-keyboard
devices: ["platform:i8042"]
provides: [input]
strategy: synthesize
specification: "none normative — accepted on convention plus host-proved scancode translation (platform-devices.yaml, i8042.accepted)"
verification:
  - "marker: [INPUT] keyboard ready"
  - "cmd: tests/kernel/run_display_test.sh"
status: specified
---

# ps2-keyboard

The other half of what Doom needs. It was the first record in this tree to say `undrivable`, and
it is now the first to be **accepted without a specification**, by a person's recorded decision.

## The decision (w11, intent-G)

**Accepted on convention plus tests.** The alternative was to wait for a citable specification,
which kept Doom blocked on input for as long as nobody publishes an i8042 document. Nobody is
likely to.

What the acceptance rests on, stated so it can be argued with:

- **Convention.** Ports `0x60`/`0x64` and scancode set 1 are the de facto PC keyboard interface,
  implemented identically by QEMU, SeaBIOS and every PC-compatible chipset still shipping one.
- **Host-proved translation.** The set-1 table in `drivers/scancodes.yaml` is checked by
  `tests/kernel/run_display_test.sh` on the host, with no hardware involved.
- **No document is claimed.** `specification` says `none normative`, and
  `platform-devices.yaml` keeps `specified_by: null`. The acceptance is recorded there as
  `accepted`, with its basis and evidence, so the gap stays visible.

What it does **not** change:

- `driver_strategy.py --device platform:i8042` **still refuses every strategy**. That is correct:
  there is still no automatic basis. The record's `synthesize` is a human override of that
  refusal, not the selector's output.
- `status: implemented` is still refused until `input` maps to real source and the marker is
  observed. The acceptance admits `specified` and nothing more.

## Why it was undrivable

`driver_strategy.py` refuses every strategy for it, and the refusal is correct rather than
inconvenient:

- **reuse**: no implemented driver in this tree binds to it.
- **port**: no driver source is inventoried.
- **synthesize**: the i8042 is a 1980s controller documented in datasheets and by convention.
  `agent/hardware/vendors.yaml` has no entry for it and no plausible publisher to add. Writing
  `specification: "Intel 8042 datasheet"` would be citing a document nobody here can produce,
  which is the defect V4 caught in `virtio-net.md` and must not be repeated knowingly.

That remains true. The decision above does not dispute it. It chooses to proceed anyway, in
writing.

## Which machines it would serve

The QEMU PC and most bare metal. **Not** a microVM: `targets/firecracker.md` records its i8042 as
vestigial (*"reset signalling only, no keyboard behind it"*), so binding there would wait forever
for a keypress from a controller with no keyboard behind it.
