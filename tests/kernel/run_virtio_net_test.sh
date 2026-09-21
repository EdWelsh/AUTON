#!/usr/bin/env bash
# Compile and run the VirtIO Network virtqueue tests on the host.
#
#   tests/kernel/run_virtio_net_test.sh --self-test    # against the reference
#   KERNEL_TREE=<dir> tests/kernel/run_virtio_net_test.sh
#
# The ring arithmetic is validated on any host. Register programming is not
# claimed here: under emulation a driver is verified against QEMU's model of the
# device, not the device.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_virtio_net_test"
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/virtio_reference/)"
	"$CC" -O1 -g -fsanitize=address,undefined \
		-I"$HERE/virtio_reference/include" \
		"$HERE/virtio_net_test.c" "$HERE/virtio_reference/virtio_ref.c" \
		-o "$OUT" || exit 1
	exec "$OUT"
fi

# exit 2 = not generated, exit 1 = generated wrong. An absent driver must not
# read as a broken one — the same distinction run_leakage_test.sh draws.
if [ ! -d "$KERNEL_TREE/kernel" ]; then
	echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
	echo "virtio-net is specified in agent/kernel_spec/subsystems/drivers.md" >&2
	echo "and recorded in agent/kernel_spec/drivers/virtio-net.md at" >&2
	echo "status: specified. Run --self-test to check the suite against the" >&2
	echo "reference." >&2
	exit 2
fi

SOURCES=""
for c in kernel/drivers/net/virtio_net.c kernel/net/virtio_net.c; do
	[ -f "$KERNEL_TREE/$c" ] && SOURCES="$SOURCES $KERNEL_TREE/$c"
done
if [ -z "$SOURCES" ]; then
	echo "kernel tree present but no virtio_net.c in it." >&2
	exit 2
fi

# shellcheck disable=SC2086
"$CC" -O1 -g -fsanitize=address,undefined \
	-I"$KERNEL_TREE/kernel/include" -I"$HERE/virtio_reference/include" \
	"$HERE/virtio_net_test.c" $SOURCES -o "$OUT" || {
		echo "compile failed — the generated driver does not match drivers.md" >&2
		exit 1
	}
exec "$OUT"
