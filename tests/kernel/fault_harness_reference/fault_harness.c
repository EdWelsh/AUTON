/* Reference for the expected-fault state machine (see include/fault_harness.h).
 * NOT kernel code and NOT shipped. */
#include "fault_harness.h"

static int armed_vector = FH_NO_VECTOR;
static void *armed_resume;
static int taken;
static int in_handler;
static fh_event_t last;

void fh_reset(void)
{
	armed_vector = FH_NO_VECTOR;
	armed_resume = 0;
	taken = 0;
	in_handler = 0;
	last = (fh_event_t){FH_NO_VECTOR, 0, 0};
}

int fh_in_handler(void)
{
	return in_handler;
}

void fh_enter_handler(void)
{
	in_handler = 1;
}

void fh_leave_handler(void)
{
	in_handler = 0;
}

int arch_expect_fault(int vec, void *resume_rip)
{
	int previous = armed_vector;
	/* Rule 4: arming inside a handler cannot be resumed correctly. */
	if (in_handler)
		return FH_NO_VECTOR;
	armed_vector = vec;
	armed_resume = resume_rip;
	return previous;
}

int arch_fault_taken(void)
{
	int v = taken;
	taken = 0;                      /* cleared by reading */
	return v;
}

fh_action_t fh_on_fault(int vec, uint64_t rip, void **resume_out, fh_event_t *out)
{
	fh_event_t ev = {vec, rip, 0};

	/* Rule 2: the VECTOR decides. A different fault than the one armed is
	 * unexpected, however plausible it looks. */
	if (armed_vector != FH_NO_VECTOR && vec == armed_vector) {
		ev.expected = 1;
		last = ev;
		if (out)
			*out = ev;
		if (resume_out)
			*resume_out = armed_resume;
		/* Rule 3: the expectation is spent. A second fault at the same place
		 * halts instead of looping forever. */
		armed_vector = FH_NO_VECTOR;
		armed_resume = 0;
		taken = 1;
		return FH_RESUMED;
	}

	/* Rule 1: an unexpected fault still halts. Arming one vector must never
	 * make the kernel one that swallows faults. */
	last = ev;
	if (out)
		*out = ev;
	return FH_HALTED;
}

const fh_event_t *fh_last_event(void)
{
	return &last;
}
