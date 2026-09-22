/* Reference for the file server's path resolution and request parsing.
 * NOT kernel code and NOT shipped: it exists so the host suite is proved
 * before it judges a generated implementation. */
#include "fileserver.h"

#include <string.h>

static int hexval(char c)
{
	if (c >= '0' && c <= '9')
		return c - '0';
	if (c >= 'a' && c <= 'f')
		return c - 'a' + 10;
	if (c >= 'A' && c <= 'F')
		return c - 'A' + 10;
	return -1;
}

/* Percent-decode ONCE. A second pass is how %252e%252e becomes "..". */
static int decode_once(const char *in, uint32_t in_len, char *out, uint32_t out_cap)
{
	uint32_t o = 0;
	for (uint32_t i = 0; i < in_len; i++) {
		if (o + 1 >= out_cap)
			return -1;
		if (in[i] == '%') {
			if (i + 2 >= in_len)
				return -1;
			int hi = hexval(in[i + 1]), lo = hexval(in[i + 2]);
			if (hi < 0 || lo < 0)
				return -1;
			out[o++] = (char)((hi << 4) | lo);
			i += 2;
		} else {
			out[o++] = in[i];
		}
	}
	out[o] = 0;
	return (int)o;
}

int fileserver_resolve(const char *url, char *out, uint32_t out_len)
{
	char decoded[FS_PATH_MAX];

	if (!url || url[0] != '/')
		return -1;                              /* 1. must begin with / */

	uint32_t url_len = (uint32_t)strlen(url);
	if (url_len >= FS_PATH_MAX)
		return -1;
	int n = decode_once(url, url_len, decoded, sizeof decoded);   /* 2. decode once */
	if (n < 0)
		return -1;

	/* 3. Reject NUL, backslash, and any ".." SEGMENT — on segment boundaries,
	 * after decoding, never by substring (a file named "..txt" is legal). */
	for (int i = 0; i < n; i++)
		if (decoded[i] == '\\' || decoded[i] == 0)
			return -1;
	if ((uint32_t)n != strlen(decoded))
		return -1;                              /* an embedded NUL truncated it */

	const char *seg = decoded;
	while (*seg) {
		if (*seg == '/')
			seg++;
		const char *end = strchr(seg, '/');
		uint32_t len = end ? (uint32_t)(end - seg) : (uint32_t)strlen(seg);
		if (len == 2 && seg[0] == '.' && seg[1] == '.')
			return -1;
		if (!end)
			break;
		seg = end;
	}

	if ((uint32_t)n > 255)                          /* 4. still over 255 */
		return -1;

	/* 5. Per-segment lookup from the volume root. FAT32 has no symlinks, so
	 * the walk is the only namespace. "/" means the index. */
	const char *want = decoded;
	if (strcmp(decoded, "/") == 0)
		want = "/index.html";
	uint32_t length = 0;
	if (fs_lookup(want, &length) < 0)
		return -1;
	if (strlen(want) >= out_len)
		return -1;
	strcpy(out, want);
	return 0;
}

int fileserver_handle(const char *request, uint32_t len, http_conn_t *conn)
{
	memset(conn, 0, sizeof *conn);

	/* Headers must end within 8 KiB. Checked first: a client that never sends
	 * CRLFCRLF must not hold the one connection slot forever. */
	const char *end = NULL;
	for (uint32_t i = 0; i + 3 < len && i < FS_HEADER_MAX; i++)
		if (memcmp(request + i, "\r\n\r\n", 4) == 0) {
			end = request + i;
			break;
		}
	if (!end) {
		conn->status = len >= FS_HEADER_MAX ? 431 : 0;   /* 0: incomplete, read more */
		return conn->status ? -1 : 0;
	}

	const char *sp = memchr(request, ' ', len);
	if (!sp) {
		conn->status = 400;
		return -1;
	}
	uint32_t method_len = (uint32_t)(sp - request);
	int is_get = method_len == 3 && memcmp(request, "GET", 3) == 0;
	int is_head = method_len == 4 && memcmp(request, "HEAD", 4) == 0;
	if (!is_get && !is_head) {
		conn->status = 405;              /* the caller sends Allow: GET, HEAD */
		return -1;
	}

	const char *url = sp + 1;
	const char *url_end = memchr(url, ' ', (uint32_t)(end - url));
	if (!url_end) {
		conn->status = 400;
		return -1;
	}
	char urlbuf[FS_PATH_MAX];
	uint32_t url_len = (uint32_t)(url_end - url);
	if (url_len >= sizeof urlbuf) {
		conn->status = 404;              /* never 414: one answer for every miss */
		return -1;
	}
	memcpy(urlbuf, url, url_len);
	urlbuf[url_len] = 0;

	if (fileserver_resolve(urlbuf, conn->path, sizeof conn->path) < 0) {
		/* 404, never 403: a distinguishable error tells a prober what exists. */
		conn->status = 404;
		return -1;
	}
	fs_lookup(conn->path, &conn->length);
	conn->status = 200;
	return 0;
}
