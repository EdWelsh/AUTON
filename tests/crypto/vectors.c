/* Published vectors for the six primitives an SSH transport needs (F12 gate).
 *
 * Every expected value below is copied from the RFC or NIST document named
 * beside it. Nothing here implements a primitive: the sources under test are
 * third-party, and a primitive that fails is a CUT, not a rewrite
 * (agent/kernel_spec/decisions/ssh-crypto.md).
 */
#include <stdio.h>
#include <stdint.h>
#include <string.h>

#include "monocypher.h"
#include "monocypher-ed25519.h"
#include "bearssl_hash.h"

static int fails;

static void hex(const uint8_t *b, size_t n, char *out)
{
	for (size_t i = 0; i < n; i++)
		snprintf(out + 2 * i, 3, "%02x", b[i]);
}

static void ok(const char *name, const uint8_t *got, const char *want, size_t n)
{
	char g[257] = {0};
	hex(got, n, g);
	int good = strcmp(g, want) == 0;
	printf("  %-46s %s\n", name, good ? "PASS" : "FAIL");
	if (!good) {
		printf("      got  %s\n      want %s\n", g, want);
		fails++;
	}
}

static void unhex(const char *h, uint8_t *out, size_t n)
{
	for (size_t i = 0; i < n; i++) {
		unsigned v;
		sscanf(h + 2 * i, "%2x", &v);
		out[i] = (uint8_t)v;
	}
}

int main(void)
{
	/* --- X25519, RFC 7748 §5.2 (first test vector) --------------------- */
	{
		uint8_t k[32], u[32], out[32];
		unhex("a546e36bf0527c9d3b16154b82465edd62144c0ac1fc5a18506a2244ba449ac4", k, 32);
		unhex("e6db6867583030db3594c1a424b15f7c726624ec26b3353b10a903a6d0ab1c4c", u, 32);
		crypto_x25519(out, k, u);
		ok("X25519 (RFC 7748 5.2)", out,
		   "c3da55379de9c6908e94ea4df28d084f32eccf03491c71f754b4075577a28552", 32);
	}

	/* --- Ed25519, RFC 8032 §7.1 TEST 2 (one-byte message) -------------- */
	{
		/* Monocypher's secret key is 64 bytes (seed || public key), derived
		 * from the RFC's 32-byte secret. Deriving it also checks the public
		 * key against the RFC's, which is the vector's other half. */
		uint8_t seed[32], sk[64], pk[32], sig[64], msg = 0x72;
		unhex("4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb", seed, 32);
		crypto_ed25519_key_pair(sk, pk, seed);
		ok("Ed25519 public key (RFC 8032 7.1 TEST 2)", pk,
		   "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c", 32);
		crypto_ed25519_sign(sig, sk, &msg, 1);
		ok("Ed25519 sign (RFC 8032 7.1 TEST 2)", sig,
		   "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da"
		   "085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00", 64);
		int good = crypto_ed25519_check(sig, pk, &msg, 1) == 0;
		printf("  %-46s %s\n", "Ed25519 verify accepts its own signature",
		       good ? "PASS" : "FAIL");
		fails += !good;
		sig[0] ^= 1;
		good = crypto_ed25519_check(sig, pk, &msg, 1) != 0;
		printf("  %-46s %s\n", "Ed25519 verify rejects a flipped bit",
		       good ? "PASS" : "FAIL");
		fails += !good;
	}

	/* --- SHA-512, NIST CAVP one-block "abc" ---------------------------- */
	{
		uint8_t out[64];
		crypto_sha512(out, (const uint8_t *)"abc", 3);
		ok("SHA-512 (\"abc\")", out,
		   "ddaf35a193617abacc417349ae20413112e6fa4e89a97ea20a9eeee64b55d39a"
		   "2192992a274fc1a836ba3c23a3feebbd454d4423643ce80e2a9ac94fa54ca49f", 64);
	}

	/* --- SHA-256, NIST CAVP one-block and two-block examples ----------- */
	{
		uint8_t out[32];
		br_sha256_context c;
		br_sha256_init(&c);
		br_sha256_update(&c, "abc", 3);
		br_sha256_out(&c, out);
		ok("SHA-256 (\"abc\")", out,
		   "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad", 32);
		br_sha256_init(&c);
		br_sha256_update(&c, "abcdbcdecdefdefgefghfghighijhijkijkljklmklmnlmnomnopnopq", 56);
		br_sha256_out(&c, out);
		ok("SHA-256 (two-block example)", out,
		   "248d6a61d20638b8e5c026930c3e6039a33ce45964ff2167f6ecedd419db06c1", 32);
	}

	/* --- ChaCha20, RFC 8439 §2.4.2 ------------------------------------- */
	{
		uint8_t key[32], nonce[12], out[114];
		const char *pt = "Ladies and Gentlemen of the class of '99: If I could offer you "
		                 "only one tip for the future, sunscreen would be it.";
		for (int i = 0; i < 32; i++)
			key[i] = (uint8_t)i;
		memset(nonce, 0, 12);
		nonce[7] = 0x4a;    /* 00:00:00:00 00:00:00:4a 00:00:00:00, RFC 8439 2.4.2.
		                     * (The 00:00:00:09 nonce belongs to 2.3.2's block
		                     * function example, which is a different vector.) */
		/* The _ietf variant: RFC 8439's 12-byte nonce and 32-bit counter.
		 * _djb takes an 8-byte nonce and is a different construction. */
		crypto_chacha20_ietf(out, (const uint8_t *)pt, 114, key, nonce, 1);
		ok("ChaCha20 (RFC 8439 2.4.2)", out,
		   "6e2e359a2568f98041ba0728dd0d6981e97e7aec1d4360c20a27afccfd9fae0b"
		   "f91b65c5524733ab8f593dabcd62b3571639d624e65152ab8f530c359f0861d8"
		   "07ca0dbf500d6a6156a38e088a22b65e52bc514d16ccf806818ce91ab7793736"
		   "5af90bbf74a35be6b40b8eedf2785e42874d", 114);
	}

	/* --- Poly1305, RFC 8439 §2.5.2 ------------------------------------- */
	{
		uint8_t key[32], mac[16];
		const char *msg = "Cryptographic Forum Research Group";
		unhex("85d6be7857556d337f4452fe42d506a80103808afb0db2fd4abff6af4149f51b", key, 32);
		crypto_poly1305(mac, (const uint8_t *)msg, 34, key);
		ok("Poly1305 (RFC 8439 2.5.2)", mac, "a8061dc1305136c6c22b8baf0c0127a9", 16);
	}

	printf("\nvectors: %s (%d failure%s)\n", fails ? "FAIL" : "PASS", fails,
	       fails == 1 ? "" : "s");
	return fails ? 1 : 0;
}
