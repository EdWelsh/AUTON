/* System-information queries answered directly from runtime state, so the chat
 * can report the machine's IP, hostname, memory, devices, and uptime with no
 * terminal commands. */
#ifndef AUTON_SYSINFO_H
#define AUTON_SYSINFO_H

#include <stdint.h>
#include "pci.h"

/* Record boot-time facts the queries report. */
void sysinfo_init(uint32_t ram_mb, const pci_device_t *devs, uint32_t ndev);

/* If 'text' is a system query, write the answer into buf[0..cap) and return 1.
 * Returns 0 if the text is not a system query. */
int sysinfo_answer(const char *text, char *buf, uint32_t cap);

/* Current hostname (default "auton"). */
const char *sysinfo_hostname(void);

#endif /* AUTON_SYSINFO_H */
