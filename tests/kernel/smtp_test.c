/* Host suite for the SMTP service (agent/kernel_spec/services/smtp.md).
 *
 * The state machine, the limits and their codes, relay refusal, dot-stuffing
 * both ways, and sequence recovery. The two failures worth naming:
 *
 *   - a terminator detected by "contains a dot" truncates a message and reads
 *     the rest of it as commands;
 *   - a sequence that restarts at 1 overwrites the mail that survived the
 *     reboot, which is the only thing this service claims to do.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "smtp.h"

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

static smtp_store_t store;
static char out[512];

/* Send one line; returns the reply as a NUL-terminated string (empty for data). */
static const char *say(const char *line)
{
	static char reply[512];
	int n = smtp_handle(line, (uint32_t)strlen(line), out, sizeof out);
	if (n > 0) {
		memcpy(reply, out, (size_t)n);
		reply[n] = 0;
	} else {
		reply[0] = 0;
	}
	return reply;
}

static int code(const char *line)
{
	const char *r = say(line);
	return r[0] ? atoi(r) : 0;
}

static void session(void)
{
	smtp_reset(&store, "auton.local", 0);
	say("EHLO client.example");
}

int main(void)
{
	/* --- the happy path --------------------------------------------------- */
	session();
	ok("EHLO is answered with our domain",
	   strncmp(say("EHLO client.example"), "250 auton.local", 15) == 0, NULL);
	ok("MAIL FROM is accepted", code("MAIL FROM:<sender@example.com>") == 250, NULL);
	ok("RCPT for our domain is accepted", code("RCPT TO:<you@auton.local>") == 250, NULL);
	ok("DATA is answered 354", code("DATA") == 354, NULL);
	say("Subject: hello");
	say("");
	say("body line");
	ok("the terminator stores the message and answers 250",
	   code(".") == 250 && store.count == 1, NULL);
	ok("it is named /MAIL/M0000001.EML",
	   strcmp(store.name[0], "/MAIL/M0000001.EML") == 0, store.name[0]);
	ok("250 comes only after a flush", store.flushes == 1,
	   "a 250 is a promise, and a client that gets one deletes its copy");

	/* --- sequence, and the reboot that must not overwrite ----------------- */
	{
		const char *listing[] = {"M0000001.EML", "M0000007.EML", "M0000003.EML",
		                         "NOTMAIL.TXT"};
		ok("the sequence is recovered from a directory listing",
		   smtp_scan_highest(listing, 4) == 7, NULL);
		const char *empty[] = {"NOTMAIL.TXT"};
		ok("an empty mail directory starts at zero",
		   smtp_scan_highest(empty, 1) == 0, NULL);
		smtp_reset(&store, "auton.local", 7);
		ok("after a reboot the next message continues the sequence",
		   smtp_next_seq() == 8,
		   "restarting at 1 overwrites the mail that survived the reboot");
	}

	/* --- order ------------------------------------------------------------ */
	session();
	ok("RCPT before MAIL is 503", code("RCPT TO:<you@auton.local>") == 503, NULL);
	ok("DATA before RCPT is 503", code("DATA") == 503, NULL);
	say("MAIL FROM:<a@example.com>");
	ok("MAIL twice is 503", code("MAIL FROM:<b@example.com>") == 503, NULL);
	ok("DATA still needs a recipient", code("DATA") == 503, NULL);
	ok("an unknown command is 500", code("FROB nothing") == 500, NULL);

	/* --- relaying --------------------------------------------------------- */
	session();
	say("MAIL FROM:<a@example.com>");
	ok("a foreign domain is refused",
	   code("RCPT TO:<someone@elsewhere.example>") == 550,
	   "this server never sends mail; accepting it would be a lie");
	ok("an address with no @ is refused", code("RCPT TO:<postmaster>") == 550, NULL);
	ok("our domain in another case is accepted",
	   code("RCPT TO:<you@AUTON.LOCAL>") == 250, "domains are case-insensitive");

	/* --- limits ----------------------------------------------------------- */
	session();
	say("MAIL FROM:<a@example.com>");
	for (int i = 0; i < SMTP_MAX_RCPT; i++)
		say("RCPT TO:<you@auton.local>");
	ok("the seventeenth recipient is 452",
	   code("RCPT TO:<you@auton.local>") == 452, NULL);
	{
		char big[SMTP_MAX_LINE + 64];
		memset(big, 'a', sizeof big);
		memcpy(big, "NOOP ", 5);
		big[sizeof big - 1] = 0;
		session();
		ok("an over-long line is 500", code(big) == 500, NULL);
	}

	/* --- dot-stuffing ------------------------------------------------------ */
	session();
	say("MAIL FROM:<a@example.com>");
	say("RCPT TO:<you@auton.local>");
	say("DATA");
	say("..stuffed");
	say("a line with a . inside it");
	say("plain");
	ok("the message ends at a line that is exactly a dot", code(".") == 250, NULL);
	{
		const char *want = ".stuffed\r\na line with a . inside it\r\nplain\r\n";
		ok("the stuffing dot is removed and the dotted line survived",
		   store.count == 1 && store.len[0] == strlen(want) &&
		   memcmp(store.body[0], want, strlen(want)) == 0,
		   "a substring terminator truncates the mail and reads the rest as commands");
	}

	/* --- oversize stores nothing ------------------------------------------ */
	{
		session();
		say("MAIL FROM:<a@example.com>");
		say("RCPT TO:<you@auton.local>");
		say("DATA");
		char chunk[1024];
		memset(chunk, 'x', sizeof chunk - 1);
		chunk[sizeof chunk - 1] = 0;
		for (int i = 0; i < 1100; i++)     /* > 1 MiB */
			say(chunk);
		ok("an oversize message is 552", code(".") == 552, NULL);
		ok("and nothing is stored", store.count == 0,
		   "a truncated message that looks like a message is worse than none");
	}

	/* --- RSET and QUIT ----------------------------------------------------- */
	session();
	say("MAIL FROM:<a@example.com>");
	say("RCPT TO:<you@auton.local>");
	ok("RSET is accepted", code("RSET") == 250, NULL);
	ok("and the transaction is gone", code("DATA") == 503, NULL);
	session();
	say("MAIL FROM:<a@example.com>");
	say("RCPT TO:<you@auton.local>");
	ok("QUIT before DATA says 221", code("QUIT") == 221, NULL);
	ok("and stores nothing", store.count == 0, NULL);

	/* Inside DATA every line is data, including one that looks like a command.
	 * A server that honours commands there can be made to truncate a message
	 * by its own contents (RFC 5321 4.1.1.4). */
	session();
	say("MAIL FROM:<a@example.com>");
	say("RCPT TO:<you@auton.local>");
	say("DATA");
	ok("QUIT inside DATA is body text, not a command", say("QUIT")[0] == 0,
	   "honouring it would let a message truncate itself");
	say("still the body");
	code(".");
	{
		const char *want = "QUIT\r\nstill the body\r\n";
		ok("and it is stored as part of the message",
		   store.count == 1 && store.len[0] == strlen(want) &&
		   memcmp(store.body[0], want, strlen(want)) == 0, NULL);
	}

	/* --- a null reverse-path is legal (a bounce) --------------------------- */
	session();
	ok("MAIL FROM:<> is accepted", code("MAIL FROM:<>") == 250,
	   "a bounce has a null reverse-path (RFC 5321 4.5.5)");

	/* --- an unwritable volume --------------------------------------------- */
	session();
	store.writable = 0;
	say("MAIL FROM:<a@example.com>");
	say("RCPT TO:<you@auton.local>");
	say("DATA");
	say("body");
	ok("an unwritable volume refuses rather than claiming 250",
	   code(".") == 452 && store.count == 0, NULL);

	/* Release what the last case stored. The reference holds message bodies
	 * for the life of the process, and smtp_reset is what drops them, so
	 * without this the final store survives to exit. LeakSanitizer reports
	 * that, and it runs under ASan on Linux but not on Darwin — which is why
	 * this suite was green on every machine here and red in CI. */
	smtp_reset(&store, NULL, 0);

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
