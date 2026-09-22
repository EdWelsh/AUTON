/* The in-kernel fault harness's state machine, as specified in
 * agent/kernel_spec/arch/x86_64.md ("Expected Faults").
 *
 * The state machine is host-provable; the IDT is not. What is tested here is
 * exactly the part that decides whether a kernel swallows faults, which is the
 * part worth getting right before any of it runs on hardware.
 *
 * NOT kernel code and NOT shipped. */
#ifndef AUTON_FAULT_HARNESS_H
#define AUTON_FAULT_HARNESS_H

#include <stdint.h>

#define FH_NO_VECTOR   (-1)

typedef struct fh_event {
	int      vector;
	uint64_t rip;
	int      expected;      /* 1 armed, 0 not: the record a verdict needs */
} fh_event_t;

typedef enum {
	FH_RESUMED,             /* the armed fault arrived; resume at resume_rip */
	FH_HALTED,              /* unexpected: the kernel halts, as it always did */
	FH_REFUSED,             /* arming was not allowed (inside a handler) */
} fh_action_t;

void       fh_reset(void);
int        arch_expect_fault(int vec, void *resume_rip);   /* returns the previous */
int        arch_fault_taken(void);                          /* clears on read */

/* One fault arrives. Returns what the kernel does, and fills `out` with the
 * record the harness keeps. */
fh_action_t fh_on_fault(int vec, uint64_t rip, void **resume_out, fh_event_t *out);

/* The last event, for a verdict line. */
const fh_event_t *fh_last_event(void);

/* Whether a fault is currently being serviced (rule 4's guard). */
int fh_in_handler(void);
void fh_enter_handler(void);
void fh_leave_handler(void);

#endif
