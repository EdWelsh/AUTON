/* Host test for silicon identity capture (H5).
 *
 * Two halves.
 *
 * The portable half validates the CPUID folding formula from
 * arch/x86_64.md against documented real parts. That formula is the single
 * thing in this specification most likely to be wrong, and getting it wrong
 * shifts every model number — an Alder Lake reading as model 7 instead of 151
 * matches a Pentium III's errata. It runs on any host, including the arm64 one
 * this was written on.
 *
 * The live half executes real CPUID and cross-checks against what the OS
 * reports for the same CPU. It runs only on x86 hosts, and says so when it
 * does not, rather than passing silently.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

#include "identity.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	if (cond) {
		printf("PASS  %-52s\n", name);
	} else {
		printf("FAIL  %-52s  %s\n", name, detail ? detail : "");
		fails = 1;
	}
}

/* Documented parts. EAX values are the architectural CPUID.1:EAX encodings;
 * family/model are what the vendor's own errata documents are indexed by. */
static const struct {
	const char *name;
	uint32_t eax;
	int is_amd;
	uint32_t family, model, stepping;
} VECTORS[] = {
	/* The fold matters: base model 7 + extended model 9 = 151. */
	{"Intel Alder Lake-S",     0x00090672, 0,  6, 151, 2},
	{"Intel Skylake-S",        0x000506E3, 0,  6,  94, 3},
	{"Intel Haswell",          0x000306C3, 0,  6,  60, 3},
	{"Intel Kaby Lake",        0x000906E9, 0,  6, 158, 9},
	/* Family 0xF folds the extended family as well. */
	{"AMD Zen 3 (Vermeer)",    0x00A20F10, 1, 25,  33, 0},
	{"AMD Zen 2 (Matisse)",    0x00870F10, 1, 23, 113, 0},
	/* No extended fields at all — and the part the whole hardware-truth PRD
	 * opens with. FDIV was a family 5 defect. */
	{"Intel Pentium (P5)",     0x00000525, 0,  5,   2, 5},
	/* Family 6 with extended model 0: folding must be a no-op, not a shift. */
	{"Intel Pentium Pro",      0x00000612, 0,  6,   1, 2},
};

static void test_folding(void)
{
	for (unsigned i = 0; i < sizeof VECTORS / sizeof VECTORS[0]; i++) {
		silicon_identity_t id;
		memset(&id, 0, sizeof id);
		identity_fold_x86(VECTORS[i].eax, VECTORS[i].is_amd, &id);

		char detail[160];
		snprintf(detail, sizeof detail,
		         "got family %u model %u stepping %u, wanted %u/%u/%u",
		         id.family, id.model, id.stepping,
		         VECTORS[i].family, VECTORS[i].model, VECTORS[i].stepping);
		ok(VECTORS[i].name,
		   id.family == VECTORS[i].family &&
		   id.model == VECTORS[i].model &&
		   id.stepping == VECTORS[i].stepping,
		   detail);
	}
}

static void test_unknown_is_not_zero(void)
{
	silicon_identity_t id;
	char buf[160];

	/* An architecture with no microcode MSR. */
	memset(&id, 0, sizeof id);
	strcpy(id.vendor, "ARM");
	id.vendor_src = IDENT_READ;
	id.family = 3401; id.model = 0; id.stepping = 1;
	id.microcode_src = IDENT_UNKNOWN;
	identity_string(&id, buf, sizeof buf);
	ok("an unread microcode revision renders as 'unknown'",
	   strstr(buf, "microcode unknown") != NULL, buf);

	/* A real reading that happens to be zero — an emulated CPU with no
	 * update applied. This is a fact, not an absence. */
	memset(&id, 0, sizeof id);
	strcpy(id.vendor, "GenuineIntel");
	id.vendor_src = IDENT_READ;
	id.microcode_src = IDENT_READ;
	id.microcode_rev = 0;
	identity_string(&id, buf, sizeof buf);
	ok("a microcode revision read as zero renders as '0x0'",
	   strstr(buf, "microcode 0x0") != NULL, buf);

	memset(&id, 0, sizeof id);
	identity_string(&id, buf, sizeof buf);
	ok("an unread vendor renders as 'unknown'",
	   strstr(buf, "[CPU] unknown ") != NULL, buf);
}

static void test_boot_line_matches_the_marker(void)
{
	/* The pattern in acceptance_tests.py SERIAL_MARKER_SETS["identity"]:
	 *   \[CPU\] \S+ family \d+ model \d+ stepping \d+ microcode (0x[0-9a-fA-F]+|unknown)
	 * Checked structurally here so the renderer and the marker cannot drift. */
	silicon_identity_t id;
	char buf[160];
	memset(&id, 0, sizeof id);
	strcpy(id.vendor, "GenuineIntel");
	id.vendor_src = IDENT_READ;
	identity_fold_x86(0x00090672, 0, &id);
	id.microcode_src = IDENT_READ;
	id.microcode_rev = 0x429;
	identity_string(&id, buf, sizeof buf);

	ok("boot line matches the identity marker shape",
	   strcmp(buf, "[CPU] GenuineIntel family 6 model 151 stepping 2 "
	               "microcode 0x429") == 0, buf);

	/* No embedded space in a vendor string: the marker uses \S+ for the
	 * vendor field, so "Genuine Intel" would break the assertion. */
	ok("vendor renders as a single token", strchr(id.vendor, ' ') == NULL, id.vendor);
}

#if defined(__x86_64__) || defined(__i386__)
#include <cpuid.h>

static void test_live_cpu(void)
{
	uint32_t a, b, c, d;
	if (!__get_cpuid(0, &a, &b, &c, &d)) {
		ok("live CPUID leaf 0", 0, "__get_cpuid failed");
		return;
	}
	char vendor[13];
	memcpy(vendor + 0, &b, 4);
	memcpy(vendor + 4, &d, 4);
	memcpy(vendor + 8, &c, 4);
	vendor[12] = '\0';

	__get_cpuid(1, &a, &b, &c, &d);
	silicon_identity_t id;
	memset(&id, 0, sizeof id);
	identity_fold_x86(a, strcmp(vendor, "AuthenticAMD") == 0, &id);
	strncpy(id.vendor, vendor, sizeof id.vendor - 1);
	id.vendor_src = IDENT_READ;

	printf("      live CPU: %s family %u model %u stepping %u\n",
	       vendor, id.family, id.model, id.stepping);

	ok("live vendor is one of the known strings",
	   strcmp(vendor, "GenuineIntel") == 0 ||
	   strcmp(vendor, "AuthenticAMD") == 0 ||
	   strcmp(vendor, "HygonGenuine") == 0, vendor);
	ok("live family is plausible", id.family >= 5 && id.family <= 0xFF, vendor);

	/* Cross-check against the OS's own view. A mismatch means the folding is
	 * wrong, which is worth catching before an errata table is keyed on it. */
	unsigned os_family = 0, os_model = 0;
	FILE *f = popen("sysctl -n machdep.cpu.family machdep.cpu.model 2>/dev/null"
	                " || awk -F': ' '/^cpu family/{print $2} /^model\\t/{print $2}'"
	                " /proc/cpuinfo 2>/dev/null | head -2", "r");
	if (f && fscanf(f, "%u %u", &os_family, &os_model) == 2) {
		char detail[128];
		snprintf(detail, sizeof detail, "kernel %u/%u vs OS %u/%u",
		         id.family, id.model, os_family, os_model);
		ok("folded family/model matches the OS's view",
		   id.family == os_family && id.model == os_model, detail);
	} else {
		printf("SKIP  %-52s  no OS CPU view available\n",
		       "cross-check against the OS");
	}
	if (f) pclose(f);
}
#else
static void test_live_cpu(void)
{
	printf("SKIP  %-52s  host is not x86; the folding vectors above\n",
	       "live CPUID cross-check");
	printf("      still validate the formula this specification requires.\n");
}
#endif

int main(void)
{
	printf("-- CPUID folding against documented parts --\n");
	test_folding();
	printf("\n-- unknown is not zero --\n");
	test_unknown_is_not_zero();
	printf("\n-- boot line --\n");
	test_boot_line_matches_the_marker();
	printf("\n-- live host --\n");
	test_live_cpu();

	printf(fails ? "\nIDENTITY: FAILURES\n" : "\nIDENTITY: ALL PASS\n");
	return fails;
}
