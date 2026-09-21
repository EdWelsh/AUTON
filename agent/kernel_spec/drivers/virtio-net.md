---
driver: virtio-net
devices: ["virtio-mmio:1", "1af4:1041", "1af4:1000"]
provides: [net]
strategy: synthesize
specification: "VIRTIO 1.2 §5.1 — Network Device"
verification:
  - "marker: [NET] virtio-net up"
  - "marker: [NET] link up, mac 52:54:00:12:34:56"
  - "cmd: tests/kernel/run_virtio_net_test.sh"
status: specified
---

# virtio-net

The driver AUTON needs and does not have.

D7 measured the consequence: `drivers.md` `provides` lists exactly one network driver, `e1000`,
so the only machines AUTON can build a network image for are machines with an Intel 82540EM. A
Firecracker target is refused outright — its network device is `virtio-mmio:1`, and nothing in
the tree can drive it. This record is the first half of changing that; V5 writes the driver.

## Why three device ids

One driver, three ways of being found:

| Id | Transport | Where |
|---|---|---|
| `virtio-mmio:1` | MMIO, device type 1 | Firecracker, QEMU `microvm` |
| `1af4:1041` | modern virtio-pci (`0x1040` + type) | Cloud Hypervisor |
| `1af4:1000` | transitional virtio-pci | QEMU with `-device virtio-net-pci` |

The device model behind all three is the same; only the discovery and the notification mechanism
differ. A format admitting only `vvvv:dddd` could not have expressed the first, which is the one
that matters most — it is the transport every microVM uses.

## Why `synthesize`

The VIRTIO specification is open, complete and normative. There is no licence question, no
datasheet to obtain, and no existing implementation whose provenance would have to be tracked.
That is the cleanest case for writing from a document rather than porting, and it is why V5
chooses this driver as its control rather than a NIC with a proprietary datasheet.

## Verification

Two markers and a command, none of them prose. The markers are ordered and must both appear on a
successful run, matching the rule `services/README.md` sets for service markers. The command does
not exist yet — `status: specified` means the driver is not written, and the verification names
how it *will* be checked rather than leaving the field empty until someone forgets to fill it in.
