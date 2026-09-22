/* The file server's host-testable half, as specified in
 * agent/kernel_spec/services/fileserver.md: path resolution (the whole attack
 * surface) and request parsing. NOT kernel code and NOT shipped.
 *
 * The docroot is behind fs_lookup() so the host suite can answer from a table
 * and a kernel can answer from the FAT32 volume. */
#ifndef AUTON_FILESERVER_H
#define AUTON_FILESERVER_H

#include <stdint.h>

#define FS_PATH_MAX     256
#define FS_HEADER_MAX   8192

typedef struct http_conn {
	int      status;               /* 200, 404, 405, 431, 400 */
	char     path[FS_PATH_MAX];    /* resolved, docroot-relative */
	uint32_t length;               /* body length for 200 */
} http_conn_t;

/* The docroot, supplied by the host suite or by the volume. Returns the file's
 * length, or -1 when it is absent. */
int fs_lookup(const char *path, uint32_t *length);

/* Resolve a URL path against the docroot. 0 and fills `out`, or -1 on
 * traversal, a bad character, an over-long path, or absence. */
int fileserver_resolve(const char *url, char *out, uint32_t out_len);

/* One request (request line + headers) in, a status out. Never touches a
 * socket, so it is testable without a NIC. */
int fileserver_handle(const char *request, uint32_t len, http_conn_t *conn);

#endif
