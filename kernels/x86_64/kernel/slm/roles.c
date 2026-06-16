/* Capability/role registry (see roles.h). Each capability has a trigger
 * keyword, a human name, a status, an explanatory note, and — when it works
 * today — an action that runs it on the in-kernel network stack. */
#include "roles.h"
#include "kstr.h"
#include "server.h"
#include "net.h"
#include "kernel.h"

typedef enum { CAP_WORKING, CAP_ROADMAP } cap_status_t;

typedef struct capability {
	const char  *keyword;       /* trigger word (lowercase) */
	const char  *name;          /* display name */
	cap_status_t status;
	const char  *note;          /* what it does / what it needs */
	void       (*action)(void); /* run it (CAP_WORKING only) */
} capability_t;

/* Order matters only for matching precedence; listing de-dupes by name. */
static const capability_t caps[] = {
	{ "web",      "web server",      CAP_WORKING, "in-kernel HTTP on port 80",                         http_server_run },
	{ "http",     "web server",      CAP_WORKING, "in-kernel HTTP on port 80",                         http_server_run },
	{ "dns",      "DNS server",      CAP_WORKING, "answers A queries on port 53 with this host's IP",  dns_server_run  },
	{ "file",     "file server",     CAP_ROADMAP, "needs a filesystem; would serve a docroot over HTTP", 0 },
	{ "email",    "email server",    CAP_ROADMAP, "needs SMTP/IMAP and mail storage",                  0 },
	{ "mail",     "email server",    CAP_ROADMAP, "needs SMTP/IMAP and mail storage",                  0 },
	{ "smtp",     "email server",    CAP_ROADMAP, "needs SMTP/IMAP and mail storage",                  0 },
	{ "database", "database server", CAP_ROADMAP, "needs persistent storage and a query engine",       0 },
	{ "sql",      "database server", CAP_ROADMAP, "needs persistent storage and a query engine",       0 },
	{ "ssh",      "SSH server",      CAP_ROADMAP, "needs crypto (key exchange, ciphers) and a PTY",    0 },
	{ "dhcp",     "DHCP server",     CAP_ROADMAP, "this host is a DHCP client; serving leases is next", 0 },
};
#define NCAPS ((int)(sizeof(caps) / sizeof(caps[0])))

static int has_action_verb(const char *t)
{
	return ks_contains(t, "be ") || ks_contains(t, "set up") ||
	       ks_contains(t, "setup") || ks_contains(t, "start") ||
	       ks_contains(t, "run ") || ks_contains(t, "make") ||
	       ks_contains(t, "become") || ks_contains(t, "turn") ||
	       ks_contains(t, "serve") || ks_contains(t, "enable") ||
	       ks_contains(t, "host") || ks_contains(t, "configure") ||
	       ks_contains(t, "act as") || ks_contains(t, "can you");
}

static int is_question(const char *t)
{
	return ks_contains(t, "what") || ks_contains(t, "how") ||
	       ks_contains(t, "why") || ks_contains(t, "explain");
}

static const capability_t *match(const char *t)
{
	for (int i = 0; i < NCAPS; i++)
		if (ks_contains(t, caps[i].keyword))
			return &caps[i];
	return 0;
}

static void list_roles(void)
{
	char line[96];

	kprintf("I can turn this machine into a server role from chat:\n");
	for (int i = 0; i < NCAPS; i++) {
		/* De-dupe aliases that share a display name. */
		int seen = 0;
		for (int j = 0; j < i; j++)
			if (kstrcmp(caps[j].name, caps[i].name) == 0)
				seen = 1;
		if (seen)
			continue;
		uint32_t p = 0;
		p = ks_append(line, sizeof(line), p, "  ");
		p = ks_append(line, sizeof(line), p, caps[i].name);
		p = ks_append(line, sizeof(line), p,
			      caps[i].status == CAP_WORKING ? " - ready" : " - roadmap");
		kprintf("%s\n", line);
	}
	kprintf("Also ask: what is my ip, hostname, memory, devices, uptime, status.\n");
}

int roles_dispatch(const char *t)
{
	if (ks_contains(t, "list role") || ks_contains(t, "what roles") ||
	    ks_contains(t, "what can you do") || ks_contains(t, "what can you be") ||
	    ks_contains(t, "capabilit")) {
		list_roles();
		return 1;
	}

	const capability_t *c = match(t);
	if (!c)
		return 0;

	/* A genuine question about a role (no command verb) is not a command. */
	if (is_question(t) && !has_action_verb(t))
		return 0;

	if (c->status == CAP_WORKING && c->action) {
		if (!net_is_up()) {
			kprintf("Networking is not up yet, so I can't start the %s.\n",
				c->name);
			return 1;
		}
		kprintf("Configuring this machine as a %s (%s)...\n", c->name, c->note);
		c->action();           /* blocks, serving, until a key is pressed */
		return 1;
	}

	kprintf("Role '%s': roadmap - %s. I recognize the request and will run "
		"it once that subsystem exists.\n", c->name, c->note);
	return 1;
}
