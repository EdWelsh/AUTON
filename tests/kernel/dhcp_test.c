/* Host tests for the DHCP server, against agent/kernel_spec/services/dhcp.md.
 *
 * dhcp.md splits `dhcp_handle` from `dhcp_serve` precisely so this is possible:
 * a serve loop that owns its parsing cannot be tested without a NIC, and the
 * cases that matter most — a malformed option length, a pool exhausted, a
 * REQUEST for an address nobody offered — are exactly the ones a live client
 * never produces.
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "dhcp.h"

static int fails;
static void ok(const char *name, int cond, const char *detail)
{
	if (cond) printf("PASS  %-56s\n", name);
	else { printf("FAIL  %-56s  %s\n", name, detail ? detail : ""); fails = 1; }
}

/* --- the world the server talks to ---------------------------------------- */
static uint32_t fake_now = 100;
static uint32_t clock_fn(void) { return fake_now; }
ipv4_t net_ip(void) { return IPV4(10,0,2,1); }

static struct {
	int      count;
	ipv4_t   dst;
	uint16_t dport, sport;
	uint8_t  payload[512];
	uint16_t len;
} sent;

static void capture(ipv4_t dst, uint16_t dport, uint16_t sport,
                    const void *payload, uint16_t len)
{
	sent.count++;
	sent.dst = dst; sent.dport = dport; sent.sport = sport;
	sent.len = len > sizeof sent.payload ? sizeof sent.payload : len;
	memcpy(sent.payload, payload, sent.len);
}

/* --- building requests ---------------------------------------------------- */
#define OFF_XID 4
#define OFF_GIADDR 24
#define OFF_CHADDR 28
#define OFF_COOKIE 236
#define OFF_OPTIONS 240

static uint8_t req[512];
static uint32_t req_len;

static void put32(uint8_t *p, uint32_t v)
{
	p[0]=(uint8_t)(v>>24); p[1]=(uint8_t)(v>>16); p[2]=(uint8_t)(v>>8); p[3]=(uint8_t)v;
}
static uint32_t get32(const uint8_t *p)
{
	return ((uint32_t)p[0]<<24)|((uint32_t)p[1]<<16)|((uint32_t)p[2]<<8)|p[3];
}

static void build(uint8_t msgtype, const uint8_t mac[6], uint32_t xid, ipv4_t requested)
{
	memset(req, 0, sizeof req);
	req[0] = 1;          /* BOOTREQUEST */
	req[1] = 1;          /* htype ethernet */
	req[2] = 6;          /* hlen */
	put32(&req[OFF_XID], xid);
	memcpy(&req[OFF_CHADDR], mac, 6);
	put32(&req[OFF_COOKIE], 0x63825363u);
	uint32_t o = OFF_OPTIONS;
	req[o++] = 53; req[o++] = 1; req[o++] = msgtype;
	if (requested) { req[o++] = 50; req[o++] = 4; put32(&req[o], requested); o += 4; }
	req[o++] = 255;
	req_len = o;
}

static uint8_t reply_type(void)
{
	for (uint32_t i = OFF_OPTIONS; i + 1 < sent.len; ) {
		if (sent.payload[i] == 255) break;
		if (sent.payload[i] == 0) { i++; continue; }
		uint8_t code = sent.payload[i], olen = sent.payload[i+1];
		if (code == 53 && olen == 1) return sent.payload[i+2];
		i += 2u + olen;
	}
	return 0;
}
static ipv4_t reply_yiaddr(void) { return get32(&sent.payload[16]); }

static const uint8_t MAC_A[6] = {0x52,0x54,0x00,0x12,0x34,0x56};
static const uint8_t MAC_B[6] = {0x52,0x54,0x00,0xAA,0xBB,0xCC};

static void reset_server(uint32_t pool)
{
	dhcp_server_t cfg;
	memset(&cfg, 0, sizeof cfg);
	cfg.pool_base = IPV4(10,0,2,100);
	cfg.pool_count = pool;
	cfg.netmask = IPV4(255,255,255,0);
	cfg.gateway = IPV4(10,0,2,1);
	cfg.dns = IPV4(10,0,2,3);
	cfg.lease_secs = 3600;
	dhcp_server_init(&cfg);
	sent.count = 0;
	fake_now = 100;
}

int main(void)
{
	dhcp_set_clock(clock_fn);
	dhcp_set_sender(capture);

	/* --- configuration ---------------------------------------------------- */
	dhcp_server_t big; memset(&big, 0, sizeof big);
	big.pool_count = DHCP_POOL_MAX + 1;
	ok("a pool larger than the table is refused", dhcp_server_init(&big) == -1, NULL);
	big.pool_count = 0;
	ok("an empty pool is refused", dhcp_server_init(&big) == -1, NULL);

	/* --- DISCOVER -> OFFER ------------------------------------------------ */
	reset_server(4);
	build(1 /*DISCOVER*/, MAC_A, 0xAAAA, 0);
	int r = dhcp_handle(req, req_len);
	ok("DISCOVER produces a reply", r == 1 && sent.count == 1, NULL);
	ok("the reply is an OFFER", reply_type() == 2, NULL);
	ok("the offer is from the pool", reply_yiaddr() == IPV4(10,0,2,100), NULL);
	ok("the offer is broadcast", sent.dst == 0xFFFFFFFFu,
	   "the client has no address, so unicast needs an ARP it cannot answer");
	ok("the reply goes to the client port", sent.dport == 68 && sent.sport == 67, NULL);

	/* --- a second DISCOVER from the same MAC ------------------------------ */
	sent.count = 0;
	build(1, MAC_A, 0xAAAB, 0);
	dhcp_handle(req, req_len);
	ok("a repeat DISCOVER re-offers the same address",
	   reply_yiaddr() == IPV4(10,0,2,100),
	   "a client that discovers twice must not consume two addresses");

	/* --- a different client gets a different address ---------------------- */
	build(1, MAC_B, 0xBBBB, 0);
	dhcp_handle(req, req_len);
	ok("a second client gets a different address",
	   reply_yiaddr() == IPV4(10,0,2,101), NULL);

	/* --- REQUEST -> ACK --------------------------------------------------- */
	sent.count = 0;
	build(3 /*REQUEST*/, MAC_A, 0xAAAB, IPV4(10,0,2,100));
	dhcp_handle(req, req_len);
	ok("REQUEST for the offered address is ACKed", reply_type() == 5, NULL);
	ok("the ACK carries the same address", reply_yiaddr() == IPV4(10,0,2,100), NULL);

	/* --- REQUEST for something nobody offered ----------------------------- */
	sent.count = 0;
	build(3, MAC_A, 0xAAAC, IPV4(10,0,2,199));
	dhcp_handle(req, req_len);
	ok("REQUEST for an unoffered address is NAKed", reply_type() == 6,
	   "a silent drop leaves the client retrying for its whole timeout");

	/* --- expiry ----------------------------------------------------------- */
	reset_server(4);
	build(1, MAC_A, 0x1111, 0);
	dhcp_handle(req, req_len);
	fake_now = 100 + DHCP_OFFER_SECS + 1;
	dhcp_expire(fake_now);
	ok("an abandoned OFFER returns to the pool",
	   dhcp_state()->leases[0].state == LEASE_FREE, NULL);

	reset_server(4);
	build(1, MAC_A, 0x2222, 0);  dhcp_handle(req, req_len);
	build(3, MAC_A, 0x2222, IPV4(10,0,2,100)); dhcp_handle(req, req_len);
	fake_now = 100 + 3600 + 1;
	dhcp_expire(fake_now);
	ok("a bound lease expires at lease_secs",
	   dhcp_state()->leases[0].state == LEASE_FREE, NULL);

	/* --- RELEASE ---------------------------------------------------------- */
	reset_server(4);
	build(1, MAC_A, 0x3333, 0);  dhcp_handle(req, req_len);
	build(7 /*RELEASE*/, MAC_A, 0x3333, 0); dhcp_handle(req, req_len);
	ok("RELEASE frees the lease",
	   dhcp_state()->leases[0].state == LEASE_FREE, NULL);

	/* --- pool exhaustion -------------------------------------------------- */
	reset_server(1);
	build(1, MAC_A, 0x4444, 0); dhcp_handle(req, req_len);
	sent.count = 0;
	build(1, MAC_B, 0x5555, 0);
	r = dhcp_handle(req, req_len);
	ok("an exhausted pool drops rather than replying", r == 0 && sent.count == 0,
	   "NAK would be a lie about this request; offering a bound address is worse");

	/* --- malformed input -------------------------------------------------- */
	reset_server(4);
	sent.count = 0;
	build(1, MAC_A, 0x6666, 0);
	ok("a frame shorter than the BOOTP header is dropped",
	   dhcp_handle(req, 100) == 0 && sent.count == 0, NULL);

	build(1, MAC_A, 0x6667, 0);
	req[0] = 2;   /* BOOTREPLY, not a request */
	ok("a BOOTREPLY is dropped", dhcp_handle(req, req_len) == 0, NULL);

	build(1, MAC_A, 0x6668, 0);
	put32(&req[OFF_COOKIE], 0xDEADBEEF);
	ok("a bad magic cookie is dropped", dhcp_handle(req, req_len) == 0, NULL);

	build(1, MAC_A, 0x6669, 0);
	put32(&req[OFF_GIADDR], IPV4(10,9,9,1));
	ok("a relayed request is dropped", dhcp_handle(req, req_len) == 0,
	   "no relay support; routing is outside this service");

	/* The classic hole: an option length that runs past the buffer. If the
	 * walk trusts it, this reads out of bounds — under ASan, visibly. */
	/* After the option being looked for: find_option() would stop before
	   reaching it, so only a full validation pass catches this one. */
	build(1, MAC_A, 0x666A, 0);
	req[OFF_OPTIONS + 3] = 50;    /* option code */
	req[OFF_OPTIONS + 4] = 200;   /* length far past the end */
	sent.count = 0;
	r = dhcp_handle(req, OFF_OPTIONS + 5);
	ok("a bad option length after the message type is dropped",
	   r == 0 && sent.count == 0,
	   "find_option stops early, so only a whole-block validation sees this");

	/* Before it: the walk hits the bad length while searching. */
	build(1, MAC_A, 0x666C, 0);
	memset(&req[OFF_OPTIONS], 0, 16);
	req[OFF_OPTIONS] = 50;        /* option code */
	req[OFF_OPTIONS + 1] = 200;   /* length far past the end */
	sent.count = 0;
	r = dhcp_handle(req, OFF_OPTIONS + 6);
	ok("a bad option length before the message type is dropped",
	   r == 0 && sent.count == 0,
	   "trusting the length is the classic parser hole");

	build(1, MAC_A, 0x666B, 0);
	req_len = OFF_OPTIONS + 1;    /* option code with no length byte */
	req[OFF_OPTIONS] = 50;
	sent.count = 0;
	ok("a truncated option is dropped",
	   dhcp_handle(req, req_len) == 0 && sent.count == 0, NULL);

	/* --- an unconfigured server ------------------------------------------- */
	dhcp_server_t none; memset(&none, 0, sizeof none);
	none.pool_count = 0;
	dhcp_server_init(&none);      /* fails, leaving the previous config */
	build(1, MAC_A, 0x7777, 0);
	ok("a failed init does not wipe a working configuration",
	   dhcp_handle(req, req_len) == 1, NULL);

	printf(fails ? "\nDHCP: FAILURES\n" : "\nDHCP: ALL PASS\n");
	return fails;
}
