/* Freestanding float math for the neural backend: expf, sqrtf, sinf, cosf,
 * fabsf. Accuracy target is ~1e-3 over the ranges the transformer needs
 * (softmax exp, RMSNorm rsqrt, RoPE sin/cos, SiLU). Compiled with SSE.
 *
 * This file is pure (no kernel deps) so the host test harness can compile it
 * natively and diff against libm. */
#include "kmath.h"

#define KM_PI    3.14159265358979323846f
#define KM_PI_2  1.57079632679489661923f
#define KM_2PI   6.28318530717958647692f

float kfabsf(float x)
{
	union { float f; uint32_t u; } v = { x };
	v.u &= 0x7FFFFFFFu;
	return v.f;
}

float ksqrtf(float x)
{
	/* With SSE enabled (the neural TU) this lowers to an inline sqrtss — no
	 * libm call. Portable to the native host test harness too. */
	return __builtin_sqrtf(x);
}

/* exp(x) via range reduction: exp(x) = 2^k * exp(r), k = round(x/ln2),
 * r = x - k*ln2 in [-ln2/2, ln2/2], exp(r) by a degree-5 minimax polynomial. */
float kexpf(float x)
{
	const float LN2 = 0.69314718056f;
	const float INV_LN2 = 1.44269504089f;

	if (x > 88.0f)
		return 3.4e38f;         /* clamp to ~FLT_MAX (overflow) */
	if (x < -88.0f)
		return 0.0f;

	int k = (int)(x * INV_LN2 + (x >= 0 ? 0.5f : -0.5f));
	float r = x - (float)k * LN2;

	/* exp(r), r small. */
	float p = 1.0f + r * (1.0f + r * (0.5f + r * (0.16666667f +
		  r * (0.041666668f + r * 0.008333334f))));

	/* Multiply by 2^k by composing the float exponent field. */
	union { float f; uint32_t u; } v;
	int e = k + 127;
	if (e <= 0)
		return 0.0f;
	if (e >= 255)
		return 3.4e38f;
	v.u = (uint32_t)e << 23;
	return p * v.f;
}

/* sin over reduced argument in [-pi, pi] via degree-7 minimax. */
static float sin_poly(float x)
{
	float x2 = x * x;
	return x * (0.9999966f + x2 * (-0.16664824f + x2 * (0.0083109378f +
		   x2 * (-0.00018363f))));
}

float ksinf(float x)
{
	/* Reduce to [-pi, pi]. */
	float k = x * (1.0f / KM_2PI);
	k = k >= 0 ? (float)(int)(k + 0.5f) : (float)(int)(k - 0.5f);
	float r = x - k * KM_2PI;
	if (r > KM_PI)
		r -= KM_2PI;
	else if (r < -KM_PI)
		r += KM_2PI;
	/* Fold into [-pi/2, pi/2] for polynomial accuracy. */
	if (r > KM_PI_2)
		r = KM_PI - r;
	else if (r < -KM_PI_2)
		r = -KM_PI - r;
	return sin_poly(r);
}

float kcosf(float x)
{
	return ksinf(x + KM_PI_2);
}
