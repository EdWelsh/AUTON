#!/usr/bin/env bash
# Build a versioned, bootable GRUB rescue ISO for release.
# Mirrors the Makefile `iso` target (proven via `docker compose run acceptance`)
# but stages a named artifact under dist/.
set -euo pipefail

ARCH="${1:-x86_64}"
VERSION="${2:-v0.1.0}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KDIR="$ROOT/kernels/$ARCH"
DIST="$ROOT/dist"

# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

# The kernel tree is agent-generated output and may not exist. Say so plainly:
# "build failed" implies a broken build, not an absent one.
if [ ! -d "$KDIR/kernel" ]; then
	echo "no kernel tree at ${KDIR#"$ROOT"/}" >&2
	echo "AUTON's premise is that the agents write it (README.md). Generate one," >&2
	echo "or extract the agreed base: scripts/kernel-base.sh kernels/x86_64" >&2
	exit 2
fi

make -C "$KDIR" iso
mkdir -p "$DIST"
cp "$KDIR/build/auton.iso" "$DIST/auton-$ARCH-$VERSION.iso"
echo "built $DIST/auton-$ARCH-$VERSION.iso"
