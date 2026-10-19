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

- **x86_64:** each feature except `INVARIANT_TSC` is the CPUID bit recorded for it in
  `agent/hardware/isa/x86.json` → `cpuid` (leaf, subleaf, register, bit, from Linux's
  `cpufeatures.h`), under the table's key: `PAGE1GB` is `gbpages`, `TSC_DEADLINE` is
  `tsc_deadline_timer`, the rest are the lower-case name. `INVARIANT_TSC` has no entry
  there: Linux records it only as the synthetic flags `constant_tsc` and `nonstop_tsc`
  (no leaf, no register), and the table has no leaf `0x80000007` entries. It is CPUID
  `0x80000007` EDX bit 8, read only when `0x80000000` reports a maximum of `0x80000007`
  or more. Leaves above the maximum reported by leaf 0 (or `0x80000000` for the extended
  range) are not read: their contents are undefined.
- **OS support is part of "has".** AVX and AVX-512 also need `CR4.OSXSAVE` set and the
  matching `XCR0` bits enabled; `cpu_has(CPU_FEAT_AVX)` is false until the kernel has done
  that.
- **aarch64:** `ID_AA64ISAR0_EL1`, `ID_AA64ISAR1_EL1`, `ID_AA64PFR0_EL1`, `ID_AA64MMFR*_EL1`.
- **riscv64:** the ISA string from the device tree (`riscv,isa` / `riscv,isa-extensions`);
  `misa` is M-mode only.

### REQUIRED: the host-test seam

The subsystem reads the machine only through five functions, declared in
`kernel/include/cpu.h` and defined by arch code in the kernel. The host suite
(`tests/kernel/run_cpu_test.sh`) defines them with a fake CPU, so the subsystem must call
nothing else for CPUID, CR4, XCR0, the microcode revision or the log line. The frozen
interface is `tests/kernel/cpu_reference/include/cpu.h`; match it exactly.

```c
void     cpu_raw_cpuid(uint32_t leaf, uint32_t subleaf, uint32_t r[4]); /* eax ebx ecx edx */
uint64_t cpu_raw_cr4(void);          /* bit 18 is OSXSAVE */
uint64_t cpu_raw_xcr0(void);         /* read only when CR4.OSXSAVE is set */
uint32_t cpu_raw_microcode(void);
void     cpu_raw_log(const char *line);
uint32_t cpu_report(const cpu_info_t *info, char *buf, uint32_t n);   /* snprintf-style */
```

- A leaf is read only when it is at or below the maximum its range reports: leaf 0's EAX for
  the basic range, `0x80000000`'s EAX for the extended range (and the extended range exists
  only when that EAX is `0x8000xxxx`). Leaf `0x80000000` itself is always read.
- OS state: `AVX`, `AVX2`, `FMA` and `FMA4` need `CR4.OSXSAVE` and `XCR0` bits 1 and 2 (mask
  `0x6`); `AVX512F` needs `CR4.OSXSAVE` and `XCR0` mask `0xE6`. `XSAVE` is only a CPUID bit.
- Family and model fold as in `arch/x86_64.md`: family adds the extended family when the base
  family is `0xF`; model takes the extended model as its high nibble when the base family is
  `6` or `0xF`. Stepping is the low four bits.
- `cpu_has` is false for any value outside `[0, CPU_FEAT__COUNT)`.
- `cpu_report` writes `[CPU] <vendor> fam F model M step S ucode 0xU:` followed by the names of
  the features that are on, in enum order, lower case (`tsc_deadline`, `invariant_tsc`, ...).
  `cpu_detect` passes that line to `cpu_raw_log` once.

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

`tests/kernel/run_cpu_test.sh`: `--self-test` runs it against `tests/kernel/cpu_reference/`; `--inject` scores it against 13 injected defects (13/13). The host suite fakes `cpuid()` and checks: an unsupported leaf is not read; AVX is false
until `XCR0` enables it; a Zen 1 signature with the FMA4 bit clear reports no FMA4; an Alder
Lake signature with the AVX-512 bit set reports AVX-512 (the CPU said so, and that wins).
