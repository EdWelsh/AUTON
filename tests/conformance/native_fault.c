/* Venue 1, fault: does an encoding the manual guarantees raises #UD actually
 * fault, and does the process survive it?
 *
 *   native_fault <faults.txt>      # lines: <id> <hex bytes> <expect UD|none> <guarantee>
 *
 * x86-64 only; elsewhere it prints SKIP. The bytes are executed from a
 * writable, executable mapping, with SIGILL caught by sigsetjmp/siglongjmp.
 *
 * An entry marked `model-specific` can never fail the chip: it is reported as
 * not-assertable. Only `architectural` entries can. That asymmetry is the
 * difference between a conformance suite and an accusation.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include <stdlib.h>

/* Linux only. On macOS/Apple Silicon a W^X page needs MAP_JIT and the
 * pthread_jit_write_protect dance; without it EVERY execution faults, which
 * made the guaranteed-#UD entries "pass" for the wrong reason. The control
 * entry below caught that, and this guard makes the platform limit explicit
 * rather than leaving the control to discover it every run. */
#if defined(__x86_64__) && defined(__linux__)
#include <setjmp.h>
#include <signal.h>
#include <sys/mman.h>

static sigjmp_buf jump;
static volatile sig_atomic_t caught;

static void on_sigill(int sig)
{
	(void)sig;
	caught = 1;
	siglongjmp(jump, 1);
}

/* Execute `bytes` followed by RET. Returns 1 if it raised #UD, 0 if it ran. */
static int faults(const uint8_t *bytes, size_t n)
{
	size_t page = 4096;
	uint8_t *code = mmap(NULL, page, PROT_READ | PROT_WRITE,
	                     MAP_PRIVATE | MAP_ANONYMOUS, -1, 0);
	if (code == MAP_FAILED) {
		perror("mmap");
		exit(2);
	}
	memcpy(code, bytes, n);
	code[n] = 0xC3;                     /* ret */
	if (mprotect(code, page, PROT_READ | PROT_EXEC) != 0) {
		perror("mprotect");
		exit(2);
	}

	struct sigaction sa = {0}, old;
	sa.sa_handler = on_sigill;
	sigemptyset(&sa.sa_mask);
	sigaction(SIGILL, &sa, &old);

	caught = 0;
	if (sigsetjmp(jump, 1) == 0) {
		void (*fn)(void) = (void (*)(void))code;
		fn();
	}
	sigaction(SIGILL, &old, NULL);
	munmap(code, page);
	return caught;
}

static size_t unhex(const char *hex, uint8_t *out, size_t cap)
{
	size_t n = 0;
	for (const char *p = hex; p[0] && p[1] && n < cap; p += 2) {
		unsigned v;
		if (sscanf(p, "%2x", &v) != 1)
			return 0;
		out[n++] = (uint8_t)v;
	}
	return n;
}

int main(int argc, char **argv)
{
	if (argc != 2) {
		fprintf(stderr, "usage: native_fault <faults.txt>\n");
		return 2;
	}
	FILE *f = fopen(argv[1], "r");
	if (!f) {
		perror("open");
		return 2;
	}

	char id[128], hex[64], expect[16], guarantee[32];
	int checked = 0, diverged = 0, not_assertable = 0;

	/* The control first: a plain NOP must execute. If it faults, this host
	 * cannot run bytes at all, and every "#UD as guaranteed" below would be a
	 * pass for the wrong reason. A harness that cannot tell those apart must
	 * report nothing. */
	{
		const uint8_t nop = 0x90;
		if (faults(&nop, 1)) {
			printf("SKIP fault: the control (a plain NOP) faulted, so this host "
			       "cannot execute test bytes; no fault verdict is reportable.\n");
			printf("SUMMARY fault checked=0 diverged=0 not-assertable=0 skipped=1\n");
			return 0;
		}
	}

	while (fscanf(f, "%127s %63s %15s %31s", id, hex, expect, guarantee) == 4) {
		uint8_t bytes[32];
		size_t n = unhex(hex, bytes, sizeof bytes - 1);
		if (n == 0) {
			fprintf(stderr, "%s: bad bytes %s\n", id, hex);
			return 2;
		}
		int did = faults(bytes, n);
		int want = !strcmp(expect, "UD");
		int architectural = !strcmp(guarantee, "architectural");
		checked++;
		if (did == want) {
			printf("OK %s %s\n", id, did ? "faulted" : "executed");
		} else if (!architectural) {
			printf("NOT-ASSERTABLE %s wanted %s, %s\n", id, expect,
			       did ? "faulted" : "executed");
			not_assertable++;
		} else {
			printf("DIVERGE %s wanted %s, %s\n", id, expect,
			       did ? "faulted" : "executed");
			diverged++;
		}
	}
	printf("SUMMARY fault checked=%d diverged=%d not-assertable=%d\n",
	       checked, diverged, not_assertable);
	return diverged ? 1 : 0;
}

#else

int main(int argc, char **argv)
{
	(void)argc;
	(void)argv;
	printf("SKIP fault: needs x86-64 with POSIX signals; this host is not that.\n");
	printf("SUMMARY fault checked=0 diverged=0 not-assertable=0 skipped=1\n");
	return 0;
}

#endif
