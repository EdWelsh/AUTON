---
driver: framebuffer
devices: ["platform:multiboot2-framebuffer"]
provides: [framebuffer]
strategy: synthesize
specification: "Multiboot2 Specification §3.6.12 — framebuffer info tag"
verification:
  - "marker: [FB] mode set 1024x768x32"
  - "marker: [FB] pitch 4096 bytes"
  - "cmd: tests/kernel/run_display_test.sh"
status: specified
---

# framebuffer

Half of what Doom needs. `I want to play Doom` has produced an INCOMPLETE package since the intent
existed, and this is one of the two reasons.

## Its basis is a boot protocol, not a datasheet

The VESA section in `drivers.md` describes a BIOS interface AUTON does not call. GRUB sets the
mode before handover and passes a linear framebuffer in the Multiboot2 information structure,
which `subsystems/boot.md` already parses into `boot_info_t`. Re-entering real mode to call VBE
would be a much larger thing that buys nothing this image needs.

So this driver binds to no display device. It works with whatever hardware the loader configured,
which is why its id is `platform:multiboot2-framebuffer` rather than a PCI pair. Running the
selector first — as V7's plan required — refused every strategy for `1234:1111`, QEMU's Bochs VGA,
and that refusal was right: the publisher of this driver's specification is the boot protocol's,
not a display vendor's.

## What the verification proves, and what it does not

`pitch` is **not** `width * bytes_per_pixel`. Firmware pads scanlines to an alignment boundary and
usually does, so a driver that computes the stride writes past the end of every row —
progressively further down the screen, invisible at the top and total at the bottom. That
arithmetic is proved on the host.

Mode setting is not proved and is not claimed: there is nothing to set. Anything that touched real
hardware would be verified against QEMU's model of a device rather than the device.
