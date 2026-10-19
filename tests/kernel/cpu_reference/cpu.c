/* Reference implementation of subsystems/cpu.md, x86_64. The host suite's own proof that it
 * can pass; each BUG_n is a defect a plausible implementation ships with, and the suite must
 * fail on every one (run_cpu_test.sh --inject). */
#include <stdio.h>
#include <string.h>
#include "cpu.h"

#define CR4_OSXSAVE (1ull << 18)
#define XCR0_AVX    0x6ull       /* SSE | AVX state */
#define XCR0_AVX512 0xE6ull      /* + opmask, ZMM_Hi256, Hi16_ZMM */

enum { EAX, EBX, ECX, EDX };

static const struct {
	const char *name;
	uint32_t leaf, sub;
	int reg, bit;
} FEATURES[CPU_FEAT__COUNT] = {
	[CPU_FEAT_NX]            = {"nx",            0x80000001, 0, EDX, 20},
	[CPU_FEAT_PAGE1GB]       = {"page1gb",       0x80000001, 0, EDX, 26},
	[CPU_FEAT_PCID]          = {"pcid",          1, 0, ECX, 17},
	[CPU_FEAT_INVPCID]       = {"invpcid",       7, 0, EBX, 10},
	[CPU_FEAT_FSGSBASE]      = {"fsgsbase",      7, 0, EBX, 0},
	[CPU_FEAT_SMEP]          = {"smep",          7, 0, EBX, 7},
#ifdef BUG_7
	[CPU_FEAT_SMAP]          = {"smap",          7, 0, EBX, 21},
#else
	[CPU_FEAT_SMAP]          = {"smap",          7, 0, EBX, 20},
#endif
	[CPU_FEAT_UMIP]          = {"umip",          7, 0, ECX, 2},
	[CPU_FEAT_XSAVE]         = {"xsave",         1, 0, ECX, 26},
	[CPU_FEAT_AVX]           = {"avx",           1, 0, ECX, 28},
	[CPU_FEAT_AVX2]          = {"avx2",          7, 0, EBX, 5},
	[CPU_FEAT_FMA]           = {"fma",           1, 0, ECX, 12},
	[CPU_FEAT_FMA4]          = {"fma4",          0x80000001, 0, ECX, 16},
	[CPU_FEAT_AVX512F]       = {"avx512f",       7, 0, EBX, 16},
	[CPU_FEAT_RTM]           = {"rtm",           7, 0, EBX, 11},
	[CPU_FEAT_RDRAND]        = {"rdrand",        1, 0, ECX, 30},
	[CPU_FEAT_RDSEED]        = {"rdseed",        7, 0, EBX, 18},
	[CPU_FEAT_X2APIC]        = {"x2apic",        1, 0, ECX, 21},
	[CPU_FEAT_TSC_DEADLINE]  = {"tsc_deadline",  1, 0, ECX, 24},
#ifdef BUG_9
	[CPU_FEAT_INVARIANT_TSC] = {"invariant_tsc", 0x80000007, 0, EDX, 7},
#else
	[CPU_FEAT_INVARIANT_TSC] = {"invariant_tsc", 0x80000007, 0, EDX, 8},
#endif
};

static cpu_info_t g_info;

static bool vector_state(uint64_t mask)
{
#ifdef BUG_4
	(void)cpu_raw_cr4;
#else
	if (!(cpu_raw_cr4() & CR4_OSXSAVE))
		return false;
#endif
#ifdef BUG_3
	(void)mask;
	return true;
#else
	return (cpu_raw_xcr0() & mask) == mask;
#endif
}

static bool needs_os_state(cpu_feature_t f, uint64_t *mask)
{
	switch (f) {
	case CPU_FEAT_AVX: case CPU_FEAT_AVX2: case CPU_FEAT_FMA: case CPU_FEAT_FMA4:
		*mask = XCR0_AVX;
		return true;
	case CPU_FEAT_AVX512F:
#ifdef BUG_8
		*mask = XCR0_AVX;
#else
		*mask = XCR0_AVX512;
#endif
		return true;
	default:
		return false;
	}
}

void cpu_detect(cpu_info_t *out)
{
	uint32_t r[4];
	uint32_t max_basic, max_ext = 0;
	memset(&g_info, 0, sizeof g_info);

	cpu_raw_cpuid(0, 0, r);
	max_basic = r[EAX];
#ifdef BUG_11
	memcpy(g_info.vendor + 0, &r[EBX], 4);
	memcpy(g_info.vendor + 4, &r[ECX], 4);
	memcpy(g_info.vendor + 8, &r[EDX], 4);
#else
	memcpy(g_info.vendor + 0, &r[EBX], 4);
	memcpy(g_info.vendor + 4, &r[EDX], 4);
	memcpy(g_info.vendor + 8, &r[ECX], 4);
#endif

	if (max_basic >= 1) {
		cpu_raw_cpuid(1, 0, r);
		uint32_t base_family = (r[EAX] >> 8) & 0xF;
		uint32_t base_model = (r[EAX] >> 4) & 0xF;
		uint32_t ext_model = (r[EAX] >> 16) & 0xF;
		uint32_t ext_family = (r[EAX] >> 20) & 0xFF;
		g_info.family = base_family == 0xF ? base_family + ext_family : base_family;
#ifdef BUG_6
		g_info.model = base_model;
		(void)ext_model;
#else
		g_info.model = (base_family == 6 || base_family == 0xF)
			? (ext_model << 4) | base_model : base_model;
#endif
#ifdef BUG_13
		g_info.stepping = r[EAX] & 0xFF;
#else
		g_info.stepping = r[EAX] & 0xF;
#endif
	}

	cpu_raw_cpuid(0x80000000u, 0, r);
	if ((r[EAX] & 0xFFFF0000u) == 0x80000000u)
		max_ext = r[EAX];

	for (int f = 0; f < CPU_FEAT__COUNT; f++) {
		uint32_t leaf = FEATURES[f].leaf;
#ifdef BUG_1
		bool readable = leaf >= 0x80000000u ? leaf <= max_ext : (leaf == 1 || leaf == 7 || leaf <= max_basic);
#elif defined(BUG_2)
		bool readable = leaf >= 0x80000000u ? max_ext != 0 : leaf <= max_basic;
#else
		bool readable = leaf >= 0x80000000u ? leaf <= max_ext : leaf <= max_basic;
#endif
		if (!readable)
			continue;
		cpu_raw_cpuid(leaf, FEATURES[f].sub, r);
		if (!(r[FEATURES[f].reg] >> FEATURES[f].bit & 1))
			continue;
		uint64_t mask;
		if (needs_os_state((cpu_feature_t)f, &mask) && !vector_state(mask))
			continue;
		g_info.features[f / 64] |= 1ull << (f % 64);
	}
#ifdef BUG_5
	if (!strcmp(g_info.vendor, "AuthenticAMD"))
		g_info.features[CPU_FEAT_FMA4 / 64] |= 1ull << (CPU_FEAT_FMA4 % 64);
#endif
	g_info.microcode = cpu_raw_microcode();

	char line[256];
	cpu_report(&g_info, line, sizeof line);
	cpu_raw_log(line);
	if (out)
		*out = g_info;
}

bool cpu_has(cpu_feature_t f)
{
#ifdef BUG_10
	/* no range check: an out-of-range feature reads past the array */
#else
	if ((int)f < 0 || f >= CPU_FEAT__COUNT)
		return false;
#endif
	return g_info.features[f / 64] >> (f % 64) & 1;
}

const cpu_info_t *cpu_info(void) { return &g_info; }

uint32_t cpu_report(const cpu_info_t *info, char *buf, uint32_t n)
{
	char tmp[256];
	int len = snprintf(tmp, sizeof tmp, "[CPU] %s fam %u model %u step %u ucode 0x%x:",
			   info->vendor, info->family, info->model, info->stepping, info->microcode);
	for (int f = 0; f < CPU_FEAT__COUNT; f++) {
		bool on = info->features[f / 64] >> (f % 64) & 1;
		if (on && len < (int)sizeof tmp - 24)
			len += snprintf(tmp + len, sizeof tmp - len, " %s", FEATURES[f].name);
	}
#ifdef BUG_12
	/* the line loses its microcode revision */
	char *u = strstr(tmp, " ucode");
	if (u) { char *c = strchr(u, ':'); memmove(u, c, strlen(c) + 1); len = (int)strlen(tmp); }
#endif
	if (n) {
		strncpy(buf, tmp, n - 1);
		buf[n - 1] = 0;
	}
	return (uint32_t)len;
}
