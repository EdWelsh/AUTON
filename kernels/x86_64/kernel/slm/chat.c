/* Interactive chat REPL. The OS *is* the conversational interface: this loop
 * is what the user reaches after boot. It reads a line from the serial console
 * and routes it: system queries -> server roles -> the rule-engine fallback. */
#include "slm.h"
#include "console.h"
#include "sysinfo.h"
#include "roles.h"
#include "kernel.h"

#define LINE_MAX 256

static void print_help(void)
{
	kprintf("Commands:\n");
	kprintf("  help                 show this help\n");
	kprintf("  quit / exit          leave the chat (halts)\n");
	kprintf("  what can you do      list the server roles I can run\n");
	kprintf("Ask in plain language, e.g.:\n");
	kprintf("  what is my ip / hostname / memory / devices / uptime / status\n");
	kprintf("  be a web server          (also: dns server)\n");
	kprintf("  set hostname web1\n");
	kprintf("  what is pci 8086:100e\n");
}

void slm_chat_loop(void)
{
	/* response[] is 2 KB; keep the result off the limited kernel stack. */
	static slm_intent_result_t result;
	static char line[LINE_MAX];

	kprintf("AUTON. Type a request, or 'help'. On-device assistant.\n");

	for (;;) {
		kprintf("auton> ");
		uint32_t len = console_readline(line, sizeof(line));

		if (len == 0)
			continue;       /* empty line: re-prompt */

		if (kstrcmp(line, "help") == 0) {
			print_help();
			continue;
		}
		if (kstrcmp(line, "quit") == 0 || kstrcmp(line, "exit") == 0) {
			kprintf("Goodbye.\n");
			return;
		}

		/* System queries (ip, hostname, memory, devices, uptime, status). */
		if (sysinfo_answer(line, result.response, sizeof(result.response))) {
			kprintf("%s\n", result.response);
			continue;
		}

		/* Server-role control plane ("be a web server", "what can you do"). */
		if (roles_dispatch(line))
			continue;

		/* Rule-engine fallback (hardware identify, driver select, etc.). */
		slm_process_text(line, len, &result);
		kprintf("%s\n", result.response);
	}
}
