/* A freestanding <stdlib.h> for the F12 gate: sizes and nothing else.
 * A source that needs malloc/free/abort from here fails to compile, which is
 * the answer criterion (b) wants. */
#ifndef AUTON_FREESTANDING_STDLIB_H
#define AUTON_FREESTANDING_STDLIB_H
#include <stddef.h>
#endif
