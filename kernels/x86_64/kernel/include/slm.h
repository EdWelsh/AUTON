/* Seed SLM runtime: rule-engine backend only.
 * (Full neural backend + intent system is layered on later — see
 * kernel_spec/subsystems/slm.md.) */
#ifndef AUTON_SLM_H
#define AUTON_SLM_H

#include <stdint.h>
#include "boot_info.h"

/* Intent classes the rule engine recognizes (subset of slm.md contract). */
typedef enum slm_intent {
	SLM_INTENT_HARDWARE_IDENTIFY = 0,   /* "what is this PCI device?" */
	SLM_INTENT_DRIVER_SELECT     = 1,   /* "which driver for this NIC?" */
	SLM_INTENT_INSTALL_CONFIGURE = 2,   /* "set up networking" */
	SLM_INTENT_APP_INSTALL       = 3,   /* "install a web server" */
	SLM_INTENT_SYSTEM_MANAGE     = 4,   /* "check memory usage" */
	SLM_INTENT_TROUBLESHOOT      = 5,   /* "why is the network down?" */
	SLM_INTENT_COUNT             = 6,
} slm_intent_t;

/* Result of processing a query. Layout mirrors slm.md:slm_intent_result_t
 * so the neural backend can fill the same struct without contract drift. */
typedef struct slm_intent_result {
	slm_intent_t intent;
	int32_t      status;            /* 0=success, negative=error */
	char         response[2048];    /* human-readable response text */
	uint32_t     response_len;
	char         action_data[1024]; /* machine-parseable action data */
	uint32_t     action_data_len;
	int          requires_followup; /* 1 if multi-step, more actions needed */
} slm_intent_result_t;

/* Initialize the SLM runtime. Selects the rule-engine backend. Prints
 * "[SLM] Rule engine initialized". Returns 0 on success. */
int slm_init(const hw_summary_t *hw);

/* Return the active backend name ("rule-engine"). */
const char *slm_backend_name(void);

/* Recommend a driver for a PCI vendor:device pair, or NULL if unknown.
 * Rule-engine knowledge base (seed subset). */
const char *slm_driver_for_pci(uint16_t vendor, uint16_t device);

/* Classify free-form text into an intent. */
slm_intent_t slm_classify_intent(const char *text, uint32_t text_len);

/* Process a free-form text query (e.g., from the console). Classifies the
 * intent, answers from the knowledge base, and fills 'result'. Returns 0 on
 * success. Dispatches to the active backend (rule engine in Stage 1). */
int slm_process_text(const char *text, uint32_t text_len,
		     slm_intent_result_t *result);

/* Interactive chat REPL over the serial console. Prints a banner and an
 * 'auton> ' prompt, reads a line, answers via slm_process_text, and loops.
 * Returns when the user types 'quit'/'exit'. */
void slm_chat_loop(void);

#endif /* AUTON_SLM_H */
