/* Seed SLM runtime: rule-engine backend only.
 * (Full neural backend + intent system is layered on later — see
 * kernel_spec/subsystems/slm.md.) */
#ifndef AUTON_SLM_H
#define AUTON_SLM_H

#include <stdint.h>
#include "boot_info.h"

/* Initialize the SLM runtime. Selects the rule-engine backend. Prints
 * "[SLM] Rule engine initialized". Returns 0 on success. */
int slm_init(const hw_summary_t *hw);

/* Return the active backend name ("rule-engine"). */
const char *slm_backend_name(void);

/* Recommend a driver for a PCI vendor:device pair, or NULL if unknown.
 * Rule-engine knowledge base (seed subset). */
const char *slm_driver_for_pci(uint16_t vendor, uint16_t device);

#endif /* AUTON_SLM_H */
