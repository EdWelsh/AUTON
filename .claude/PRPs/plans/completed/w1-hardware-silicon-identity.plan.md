# Plan: Silicon Identity at Boot (H5)

**Source PRD**: `.claude/PRPs/prds/auton-hardware-truth.prd.md` — phase H5
**Complexity**: Small — and the join key every later hardware phase depends on
**Unblocks**: H8 ("is this machine safe?"), H10 (conformance), errata table lookup

## Summary

Every errata record, every mitigation, and every conformance result is keyed on exactly which
silicon is running. AUTON currently identifies its hardware as *"4 devices on PCI bus 0"* and
cannot name its own CPU.

This specifies identity capture at boot: CPU vendor/family/model/stepping and microcode
revision, board and firmware identity, and the target-neutral equivalents for non-x86. It is
small, it blocks three later phases, and it needs no agents — it is spec plus a host-side test.

## Evidence

- `arch/x86_64.md:1617-1624` already documents CPUID leaf `0x1` returning family/model/stepping
  in EAX. The instruction is specified; nothing captures the result.
- `arch/hal.md:158-180` "Device Discovery HAL" abstracts firmware by type —
  `FIRMWARE_ACPI` / `FIRMWARE_DEVICE_TREE` / `FIRMWARE_NONE` — which is exactly the
  abstraction identity capture needs to stay target-neutral.
- `boot_info.c` in the retired tree captured only `total_ram_bytes` and boot modules from the
  Multiboot2 tag list. No CPU identity, no SMBIOS.
- The hardware-truth PRD keys errata on
  `(vendor, family, model, stepping, microcode_rev_min, microcode_rev_fixed)` — five fields,
  none of which AUTON reads today.
- Microcode revision is the field that distinguishes "fixed in silicon" from "patched at boot"
  from "unpatched", and it is the one an operator asking *"is this machine safe?"* most needs.

## Patterns to Mirror

| Category | Source | Pattern |
|---|---|---|
| Firmware abstraction | `arch/hal.md:161-170` | `firmware_type_t` — one enum covering ACPI, device tree, and none |
| Per-arch HAL split | `arch/hal.md` categories | Mechanism per architecture, contract shared |
| Boot info capture | `boot_info.c` tag walk | Sticky current-file style walking; extend rather than replace |
| Honest unknowns | `slm.md` rejection reasons | Identity that cannot be read is reported as unknown, never guessed |
| Structured markers | `acceptance_tests.py` `SERIAL_MARKER_SETS` | A new `identity` set the spine can assert |

## Files to Change

| File | Action | Why |
|---|---|---|
| `agent/kernel_spec/subsystems/dev.md` | UPDATE | Identity capture alongside device identification |
| `agent/kernel_spec/arch/hal.md` | UPDATE | `arch_cpu_identity()` as a HAL category |
| `agent/kernel_spec/arch/{x86_64,aarch64,riscv64}.md` | UPDATE | Per-arch mechanism |
| `agent/kernel_spec/tests/acceptance_tests.py` | UPDATE | An `identity` marker set |

## Tasks

### Task 1: Define the identity record, target-neutrally
- **Action**: One structure, populated differently per architecture:
  ```c
  typedef struct silicon_identity {
      char     vendor[13];      /* CPUID 0x0 / MIDR implementer / mvendorid */
      uint32_t family, model, stepping;
      uint64_t microcode_rev;   /* 0 = unknown, which is NOT the same as 0 revision */
      char     brand[49];       /* CPUID 0x80000002-4, where available */
      char     board_vendor[64], board_product[64];   /* SMBIOS / device tree */
      uint8_t  firmware_type;   /* firmware_type_t */
  } silicon_identity_t;
  ```
- **Critical**: `0` and "unknown" must be distinguishable. An errata lookup that treats an
  unread microcode revision as revision 0 will conclude a patched machine is unpatched — or
  worse, the reverse.
- **Validate**: the structure expresses x86_64, AArch64 (MIDR_EL1) and RISC-V
  (`mvendorid`/`marchid`/`mimpid`) without per-arch fields.

### Task 2: Specify the per-arch mechanism
- **Action**: x86_64 — CPUID leaves `0x0`, `0x1`, `0x80000002-4`, and `IA32_BIOS_SIGN_ID`
  (MSR `0x8B`) for microcode revision, read after a `CPUID` serialising write of 0.
  AArch64 — `MIDR_EL1`, `REVIDR_EL1`. RISC-V — the `mvendorid`/`marchid`/`mimpid` CSRs.
  Board identity from SMBIOS on x86, device tree elsewhere.
- **Gotcha**: the x86 microcode read has a required sequence — write 0 to the MSR, execute
  `CPUID`, then read — and getting it wrong silently returns stale data. Specify the sequence,
  not just the register.
- **Validate**: each arch spec names its registers and any required sequence.

### Task 3: Report it, and make it assertable
- **Action**: A `[CPU]` boot line carrying vendor, family/model/stepping, and microcode
  revision, plus an `identity` marker set so the spine asserts identity was captured rather
  than trusting it. Chat answers `what cpu is this` from the record — a fact from a register,
  never from the model.
- **Mirror**: the retrieval-not-generation rule already in `dev.md`. Identity is the same
  class of fact as a device id.
- **Validate**: the marker set passes on a generated kernel; the chat answer matches the boot line.

### Task 4: Host-side verification
- **Action**: A host test that reads the same identity through the OS's own interfaces and
  compares — on macOS `sysctl machdep.cpu`, on Linux `/proc/cpuinfo` and
  `/sys/devices/system/cpu/cpu0/microcode/version`. A mismatch means the kernel's capture is
  wrong, and that is worth catching before an errata table is keyed on it.
- **Validate**: identity captured under QEMU matches what the host reports for the guest CPU model.

## Validation

```bash
scripts/e2e.sh --target <target> --skip-train     # identity marker set asserted
KERNEL_TREE=<target> tests/kernel/run_identity_test.sh
# cross-check against the host's own view:
sysctl machdep.cpu.family machdep.cpu.model machdep.cpu.stepping 2>/dev/null || cat /proc/cpuinfo | head
```

## Risks

| Risk | Likelihood | Mitigation |
|---|---|---|
| Microcode revision read incorrectly, silently | **H** | The read sequence is specified, not just the register; Task 4 cross-checks against the host |
| "Unknown" conflated with zero | **M** | Task 1 makes the distinction explicit — it is the difference between "unpatched" and "we did not look" |
| QEMU reports an idealised CPU | **H** | Expected and fine for capture testing. Conformance (H10) needs real hardware, which is the windows-linux PRD's job |
| Identity spec drifts from the errata table's key | **M** | Both are in the hardware-truth PRD; H4's key must be written against this structure, not alongside it |

## Acceptance
- [ ] One identity structure expresses x86_64, AArch64 and RISC-V without per-arch fields
- [ ] "Unknown" is distinguishable from zero in every field
- [ ] The x86 microcode read sequence is specified, not just the register
- [ ] A `[CPU]` boot line exists and an `identity` marker set asserts it
- [ ] Captured identity cross-checks against the host's own view of the guest CPU
