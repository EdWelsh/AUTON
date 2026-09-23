# Plan: Derive a microVM Target (D3)

**Source PRD**: `auton-hardware-definition.prd.md` — phase D3
**Depends on**: D1
**Why first among the derivations**: the most derivable class, the smallest device surface, and
the realistic deployment shape for a kernel that a container runtime schedules

## Summary

A microVM's device set is not discovered — it is *decided* by the hypervisor and its machine
type. Firecracker with a given config has exactly the devices that config declares. So a target
definition for a microVM should be derived from two facts the operator already knows, and should
need no elicitation at all.

If the PRD's key hypothesis holds anywhere, it holds here.

## Evidence

- `auton-hardware-definition.prd.md`, target table — microVM: "a deliberately minimal virtio
  set; often no PCI at all, MMIO instead".
- `SLM/tools/build_corpus.py` `DRIVER_CAPS` — `virtio-net` and `virtio-blk` are already
  capability-mapped, so a derived microVM target joins cleanly to the existing index.
- `agent/kernel_spec/subsystems/drivers.md:163` — VirtIO Block is specified and unimplemented,
  which is the driver PRD's V6. This plan produces its input.
- `.claude/PRPs/reports/w3-factory-dhcp-service.md` — the DHCP image never received a packet
  under QEMU user networking. A microVM with virtio-net is a different and more tractable
  network path.

## Tasks

### Task 1: The hypervisor table
- **Action**: `agent/kernel_spec/targets/hypervisors.yaml` — per hypervisor and machine type, the
  device set it presents: transport (PCI or MMIO), virtio devices, console, and what is *absent*.
- **Start with Firecracker**, then Cloud Hypervisor, then QEMU `microvm`. Not full QEMU: that is
  a different class with a much larger surface.
- **Why data**: the same reason `source_map.yaml` is data. A hypervisor's device set is a fact to
  look up, not logic to write.
- **Validate**: each entry states what is absent as explicitly as what is present — a microVM
  with no PCI bus at all is the interesting case and the one a driver decision turns on.

### Task 2: Derivation
- **Action**: `target_spec.py --derive-microvm <hypervisor> <machine-type>` emits a complete
  target with `source: derived` on every fact.
- **Validate**: the emitted target validates under D1, and a round-trip against a hand-written
  Firecracker example agrees — resolving every difference in writing, as intent-B did.

### Task 3: Prove it needs no questions
- **Action**: Measure it. Derivation must ask nothing, and the resulting definition must be
  complete enough for D6 to accept.
- **Why measured**: the PRD's hypothesis is that elicitation is a fallback rather than the main
  road. That is a claim with a number behind it, and this is the first phase that can produce one.
- **Validate**: `assumptions` is empty for a derived microVM target, or every entry in it is
  justified.

## Validation

```bash
python agent/tools/target_spec.py --derive-microvm firecracker default > /tmp/fc.md
python agent/tools/target_spec.py --validate /tmp/fc.md
diff <(...) agent/kernel_spec/targets/firecracker.md    # differences resolved in writing
cd agent && python -m pytest tests/unit/test_target_derivation.py -q
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| The hypervisor table rots as versions change | **M** | Record the version the entry describes, as `vendors.yaml` records document revisions |
| Derived and real devices disagree | **M** | D4's probe path is the check; a derived target that a probe contradicts is a finding about the table |
| microVM chosen because it is easy, not because it is useful | **L** | It is also the honest answer to "put this in a container", and the shape a k8s pod takes |

## Acceptance
- [ ] A hypervisor table stating present *and* absent devices, versioned
- [ ] Firecracker derives a complete, valid target with no questions asked
- [ ] Derived facts carry `source: derived`; `assumptions` is empty or justified
- [ ] A round-trip against the hand-written example resolves every difference in writing
