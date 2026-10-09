#!/usr/bin/env bash
# Run a task on a Linux host inside Rancher/Docker (w23 X4 stand-in).
#
#   scripts/host-run.sh arm64 tests/kernel/run_aarch64_smoke.sh
#   scripts/host-run.sh amd64 "CHECK_E2E=0 scripts/preflight.sh"
#
# The repo is copied in (not mounted writable): a host run must not touch the checkout.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ARCH="${1:?arm64 or amd64}"; shift
case "$ARCH" in arm64|amd64) ;; *) echo "arch must be arm64 or amd64" >&2; exit 2;; esac
IMG="auton-host-linux-$ARCH"
if ! docker image inspect "$IMG" >/dev/null 2>&1; then
	docker build -q --platform "linux/$ARCH" -f "$ROOT/tests/hosts/Dockerfile.linux" -t "$IMG" "$ROOT" >/dev/null || exit 2
fi
exec docker run --rm --platform "linux/$ARCH" -v "$ROOT:/src:ro" "$IMG" \
	bash -c 'rm -rf /work/repo && mkdir /work/repo && cd /src && tar --exclude=.venv --exclude=.artifacts --exclude=.cache --exclude=node_modules -cf - . | tar -xf - -C /work/repo && cd /work/repo && '"$*"
