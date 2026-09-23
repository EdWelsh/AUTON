/* Host definitions of the kernel's libk, for the TFTP gate. They are the C
 * library's, because what is under test is the TFTP server, not memcpy. */
#include <string.h>

#include "kernel.h"

void *kmemset(void *dst, int c, size_t n) { return memset(dst, c, n); }
void *kmemcpy(void *dst, const void *src, size_t n) { return memcpy(dst, src, n); }
size_t kstrlen(const char *s) { return strlen(s); }
int kstrcmp(const char *a, const char *b) { return strcmp(a, b); }
