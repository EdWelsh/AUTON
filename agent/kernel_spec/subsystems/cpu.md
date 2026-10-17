---
subsystem: cpu
provides: [cpu-features]
depends_on: []
optional: []
# Every other subsystem asks this one before using an instruction outside the baseline.
---

# CPU Feature Discovery Specification

## Overview

A generated kernel runs on a CPU nobody read about in advance. This subsystem finds out,
at boot, which instructions that CPU actually executes, and is the only place any other
code asks.

The rule this subsystem exists for: **a document never proves an instruction is
present.** Vendor manuals describe extensions that were announced and never shipped
(Intel's FMA4), extensions that later parts dropped (AMD's FMA4, XOP and 3DNow! on Zen),
and extensions that one stepping or microcode revision has and the next does not
(AVX-512 on Alder Lake; TSX on Haswell and Skylake). The facts are tabulated, with
sources, in `agent/hardware/isa/` (`exceptions.yaml` for the cases above). The tables
tell a generator what *may* be there. Only the running CPU says what *is*.

## Requirements

### REQUIRED: baseline only, unless asked

Code outside this subsystem uses only the baseline instruction set of its architecture:

| Arch | Baseline | Compiler flag |
|---|---|---|
| x86_64 | x86-64 (v1): SSE2, CMPXCHG8B, CMOV, FXSR, no AVX | `-march=x86-64 -mno-sse -mno-mmx -mno-avx` in the kernel; SIMD needs `fpu_begin()` |
| aarch64 | Armv8.0-A, no SVE | `-march=armv8-a -mgeneral-regs-only` |
| riscv64 | RV64IMAC + Zicsr + Zifencei | `-march=rv64imac_zicsr_zifencei` |

Anything else is optional and is used only behind a `cpu_has()` check.

### REQUIRED: detect once, at boot, before the first optional instruction

```c
typedef enum cpu_feature {
    CPU_FEAT_NX, CPU_FEAT_PAGE1GB, CPU_FEAT_PCID, CPU_FEAT_INVPCID,
    CPU_FEAT_FSGSBASE, CPU_FEAT_SMEP, CPU_FEAT_SMAP, CPU_FEAT_UMIP,
    CPU_FEAT_XSAVE, CPU_FEAT_AVX, CPU_FEAT_AVX2, CPU_FEAT_FMA, CPU_FEAT_FMA4,
    CPU_FEAT_AVX512F, CPU_FEAT_RTM, CPU_FEAT_RDRAND, CPU_FEAT_RDSEED,
    CPU_FEAT_X2APIC, CPU_FEAT_TSC_DEADLINE, CPU_FEAT_INVARIANT_TSC,
    CPU_FEAT__COUNT
} cpu_feature_t;

typedef struct cpu_info {
    char     vendor[13];          /* CPUID leaf 0: EBX, EDX, ECX */
    uint32_t family, model, stepping;   /* leaf 1, extended fields folded in */
    uint32_t microcode;           /* IA32_BIOS_SIGN_ID where readable, else 0 */
    uint64_t features[(CPU_FEAT__COUNT + 63) / 64];
} cpu_info_t;

void cpu_detect(cpu_info_t *out);              /* called once from kernel_main */
bool cpu_has(cpu_feature_t f);                 /* after cpu_detect */
const cpu_info_t *cpu_info(void);
```

- **x86_64:** each feature is the CPUID bit recorded for it in
  `agent/hardware/isa/x86.json` → `cpuid` (leaf, subleaf, register, bit, from Linux's
  `cpufeatures.h`). Leaves above the maximum reported by leaf 0 (or `0x80000000` for the
  extended range) are not read: their contents are undefined.
- **OS support is part of "has".** AVX and AVX-512 also need `CR4.OSXSAVE` set and the
  matching `XCR0` bits enabled; `cpu_has(CPU_FEAT_AVX)` is false until the kernel has done
  that.
- **aarch64:** `ID_AA64ISAR0_EL1`, `ID_AA64ISAR1_EL1`, `ID_AA64PFR0_EL1`, `ID_AA64MMFR*_EL1`.
- **riscv64:** the ISA string from the device tree (`riscv,isa` / `riscv,isa-extensions`);
  `misa` is M-mode only.

### REQUIRED: the vendor string never implies a feature

`if vendor == "AuthenticAMD" then FMA4` is wrong on every Zen part. A family/model match
is allowed only to **remove** a feature (an erratum or exception says the bit lies), never
to add one.

### REQUIRED: report

`cpu_detect` prints one line:

```
[CPU] GenuineIntel fam 6 model 151 step 2 ucode 0x2c: nx pcid invpcid smep smap xsave avx avx2 fma
```

The conformance harness (H10) compares this line with what it measured, and a feature
listed here that faults when used is a finding.

## Edge Cases

- **Hypervisors** can mask bits, so a guest may lack a feature its host has. Trust the
  guest's CPUID; never probe by executing an instruction and catching `#UD` in production.
- **Hybrid parts** (performance and efficiency cores) can differ per core. Detect on the
  boot CPU; an SMP kernel re-checks each AP and uses the intersection.
- **Undocumented behaviour is not a feature.** First-generation Zen reportedly executes
  FMA4 with the CPUID bit clear (`exceptions.yaml`). The bit is clear, so the kernel does
  not use it.

## Testing

The host suite fakes `cpuid()` and checks: an unsupported leaf is not read; AVX is false
until `XCR0` enables it; a Zen 1 signature with the FMA4 bit clear reports no FMA4; an Alder
Lake signature with the AVX-512 bit set reports AVX-512 (the CPU said so, and that wins).
