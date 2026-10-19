/* The cpu subsystem's interface, as agent/kernel_spec/subsystems/cpu.md specifies it.
 * A generated kernel must provide exactly this, and the host suite links against it. */
#ifndef AUTON_CPU_H
#define AUTON_CPU_H
#include <stdbool.h>
#include <stdint.h>

typedef enum cpu_feature {
	CPU_FEAT_NX, CPU_FEAT_PAGE1GB, CPU_FEAT_PCID, CPU_FEAT_INVPCID,
	CPU_FEAT_FSGSBASE, CPU_FEAT_SMEP, CPU_FEAT_SMAP, CPU_FEAT_UMIP,
	CPU_FEAT_XSAVE, CPU_FEAT_AVX, CPU_FEAT_AVX2, CPU_FEAT_FMA, CPU_FEAT_FMA4,
	CPU_FEAT_AVX512F, CPU_FEAT_RTM, CPU_FEAT_RDRAND, CPU_FEAT_RDSEED,
	CPU_FEAT_X2APIC, CPU_FEAT_TSC_DEADLINE, CPU_FEAT_INVARIANT_TSC,
	CPU_FEAT__COUNT
} cpu_feature_t;

typedef struct cpu_info {
	char     vendor[13];                 /* CPUID leaf 0: EBX, EDX, ECX */
	uint32_t family, model, stepping;    /* leaf 1, extended fields folded in */
	uint32_t microcode;                  /* 0 where unreadable */
	uint64_t features[(CPU_FEAT__COUNT + 63) / 64];
} cpu_info_t;

void cpu_detect(cpu_info_t *out);        /* called once from kernel_main */
bool cpu_has(cpu_feature_t f);           /* after cpu_detect; false for anything out of range */
const cpu_info_t *cpu_info(void);

/* "[CPU] <vendor> fam F model M step S ucode 0xU: <feature names in enum order>"
 * Returns the length that would be written, snprintf-style. cpu_detect passes
 * this line to cpu_raw_log. */
uint32_t cpu_report(const cpu_info_t *info, char *buf, uint32_t n);

/* The seam. Arch code defines these in the kernel; the host suite defines them
 * with a fake CPU. cpu.c reads the machine ONLY through them. */
void     cpu_raw_cpuid(uint32_t leaf, uint32_t subleaf, uint32_t r[4]); /* eax ebx ecx edx */
uint64_t cpu_raw_cr4(void);              /* bit 18 is OSXSAVE */
uint64_t cpu_raw_xcr0(void);             /* read only when CR4.OSXSAVE is set */
uint32_t cpu_raw_microcode(void);
void     cpu_raw_log(const char *line);

#endif
