/* Interactive chat REPL. The OS *is* the conversational interface: this loop
 * is what the user reaches after boot. It reads a line from the serial
 * console, routes it through the active SLM backend, and prints the reply. */
#include "slm.h"
#include "console.h"
#include "server.h"
#include "net.h"
#include "kernel.h"

#define LINE_MAX 256

static void print_help(void)
{
	kprintf("Commands:\n");
	kprintf("  help                 show this help\n");
	kprintf("  quit / exit          leave the chat (halts)\n");
	kprintf("Ask in plain language, e.g.:\n");
	kprintf("  what is my ip\n");
	kprintf("  what is pci 8086:100e\n");
	kprintf("  which driver for 1af4:1000\n");
	kprintf("  be a web server\n");
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

		/* Action: turn this machine into a web server. */
		if (slm_is_web_server_request(line)) {
			if (!net_is_up()) {
				kprintf("Networking is not up yet, so I can't "
					"start a web server.\n");
				continue;
			}
			kprintf("Configuring this machine as a web server...\n");
			http_server_run();
			continue;
		}

		slm_process_text(line, len, &result);
		kprintf("%s\n", result.response);
	}
}
