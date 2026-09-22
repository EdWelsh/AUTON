/* Host suite for the in-kernel fault harness (x86_64.md, "Expected Faults").
 *
 * The rule this exists to protect: arming one expected fault must not turn the
 * kernel into one that swallows faults. Every other check here is a way that
 * could happen by accident.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "fault_harness.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-62s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

#define UD 6
#define GP 13

int main(void)
{
	void *resume = (void *)0xDEAD1000;
	void *got = NULL;
	fh_event_t ev;

	/* --- the armed fault resumes ---------------------------------------- */
	fh_reset();
	arch_expect_fault(UD, resume);
	ok("an armed #UD resumes at the given rip",
	   fh_on_fault(UD, 0x1234, &got, &ev) == FH_RESUMED && got == resume, NULL);
	ok("and it is recorded as expected", ev.expected == 1 && ev.vector == UD, NULL);
	ok("the faulting rip is recorded", ev.rip == 0x1234,
	   "a verdict must say what faulted, not only that something did");
	ok("arch_fault_taken reports it", arch_fault_taken() == 1, NULL);
	ok("and clears on reading", arch_fault_taken() == 0, NULL);

	/* --- rule 1: an unexpected fault still halts -------------------------- */
	fh_reset();
	ok("an unexpected fault halts", fh_on_fault(GP, 0x2000, &got, &ev) == FH_HALTED,
	   "a kernel that swallows faults turns every future bug into silence");
	ok("and is recorded as unexpected", ev.expected == 0 && ev.vector == GP, NULL);

	/* --- rule 2: the VECTOR decides -------------------------------------- */
	fh_reset();
	arch_expect_fault(UD, resume);
	ok("a #GP while #UD is armed still halts",
	   fh_on_fault(GP, 0x3000, &got, &ev) == FH_HALTED,
	   "the vector decides, not how plausible the fault looks");
	ok("the armed expectation survives the unrelated fault",
	   fh_on_fault(UD, 0x3004, &got, &ev) == FH_RESUMED, NULL);

	/* --- rule 3: the expectation is spent once ---------------------------- */
	fh_reset();
	arch_expect_fault(UD, resume);
	fh_on_fault(UD, 0x4000, &got, &ev);
	ok("a second fault at the same place halts rather than looping",
	   fh_on_fault(UD, 0x4000, &got, &ev) == FH_HALTED,
	   "resuming twice is an infinite loop, not a test result");

	/* --- rule 4: no arming inside a handler ------------------------------- */
	fh_reset();
	fh_enter_handler();
	ok("arming inside a handler is refused",
	   arch_expect_fault(UD, resume) == FH_NO_VECTOR, NULL);
	ok("and nothing is armed as a side effect",
	   fh_on_fault(UD, 0x5000, &got, &ev) == FH_HALTED, NULL);
	fh_leave_handler();

	/* --- arming nests ----------------------------------------------------- */
	fh_reset();
	arch_expect_fault(UD, resume);
	ok("arming returns the previous vector so it can be restored",
	   arch_expect_fault(GP, resume) == UD, NULL);
	ok("disarming with -1 leaves nothing armed",
	   arch_expect_fault(FH_NO_VECTOR, NULL) == GP &&
	   fh_on_fault(GP, 0x6000, &got, &ev) == FH_HALTED, NULL);

	/* --- the record a verdict reads --------------------------------------- */
	fh_reset();
	arch_expect_fault(UD, resume);
	fh_on_fault(UD, 0x7000, &got, &ev);
	ok("the last event is readable after the fact",
	   fh_last_event()->rip == 0x7000 && fh_last_event()->expected == 1, NULL);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
