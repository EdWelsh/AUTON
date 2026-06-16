/* See kstr.h. No libc; matches the style of the seed kernel. */
#include "kstr.h"

char ks_lower(char c)
{
	return (c >= 'A' && c <= 'Z') ? (char)(c + 32) : c;
}

int ks_contains(const char *hay, const char *needle)
{
	for (uint32_t i = 0; hay[i]; i++) {
		uint32_t j = 0;
		while (needle[j] && ks_lower(hay[i + j]) == needle[j])
			j++;
		if (!needle[j])
			return 1;
	}
	return 0;
}

uint32_t ks_append(char *dst, uint32_t cap, uint32_t pos, const char *s)
{
	while (*s && pos < cap - 1)
		dst[pos++] = *s++;
	dst[pos] = '\0';
	return pos;
}

uint32_t ks_append_dec(char *dst, uint32_t cap, uint32_t pos, uint32_t v)
{
	char tmp[12];
	int n = 0;

	if (v == 0)
		tmp[n++] = '0';
	while (v > 0 && n < (int)sizeof(tmp)) {
		tmp[n++] = (char)('0' + v % 10);
		v /= 10;
	}
	while (n > 0 && pos < cap - 1)
		dst[pos++] = tmp[--n];
	dst[pos] = '\0';
	return pos;
}

uint32_t ks_append_ip(char *dst, uint32_t cap, uint32_t pos, uint32_t ip)
{
	pos = ks_append_dec(dst, cap, pos, (ip >> 24) & 0xFF);
	pos = ks_append(dst, cap, pos, ".");
	pos = ks_append_dec(dst, cap, pos, (ip >> 16) & 0xFF);
	pos = ks_append(dst, cap, pos, ".");
	pos = ks_append_dec(dst, cap, pos, (ip >> 8) & 0xFF);
	pos = ks_append(dst, cap, pos, ".");
	pos = ks_append_dec(dst, cap, pos, ip & 0xFF);
	return pos;
}
