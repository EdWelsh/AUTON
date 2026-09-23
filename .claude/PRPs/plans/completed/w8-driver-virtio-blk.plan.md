# Plan: virtio-blk (V6)

**Source PRD**: `auton-driver-development.prd.md` — phase V6
**Depends on**: V5 (landed — its control), V1a (this wave)
**Unblocks**: F7–F11, the storage unlock and the whole service ladder

## Summary

V9's join already reports the gap, without being asked:

```
$ driver_verify.py --target agent/kernel_spec/targets/firecracker.md
  no record: virtio-blk (for virtio-mmio:2)
```

The machine has a storage device, `device_drivers` resolves it, and nothing in the tree describes
what would drive it. Factory phase 7 — *"storage unlock: block driver + minimal FS"* — is waiting
on exactly this.

**V5 is the control, and the measurement is the point.** V6 should cost materially less, because
the virtqueue arithmetic is already specified and already proved. If it does not, the reuse was
imaginary and that is worth knowing before V8 asks an agent to do the same.

## Evidence

- `agent/kernel_spec/subsystems/drivers.md:163-215` — **the VirtIO Block section already exists**,
  with `virtq_desc_t`, `virtq_avail_t`, `virtq_used_t` and `virtio_blk_req_t`. What it does not
  have is the MMIO transport, the initialisation order, the queue conventions or markers. V6
  completes a section rather than writing one.
- `agent/kernel_spec/subsystems/drivers.md:216-328` — V5's VirtIO Network section, written this
  wave. The two transports, the status-bit order and the feature-negotiation discipline are
  specified there and must be **referenced, not restated** — `services/README.md:45`.
- `tests/kernel/virtio_net_reference/` — the ring arithmetic, host-proved under ASan/UBSan against
  six injected DMA bugs. virtio-blk uses the same rings; a second copy would be a second thing to
  get wrong.
- `agent/kernel_spec/subsystems/drivers.md:535-555` — `blk_read`, `blk_write`, `blk_get_info`,
  the interface *"shared by AHCI, NVMe, virtio-blk"*. The seam exists and already names this
  driver, as `:444` did for virtio-net.
- `agent/tools/device_drivers.py` `VIRTIO_TYPE_DRIVERS` — type 2 already resolves to `virtio-blk`
  on both transports.
- `agent/kernel_spec/source_map.yaml:80` — `virtio-blk: [kernel/drivers/blk/**]`, a directory that
  has never existed. V1a makes that detectable; without it, `status: implemented` would pass.
- `.claude/PRPs/reports/w7-driver-virtio-net-report.md` — V5's cost, which this is measured
  against: 113 spec lines, 135 reference lines, 160 test lines, 29 checks.

## Patterns to Mirror

- **The record**: `kernel_spec/drivers/virtio-net.md` — `synthesize`, `specification` citing
  VIRTIO 1.2 by section, `verification` as commands and markers, `status: specified`.
- **The host reference**: `tests/kernel/virtio_net_reference/` — marked not-shipped in its own
  header, and covering only what can be proved without hardware.
- **The harness**: `tests/kernel/run_virtio_net_test.sh` — `--self-test` against the reference,
  exit 2 when there is no tree.
- **Advertise nothing that does not exist**: V5's Task 4. `provides` yes, `source_map` no.

## Tasks

### Task 1: Complete the specification
- **Action**: Extend the existing VirtIO Block section with the MMIO transport, the initialisation
  order, queue conventions, the request/status protocol and markers.
- **Gotcha**: the section currently specifies only the legacy PCI register block. Firecracker's
  storage device is `virtio-mmio:2` and has no PCI bus at all — the same gap V5 found in the
  network case, in a section written before either.
- **Gotcha**: do not restate the status bits, the feature-negotiation order or the ring layout.
  They are in the VirtIO Network section and under VirtIO Block respectively. Reference them.
- **Gotcha**: `virtio_blk_req_t` is a **three-descriptor chain** — header, data, status byte — and
  the status byte is device-writable while the header is not. A chain with uniform flags is the
  bug this specification most needs to prevent.
- **Validate**: the section cites VIRTIO 1.2 §5.2 by subsection and defines nothing already
  defined above it.

### Task 2: Reuse the ring reference rather than copying it
- **Action**: The host test for virtio-blk links `virtio_net_reference/` for the queue arithmetic
  and adds only what is block-specific: request-chain construction and status decoding.
- **Why**: this is the measurement. If V6 needs its own copy of the rings, the claim that V5 made
  it cheaper is false and the report should say so.
- **Gotcha**: the reference directory is named for the network driver because it was written
  there. If it is now shared, rename it — a shared component named after one of its consumers is
  how the second consumer ends up with a copy.
- **Validate**: no ring arithmetic is duplicated; the block test links the shared reference.

### Task 3: The record and its verification
- **Action**: `kernel_spec/drivers/virtio-blk.md` and `tests/kernel/run_virtio_blk_test.sh`.
- **Gotcha**: three device ids again — `virtio-mmio:2`, `1af4:1042` (modern), `1af4:1001`
  (transitional). The format admits both forms; use them.
- **Validate**: `driver_spec.py --validate` passes at `status: specified`; V9 reports the command
  as *nothing to check* rather than absent.

### Task 4: Advertise it honestly
- **Action**: `virtio-blk` is already in `drivers.md` `provides`. Confirm the `source_map` entry
  is **removed**, not added — it currently points at a directory that has never existed.
- **Why removing rather than leaving**: V1a makes a phantom mapping a refusal, and leaving it
  would refuse every build requiring `virtio-blk` with a message about a pattern rather than about
  a driver that has not been written. No mapping is the truthful state.
- **Validate**: `gate_capabilities` refuses a spec requiring `virtio-blk` as *unmapped*, and V9's
  join no longer reports `virtio-blk` as having no record.

### Task 5: Measure against V5
- **Action**: Record spec lines, reference lines, test lines and checks, beside V5's.
- **Why**: V8 asks whether an agent can do this. *"Cheaper than what"* needs two numbers, and this
  is the second.
- **Validate**: the report carries both columns and states the ratio plainly, including if it is
  unflattering.

## Validation

```bash
python agent/tools/driver_spec.py --validate agent/kernel_spec/drivers/virtio-blk.md
tests/kernel/run_virtio_blk_test.sh --self-test
python agent/tools/driver_verify.py --target agent/kernel_spec/targets/firecracker.md
cd agent && python -m pytest tests/unit/test_driver_verify.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The rings get copied and the reuse claim is hollow | **H** | Task 2 renames the shared reference and forbids duplication; the measurement would expose it anyway |
| The MMIO transport is skipped again | **H** | Task 1's first gotcha — Firecracker's disk is `virtio-mmio:2` and is the reason for the phase |
| Uniform descriptor flags on the request chain | **H** | Task 1's third gotcha; the status byte must be device-writable and the header must not |
| `source_map` is "fixed" by pointing at a path a tree might generate | **M** | Task 4; V1a refuses it and the report says why |
| V6 costs the same as V5 and the control is worthless | **L** | Then the report says so. A measurement that can only flatter is not one |

## Acceptance
- [ ] The VirtIO Block section covers both transports and the three-descriptor request chain
- [ ] Nothing restated from VirtIO Network or from the ring layout above it
- [ ] The ring reference is shared, renamed, and not duplicated
- [ ] `virtio-blk.md` validates at `status: specified` with three device ids
- [ ] No `source_map` entry; `gate_capabilities` refuses as unmapped
- [ ] V9's join no longer reports `virtio-blk` as undeclared
- [ ] Cost recorded beside V5's, whichever way it falls
