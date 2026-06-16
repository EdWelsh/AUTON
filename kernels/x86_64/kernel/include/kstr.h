/* Tiny freestanding string-builder + case-insensitive matching helpers, shared
 * by the chat-facing modules (sysinfo, roles). */
#ifndef AUTON_KSTR_H
#define AUTON_KSTR_H

#include <stdint.h>

char     ks_lower(char c);
/* 1 if lowercased 'hay' contains 'needle' (needle must already be lowercase). */
int      ks_contains(const char *hay, const char *needle);
/* Append helpers: write into dst[pos..cap), NUL-terminate, return new length. */
uint32_t ks_append(char *dst, uint32_t cap, uint32_t pos, const char *s);
uint32_t ks_append_dec(char *dst, uint32_t cap, uint32_t pos, uint32_t v);
uint32_t ks_append_ip(char *dst, uint32_t cap, uint32_t pos, uint32_t ip);

#endif /* AUTON_KSTR_H */
