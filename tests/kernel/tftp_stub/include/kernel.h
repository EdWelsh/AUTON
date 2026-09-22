#ifndef AUTON_TEST_KERNEL_H
#define AUTON_TEST_KERNEL_H
/* The TFTP server logs its markers through kprintf. The host test captures
 * them, so a case can assert the marker the spec requires, not just print it. */
int test_kprintf(const char *fmt, ...) __attribute__((format(printf, 1, 2)));
#define kprintf test_kprintf
#endif
