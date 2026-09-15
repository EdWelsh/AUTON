#!/usr/bin/env bash
# Assert that an excluded capability contributes no symbols to a built image.
#
#   KERNEL_TREE=kernels/x86_64 tests/kernel/run_leakage_test.sh --excludes net,fs
#
# Every other check in the factory is about inputs — a manifest, a source list,
# a slice. This is the only one that inspects the artifact, which is the only
# place `excludes` can actually be false. intent-E's enforcement is built on it.
#
# Symbols are attributed to a capability through the same source map the build
# list comes from, so the two cannot disagree about what `net` means.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac

EXCLUDES=""
IMAGE=""
STUBS=""
while [ $# -gt 0 ]; do
	case "$1" in
		--excludes)   EXCLUDES="${2:?--excludes needs a value}"; shift 2 ;;
		--excludes=*) EXCLUDES="${1#*=}"; shift ;;
		--image)      IMAGE="${2:?--image needs a value}"; shift 2 ;;
		--stubs)      STUBS="${2:?--stubs needs a value}"; shift 2 ;;
		--stubs=*)    STUBS="${1#*=}"; shift ;;
		*) echo "unknown argument: $1" >&2; exit 2 ;;
	esac
done
[ -n "$EXCLUDES" ] || { echo "usage: $0 --excludes net[,fs,...] [--image FILE]" >&2; exit 2; }

IMAGE="${IMAGE:-$KERNEL_TREE/build/kernel.bin}"
if [ ! -f "$IMAGE" ]; then
	# exit 2 = nothing to check, exit 1 = check failed. An unbuilt image must
	# not read as a clean one, which is the whole failure mode here.
	echo "no image at $IMAGE — build first." >&2
	exit 2
fi

NM="${NM:-}"
if [ -z "$NM" ]; then
	for c in x86_64-elf-nm nm; do command -v "$c" >/dev/null 2>&1 && { NM="$c"; break; }; done
fi
[ -n "$NM" ] || { echo "no nm on PATH" >&2; exit 2; }

"$NM" "$IMAGE" > "${TMPDIR:-/tmp}/auton_syms.txt" 2>/dev/null || {
	echo "$NM could not read $IMAGE" >&2; exit 2; }

exec "$PY" "$ROOT/tests/kernel/leakage_check.py" \
	--symbols "${TMPDIR:-/tmp}/auton_syms.txt" \
	--tree "$KERNEL_TREE" \
	--excludes "$EXCLUDES" \
	--image "$IMAGE" \
	--stubs "$STUBS"
