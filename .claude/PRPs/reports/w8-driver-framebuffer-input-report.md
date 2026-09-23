# Implementation Report: Framebuffer + Input (V7)

## Summary

`I want to play Doom` has produced an INCOMPLETE package since the intent existed, for want of a
framebuffer and an input driver. Both are now specified, one is `status: specified` and the other
is the tree's first `status: undrivable` — and that second answer is the more useful of the two.

## Tasks

| # | Task | Status | Notes |
|---|---|---|---|
| 1 | Run the selector first, record what it says | Complete | it refused; recorded verbatim |
| 2 | Framebuffer from what is actually knowable | Complete | Multiboot2 tag, no VBE call |
| 3 | Input, and the honest boundary | Complete | `undrivable`, with the reason |
| 4 | Host references for what can be proved | Complete | 21 checks, ASan/UBSan |
| 5 | Records, and `undrivable` where it applies | Complete | one of each |
| 6 | What Doom still needs | Complete | checked, not assumed |

## Task 1: the selector went first, and refused

```
$ driver_strategy.py --device 1234:1111
device:   1234:1111
identity: unidentified
   reuse       absent     no implemented driver in kernel_spec/drivers/ binds to this device
   port        absent     no driver source is inventoried
   synthesize  absent     device 1234:1111 maps to no vendor in vendors.yaml
REFUSED: no strategy is defensible for this device.
```

V5's record asserted `synthesize` against an uninventoried document and V4 caught it afterwards.
Doing it in this order is the point of having a selector, and the refusal turned out to be
pointing at something true: **the publisher of the framebuffer driver's specification is the boot
protocol's, not a display vendor's.** There was never going to be a document for `1234:1111`.

## Task 2: the driver does not call VESA

`drivers.md`'s VESA section describes a BIOS interface AUTON does not use. GRUB sets the mode
before handover and passes a linear framebuffer in the Multiboot2 information structure, which
`subsystems/boot.md` already parses into `boot_info_t` — address, width, height, **pitch**, bpp.
Re-entering real mode to call VBE would be a much larger thing that buys nothing.

So the basis is a boot protocol, and the Multiboot2 Specification is now inventoried as
`gnu-multiboot/multiboot2-spec` (46th document). The record cites something the tree can resolve
rather than something remembered.

## The format grew a third id form, for the same reason it grew the second

Both of these drivers bind to devices **on no enumerable bus**. A framebuffer handed over by the
loader has no device id; an i8042 sits at fixed ISA ports and is in no registry. Neither had a
writable id.

```
vvvv:dddd            PCI — the original form
virtio-mmio:<type>   V5: a microVM has no PCI bus
platform:<name>      V7: no enumerable bus at all
```

The pattern each time is identical, and it is worth stating plainly because it has now happened
three times: **a format admitting only one id shape does not merely fail to express the others —
it makes the wrong answer the only writable one.** `firecracker.md` shipped with PCI ids on a
machine with no PCI bus for exactly this reason. Had the grammar not grown here, the framebuffer
record's only writable id would have been `1234:1111`, claiming the driver binds to QEMU's Bochs
VGA specifically, which is false: it works with whatever the loader configured.

`drivers/platform-devices.yaml` resolves the new form and names the document specifying each
device — or records that there is none.

## Task 3: the first `undrivable` record

`ps2-keyboard.md` says `status: undrivable`, and the reason is not that the keyboard cannot be
made to work. The port protocol is widely known and the scancode table is proved on the host. It
is that **this project cannot point at a normative document and say *this is what we implemented
from***, so the verification burden a synthesized ring-0 driver carries cannot be discharged the
usual way.

Writing `specification: "Intel 8042 datasheet"` would have made the record validate. It would also
have repeated the exact defect V4 found in `virtio-net.md`, knowingly. `drivers/README.md` already
admits `undrivable` for this case, and this is the first use.

`driver_spec` was adjusted so an `undrivable` record **may** name a device nothing specifies —
refusing it would leave no way to say a device is undrivable, which is the one thing the status
exists for.

The record also says which machines it would serve. `firecracker.md` records its i8042 as
vestigial — *"reset signalling only, no keyboard behind it"* — so binding there waits forever for
a keypress.

## Task 4: pitch is not width × bpp

Firmware pads scanlines to an alignment boundary and usually does. A driver that computes the
stride instead of reading it writes past the end of every row, progressively further down the
screen — invisible at the top, total at the bottom. It is the framebuffer's ring-index bug.

Six bugs injected into the reference, six caught:

| Injected | Result |
|---|---|
| pitch computed instead of read | 2 failures |
| bounds checked against pitch instead of width | 1 failure |
| buffer size uses width instead of pitch | 2 failures |
| the release bit not masked off | **ASan: global-buffer-overflow, exit 134** |
| release never flagged | 1 failure |
| shift ignored | 2 failures |

The fourth is why these are built under sanitizers: the bug is a genuine out-of-bounds read, and
ASan named the line rather than leaving it to an assertion that might not have existed.

A seventh check guards a different kind of drift — the reference's C arrays are parsed and
compared against `scancodes.yaml`. The table is reviewable, the reference is executable, and a
driver generated from one while tested against the other passes its tests and does the wrong
thing. Verified by changing one entry and watching it fail.

## Task 6: what Doom still needs, checked

| Blocker | State |
|---|---|
| `play-doom` service spec | **missing** — the package's own stated blocker, unchanged |
| `framebuffer` | specified, **not implemented** (no source mapping) |
| `input` | specified, driver **undrivable** — needs a recorded human decision |
| `module-asset` | specified, **not implemented** — not a driver problem; the WAD needs handing in as a boot module |

Doom is **not** unblocked. Two of its four blockers moved from "nothing describes this" to
"specified, not written", one is now a decision someone has to make deliberately, and one was
never a driver issue. That is progress worth stating precisely rather than claiming.

## The last phantom mapping is gone

`framebuffer: [kernel/drivers/fb/**]` pointed at a directory that has never existed. V1a made it
detectable; this removed it. Both known phantoms — `virtio-blk` and `framebuffer` — are now
honestly unmapped.

The phantom tests had pinned themselves to whichever real defect existed and broke **twice** when
the phases that fixed those defects removed the mappings. A test that fails on success is badly
designed, so they now derive their example from the map rather than naming one.

## Validation

1435 unit tests pass (was 1415), 111 SLM tests, 21 display host checks under ASan/UBSan.

## Files

| File | Action |
|---|---|
| `agent/kernel_spec/subsystems/drivers.md` | UPDATED — two sections added |
| `agent/kernel_spec/drivers/framebuffer.md` | CREATED |
| `agent/kernel_spec/drivers/ps2-keyboard.md` | CREATED — first `undrivable` |
| `agent/kernel_spec/drivers/scancodes.yaml` | CREATED — 48 printable, 9 control |
| `agent/kernel_spec/drivers/platform-devices.yaml` | CREATED |
| `tests/kernel/display_reference/` | CREATED |
| `tests/kernel/display_test.c` | CREATED — 21 checks |
| `tests/kernel/run_display_test.sh` | CREATED |
| `agent/tools/target_spec.py` | UPDATED — `platform:` id form |
| `agent/tools/driver_spec.py` | UPDATED — `undrivable` may name an unidentifiable device |
| `agent/hardware/vendors.yaml` | UPDATED — Multiboot2, 46th document |
| `agent/kernel_spec/source_map.yaml` | UPDATED — last phantom removed |
| `agent/tests/unit/test_display_drivers.py` | CREATED — 16 tests |
| `agent/tests/unit/test_phantom_mappings.py` | UPDATED — no longer pinned to live defects |
| `agent/tests/unit/test_driver_spec.py` | UPDATED — all three id forms |

## Acceptance

- [x] The selector was run first and its answer recorded verbatim
- [x] Framebuffer geometry comes from the Multiboot2 tag, cited, with no VBE call
- [x] Input names the machine classes it serves; the scancode table is data
- [x] Host references for scancode translation and pitch arithmetic, ASan/UBSan clean
- [x] A pitch-equals-width bug is caught by the tests
- [x] Records validate; the keyboard says `undrivable` with a reason
- [x] What Doom still needs is stated by name, not assumed
