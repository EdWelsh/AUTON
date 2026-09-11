#!/usr/bin/env bash
# Per-platform build-tool resolution, sourced by the scripts under scripts/.
#
#   source "$(dirname "$0")/lib/toolchain.sh"
#
# Sets CC, GRUB_MKRESCUE, QEMU and TIMEOUT_BIN, and defines auton_timeout().
# Any value already present in the environment wins — never override an
# explicit choice by the caller.
#
# Why CC is set here and not left to the Makefile: kernel/arch/x86_64/
# toolchain.mk says `CC ?= x86_64-elf-gcc`, but GNU make predefines CC (origin
# "default", value "cc"), so `?=` never fires and a bare `make` picks up the
# host compiler. On macOS that is Apple clang, which cannot emit ELF64.

# Darwin: Homebrew names. `brew install qemu xorriso x86_64-elf-gcc \
#   x86_64-elf-binutils i686-elf-grub`
# Linux/Docker: distro names; CC stays gcc, matching the amd64 image.
case "$(uname -s)" in
	Darwin)
		: "${CC:=x86_64-elf-gcc}"
		: "${GRUB_MKRESCUE:=i686-elf-grub-mkrescue}"
		;;
	*)
		: "${CC:=gcc}"
		: "${GRUB_MKRESCUE:=grub-mkrescue}"
		;;
esac
: "${QEMU:=qemu-system-x86_64}"

export CC GRUB_MKRESCUE QEMU

# GNU coreutils `timeout` is absent on stock macOS. Prefer the real binary when
# present (timeout, or gtimeout from `brew install coreutils`); otherwise fall
# back to a background-and-kill shim with the same argument order.
TIMEOUT_BIN="${TIMEOUT_BIN:-$(command -v timeout || command -v gtimeout || true)}"
export TIMEOUT_BIN

# auton_timeout <seconds> <command> [args...]
# Returns the command's exit status, or 124 when it was killed on timeout
# (matching coreutils `timeout`).
auton_timeout() {
	local secs="$1"
	shift
	if [ -n "$TIMEOUT_BIN" ]; then
		"$TIMEOUT_BIN" "$secs" "$@"
		return $?
	fi

	# `<&0` is load-bearing: bash sends an async command's stdin to /dev/null
	# when job control is off, which would sever a caller's pipe (the acceptance
	# harness pipes chat input into QEMU this way). An explicit redirection
	# suppresses that substitution.
	"$@" <&0 &
	local cmd_pid=$!
	( sleep "$secs"; kill -TERM "$cmd_pid" 2>/dev/null ) &
	local killer_pid=$!

	local rc=0
	wait "$cmd_pid" 2>/dev/null || rc=$?
	# Killer still alive => the command finished on its own.
	if kill -0 "$killer_pid" 2>/dev/null; then
		kill "$killer_pid" 2>/dev/null
		wait "$killer_pid" 2>/dev/null || true
	else
		rc=124
	fi
	return "$rc"
}
