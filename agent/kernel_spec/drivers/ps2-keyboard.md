---
driver: ps2-keyboard
devices: ["platform:i8042"]
provides: [input]
strategy: synthesize
specification: "none — see the undrivable note below"
verification:
  - "marker: [INPUT] keyboard ready"
  - "cmd: tests/kernel/run_display_test.sh"
status: undrivable
---

# ps2-keyboard

The other half of what Doom needs, and the first record in this tree to say `undrivable`.

## Why

`driver_strategy.py` refuses every strategy for it, and the refusal is correct rather than
inconvenient:

- **reuse** — no implemented driver in this tree binds to it.
- **port** — no driver source is inventoried.
- **synthesize** — the i8042 is a 1980s controller documented in datasheets and by convention.
  `agent/hardware/vendors.yaml` has no entry for it and no plausible publisher to add. Writing
  `specification: "Intel 8042 datasheet"` would be citing a document nobody here can produce,
  which is the defect V4 caught in `virtio-net.md` and must not be repeated knowingly.

`drivers/README.md` admits `undrivable` for exactly this: *"some devices cannot be driven from any
open document, and saying so is more useful than an empty record."*

## What that does and does not mean

It does **not** mean the keyboard cannot be made to work. The port protocol is widely known and
the scancode table is in `drivers/scancodes.yaml`, proved on the host. It means this project
cannot point at a normative document and say *this is what we implemented from*, so the
verification burden a synthesized ring-0 driver carries cannot be discharged the usual way.

Unblocking Doom therefore needs a decision recorded by a person: accept the driver on
convention-plus-tests, or find a citable specification. This record exists so that decision is
made deliberately rather than by someone quietly writing `synthesize`.

## Which machines it would serve

The QEMU PC and most bare metal. **Not** a microVM: `targets/firecracker.md` records its i8042 as
vestigial — *"reset signalling only, no keyboard behind it"* — so binding there would wait forever
for a keypress from a controller with no keyboard behind it.
