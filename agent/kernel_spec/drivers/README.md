# Driver Decision Records

A target says a device is present. The capability index says whether the tree can drive it.
Neither says **how this driver came to exist, and how anyone would know it works**.

That is what these records are for. They are not drivers and not specifications — the register
layouts live in [`../subsystems/drivers.md`](../subsystems/drivers.md) and a record that repeats
them creates a second source of truth that will drift.

## Shape

```yaml
---
driver: virtio-net
devices: ["virtio-mmio:1", "1af4:1041", "1af4:1000"]
provides: [net]
strategy: synthesize
specification: "VIRTIO 1.2 §5.1 — Network Device"
verification:
  - "marker: [NET] virtio-net up"
  - "cmd: tests/kernel/run_virtio_net_test.sh"
status: specified
---
```

## Why each field exists

| Field | Why it is here |
|---|---|
| `driver` | Its identity; must match the filename, as service specs and mitigations do. |
| `devices` | The ids it binds to, in either form — `vvvv:dddd` or `virtio-mmio:<type>`. A driver with no device is a library. Both forms are admitted because a microVM's devices have no PCI pair at all, and a format that could not express them could not describe the one driver a microVM needs. |
| `provides` | Capability names from the subsystem index. This is what joins a record to `source_map.yaml`, and therefore to whether a build can actually use it. |
| `strategy` | `reuse`, `port` or `synthesize`, chosen by [`driver_strategy.py`](../../tools/driver_strategy.py) against the criteria in [STRATEGY.md](STRATEGY.md). A driver whose origin nobody wrote down cannot be re-reviewed when its source changes. |
| `source` | **Mandatory for `reuse` and `port`**, and it must carry the licence. A ported driver with an unrecorded licence is a legal defect that surfaces at distribution, long after the decision — and by then the code is in an image someone shipped. |
| `specification` | **Mandatory for `synthesize`**, naming the document and section. "Synthesized" without a citation means "written from memory", which is the phantom-device defect with a register map attached. |
| `verification` | **Mandatory, and mechanical.** A command to run or a marker to observe. An image that claims a driver works is making the claim a user acts on; prose describing how one *might* check is not a check. Required even at `status: specified`, because a field allowed to be empty until implementation stays empty afterwards. |
| `status` | `implemented`, `specified`, or `undrivable`. The third is a real answer: some devices cannot be driven from any open document, and saying so is more useful than an empty record. |

Nothing else. No `author`, no `date`, no `version` — git records all three, and a field git
already owns goes stale in the file while staying correct in the history. A field is added when a
second driver genuinely cannot be expressed without it, not in anticipation.

## Rules

1. **Do not restate a subsystem spec.** `drivers.md` already carries the register layouts for
   AHCI, NVMe, VirtIO Block, e1000 and VESA. A record says how the driver came to be and how it
   is checked, not how the hardware works.
2. **Cite normatively.** "VIRTIO 1.2 §5.1.6" is implementable; a paraphrase is a second source of
   truth that will drift. Same rule `services/README.md` sets for protocols.
3. **A device id must resolve.** PCI ids are checked against the ingested `pci.ids`;
   `virtio-mmio:<type>` against the VIRTIO type table in
   [`../targets/hypervisors.yaml`](../targets/hypervisors.yaml). Unlike a *target*, a record
   cannot appeal to `source: probed` — there is no machine here to have observed anything.
4. **`status: implemented` is a claim about this tree.** It is refused when `provides` has no
   mapping in `source_map.yaml`, because that combination says the driver is in an image that
   does not contain it. `status: specified` with no mapping is the normal state before the driver
   is written, and is reported rather than refused.

## Choosing a strategy

```bash
python agent/tools/driver_strategy.py --device 8086:100e
```

The criteria are in [STRATEGY.md](STRATEGY.md) and the licence obligations in
[licences.yaml](licences.yaml), both as documents rather than only as code: this is a decision
about ring-0 DMA-capable code with no process boundary, and being argued with is the point.

The ordering is **reuse > port > synthesize**, which is not the intuitive one for a project that
generates its own OS. Synthesis is the most dangerous option available — nobody has ever run the
result — so it is the last resort and carries the heaviest verification burden.

The selector refuses when no option is defensible, naming all three and why each failed. A record
asserting a strategy anyway would validate structurally and be a lie.

## Validating

```bash
python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/virtio-net.md
python agent/tools/driver_spec.py --all
```

Three outcomes, as `target_spec.py` has: valid (0), refused (1), unverifiable (3 — no registry
cached, so nothing confirms or denies the device ids).

## Running the verification

```bash
python agent/tools/driver_verify.py --target agent/kernel_spec/targets/qemu-pc.md
python agent/tools/driver_verify.py --target <t> --serial boot.log --slow
```

`cmd:` entries are executed; `marker:` entries are checked against a boot log where one exists.
Three outcomes again, and **unverified is not verified**: a command that does not exist because
the driver does not exist, a marker with no boot to observe it in, and a check skipped because it
boots an image under QEMU are all *unverified*. A check that exits 2 is *nothing to check*, which
is the `run_leakage_test.sh` convention and is also not a pass.

The build gate refuses two things: a check that **fails**, and a record claiming
`status: implemented` with no observed pass. The second is the other half of what
`driver_spec.py` already enforces — that one refuses `implemented` with no source mapping, this
one refuses `implemented` that nobody has checked.

A recorded pass is bound to the sha256 of the record it passed against. A pass against a
different record is not evidence: the verification may have been rewritten since.

## Records

| Driver | Strategy | Status | Exercises |
|---|---|---|---|
| [virtio-net.md](virtio-net.md) | `synthesize` | `specified` | One driver, two transports; an open specification; nothing implemented yet |
| [e1000.md](e1000.md) | `port` | `implemented` | A single PCI id; a vendor datasheet with a licence; code that exists |

The two are deliberately far apart — different strategy, different id forms, different transport
counts, different status. `e1000.md` was written second and **without adding a field**, the same
bar `firecracker.md` set for the target format.
