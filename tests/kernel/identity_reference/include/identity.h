/* The silicon identity record as specified in agent/kernel_spec/arch/hal.md
 * category 8. A generated kernel must provide exactly this. */
#ifndef AUTON_TEST_IDENTITY_H
#define AUTON_TEST_IDENTITY_H
#include <stdint.h>

typedef enum {
	IDENT_UNKNOWN  = 0,
	IDENT_READ     = 1,
	IDENT_FIRMWARE = 2,
} ident_source_t;

typedef struct silicon_identity {
	char     vendor[13];
	uint32_t family, model, stepping;
	uint64_t microcode_rev;
	char     brand[49];
	char     board_vendor[64], board_product[64];
	uint8_t  firmware_type;
	ident_source_t vendor_src, version_src, microcode_src, board_src;
} silicon_identity_t;

/* x86: fold CPUID.1:EAX into family/model/stepping per the rules in
 * arch/x86_64.md. `is_amd` selects the vendor's model-fold rule. */
void identity_fold_x86(uint32_t eax, int is_amd, silicon_identity_t *out);

/* Render the boot line. Shared by the boot report and the chat answer so the
 * two cannot disagree — see subsystems/dev.md. */
uint32_t identity_string(const silicon_identity_t *id, char *buf, uint32_t n);

#endif
