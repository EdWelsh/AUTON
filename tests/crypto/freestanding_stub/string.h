/* A freestanding <string.h> for the F12 crypto gate.
 *
 * Criterion (b) asks whether a primitive's source needs libc. BearSSL's
 * inner.h includes <string.h> for memcpy/memset, which a kernel provides
 * itself; this stub declares exactly those, so the compile proves the source
 * needs nothing more. If a unit needs another function from here, it fails to
 * compile — which is the answer the criterion wants.
 */
#ifndef AUTON_FREESTANDING_STRING_H
#define AUTON_FREESTANDING_STRING_H
#include <stddef.h>
void *memcpy(void *dst, const void *src, size_t n);
void *memmove(void *dst, const void *src, size_t n);
void *memset(void *dst, int c, size_t n);
int memcmp(const void *a, const void *b, size_t n);
size_t strlen(const char *s);
#endif
