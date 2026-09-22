/* Reference for the repository server's index and resolution.
 * NOT kernel code and NOT shipped: it exists so the host suite is proved
 * before it judges a generated implementation. */
#include "host_repo.h"

#include <string.h>
#include <stdlib.h>

#define MAX_FILES 4096

static struct { char path[HR_PATH_MAX]; const uint8_t *data; uint32_t len; } files[MAX_FILES];
static int file_count;

/* --- CPIO (newc) -------------------------------------------------------- */

static uint32_t hex8(const char *p)
{
	uint32_t v = 0;
	for (int i = 0; i < 8; i++) {
		char c = p[i];
		v <<= 4;
		if (c >= '0' && c <= '9')
			v |= (uint32_t)(c - '0');
		else if (c >= 'a' && c <= 'f')
			v |= (uint32_t)(c - 'a' + 10);
		else if (c >= 'A' && c <= 'F')
			v |= (uint32_t)(c - 'A' + 10);
		else
			return 0xFFFFFFFFu;
	}
	return v;
}

static uint32_t align4(uint32_t n)
{
	return (n + 3u) & ~3u;
}

int host_repo_init(const void *module, uint32_t module_len)
{
	const uint8_t *base = module;
	uint32_t at = 0;

	file_count = 0;
	if (!base)
		return -1;

	while (at + 110 <= module_len) {
		const char *h = (const char *)(base + at);
		if (memcmp(h, "070701", 6) != 0)
			return -1;                       /* not newc */
		uint32_t namesize = hex8(h + 94);
		uint32_t filesize = hex8(h + 54);
		if (namesize == 0xFFFFFFFFu || filesize == 0xFFFFFFFFu)
			return -1;
		uint32_t name_at = at + 110;
		if (name_at + namesize > module_len)
			return -1;
		const char *name = (const char *)(base + name_at);
		uint32_t data_at = align4(name_at + namesize);
		if (data_at + filesize > module_len)
			return -1;

		if (namesize >= 10 && memcmp(name, "TRAILER!!!", 10) == 0)
			break;
		if (file_count < MAX_FILES && namesize + 1 < HR_PATH_MAX) {
			/* Archive names are relative ("info/refs"); URLs are absolute. */
			files[file_count].path[0] = '/';
			memcpy(files[file_count].path + 1, name, namesize);
			files[file_count].path[namesize] = 0;   /* namesize includes the NUL */
			files[file_count].data = base + data_at;
			files[file_count].len = filesize;
			file_count++;
		}
		at = align4(data_at + filesize);
	}

	/* A repository nobody ran update-server-info on cannot be cloned over dumb
	 * HTTP. Saying so at boot beats failing at the client's first fetch. */
	uint32_t ignored;
	char resolved[HR_PATH_MAX];
	if (host_repo_resolve("/info/refs", resolved, sizeof resolved) < 0)
		return -1;
	(void)ignored;
	return file_count;
}

static int lookup(const char *path, uint32_t *len)
{
	for (int i = 0; i < file_count; i++)
		if (strcmp(files[i].path, path) == 0) {
			if (len)
				*len = files[i].len;
			return i;
		}
	return -1;
}

/* --- resolution ---------------------------------------------------------- */

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

int host_repo_resolve(const char *url, char *out, uint32_t out_len)
{
	char stripped[HR_PATH_MAX], decoded[HR_PATH_MAX];

	if (!url || url[0] != '/')
		return -1;

	/* The query string goes before resolution: git asks for
	 * /info/refs?service=git-upload-pack, and looking that up verbatim is a
	 * miss that makes the clone fail with no useful error. */
	uint32_t n = 0;
	for (; url[n] && url[n] != '?'; n++) {
		if (n + 1 >= sizeof stripped)
			return -1;
		stripped[n] = url[n];
	}
	stripped[n] = 0;

	/* Decode once. A second pass is how %252e%252e becomes "..". */
	uint32_t o = 0;
	for (uint32_t i = 0; i < n; i++) {
		if (o + 1 >= sizeof decoded)
			return -1;
		if (stripped[i] == '%') {
			if (i + 2 >= n)
				return -1;
			int hi = hexval(stripped[i + 1]), lo = hexval(stripped[i + 2]);
			if (hi < 0 || lo < 0)
				return -1;
			decoded[o++] = (char)((hi << 4) | lo);
			i += 2;
		} else {
			decoded[o++] = stripped[i];
		}
	}
	decoded[o] = 0;

	for (uint32_t i = 0; i < o; i++)
		if (decoded[i] == '\\' || decoded[i] == 0)
			return -1;
	if (o != strlen(decoded))
		return -1;
	if (o > 255)
		return -1;

	/* ".." as a SEGMENT, never as a substring: an object named "..pack" is a
	 * legal filename. */
	for (const char *seg = decoded; seg && *seg; ) {
		const char *next = strchr(seg + 1, '/');
		uint32_t len = next ? (uint32_t)(next - seg - 1) : (uint32_t)strlen(seg + 1);
		if (len == 2 && seg[1] == '.' && seg[2] == '.')
			return -1;
		seg = next;
	}

	if (lookup(decoded, NULL) < 0)
		return -1;
	if (strlen(decoded) >= out_len)
		return -1;
	strcpy(out, decoded);
	return 0;
}

int host_repo_handle(const char *request, uint32_t len, hr_conn_t *conn)
{
	memset(conn, 0, sizeof *conn);

	const char *end = NULL;
	for (uint32_t i = 0; i + 3 < len && i < HR_HEADER_MAX; i++)
		if (memcmp(request + i, "\r\n\r\n", 4) == 0) {
			end = request + i;
			break;
		}
	if (!end) {
		conn->status = len >= HR_HEADER_MAX ? 431 : 0;
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
		/* A push or a smart fetch is refused by METHOD, before any path work. */
		conn->status = 405;
		return -1;
	}

	const char *url = sp + 1;
	const char *url_end = memchr(url, ' ', (uint32_t)(end - url));
	if (!url_end) {
		conn->status = 400;
		return -1;
	}
	char urlbuf[HR_PATH_MAX];
	uint32_t url_len = (uint32_t)(url_end - url);
	if (url_len >= sizeof urlbuf) {
		conn->status = 404;
		return -1;
	}
	memcpy(urlbuf, url, url_len);
	urlbuf[url_len] = 0;

	if (host_repo_resolve(urlbuf, conn->path, sizeof conn->path) < 0) {
		conn->status = 404;    /* never 403: object names are content hashes */
		return -1;
	}
	lookup(conn->path, &conn->length);
	conn->text = strcmp(conn->path, "/HEAD") == 0 || strcmp(conn->path, "/info/refs") == 0;
	conn->status = 200;
	return 0;
}
