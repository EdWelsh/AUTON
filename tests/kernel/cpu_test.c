/* Host test for the cpu subsystem (agent/kernel_spec/subsystems/cpu.md).
 *
 * The CPU is fake: cpu_raw_cpuid/cr4/xcr0 answer from a table, and every leaf the code asks
 * for is recorded. That is what lets this suite check what no real machine can: that a leaf
 * above the CPU's reported maximum is never read (its contents are undefined), that AVX is
 * false until the OS enabled the state, and that a vendor string never adds a feature.
 * Feature bit positions come from agent/hardware/isa/x86.json (Linux's cpufeatures.h),
 * restated here so a wrong bit in an implementation is a failure, not a self-agreement. */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "cpu.h"

enum { EAX, EBX, ECX, EDX };
#define CR4_OSXSAVE (1ull << 18)

typedef struct { uint32_t leaf, sub, r[4]; } leaf_t;

typedef struct {
	const char *name;
	uint32_t max_basic, max_ext;     /* what leaves 0 and 0x80000000 report */
	const char *vendor;
	leaf_t leaves[12];
	uint64_t cr4, xcr0;
	uint32_t ucode;
} fake_cpu_t;

static const fake_cpu_t *cur;
static uint32_t read_leaves[64], n_reads;
static char logged[256];
static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	if (cond) printf("PASS  %-60s\n", name);
	else { printf("FAIL  %-60s  %s\n", name, detail ? detail : ""); fails = 1; }
}

void cpu_raw_cpuid(uint32_t leaf, uint32_t sub, uint32_t r[4])
{
	if (n_reads < 64) read_leaves[n_reads++] = leaf;
	memset(r, 0, 16);
	if (leaf == 0) {
		r[EAX] = cur->max_basic;
		memcpy(&r[EBX], cur->vendor + 0, 4);
		memcpy(&r[EDX], cur->vendor + 4, 4);
		memcpy(&r[ECX], cur->vendor + 8, 4);
		return;
	}
	if (leaf == 0x80000000u) { r[EAX] = cur->max_ext; return; }
	for (int i = 0; i < 12 && cur->leaves[i].leaf; i++)
		if (cur->leaves[i].leaf == leaf && cur->leaves[i].sub == sub)
			memcpy(r, cur->leaves[i].r, 16);
}
uint64_t cpu_raw_cr4(void) { return cur->cr4; }
uint64_t cpu_raw_xcr0(void) { return cur->xcr0; }
uint32_t cpu_raw_microcode(void) { return cur->ucode; }
void cpu_raw_log(const char *line) { snprintf(logged, sizeof logged, "%s", line); }

#define B(n) (1u << (n))
/* leaf 1 ECX: pcid 17, x2apic 21, tsc_deadline 24, xsave 26, avx 28, fma 12, rdrand 30
 * leaf 7 EBX: fsgsbase 0, avx2 5, smep 7, invpcid 10, rtm 11, avx512f 16, rdseed 18, smap 20
 * leaf 7 ECX: umip 2;  0x80000001 EDX: nx 20, page1gb 26;  ECX: fma4 16;  0x80000007 EDX bit 8 */
static const fake_cpu_t ALDER_LAKE = {
	"Alder Lake P-core, OS enabled AVX-512", 0x20, 0x80000008u, "GenuineIntel",
	{ {1, 0, {0x00090672, 0, B(17)|B(21)|B(24)|B(26)|B(28)|B(12)|B(30), 0}},
	  {7, 0, {0, B(0)|B(5)|B(7)|B(10)|B(16)|B(18)|B(20), B(2), 0}},
	  {0x80000001u, 0, {0, 0, 0, B(20)|B(26)}},
	  {0x80000007u, 0, {0, 0, 0, B(8)}} },
	CR4_OSXSAVE, 0xE7, 0x2c };
static const fake_cpu_t ZEN1 = {
	"Zen 1, FMA4 bit clear", 0xD, 0x8000001Fu, "AuthenticAMD",
	{ {1, 0, {0x00800F11, 0, B(26)|B(28)|B(12)|B(30), 0}},
	  {7, 0, {0, B(0)|B(5)|B(7)|B(18)|B(20), 0, 0}},
	  {0x80000001u, 0, {0, 0, 0, B(20)|B(26)}} },
	CR4_OSXSAVE, 0x7, 0 };
static const fake_cpu_t PENTIUM = {
	"Pentium P5, no leaf 7, no extended range", 1, 0, "GenuineIntel",
	{ {1, 0, {0x00000525, 0, 0, 0}},
	  {7, 0, {0, 0xFFFFFFFFu, 0xFFFFFFFFu, 0}} },   /* undefined garbage above the maximum */
	0, 0, 0 };
static const fake_cpu_t PRESCOTT = {
	"Pentium 4, extended maximum 0x80000004", 5, 0x80000004u, "GenuineIntel",
	{ {1, 0, {0x00000F41, 0, 0, 0}},
	  {0x80000001u, 0, {0, 0, 0, B(20)}},
	  {0x80000007u, 0, {0, 0, 0, 0xFFFFFFFFu}} },     /* above the extended maximum: garbage */
	0, 0, 0 };
static const fake_cpu_t AVX_BIT_NO_OS = {
	"AVX bit set, OS has not enabled XCR0", 0xD, 0x80000008u, "GenuineIntel",
	{ {1, 0, {0x000306C3, 0, B(26)|B(28)|B(12), 0}},
	  {7, 0, {0, B(5)|B(16), 0, 0}} },
	CR4_OSXSAVE, 0x3, 0 };
static const fake_cpu_t AVX_NO_OSXSAVE = {
	"AVX bit set, CR4.OSXSAVE clear, XCR0 stale", 0xD, 0x80000008u, "GenuineIntel",
	{ {1, 0, {0x000306C3, 0, B(26)|B(28), 0}} },
	0, 0x7, 0 };
static const fake_cpu_t AVX256_ONLY_OS = {
	"AVX-512F bit set, OS enabled only AVX state", 0x20, 0x80000008u, "GenuineIntel",
	{ {1, 0, {0x00090672, 0, B(26)|B(28)|B(12), 0}},
	  {7, 0, {0, B(5)|B(16), 0, 0}} },
	CR4_OSXSAVE, 0x7, 0 };
static const fake_cpu_t AMD_ALL_CLEAR = {
	"AuthenticAMD with every bit clear", 0xD, 0x8000001Fu, "AuthenticAMD",
	{ {1, 0, {0x00800F11, 0, 0, 0}} }, CR4_OSXSAVE, 0x7, 0 };
static const fake_cpu_t ZEN3 = {
	"Zen 3 signature", 0x10, 0x80000023u, "AuthenticAMD",
	{ {1, 0, {0x00A20F10, 0, 0, 0}} }, 0, 0, 0 };
static const fake_cpu_t PENTIUM_PRO = {
	"Pentium Pro: extended model 0 folds as a no-op", 2, 0, "GenuineIntel",
	{ {1, 0, {0x00000612, 0, 0, 0}} }, 0, 0, 0 };

static void run(const fake_cpu_t *c)
{
	cur = c; n_reads = 0; logged[0] = 0;
	cpu_info_t info;
	cpu_detect(&info);
}

static void check_reads(const fake_cpu_t *c)
{
	char name[96];
	snprintf(name, sizeof name, "no leaf above the maximum is read: %s", c->name);
	for (uint32_t i = 0; i < n_reads; i++) {
		uint32_t leaf = read_leaves[i];
		int over = leaf >= 0x80000000u ? (leaf != 0x80000000u && leaf > c->max_ext)
						: leaf > c->max_basic;
		if (over) { char d[48]; snprintf(d, sizeof d, "read leaf 0x%x", leaf); ok(name, 0, d); return; }
	}
	ok(name, 1, 0);
}

static void test_alder_lake(void)
{
	run(&ALDER_LAKE);
	static const cpu_feature_t ALL[] = {
		CPU_FEAT_NX, CPU_FEAT_PAGE1GB, CPU_FEAT_PCID, CPU_FEAT_INVPCID, CPU_FEAT_FSGSBASE,
		CPU_FEAT_SMEP, CPU_FEAT_SMAP, CPU_FEAT_UMIP, CPU_FEAT_XSAVE, CPU_FEAT_AVX,
		CPU_FEAT_AVX2, CPU_FEAT_FMA, CPU_FEAT_AVX512F, CPU_FEAT_RDRAND, CPU_FEAT_RDSEED,
		CPU_FEAT_X2APIC, CPU_FEAT_TSC_DEADLINE, CPU_FEAT_INVARIANT_TSC };
	int all = 1;
	for (unsigned i = 0; i < sizeof ALL / sizeof ALL[0]; i++) all &= cpu_has(ALL[i]);
	ok("Alder Lake: every set bit is reported (the CPU said so, that wins)", all, 0);
	ok("Alder Lake: bits that are clear stay clear (RTM, FMA4)",
	   !cpu_has(CPU_FEAT_RTM) && !cpu_has(CPU_FEAT_FMA4), 0);
	ok("Alder Lake: vendor string", !strcmp(cpu_info()->vendor, "GenuineIntel"), cpu_info()->vendor);
	ok("Alder Lake: family 6 model 151 step 2",
	   cpu_info()->family == 6 && cpu_info()->model == 151 && cpu_info()->stepping == 2, 0);
	ok("Alder Lake: microcode revision is reported", cpu_info()->microcode == 0x2c, 0);
	check_reads(&ALDER_LAKE);
}

static void test_zen(void)
{
	run(&ZEN1);
	ok("Zen 1: FMA4 bit clear reports no FMA4", !cpu_has(CPU_FEAT_FMA4), 0);
	ok("Zen 1: its real features are found",
	   cpu_has(CPU_FEAT_AVX) && cpu_has(CPU_FEAT_AVX2) && cpu_has(CPU_FEAT_FMA) &&
	   cpu_has(CPU_FEAT_SMEP) && cpu_has(CPU_FEAT_SMAP) && cpu_has(CPU_FEAT_NX), 0);
	ok("Zen 1: AVX-512 and INVARIANT_TSC are absent (leaf bits clear)",
	   !cpu_has(CPU_FEAT_AVX512F) && !cpu_has(CPU_FEAT_INVARIANT_TSC), 0);
	ok("Zen 1: family 23 model 1 step 1",
	   cpu_info()->family == 23 && cpu_info()->model == 1 && cpu_info()->stepping == 1, 0);
	check_reads(&ZEN1);

	run(&AMD_ALL_CLEAR);
	int none = 1;
	for (int f = 0; f < CPU_FEAT__COUNT; f++) none &= !cpu_has((cpu_feature_t)f);
	ok("the vendor string never implies a feature (AuthenticAMD, all clear)", none, 0);

	run(&ZEN3);
	ok("Zen 3 signature folds to family 25 model 33",
	   cpu_info()->family == 25 && cpu_info()->model == 33, 0);
	run(&PENTIUM_PRO);
	ok("Pentium Pro: model stays 1 (extended model 0)", cpu_info()->family == 6 && cpu_info()->model == 1, 0);
}

static void test_leaf_limits(void)
{
	run(&PENTIUM);
	int none = 1;
	for (int f = 0; f < CPU_FEAT__COUNT; f++) none &= !cpu_has((cpu_feature_t)f);
	ok("Pentium P5: nothing from garbage above the maximum", none, 0);
	ok("Pentium P5: family 5 model 2 step 5",
	   cpu_info()->family == 5 && cpu_info()->model == 2 && cpu_info()->stepping == 5, 0);
	check_reads(&PENTIUM);
	run(&PRESCOTT);
	ok("extended leaf above the extended maximum is not read (INVARIANT_TSC)",
	   !cpu_has(CPU_FEAT_INVARIANT_TSC), 0);
	ok("Prescott: NX from 0x80000001 is found", cpu_has(CPU_FEAT_NX), 0);
	check_reads(&PRESCOTT);
}

static void test_os_state(void)
{
	run(&AVX_BIT_NO_OS);
	ok("AVX is false until XCR0 enables it", !cpu_has(CPU_FEAT_AVX), 0);
	ok("AVX2, FMA and AVX-512 wait for the OS too",
	   !cpu_has(CPU_FEAT_AVX2) && !cpu_has(CPU_FEAT_FMA) && !cpu_has(CPU_FEAT_AVX512F), 0);
	ok("XSAVE itself is a CPUID bit, not OS state", cpu_has(CPU_FEAT_XSAVE), 0);
	run(&AVX_NO_OSXSAVE);
	ok("AVX is false when CR4.OSXSAVE is clear, whatever XCR0 holds", !cpu_has(CPU_FEAT_AVX), 0);
	run(&AVX256_ONLY_OS);
	ok("AVX-512F is false when only the AVX state is enabled", !cpu_has(CPU_FEAT_AVX512F), 0);
	ok("... while AVX and AVX2 are true", cpu_has(CPU_FEAT_AVX) && cpu_has(CPU_FEAT_AVX2), 0);
}

static void test_api_and_report(void)
{
	run(&ALDER_LAKE);
	ok("cpu_has is false out of range",
	   !cpu_has(CPU_FEAT__COUNT) && !cpu_has((cpu_feature_t)-1) && !cpu_has((cpu_feature_t)200), 0);
	ok("cpu_detect logs exactly one [CPU] line", !strncmp(logged, "[CPU] GenuineIntel", 18) && !strchr(logged, '\n'), logged);
	ok("report: family, model, step and ucode in the specified shape",
	   strstr(logged, " fam 6 model 151 step 2 ucode 0x2c:") != NULL, logged);
	ok("report: features in enum order, lower case",
	   strstr(logged, ": nx page1gb pcid invpcid fsgsbase smep smap umip xsave avx avx2 fma avx512f") != NULL, logged);
	char small[8];
	uint32_t need = cpu_report(cpu_info(), small, sizeof small);
	ok("cpu_report truncates safely and returns the full length", need > 8 && strlen(small) == 7, 0);
	run(&ZEN1);
	ok("report: a feature that is off is not listed", strstr(logged, "fma4") == NULL && strstr(logged, "avx512") == NULL, logged);
}

int main(void)
{
	test_alder_lake();
	test_zen();
	test_leaf_limits();
	test_os_state();
	test_api_and_report();
	printf(fails ? "\nFAILED\n" : "\nall cpu tests passed\n");
	return fails;
}
