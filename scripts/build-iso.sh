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

make -C "$KDIR" CC="${CC:-gcc}" iso
mkdir -p "$DIST"
cp "$KDIR/build/auton.iso" "$DIST/auton-$ARCH-$VERSION.iso"
echo "built $DIST/auton-$ARCH-$VERSION.iso"
