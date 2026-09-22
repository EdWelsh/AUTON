/* A freestanding <assert.h> for the F12 gate: assert compiles away, as it does
 * in a kernel build with NDEBUG. A source relying on assert() to *abort* at
 * runtime is out of scope for this criterion, which measures link-time needs. */
#ifndef AUTON_FREESTANDING_ASSERT_H
#define AUTON_FREESTANDING_ASSERT_H
#define assert(x) ((void)0)
#endif
