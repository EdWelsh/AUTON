/* Host suite for the repository server (services/host-repo.md).
 *
 * Built around a real CPIO archive of a real bare repository, produced by
 * run_host_repo_test.sh with git itself. Testing a CPIO parser against an
 * archive written by the same test would prove only self-consistency.
 *
 * The query-string rule has its own section: git's first request is
 * /info/refs?service=git-upload-pack, and a server that looks that up verbatim
 * fails the clone with no useful error.
 */
#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "host_repo.h"

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

static uint8_t *slurp(const char *path, uint32_t *len)
{
	FILE *f = fopen(path, "rb");
	if (!f) {
		fprintf(stderr, "cannot open %s\n", path);
		exit(2);
	}
	fseek(f, 0, SEEK_END);
	long n = ftell(f);
	fseek(f, 0, SEEK_SET);
	uint8_t *b = malloc((size_t)n);
	if (fread(b, 1, (size_t)n, f) != (size_t)n)
		exit(2);
	fclose(f);
	*len = (uint32_t)n;
	return b;
}

static int resolves(const char *url)
{
	char out[HR_PATH_MAX];
	return host_repo_resolve(url, out, sizeof out) == 0;
}

static int status_of(const char *request)
{
	hr_conn_t conn;
	host_repo_handle(request, (uint32_t)strlen(request), &conn);
	return conn.status;
}

int main(int argc, char **argv)
{
	const char *archive = argc > 1 ? argv[1] : "repo.cpio";
	const char *hostile = argc > 2 ? argv[2] : NULL;
	const char *unservable = argc > 3 ? argv[3] : NULL;
	uint32_t len = 0;
	uint8_t *cpio = slurp(archive, &len);

	int count = host_repo_init(cpio, len);
	ok("a real repository archive indexes", count > 0, "produced by git itself");
	ok("it contains more than a handful of files", count >= 5, NULL);

	/* --- the layout a dumb clone needs ---------------------------------- */
	ok("/info/refs is present", resolves("/info/refs"),
	   "without it git cannot enumerate refs and the clone fails");
	ok("/HEAD is present", resolves("/HEAD"), NULL);
	ok("/objects/info/packs is present", resolves("/objects/info/packs"),
	   "git update-server-info writes it; a dumb clone reads it to find packs");

	/* --- the query string ------------------------------------------------ */
	{
		char out[HR_PATH_MAX];
		ok("/info/refs?service=git-upload-pack resolves to /info/refs",
		   host_repo_resolve("/info/refs?service=git-upload-pack", out, sizeof out) == 0 &&
		   strcmp(out, "/info/refs") == 0,
		   "looked up verbatim this is a miss, and the clone fails");
		ok("a query string on any path is stripped",
		   host_repo_resolve("/HEAD?x=1&y=2", out, sizeof out) == 0 &&
		   strcmp(out, "/HEAD") == 0, out);
		ok("an empty query string is fine",
		   host_repo_resolve("/HEAD?", out, sizeof out) == 0, NULL);
	}
	ok("the smart endpoint is a 404, which is the fallback signal",
	   status_of("GET /git-upload-pack HTTP/1.1\r\nHost: x\r\n\r\n") == 404, NULL);
	ok("POST is 405, refused by method before any path work",
	   status_of("POST /git-upload-pack HTTP/1.1\r\nHost: x\r\n\r\n") == 405,
	   "a push must not reach resolution at all");

	/* --- serving --------------------------------------------------------- */
	{
		hr_conn_t conn;
		const char *req = "GET /info/refs?service=git-upload-pack HTTP/1.1\r\nHost: x\r\n\r\n";
		host_repo_handle(req, (uint32_t)strlen(req), &conn);
		ok("the refs request is 200 with a length", conn.status == 200 && conn.length > 0,
		   NULL);
		ok("and it is served as text", conn.text == 1, NULL);
		const char *head = "GET /HEAD HTTP/1.1\r\nHost: x\r\n\r\n";
		host_repo_handle(head, (uint32_t)strlen(head), &conn);
		ok("HEAD the file is text too", conn.status == 200 && conn.text == 1, NULL);
	}
	ok("the repository root is a 404, not an index page",
	   status_of("GET / HTTP/1.1\r\nHost: x\r\n\r\n") == 404, NULL);
	ok("an absent loose object is 404, which a dumb clone expects",
	   status_of("GET /objects/ab/" "0123456789012345678901234567890123456789"
	             " HTTP/1.1\r\nHost: x\r\n\r\n") == 404, NULL);

	/* --- the traversal corpus, as in fileserver.md ----------------------- */
	ok("/../x is refused", !resolves("/../x"), NULL);
	ok("/%2e%2e/x is refused", !resolves("/%2e%2e/x"), NULL);
	ok("/%252e%252e/x is refused, without decoding twice", !resolves("/%252e%252e/x"), NULL);
	ok("a backslash is refused", !resolves("/objects\\info\\packs"), NULL);
	ok("a relative path is refused", !resolves("info/refs"), NULL);
	ok("a traversal with a query string is still refused",
	   !resolves("/../etc/passwd?service=git-upload-pack"),
	   "stripping the query must not skip the traversal check");
	{
		char big[300];
		memset(big, 'a', sizeof big);
		big[0] = '/';
		big[sizeof big - 1] = 0;
		ok("an over-long path is refused", !resolves(big), NULL);
	}

	/* --- the checks must do the work, not absence ------------------------ */
	if (hostile) {
		uint32_t hlen = 0;
		uint8_t *h = slurp(hostile, &hlen);
		int n = host_repo_init(h, hlen);
		ok("the hostile archive indexes (it has no /info/refs, so init refuses)",
		   n < 0, "it exists to make the next checks non-vacuous");
		/* init refused, but the index is populated: resolution is what is
		 * under test here, and it must refuse these on their own merits. */
		ok("a member named ../outside.txt is NOT reachable by traversal",
		   !resolves("/../outside.txt"),
		   "the file exists in the archive: only the check stops it");
		{
			char out[HR_PATH_MAX];
			ok("a member whose NAME holds escapes is found by decoding ONCE",
			   host_repo_resolve("/%252e%252e.txt", out, sizeof out) == 0 &&
			   strcmp(out, "/%2e%2e.txt") == 0,
			   "decoding twice turns it into /...txt, which is absent");
		}
		free(h);
		host_repo_init(cpio, len);
	}

	if (unservable) {
		uint32_t ulen = 0;
		uint8_t *u = slurp(unservable, &ulen);
		ok("an archive without /info/refs is refused at init",
		   host_repo_init(u, ulen) < 0,
		   "nobody ran update-server-info: it cannot be cloned");
		free(u);
		host_repo_init(cpio, len);
	}

	/* --- init's own refusal ---------------------------------------------- */
	{
		/* A truncated archive is malformed, not a smaller repository. */
		int truncated = host_repo_init(cpio, len / 2);
		ok("a truncated archive is refused at init", truncated < 0,
		   "half an archive is not half a repository");
		host_repo_init(cpio, len);       /* restore for anything after */
	}

	printf("\n%s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails, fails == 1 ? "" : "s");
	free(cpio);
	return fails ? 1 : 0;
}
