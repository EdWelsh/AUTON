/* Freestanding string/memory helpers. */
#include "kernel.h"

void *kmemset(void *dst, int c, size_t n)
{
	unsigned char *d = dst;
	for (size_t i = 0; i < n; i++)
		d[i] = (unsigned char)c;
	return dst;
}

void *kmemcpy(void *dst, const void *src, size_t n)
{
	unsigned char *d = dst;
	const unsigned char *s = src;
	for (size_t i = 0; i < n; i++)
		d[i] = s[i];
	return dst;
}

size_t kstrlen(const char *s)
{
	size_t n = 0;
	while (s[n])
		n++;
	return n;
}

int kstrcmp(const char *a, const char *b)
{
	while (*a && (*a == *b)) {
		a++;
		b++;
	}
	return (int)(unsigned char)*a - (int)(unsigned char)*b;
}

/* Freestanding C compilers (gcc) may lower __builtin_memcpy/memset and large
 * aggregate copies in the neural backend to calls to these symbols. Provide
 * them so the kernel links -nostdlib. */
void *memcpy(void *dst, const void *src, size_t n)
{
	return kmemcpy(dst, src, n);
}

void *memset(void *dst, int c, size_t n)
{
	return kmemset(dst, c, n);
}
