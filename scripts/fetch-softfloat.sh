#!/usr/bin/env bash
# Fetch Berkeley SoftFloat, the conformance harness's oracle (hardware-truth H10).
#
#   scripts/fetch-softfloat.sh && tests/conformance/run_conformance.sh
#
# Pinned by commit, not by tag: the upstream mirror publishes no v3e tag, and a
# moving `master` is not an oracle. The archive's SHA-256 is checked, and a
# mismatch is fatal — an oracle nobody can reproduce is not evidence.
#
# It lands in .cache/third_party/, which git ignores. Nothing is vendored:
# SoftFloat is BSD-3-Clause and could be, but this repo's rule is that a
# third-party source is fetched with its provenance recorded, not copied in.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DST="$ROOT/.cache/third_party"
COMMIT="a0c6494cdc11865811dec815d5c0049fba9d82a8"
SHA256="1f719bcc8878be9627f6cfc44a0d6dbddf32bacc70ac81193bcbf2c62f97cbe9"
DIR="$DST/berkeley-softfloat-3-$COMMIT"

mkdir -p "$DST"
if [ -d "$DIR" ]; then
	echo "softfloat: ${DIR#"$ROOT"/}"
	exit 0
fi

TAR="$DST/softfloat-$COMMIT.tar.gz"
if [ ! -f "$TAR" ]; then
	curl -sSL -o "$TAR" \
		"https://github.com/ucb-bar/berkeley-softfloat-3/archive/$COMMIT.tar.gz"
fi
got="$(shasum -a 256 "$TAR" | cut -d' ' -f1)"
if [ "$got" != "$SHA256" ]; then
	echo "softfloat: sha256 $got, expected $SHA256" >&2
	echo "Refusing to build an oracle from an archive that is not the pinned one." >&2
	exit 1
fi
tar xzf "$TAR" -C "$DST"
echo "softfloat: ${DIR#"$ROOT"/}"
