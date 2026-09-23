# Report: Silicon Identity at Boot (H5)

**Plan**: `.claude/PRPs/plans/w1-hardware-silicon-identity.plan.md`
**Source PRD**: `auton-hardware-truth.prd.md` — phase H5

AUTON identified its hardware as *"4 devices on PCI bus 0"* and could not name its own CPU.
Every errata record, mitigation and conformance result is keyed on exactly which silicon is
running, so this is the join key three later phases need.

## One record, three architectures

`arch_cpu_identity()` is now HAL category 8, alongside Boot, CPU, MMU, Context Switch, Timer,
I/O and Device Discovery. One `silicon_identity_t` populated from different registers:

| | x86_64 | AArch64 | RISC-V |
|---|---|---|---|
| vendor | CPUID `0x0` | `MIDR_EL1` Implementer | `mvendorid` |
| family/model/stepping | CPUID `0x1`, extended fields folded | `MIDR_EL1` PartNum/Variant/Revision | `marchid`/`mimpid` |
| microcode_rev | `IA32_BIOS_SIGN_ID` | none | none |
| board | SMBIOS type 1/2 | device tree | device tree |

No per-architecture field was added. The names are x86 heritage; the shape is not.

## Unknown is not zero

The record carries an `ident_source_t` per field group — `IDENT_UNKNOWN`, `IDENT_READ`,
`IDENT_FIRMWARE` — and the boot line renders them differently:

```
[CPU] GenuineIntel family 6 model 151 stepping 2 microcode 0x429
[CPU] ARM family 3401 model 0 stepping 1 microcode unknown
```

`microcode 0x0` says the machine carries no update. `microcode unknown` says nobody looked. An
errata lookup that conflates them reports a patched machine as vulnerable, or a vulnerable one
as patched, and both are worse than no answer. Under QEMU the MSR commonly reads 0 after a
correct sequence — that is `IDENT_READ` with value 0, a real reading.

## The two mechanisms specified as sequences, not registers

**Folding CPUID.1:EAX.** `family`/`model` are split across base and extended fields, and
reading only the base fields misidentifies every modern part. An Alder Lake reports base family
6, base model 7, extended model 9 — family 6 **model 151**, which is what Intel's Specification
Update is indexed by. Without the fold it reads as model 7 and matches a Pentium III's errata.
Intel folds the extended model for family 6 as well as 0xF; AMD only for 0xF, and the rule is
written per vendor because "harmless today" is not a specification.

**Reading the microcode revision.** The order is architectural: write 0 to `IA32_BIOS_SIGN_ID`,
execute `CPUID` to serialise, then read — and the revision is the *high* dword. Skipping either
step returns whatever the MSR held before, frequently a plausible-looking revision from an
earlier read. Specified as a sequence, because a register name alone would be implemented wrong
and fail silently.

## Assertable, and shared with the chat

A new `identity` marker set, separate from `boot` so a kernel that boots without capturing
identity fails visibly rather than being assumed to have it. The regex permits `unknown` on
purpose — an architecture with no microcode MSR must be able to give the honest answer without
failing the assertion.

`dev_identity_string()` is used by both the boot report and the chat answer, deliberately: a
chat answer contradicting the boot line is the failure this interface exists to prevent.
`what cpu is this` is answered from the record by the deterministic path before the model is
consulted — the same retrieval-not-generation rule that already covers PCI ids, and for the
same reason. A model asked what CPU it runs on will produce a plausible one.

## Tests

`tests/kernel/identity_test.c` + `run_identity_test.sh`, with a reference implementation so
the suite is proved rather than asserted — the same approach as the allocator work, for the
same reason: these tests are the deliverable for code that does not exist yet.

The folding formula is validated against **eight documented parts**, which runs on any host
including the arm64 one this was written on:

Alder Lake-S, Skylake-S, Haswell, Kaby Lake, Zen 3 (Vermeer), Zen 2 (Matisse), Pentium P5 —
the family-5 part the hardware-truth PRD opens with, whose FDIV defect is the motivating
example — and Pentium Pro, where extended model 0 must make folding a no-op rather than a shift.

Mutation-tested, all seven caught:

| Mutation | Caught by |
|---|---|
| Never fold the extended model | 7 vectors |
| Use AMD's model rule for Intel too | 5 vectors |
| Never fold the extended family | 2 AMD vectors |
| Extended model shifted by 8 not 4 | 7 vectors |
| Stepping read from the wrong nibble | 9 checks |
| Unknown microcode rendered as `0x0` | the unknown-is-not-zero check |
| Unknown vendor rendered as empty | the unknown-is-not-zero check |

The rendered boot line was then checked against the **actual marker regex** from
`acceptance_tests.py`, not only against the C-side assertion, including the negative: a line
missing the microcode field is rejected.

The live CPUID cross-check against the OS's own view (`sysctl machdep.cpu` / `/proc/cpuinfo`)
is written and will run on x86 hosts. On this arm64 host it announces itself skipped rather
than passing silently.

## Acceptance

- [x] One structure expresses x86_64, AArch64 and RISC-V without per-arch fields
- [x] "Unknown" distinguishable from zero in every field, and rendered differently
- [x] The x86 microcode read sequence specified, not just the register
- [x] A `[CPU]` boot line exists and an `identity` marker set asserts it
- [ ] **Captured identity cross-checks against the host's own view** — the check is written
      and mutation-tested, but cannot run here: the host is arm64, and no kernel has generated
      `identity.h` yet. The runner exits 2 for "not generated" rather than 1.

## Follow-on

- H4's errata table key must be written *against* this structure rather than alongside it, or
  the two drift and the join silently fails.
- RISC-V is the one architecture where the register cannot distinguish "not implemented" from
  "value 0" — all three CSRs read 0 in both cases. Specified as `IDENT_UNKNOWN` when all three
  are 0, which is the safe reading but loses a genuine zero.
- QEMU reports an idealised CPU. Fine for capture testing; conformance (H10) needs real
  hardware, which is the windows-linux PRD's job.
