#!/usr/bin/env bash
# Verify this host can build and boot AUTON natively, before anything long runs.
# Checks the cross toolchain, the ISO tooling, QEMU, and free disk space.
#
#   scripts/preflight.sh              # default floor: 5 GiB
#   MIN_FREE_GB=20 scripts/preflight.sh
#
# No -e: every check reports before we exit, so one run lists everything missing.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

MIN_FREE_GB="${MIN_FREE_GB:-5}"
BREW_INSTALL="brew install qemu xorriso x86_64-elf-gcc x86_64-elf-binutils i686-elf-grub"

fail=0
pass() { echo "PASS  $1"; }
bad()  { echo "FAIL  $1"; [ -n "${2:-}" ] && echo "      -> $2"; fail=1; }

have() { command -v "$1" >/dev/null 2>&1; }

# --- toolchain ------------------------------------------------------------ #
if have "$CC"; then
	# Must be able to emit ELF64 x86-64. Apple clang reports arm64-apple-darwin
	# and silently fails much later, so check the target triple, not the name.
	triple="$("$CC" -dumpmachine 2>/dev/null)"
	case "$triple" in
		x86_64*) pass "cc ($CC -> $triple)" ;;
		*)       bad  "cc ($CC -> ${triple:-unknown})" \
		              "cannot emit x86-64 ELF; expected an x86_64-* target. $BREW_INSTALL" ;;
	esac
else
	bad "cc ($CC)" "not on PATH. $BREW_INSTALL"
fi

for tool_var in GRUB_MKRESCUE QEMU; do
	tool="${!tool_var}"
	if have "$tool"; then pass "$tool_var ($tool)"
	else bad "$tool_var ($tool)" "not on PATH. $BREW_INSTALL"; fi
done

if have xorriso; then pass "xorriso"
else bad "xorriso" "not on PATH ($GRUB_MKRESCUE needs it). $BREW_INSTALL"; fi

# --- disk ------------------------------------------------------------------ #
# Emulated builds and model artifacts are large, and a full volume has
# previously corrupted Docker layers mid-run. Fail before, not during.
free_kb="$(df -k "$ROOT" | awk 'NR==2 {print $4}')"
if [ -n "$free_kb" ]; then
	free_gb=$((free_kb / 1024 / 1024))
	if [ "$free_gb" -ge "$MIN_FREE_GB" ]; then
		pass "disk (${free_gb} GiB free, floor ${MIN_FREE_GB} GiB)"
	else
		bad "disk (${free_gb} GiB free, floor ${MIN_FREE_GB} GiB)" \
		    "short by $((MIN_FREE_GB - free_gb)) GiB; free space or lower MIN_FREE_GB"
	fi
else
	bad "disk" "could not read free space for $ROOT"
fi

# --- timeout --------------------------------------------------------------- #
if [ -n "${TIMEOUT_BIN:-}" ]; then pass "timeout ($TIMEOUT_BIN)"
else pass "timeout (built-in shim; install coreutils for the real one)"; fi

if [ "$fail" -eq 0 ]; then
	echo "ALL PASS"
else
	echo "FAILURES"
	exit 1
fi
