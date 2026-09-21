---
target: qemu-pc
class: vm
arch: x86_64
firmware: bios
silicon:
  vendor: GenuineIntel
  family: 6
  model: 6
  stepping: 3
  source: probed
devices:
  - id: "8086:1237"
    role: host-bridge
    source: probed
  - id: "8086:7000"
    role: isa-bridge
    source: probed
  - id: "1234:1111"
    role: display
    source: probed
  - id: "8086:100e"
    role: network
    source: probed
assumptions:
  - "input: serial console only; the display device is present but no framebuffer driver exists"
provenance:
  stated_by: qemu-default-machine
  stated_at: 2026-09-16T00:00:00Z
---

# QEMU Default PC

The machine every AUTON image has implicitly been built for until now. Writing it down is the
point: it was never a decision, it was a hardcoded literal in `SLM/tools/build_corpus.py`.

## What it is

QEMU's default `pc` machine with SeaBIOS, an emulated PIIX3 chipset and an e1000 NIC. A full
VM rather than a microVM: it has a real PCI bus, legacy devices, and a BIOS.

## Notes on the devices

`1234:1111` is QEMU's Bochs VGA adapter and is **not in `pci.ids`** — vendor `1234` is QEMU's
own invented id. A target definition referencing it will validate as *unidentifiable*, not as
invalid: the device is genuinely present on this machine, and the registry simply does not know
it. That distinction is why identification is three-valued.

`8086:1237` and `8086:7000` are the 440FX host bridge and PIIX3 ISA bridge. AUTON's knowledge
base answers "unknown device" for both, though the registry names them — recorded in
`reports/w2-hardware-ingestion.md` as an available grounding improvement.

## Why `source: probed`

These ids were read from a running instance via `[DEV] PCI scan`, not stated by a person. A
later probe of a different QEMU version may disagree, and the `source` is what makes that
disagreement legible rather than confusing.
