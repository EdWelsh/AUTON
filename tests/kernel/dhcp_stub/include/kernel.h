#ifndef AUTON_TEST_KERNEL_H
#define AUTON_TEST_KERNEL_H
/* The server logs its markers through kprintf. The host test prints them so a
 * failing case shows what the server said, not only that it said something. */
#include <stdio.h>
#define kprintf printf
#endif
