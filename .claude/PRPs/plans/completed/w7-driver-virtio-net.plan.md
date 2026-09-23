# Plan: virtio-net, Human-Authored (V5)

**Source PRD**: `auton-driver-development.prd.md` — phase V5
**Depends on**: V2 (landed), F5 (landed), V4 (selects the strategy), V9 (runs the verification)
**Why after V4 and V9**: V5 should be the first *output* of a strategy decision and the first
thing the verification gate actually runs. Built before them, it is a driver that documents its
own choices and checks itself.

## Summary

`e1000` is the only network driver in the capability index. D7 measured the consequence: the only
machines AUTON can build a network image for are machines with an Intel 82540EM, and a Firecracker
target is refused outright. This is the phase that changes it.

Human-authored on purpose. It is the control V8 measures agent-authored driver cost against, the
same role F4's DHCP service played for F6.

## The deliverable has changed shape, and that must be said first

F4's control was **C code in `kernels/x86_64`**, compiled into a 53 KB image. That tree is gone —
deleted deliberately, because this project does not write the kernel. So V5 cannot be "write a
driver into the tree", and pretending otherwise would produce code with nowhere to live.

What V5 delivers instead, all of which is real and none of which is the tree:

1. **The specification** — a `### SLM-Managed Driver: VirtIO Network` section in
   `subsystems/drivers.md`, complete enough to generate from, in the voice of the four sections
   already there.
2. **A host-testable reference** — `tests/kernel/virtio_net_reference/`, the pattern
   `identity_reference/identity.c` already sets: *"NOT kernel code and not shipped. It exists so
   the test can be proved correct, and so the specification is executable rather than prose."*
3. **The capability index entry** — `virtio-net` in `drivers.md` `provides`, which is what D7's
   join needs before a Firecracker target stops being refused.
4. **A verification that V9 can run** — `tests/kernel/run_virtio_net_test.sh`, the command
   `drivers/virtio-net.md` already names and which does not yet exist.

## Evidence

- `.claude/PRPs/reports/w6-target-capability-join-report.md` — the measurement: `drivers.md`
  `provides` lists exactly one network driver, so a Firecracker target is refused with
  *"needs 'virtio-net' … no subsystem spec provides it"*.
- `agent/kernel_spec/subsystems/drivers.md:163` — `### SLM-Managed Driver: VirtIO Block`, which
  already defines `VIRTIO_DEVICE_NET 0x1000` and the shared ring structures. The net section sits
  beside it and must not restate them.
- `agent/kernel_spec/subsystems/drivers.md:444` — `/* === Network device interface (shared by
  e1000, virtio-net) === */`. The interface a second NIC driver must satisfy **already exists**
  and already names virtio-net. This is the seam.
- `agent/kernel_spec/drivers/virtio-net.md` — the V2 record: `synthesize`, three device ids across
  two transports, `status: specified`, and the verification command this phase must create.
- `tests/kernel/identity_reference/identity.c:1-8` — the host-reference pattern and its stated
  reason, which applies here with more force: a ring-descriptor error is a DMA bug.
- `tests/kernel/run_identity_test.sh`, `run_dhcp_test.sh` — the harness shape to mirror.
- `agent/tools/device_drivers.py` `VIRTIO_TYPE_DRIVERS` — `virtio-mmio:1` and `1af4:1041` already
  resolve to `virtio-net`. The join is waiting for the capability to exist.
- **`vendors.yaml` has no VIRTIO entry.** V4 Task 5 adds it. Until then this record's
  `specification` cites a document the tree cannot fetch — see that plan.

## Patterns to Mirror

- **Spec voice**: `drivers.md`'s four existing SLM-Managed Driver sections — struct layouts,
  register offsets, and the `slm_driver_t` binding, not prose.
- **Do not restate a subsystem spec**: `services/README.md:45`. The VirtIO Block section already
  carries the shared ring layout.
- **Cite normatively**: `services/README.md:49`. "VIRTIO 1.2 §5.1.6" is implementable; a
  paraphrase drifts.
- **Verification outside the artifact**: `tests/kernel/`, per the repo README — *"verification
  must not live inside the artifact it verifies"*.

## Tasks

### Task 1: The specification
- **Action**: `### SLM-Managed Driver: VirtIO Network` in `drivers.md` — virtqueue setup, the
  receive and transmit paths, the feature negotiation subset AUTON needs, and the
  `net_device_ops` binding at `:444`.
- **Gotcha**: **two transports, one device model.** MMIO discovery reads a magic value and a
  device type from a register; PCI discovery reads a capability list. The device model behind
  both is identical, and a spec that describes only PCI cannot serve the microVM case that is the
  whole reason for this driver.
- **Gotcha**: do not restate the ring structures from `:163`. Reference them.
- **Validate**: the section cites VIRTIO 1.2 by section for every structure it defines, and
  defines nothing already defined at `:163`.

### Task 2: The host reference
- **Action**: `tests/kernel/virtio_net_reference/` — virtqueue descriptor-chain construction and
  the available/used ring index arithmetic, as host-compilable C with no hardware.
- **Why this part and not the rest**: the ring arithmetic is where a DMA bug lives, and it is the
  part that can be proved on a host. Register pokes cannot be, and pretending otherwise would be
  the "verified against nothing" case the PRD's capability boundary names.
- **Gotcha**: the reference is **not shipped**, and `identity_reference/identity.c` says so in its
  header comment. Say it here too, or someone will link it.
- **Validate**: builds under ASan and UBSan, as `dhcp_test.c` does; a deliberately wrong index
  wraps and is caught.

### Task 3: The verification command V9 runs
- **Action**: `tests/kernel/run_virtio_net_test.sh`, mirroring `run_identity_test.sh`.
- **Why it exists before the driver**: `drivers/virtio-net.md` already names it, and V9 reports a
  named-but-absent command as *unverified*. This turns that into a real result.
- **Gotcha**: the script must exit 2 — *nothing to check* — when there is no generated driver to
  test, distinct from exit 0. `run_leakage_test.sh` sets this precedent, and collapsing the two is
  how an untested driver reads as a tested one.
- **Validate**: with no generated tree it exits 2 and says so; against the reference it exits 0.

### Task 4: Advertise it only once it exists
- **Action**: Add `virtio-net` to `drivers.md` `provides`, and a `source_map.yaml` entry for it.
- **Gotcha — this is the trap V1 exists for.** `source_map.yaml` already maps `framebuffer` to
  `kernel/drivers/fb/**`, a directory that has never existed, and a glob matching nothing is not
  an error. Adding `virtio-net → kernel/drivers/net/virtio_net.c` before anything generates that
  file repeats the defect exactly: `[gate: capabilities]` would pass and the image would contain
  no driver.
- **Resolution**: add the `provides` entry (the spec exists, so the capability is genuinely
  specified) and **withhold the `source_map` entry** until a tree is generated. `drivers.md`
  already lists `virtio-blk` and `nvme` in `provides` with no mapping, and V1 made that state
  explicit and reportable rather than fatal.
- **Validate**: a Firecracker target stops being refused by D7 and reports `virtio-net` as
  unmapped; `driver_spec.py --validate virtio-net.md` still passes at `status: specified`.

### Task 5: Record the cost, as F4 did
- **Action**: Lines of specification, lines of reference, hours, and the defects the host tests
  caught. This is V8's control.
- **Why**: F4's report recorded its cost so F6 could be measured against it. V8 asks whether an
  agent can do this, and *"cheaper than what"* needs a number.
- **Validate**: the report carries the four figures and names each defect the tests found.

## Validation

```bash
python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/virtio-net.md
tests/kernel/run_virtio_net_test.sh                 # 0 against the reference, 2 with no tree
python agent/tools/intent_manifest.py "hand out addresses" \
    --target agent/kernel_spec/targets/firecracker.md    # no longer MISMATCH
cd agent && python -m pytest tests/unit/test_target_join.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| A `source_map` entry is added to a path nothing generates | **H** | Task 4 withholds it and says why; this is the `framebuffer` defect and it is already in the tree |
| The spec covers PCI only and the microVM case stays broken | **H** | Task 1's first gotcha; the microVM is the reason this driver exists |
| The host reference is mistaken for shippable code | **M** | Task 2 states it in the file, as `identity_reference` does |
| Verified against QEMU's virtio, not a device | **M** | The PRD's capability boundary says this plainly; the report must repeat it rather than claim more |
| The `specification` cites an uninventoried document | **H** | V4 Task 5 inventories VIRTIO first; this plan depends on it |
| "Human-authored" is read as "write the kernel" | **H** | The deliverable section above; the tree is gone on purpose |

## Acceptance
- [ ] A VirtIO Network section in `drivers.md`, citing VIRTIO 1.2 by section, restating nothing
- [ ] Both transports specified — MMIO discovery is not an afterthought
- [ ] A host-testable reference for the ring arithmetic, marked not-shipped, clean under ASan/UBSan
- [ ] `run_virtio_net_test.sh` exists, exits 2 when there is nothing to check
- [ ] `virtio-net` in `provides`; **no** `source_map` entry until a tree generates the file
- [ ] A Firecracker target is no longer refused by D7
- [ ] Cost recorded as V8's control
