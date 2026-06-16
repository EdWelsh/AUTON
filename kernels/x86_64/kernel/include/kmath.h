/* Freestanding float math for the neural backend (see kmath.c). */
#ifndef AUTON_KMATH_H
#define AUTON_KMATH_H

#include <stdint.h>

float kfabsf(float x);
float ksqrtf(float x);
float kexpf(float x);
float ksinf(float x);
float kcosf(float x);

#endif /* AUTON_KMATH_H */
