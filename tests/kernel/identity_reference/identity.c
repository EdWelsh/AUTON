/* Reference implementation of the identity folding and rendering specified in
 * agent/kernel_spec/arch/x86_64.md and subsystems/dev.md.
 *
 * NOT kernel code and not shipped. It exists so identity_test.c can be proved
 * correct, and so the specification's folding formula is executable rather than
 * prose — the formula is the single thing in H5 most likely to be wrong, and
 * getting it wrong shifts every errata lookup by a whole model number.
 */
#include <stdint.h>
#include <stdio.h>
#include <string.h>
#include "identity.h"

void identity_fold_x86(uint32_t eax, int is_amd, silicon_identity_t *out)
{
	uint32_t base_family = (eax >> 8)  & 0xF;
	uint32_t base_model  = (eax >> 4)  & 0xF;
	uint32_t ext_family  = (eax >> 20) & 0xFF;
	uint32_t ext_model   = (eax >> 16) & 0xF;

	out->family = (base_family == 0xF) ? base_family + ext_family : base_family;

	/* Intel folds the extended model for family 6 as well as 0xF; AMD only
	 * for 0xF. AMD's family 6 parts (K7) all carry ext_model 0, so folding
	 * there would be harmless — but the rule is written per vendor because
	 * "harmless today" is not a specification. */
	int fold_model = (base_family == 0xF) || (!is_amd && base_family == 6);
	out->model = fold_model ? base_model + (ext_model << 4) : base_model;

	out->stepping = eax & 0xF;
	out->version_src = IDENT_READ;
}

uint32_t identity_string(const silicon_identity_t *id, char *buf, uint32_t n)
{
	char micro[24];
	/* `unknown` and `0x0` are different statements: one says nobody looked,
	 * the other says the machine carries no microcode update. An errata
	 * lookup that conflates them reports a patched machine as vulnerable. */
	if (id->microcode_src == IDENT_UNKNOWN)
		snprintf(micro, sizeof micro, "unknown");
	else
		snprintf(micro, sizeof micro, "0x%llx",
		         (unsigned long long)id->microcode_rev);

	const char *vendor = (id->vendor_src == IDENT_UNKNOWN || !id->vendor[0])
		? "unknown" : id->vendor;

	int w = snprintf(buf, n, "[CPU] %s family %u model %u stepping %u microcode %s",
	                 vendor, id->family, id->model, id->stepping, micro);
	return (w < 0) ? 0 : (uint32_t)((uint32_t)w < n ? (uint32_t)w : n - 1);
}
