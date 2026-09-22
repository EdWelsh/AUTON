#!/usr/bin/env bash
# Fetch the crypto sources the F12 gate judges, into the gitignored cache.
#
#   tests/crypto/fetch_sources.sh && tests/crypto/run_crypto_gate.sh
#
# Nothing is vendored into the repo by this script: it downloads into
# .cache/vendor/crypto/, which git ignores, exactly as vendor_fetch.py does for
# silicon documents. What may later be ported, and under which licence, is the
# decision record's business (agent/kernel_spec/decisions/ssh-crypto.md).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
DST="$ROOT/.cache/vendor/crypto"
MONO_VER=4.0.2
mkdir -p "$DST"

if [ ! -d "$DST/Monocypher-$MONO_VER" ]; then
	echo "Monocypher $MONO_VER"
	curl -sSL -o "$DST/monocypher.tar.gz" \
		"https://github.com/LoupVaillant/Monocypher/archive/refs/tags/$MONO_VER.tar.gz"
	tar xzf "$DST/monocypher.tar.gz" -C "$DST"
fi

# BearSSL has no release tarball on a CDN that answers to curl; its own gitweb
# serves the files. Only the three units SHA-256 needs, plus its headers.
BR="$DST/bearssl"
gitweb() { curl -sSL -o "$2" "https://bearssl.org/gitweb/?p=BearSSL;a=blob_plain;f=$1;hb=HEAD"; }
if [ ! -f "$BR/src/sha2small.c" ]; then
	echo "BearSSL (SHA-256 units and headers)"
	mkdir -p "$BR/inc" "$BR/src/codec"
	for h in bearssl.h bearssl_hash.h bearssl_block.h bearssl_hmac.h bearssl_rand.h \
		bearssl_prf.h bearssl_kdf.h bearssl_aead.h bearssl_ssl.h bearssl_x509.h \
		bearssl_rsa.h bearssl_ec.h bearssl_pem.h; do
		gitweb "inc/$h" "$BR/inc/$h"
	done
	for f in config.h inner.h hash/sha2small.c codec/enc32be.c codec/dec32be.c; do
		mkdir -p "$BR/src/$(dirname "$f")"
		gitweb "src/$f" "$BR/src/$(basename "$(dirname "$f")")/$(basename "$f")"
	done
	mv "$BR/src/hash/sha2small.c" "$BR/src/sha2small.c" 2>/dev/null || true
	gitweb LICENSE.txt "$BR/LICENSE.txt"
fi

echo "sources in ${DST#"$ROOT"/}"
