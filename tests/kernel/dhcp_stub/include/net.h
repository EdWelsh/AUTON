/* Minimal net surface the DHCP server needs, for host testing. Mirrors the
 * kernel's kernel/include/net.h; not kernel code. */
#ifndef AUTON_TEST_NET_H
#define AUTON_TEST_NET_H
#include <stdint.h>
typedef uint32_t ipv4_t;
#define IPV4(a,b,c,d) (((ipv4_t)(a)<<24)|((ipv4_t)(b)<<16)|((ipv4_t)(c)<<8)|(ipv4_t)(d))
ipv4_t net_ip(void);
#endif
