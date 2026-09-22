/* The repository server's host-testable half, as specified in
 * agent/kernel_spec/services/host-repo.md: the CPIO index, query-string
 * stripping and path resolution. NOT kernel code and NOT shipped. */
#ifndef AUTON_HOST_REPO_H
#define AUTON_HOST_REPO_H

#include <stdint.h>

#define HR_PATH_MAX     256
#define HR_HEADER_MAX   8192

typedef struct hr_conn {
	int      status;               /* 200, 404, 405, 431, 400 */
	char     path[HR_PATH_MAX];    /* resolved, archive-relative */
	uint32_t length;
	int      text;                 /* 1 for text/plain (HEAD, info/refs) */
} hr_conn_t;

/* Index a CPIO (newc) archive in place. Returns the file count, or -1 when it
 * is malformed or has no /info/refs. */
int  host_repo_init(const void *module, uint32_t module_len);

/* Resolve a URL, query string included, against the index. -1 on traversal,
 * a bad character, an over-long path, or absence. */
int  host_repo_resolve(const char *url, char *out, uint32_t out_len);

/* One request in, a status out. No socket. */
int  host_repo_handle(const char *request, uint32_t len, hr_conn_t *conn);

#endif
