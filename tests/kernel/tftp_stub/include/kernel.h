#ifndef AUTON_TEST_KERNEL_H
#define AUTON_TEST_KERNEL_H

#include <stddef.h>

/* The TFTP server logs its markers through kprintf. The host test captures
 * them, so a case can assert the marker the spec requires, not just print it. */
int test_kprintf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#define kprintf test_kprintf

/* The rest of libk, declared EXACTLY as kernel/include/kernel.h declares it.
 *
 * This stub is on the include path ahead of the tree's own headers, so it
 * shadows the real kernel.h completely. When it declared only kprintf, an
 * implementation that called kmemcpy or kstrcmp — as the real kernel.h offers
 * and as a correct TFTP server naturally does — could not compile under this
 * gate at all. That is a defect in the gate, and it cost a run: w14's
 * qwen3.5:27b server failed to build on `NULL`, `kmemcpy` and `kstrcmp`, none
 * of which were its fault.
 *
 * tftp_stub/libk.c defines these for the host build. */
void  *kmemset(void *dst, int c, size_t n);
void  *kmemcpy(void *dst, const void *src, size_t n);
size_t kstrlen(const char *s);
int    kstrcmp(const char *a, const char *b);

#endif
