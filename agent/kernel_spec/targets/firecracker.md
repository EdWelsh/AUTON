---
target: firecracker
class: microvm
arch: x86_64
firmware: none
silicon:
  vendor: unknown
  family: 0
  model: 0
  stepping: 0
  source: assumed
platform:
  hypervisor: firecracker
  machine: default
  transport: virtio-mmio
  console: serial-16550a
  source: user-stated
devices:
  - id: "virtio-mmio:1"
    role: network
    source: derived
  - id: "virtio-mmio:2"
    role: storage
    source: derived
assumptions:
  - "silicon: not stated; a microVM inherits the host CPU and the guest cannot choose it"
absent:
  - "PCI bus — enumeration finds nothing; virtio is on MMIO"
  - "display — no VGA, no framebuffer, no GPU device of any kind"
  - "firmware — the kernel is loaded directly, so no firmware tables"
  - "USB, IDE, floppy, sound"
provenance:
  stated_by: hand-written-control
  stated_at: 2026-09-16T00:00:00Z
---

# Firecracker microVM

**This file is the control.** It was written by hand before `--derive-microvm` existed, and it is
kept rather than regenerated so the derivation has something independent to be checked against.
`tests/unit/test_target_derivation.py` asserts the two agree on every fact about the machine —
class, firmware, transport, console, device ids and roles, and the absence list. They differ only
on provenance: this one is `source: user-stated`, the derived one `source: derived`. The same
value, two ways of knowing it, which is what `source` exists to record.

The round-trip found two errors here, both in this file: the machine type was `microvm` (QEMU's
name for its machine type, not Firecracker's, which has none) and the device ids were PCI pairs.

Written second, deliberately, and **without adding a field**. A format proven only against the
machine it was written alongside has not been tested — the same bar `fileserver.md` set for the
service format.

## How it differs from a full VM

| | qemu-pc | firecracker |
|---|---|---|
| PCI bus | yes | **no** — virtio over MMIO |
| Firmware | BIOS | **none** — direct kernel boot |
| Devices | 4, mostly legacy | 2, both virtio |
| Display | Bochs VGA present | **none** |
| Silicon | probed | **assumed** — the guest cannot choose it |
| Device set pinned by | the enumeration | the **platform** — see below |

## The ids are not PCI ids

This file first named these devices `1af4:1000` and `1af4:1001`, which are virtio's **PCI**
vendor:device pairs — on a machine whose own table two rows up says it has no PCI bus. The
error was invisible because the format only admitted one id shape, so the only writable id was
the wrong one.

Over virtio-MMIO there is no vendor:device pair anywhere in the transport. The guest reads a
device *type number* out of an MMIO register: 1 is network, 2 is block (VIRTIO 1.2 §5). So the
id form is `virtio-mmio:<type>`, and it resolves against the type table in
[hypervisors.yaml](hypervisors.yaml) rather than against `pci.ids`.

A format that admits only one id shape does not merely fail to express the other — it makes the
wrong answer the only writable one.

## Why `platform` and not a longer device list

The two virtio devices are listed because this instance has them, but they are not what makes
the definition complete — `platform.hypervisor` and `platform.machine` are. A Firecracker
microVM's device set follows from the hypervisor and machine type, so a definition that names
them can leave `devices` empty and still be a statement about a real machine. A definition that
names neither, and lists nothing, is not "implying" a device set; it is blank, and
`target_spec.py` refuses it on exactly that ground.

`class: bare-metal` and `class: vm` have no such platform to appeal to. There, the enumeration
*is* the fact, and silence means nobody looked.

Three of those are absences, and absence is the harder thing for a format to express. A target
that can only list what is present cannot say "there is no PCI bus here", which is precisely the
fact a driver decision turns on.

## The honest reading of "put it in a container"

A kernel cannot run inside a container; a container shares the host's kernel. When someone asks
for that, this is usually what they mean: a microVM that a container runtime schedules — Kata
Containers, or Firecracker under containerd. AUTON is the guest kernel and the runtime is the
scheduler.

That makes this class the most realistic deployment shape AUTON has, not an exotic one.

## The virtio ids

`1af4:1000` and `1af4:1001` are Red Hat's virtio network and block devices, both in the ingested
registry, and both already in `PCI_KB`. A guest needing only virtio needs roughly four drivers
rather than 21,564 — which is why the recursive AUTON-hosted case may be the correct default
rather than merely elegant.

## Why silicon is `assumed`

Firecracker passes through the host CPU. The guest does not choose it and, before boot, cannot
know it. Recording `source: assumed` rather than omitting the field is what lets an errata join
later report *unknown* instead of *safe* — the rule `machine_safety.py` already enforces.
