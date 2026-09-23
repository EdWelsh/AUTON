# Plan: Framebuffer + Input (V7)

**Source PRD**: `auton-driver-development.prd.md` — phase V7
**Depends on**: V5 (landed — the pattern), V1a (this wave)
**Unblocks**: intent-G, Doom — the PRD set's headline intent, currently `INCOMPLETE`

## Summary

`I want to play Doom` resolves to `requires: [boot, allocator, pci, terminal, scoped, framebuffer,
input, module-asset]` and produces an INCOMPLETE package. Both driver capabilities are advertised
in `drivers.md` `provides` and both map to `kernel/drivers/fb/**` and `kernel/drivers/arch/**` —
the first of which has never existed.

This phase also forces a decision V5 did not have to make: **what happens when there is no open
specification to synthesize from.** virtio has one. VESA's is a 1990s BIOS interface, and PS/2 is
a legacy controller documented in datasheets rather than a standard. V4's refusal path was built
for exactly this and has never been exercised on a device that matters.

## Evidence

- `agent/kernel_spec/subsystems/drivers.md:392+` — the VESA Framebuffer section, with `vesa_state`
  and the linear-framebuffer geometry. Present and incomplete in the same way VirtIO Block was.
- `agent/kernel_spec/subsystems/drivers.md:34-49` — `keyboard_state`, *"shared by all architecture
  keyboard drivers"*. The input seam already exists.
- `agent/kernel_spec/subsystems/drivers.md:16` — *"x86_64: 16550A UART (COM1), VGA text mode, PIT
  8254, PS/2 keyboard"*. The architecture's device set is already written down.
- `agent/kernel_spec/source_map.yaml:77-78` — `input: [kernel/drivers/arch/**]` and
  `framebuffer: [kernel/drivers/fb/**]`. The first may match something in a generated tree; the
  second never has. V1a makes the difference visible.
- `agent/kernel_spec/targets/qemu-pc.md` — device `1234:1111`, role `display`, and the file's own
  note: *"the display device is present but no framebuffer driver exists"*. The target has said
  this all along.
- `agent/hardware/vendors.yaml` — 45 documents. **No VESA/VBE entry and no PS/2 entry.** V4's
  selector will refuse `synthesize` for both, and that refusal is a finding, not an obstacle.
- `.claude/PRPs/reports/w6-target-capability-join-report.md` — the Bochs VGA at `1234:1111` is in
  no registry either. A display device that is neither identified nor specified is the hardest
  case the driver PRD has.

## Patterns to Mirror

- **V5's shape**: specification section, host reference for what can be proved without hardware,
  record, harness, `provides` without `source_map`.
- **V4's refusal**: `driver_strategy.py` names all three options and why each failed.
- **`status: undrivable`**: `drivers/README.md` already admits it — *"some devices cannot be
  driven from any open document, and saying so is more useful than an empty record"*.

## Tasks

### Task 1: Run the selector first, and record what it says
- **Action**: `driver_strategy.py --device 1234:1111` before writing anything, and record the
  result verbatim in the report.
- **Why first**: V5's record asserted `synthesize` against an uninventoried document and V4 caught
  it afterwards. Doing it in the other order here is the whole point of having a selector.
- **Gotcha**: a refusal is a legitimate outcome and must not be worked around by inventing an
  inventory entry for a document nobody has. If VESA's specification is genuinely unavailable
  under terms this project can use, the honest record is `status: undrivable` with the reason.
- **Validate**: the selector's output appears in the report, whatever it says.

### Task 2: Framebuffer, from what is actually knowable
- **Action**: Complete the VESA Framebuffer section for the case AUTON can actually reach — a
  linear framebuffer whose address, geometry and pitch come from **Multiboot2**, not from a VBE
  BIOS call.
- **Why this scoping is honest rather than convenient**: AUTON boots via Multiboot2 and GRUB
  already sets the mode. A driver that re-enters real mode to call VBE is a different and much
  larger thing, and `boot.md` already carries the framebuffer tag. What is needed is the consumer
  of a tag that already exists, which needs no vendor document at all.
- **Gotcha**: this makes the *strategy* neither reuse nor port nor synthesize-from-vendor-spec —
  it is synthesis from **Multiboot2**, which `vendors.yaml` does not list either. Inventory the
  Multiboot2 specification, or record plainly that the basis is a boot protocol rather than a
  device datasheet.
- **Validate**: the section derives geometry from the Multiboot2 framebuffer tag and cites it;
  nothing depends on a VBE call.

### Task 3: Input, and the honest boundary
- **Action**: Complete the PS/2 keyboard path against the existing `keyboard_state`, covering the
  i8042 controller's data and status ports and scancode set 1 translation.
- **Gotcha**: `firecracker.md` records i8042 as **vestigial** — *"reset signalling only, no
  keyboard behind it"*. An input driver is meaningful on the QEMU PC and meaningless on a microVM,
  and the specification must say which machines it serves rather than implying all of them.
- **Gotcha**: scancode translation is a table. It belongs beside `pci-classes.yaml` as data, not
  inline in a driver.
- **Validate**: the section names the machine classes it applies to; the scancode table is data.

### Task 4: Host references for what can be proved
- **Action**: `tests/kernel/` references for scancode translation and framebuffer pixel/pitch
  arithmetic.
- **Why these two**: both are pure functions of their inputs and neither needs hardware. Mode
  setting and port I/O cannot be proved on a host and are not claimed — the same line V5 drew.
- **Gotcha**: pitch is **not** `width * bytes_per_pixel`. A driver that assumes it writes past the
  end of every scanline, which is the framebuffer equivalent of the ring-index bug, and it is the
  case the test most needs.
- **Validate**: a deliberate pitch-equals-width bug is caught; ASan/UBSan clean.

### Task 5: Records, and `undrivable` where it applies
- **Action**: `drivers/framebuffer.md` and `drivers/ps2-keyboard.md`, with whatever `status` the
  evidence supports.
- **Gotcha**: `1234:1111` is in no registry, so `driver_spec` refuses a record naming it — a
  record cannot appeal to `source: probed`. The framebuffer record should key on the Multiboot2
  tag rather than on a device id, or say why it cannot.
- **Validate**: both records validate, or the one that cannot is `undrivable` with its reason.

### Task 6: What Doom still needs
- **Action**: Re-run the Doom package and record precisely what remains blocking.
- **Why**: the PRD calls Doom the headline intent, and *"framebuffer and input now exist"* is a
  claim that must be checked rather than assumed. `module-asset` is also unmapped.
- **Validate**: the report states the remaining blockers by name.

## Validation

```bash
python agent/tools/driver_strategy.py --device 1234:1111
python agent/tools/driver_spec.py --all
tests/kernel/run_framebuffer_test.sh --self-test
python agent/tools/package_image.py "I want to play Doom" --output /tmp/doom \
    --target agent/kernel_spec/targets/qemu-pc.md
cd agent && python -m pytest tests/unit/ -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A VESA driver is specified that AUTON cannot reach from Multiboot2 | **H** | Task 2 scopes to the tag that already exists; re-entering real mode is out |
| An inventory entry is invented to make `synthesize` available | **H** | Task 1's gotcha; `undrivable` is a real answer the format already admits |
| Input is specified for machines that have no keyboard | **M** | Task 3's first gotcha — Firecracker's i8042 is vestigial and the spec must say so |
| `pitch == width * bpp` assumed | **H** | Task 4's gotcha; it is the test's central case |
| Doom is declared unblocked when it is not | **H** | Task 6 checks rather than claims |

## Acceptance
- [ ] The selector was run first and its answer recorded verbatim
- [ ] Framebuffer geometry comes from the Multiboot2 tag, cited, with no VBE call
- [ ] Input names the machine classes it serves; the scancode table is data
- [ ] Host references for scancode translation and pitch arithmetic, ASan/UBSan clean
- [ ] A pitch-equals-width bug is caught by the tests
- [ ] Records validate, or say `undrivable` with a reason
- [ ] What Doom still needs is stated by name, not assumed
