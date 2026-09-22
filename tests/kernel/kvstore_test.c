/* Host suite for the KV store service (agent/kernel_spec/services/kvstore.md).
 *
 * What a host can prove without a NIC or a disk: the RESP2 parser (including a
 * frame split across reads, which is where a parser that assumes TCP preserves
 * message boundaries fails), the command semantics, every limit's refusal, and
 * the log's replay — in particular that a torn final record costs the last
 * write and not the store.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "kvstore.h"

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

static uint8_t log_bytes[64 * 1024];
static kv_log_t log;
static uint8_t out[8192];

static void fresh(void)
{
	log.bytes = log_bytes;
	log.cap = sizeof log_bytes;
	log.len = 0;
	log.pending = 0;
	log.flushes = 0;
	kv_reset(&log);
}

/* Feed one request; returns the reply as a NUL-terminated string in `buf`. */
static int request(const char *req, char *buf, size_t cap)
{
	uint32_t consumed = 0;
	int n = kv_handle((const uint8_t *)req, (uint32_t)strlen(req), out, sizeof out,
	                  &consumed, &log);
	if (n > 0) {
		size_t k = (size_t)n < cap - 1 ? (size_t)n : cap - 1;
		memcpy(buf, out, k);
		buf[k] = 0;
	} else {
		buf[0] = 0;
	}
	return n;
}

int main(void)
{
	char r[8192];

	/* --- inline and array forms ---------------------------------------- */
	fresh();
	request("PING\r\n", r, sizeof r);
	ok("an inline PING is answered", strcmp(r, "+PONG\r\n") == 0, r);
	request("*1\r\n$4\r\nPING\r\n", r, sizeof r);
	ok("an array PING is answered", strcmp(r, "+PONG\r\n") == 0, r);
	request("*1\r\n$4\r\nping\r\n", r, sizeof r);
	ok("commands are case-insensitive", strcmp(r, "+PONG\r\n") == 0, r);

	/* --- set, get, del -------------------------------------------------- */
	request("*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$5\r\nhello\r\n", r, sizeof r);
	ok("SET replies +OK", strcmp(r, "+OK\r\n") == 0, r);
	request("*2\r\n$3\r\nGET\r\n$1\r\nk\r\n", r, sizeof r);
	ok("GET returns the value as a bulk string", strcmp(r, "$5\r\nhello\r\n") == 0, r);
	request("*2\r\n$3\r\nGET\r\n$1\r\nz\r\n", r, sizeof r);
	ok("GET of an absent key is nil, not an error", strcmp(r, "$-1\r\n") == 0, r);
	request("*2\r\n$6\r\nEXISTS\r\n$1\r\nk\r\n", r, sizeof r);
	ok("EXISTS is 1 for a live key", strcmp(r, ":1\r\n") == 0, r);
	uint32_t before = log.len;
	request("*2\r\n$3\r\nDEL\r\n$1\r\nz\r\n", r, sizeof r);
	ok("DEL of an absent key is 0", strcmp(r, ":0\r\n") == 0, r);
	ok("and it writes no log record", log.len == before,
	   "an absent key's deletion changes nothing");
	request("*2\r\n$3\r\nDEL\r\n$1\r\nk\r\n", r, sizeof r);
	ok("DEL of a live key is 1", strcmp(r, ":1\r\n") == 0, r);
	request("*2\r\n$3\r\nGET\r\n$1\r\nk\r\n", r, sizeof r);
	ok("and the key is gone", strcmp(r, "$-1\r\n") == 0, r);

	/* --- framing -------------------------------------------------------- */
	fresh();
	uint32_t consumed = 0;
	const char *split = "*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$5\r\nhel";
	int n = kv_handle((const uint8_t *)split, (uint32_t)strlen(split), out, sizeof out,
	                  &consumed, &log);
	ok("a frame split mid-bulk is incomplete, not an error", n == 0 && consumed == 0,
	   "TCP does not preserve message boundaries");
	const char *whole = "*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$5\r\nhello\r\n";
	n = kv_handle((const uint8_t *)whole, (uint32_t)strlen(whole), out, sizeof out,
	              &consumed, &log);
	ok("the completed frame is handled", n > 0 && consumed == strlen(whole), NULL);

	const char *two = "*1\r\n$4\r\nPING\r\n*1\r\n$4\r\nPING\r\n";
	n = kv_handle((const uint8_t *)two, (uint32_t)strlen(two), out, sizeof out,
	              &consumed, &log);
	ok("two commands in one read: the first is consumed only",
	   n > 0 && consumed == strlen("*1\r\n$4\r\nPING\r\n"),
	   "consuming both would drop the second reply");

	/* --- refusals ------------------------------------------------------- */
	fresh();
	request("*2\r\n$3\r\nSET\r\n$1\r\nk\r\n", r, sizeof r);
	ok("wrong arity names the command",
	   strstr(r, "-ERR wrong number of arguments for 'set'") == r, r);
	request("*1\r\n$7\r\nEXPLODE\r\n", r, sizeof r);
	ok("an unknown command names itself",
	   strcmp(r, "-ERR unknown command 'EXPLODE'\r\n") == 0, r);

	{
		/* A bulk header claiming 5000 bytes, with no bytes after it: the
		 * refusal must come from the header alone. */
		char big[64];
		snprintf(big, sizeof big, "*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$%d\r\n", KV_MAX_VALUE + 1);
		request(big, r, sizeof r);
		ok("an oversize bulk is refused from its header, unbuffered",
		   strcmp(r, "-ERR value exceeds 4096 bytes\r\n") == 0, r);
	}

	/* --- the log and its replay ----------------------------------------- */
	fresh();
	request("*3\r\n$3\r\nSET\r\n$1\r\na\r\n$1\r\n1\r\n", r, sizeof r);
	request("*3\r\n$3\r\nSET\r\n$1\r\nb\r\n$1\r\n2\r\n", r, sizeof r);
	request("*3\r\n$3\r\nSET\r\n$1\r\nc\r\n$1\r\n3\r\n", r, sizeof r);
	request("*2\r\n$3\r\nDEL\r\n$1\r\nb\r\n", r, sizeof r);
	uint32_t good_len = log.len;

	uint32_t bad_at = 0;
	kv_reset(NULL);                       /* empty the store, keep the log */
	int applied = kv_replay(&log, &bad_at);
	ok("replay applies every record", applied == 4, NULL);
	ok("replay counts records, not live keys", kv_count() == 2, NULL);
	request("*2\r\n$3\r\nGET\r\n$1\r\na\r\n", r, sizeof r);
	ok("a value survives replay", strcmp(r, "$1\r\n1\r\n") == 0, r);
	request("*2\r\n$3\r\nGET\r\n$1\r\nb\r\n", r, sizeof r);
	ok("a deleted key stays deleted", strcmp(r, "$-1\r\n") == 0, r);
	ok("a clean log is not truncated", bad_at == 0 && log.len == good_len, NULL);

	/* A torn final record: the last byte of the crc never reached the disk. */
	log.len = good_len - 1;
	uint32_t torn_at = 0;
	kv_reset(NULL);
	applied = kv_replay(&log, &torn_at);
	ok("a torn final record costs that record only", applied == 3, NULL);
	ok("and the log is truncated at its offset", torn_at > 0 && log.len == torn_at, NULL);
	ok("the records before it survive", kv_count() == 3, NULL);

	/* A corrupted byte inside an earlier record stops replay there. */
	fresh();
	request("*3\r\n$3\r\nSET\r\n$1\r\na\r\n$1\r\n1\r\n", r, sizeof r);
	uint32_t first = log.len;
	request("*3\r\n$3\r\nSET\r\n$1\r\nb\r\n$1\r\n2\r\n", r, sizeof r);
	log_bytes[first + 9] ^= 0xFF;         /* flip a byte in the second record */
	uint32_t corrupt_at = 0;
	kv_reset(NULL);
	applied = kv_replay(&log, &corrupt_at);
	ok("a bad crc stops replay at that record", applied == 1, NULL);
	ok("and the log is truncated there", corrupt_at == first && log.len == first, NULL);

	/* --- the flush rule -------------------------------------------------- */
	fresh();
	request("*3\r\n$3\r\nSET\r\n$1\r\nk\r\n$1\r\nv\r\n", r, sizeof r);
	ok("+OK is sent only after the record is durable",
	   strcmp(r, "+OK\r\n") == 0 && log.pending == 0 && log.flushes == 1,
	   "a reply before the flush is a lie the client will believe and act on");
	request("*2\r\n$3\r\nDEL\r\n$1\r\nk\r\n", r, sizeof r);
	ok("a DEL is durable before its reply too",
	   strcmp(r, ":1\r\n") == 0 && log.pending == 0, NULL);

	/* --- shutdown -------------------------------------------------------- */
	n = request("*1\r\n$8\r\nSHUTDOWN\r\n", r, sizeof r);
	ok("SHUTDOWN asks for no reply, and is not 'incomplete'", n == KV_SHUTDOWN,
	   "returning 0 would make the caller wait for bytes that never come");

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
