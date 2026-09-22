/* Host suite for the file server (agent/kernel_spec/services/fileserver.md).
 *
 * Path resolution is the whole attack surface, so most of this is the
 * traversal corpus: the encodings that defeat a naive check, and the ones a
 * too-eager check would reject when they are legal filenames.
 *
 * Every rejection is 404, never 403: a distinguishable error tells a prober
 * which files exist, which is the information the boundary exists to withhold.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "fileserver.h"

static int fails;

static void ok(const char *name, int cond, const char *detail)
{
	printf("%-64s %s", name, cond ? "PASS" : "FAIL");
	if (!cond && detail)
		printf("  (%s)", detail);
	printf("\n");
	if (!cond)
		fails++;
}

/* The docroot the suite serves: a volume with an index, a nested page, a
 * zero-length file, and a file whose name starts with dots (legal). */
static const struct { const char *path; uint32_t len; } DOCROOT[] = {
	{"/index.html", 1024},
	{"/a/b/page.html", 42},
	/* Present so that "/a\\b" (backslash as a separator) and "a/b" (relative)
	 * would BOTH resolve on the permissive volume — the resolver has to refuse
	 * them itself, and an injection proves it does. */
	{"/a/b", 10},
	{"/empty.txt", 0},
	{"/..txt", 7},
	/* A file whose NAME contains percent escapes. Decoding once finds it;
	 * decoding twice turns it into "/...txt", which does not exist. */
	{"/%2e%2e.txt", 5},
};

/* A DELIBERATELY PERMISSIVE filesystem, which is the point.
 *
 * If the fake volume answers "absent" to everything unusual, the traversal
 * tests are vacuous: a resolver with no checks at all still returns -1, and
 * the suite passes while the boundary does nothing. Proved by injection —
 * removing the traversal check, the backslash check and the leading-slash
 * check were each caught by nothing until this function got permissive.
 *
 * So this models the worst realistic volume: one that resolves `..`, accepts
 * backslash as a separator, and resolves a relative path. Every rejection then
 * has to come from fileserver_resolve, which is what is under test.
 */
int fs_lookup(const char *path, uint32_t *length)
{
	char norm[FS_PATH_MAX * 2];
	uint32_t o = 0;

	if (!path)
		return -1;
	/* Backslash as a separator, and a relative path resolved from the root. */
	if (path[0] != '/' && o + 1 < sizeof norm)
		norm[o++] = '/';
	for (uint32_t i = 0; path[i] && o + 1 < sizeof norm; i++)
		norm[o++] = path[i] == '\\' ? '/' : path[i];
	norm[o] = 0;

	for (unsigned i = 0; i < sizeof DOCROOT / sizeof DOCROOT[0]; i++)
		if (strcmp(DOCROOT[i].path, norm) == 0) {
			if (length)
				*length = DOCROOT[i].len;
			return (int)DOCROOT[i].len;
		}
	/* Anything that walks out of the docroot lands on a file that exists. */
	for (const char *seg = norm; seg && *seg; ) {
		if (seg[0] == '/' && seg[1] == '.' && seg[2] == '.' &&
		    (seg[3] == '/' || seg[3] == 0)) {
			if (length)
				*length = 99;
			return 99;
		}
		seg = strchr(seg + 1, '/');
	}
	return -1;
}

static int resolves(const char *url)
{
	char out[FS_PATH_MAX];
	return fileserver_resolve(url, out, sizeof out) == 0;
}

static int status_of(const char *request)
{
	http_conn_t conn;
	fileserver_handle(request, (uint32_t)strlen(request), &conn);
	return conn.status;
}

int main(void)
{
	char out[FS_PATH_MAX];

	/* --- what must be served -------------------------------------------- */
	ok("/ serves the index", fileserver_resolve("/", out, sizeof out) == 0 &&
	   strcmp(out, "/index.html") == 0, out);
	ok("a nested path resolves", resolves("/a/b/page.html"), NULL);
	ok("a zero-length file is servable", resolves("/empty.txt"), NULL);
	ok("a percent-encoded legal path resolves",
	   fileserver_resolve("/a/b/%70age.html", out, sizeof out) == 0 &&
	   strcmp(out, "/a/b/page.html") == 0, out);
	ok("a filename beginning with dots is not a traversal",
	   resolves("/..txt"), "'..' must be matched as a SEGMENT, not a substring");

	/* --- the traversal corpus -------------------------------------------- */
	ok("/../x is refused", !resolves("/../x"), NULL);
	ok("/a/../../x is refused", !resolves("/a/../../x"), NULL);
	ok("/%2e%2e/x is refused (decoded once, then checked)", !resolves("/%2e%2e/x"), NULL);
	ok("/%252e%252e/x is refused", !resolves("/%252e%252e/x"), NULL);
	ok("...and by decoding ONCE, not twice",
	   fileserver_resolve("/%252e%252e.txt", out, sizeof out) == 0 &&
	   strcmp(out, "/%2e%2e.txt") == 0,
	   "decoding twice turns a legal filename into a traversal: the second "
	   "pass IS the vulnerability");
	ok("/%2E%2E/x is refused (hex case)", !resolves("/%2E%2E/x"), NULL);
	ok("a backslash is refused", !resolves("/a\\b"), NULL);
	ok("a path not beginning with / is refused", !resolves("a/b"), NULL);
	ok("a bare .. segment at the end is refused", !resolves("/a/.."), NULL);
	ok("an incomplete escape is refused", !resolves("/a%2"), NULL);
	ok("a non-hex escape is refused", !resolves("/a%zz"), NULL);

	{
		char embedded[] = "/a%00b";
		ok("an embedded NUL is refused", !resolves(embedded),
		   "decoded to a NUL it would truncate the path inside the lookup");
	}
	{
		char big[300];
		memset(big, 'a', sizeof big);
		big[0] = '/';
		big[sizeof big - 1] = 0;
		ok("a 299-byte path is refused", !resolves(big), NULL);
	}

	/* --- absence and method ---------------------------------------------- */
	ok("a missing file does not resolve", !resolves("/nope.html"), NULL);
	ok("GET of a missing file is 404, never 403",
	   status_of("GET /nope.html HTTP/1.1\r\nHost: x\r\n\r\n") == 404, NULL);
	ok("a traversal is 404 too, indistinguishable from a miss",
	   status_of("GET /../etc/passwd HTTP/1.1\r\nHost: x\r\n\r\n") == 404,
	   "403 would confirm the file exists");
	ok("GET of a present file is 200",
	   status_of("GET /index.html HTTP/1.1\r\nHost: x\r\n\r\n") == 200, NULL);
	ok("HEAD is allowed", status_of("HEAD /index.html HTTP/1.1\r\nHost: x\r\n\r\n") == 200,
	   NULL);
	ok("POST is 405", status_of("POST /index.html HTTP/1.1\r\nHost: x\r\n\r\n") == 405, NULL);
	ok("DELETE is 405", status_of("DELETE /index.html HTTP/1.1\r\nHost: x\r\n\r\n") == 405,
	   NULL);

	/* --- framing ---------------------------------------------------------- */
	ok("a request without CRLFCRLF yet is incomplete, not an error",
	   status_of("GET /index.html HTTP/1.1\r\nHost: x\r\n") == 0,
	   "the loop reads more; erroring here would break a split request");
	{
		static char huge[FS_HEADER_MAX + 64];
		int n = snprintf(huge, sizeof huge, "GET /index.html HTTP/1.1\r\nX: ");
		memset(huge + n, 'a', sizeof huge - (size_t)n - 1);
		huge[sizeof huge - 1] = 0;
		ok("headers past 8 KiB with no CRLFCRLF are 431",
		   status_of(huge) == 431, "a client must not hold the one slot forever");
	}

	/* --- the body length the response will claim -------------------------- */
	{
		http_conn_t conn;
		const char *req = "GET /a/b/page.html HTTP/1.1\r\nHost: x\r\n\r\n";
		fileserver_handle(req, (uint32_t)strlen(req), &conn);
		ok("a 200 carries the file's length", conn.status == 200 && conn.length == 42, NULL);
		const char *empty = "GET /empty.txt HTTP/1.1\r\nHost: x\r\n\r\n";
		fileserver_handle(empty, (uint32_t)strlen(empty), &conn);
		ok("a zero-length file is 200 with length 0",
		   conn.status == 200 && conn.length == 0, NULL);
	}

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
