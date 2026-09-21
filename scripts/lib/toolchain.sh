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

# --- accelerator selection -------------------------------------------------- #
# Which QEMU accelerator to boot under. Probed, never inferred from `uname`:
# `uname -s` says Darwin, not whether this QEMU can use HVF for an x86 guest.
# On an arm64 Mac it cannot — HVF only accelerates a guest of the host's own
# architecture, and qemu-system-x86_64 there lists nothing but tcg.
#
# Precedence, as for CC: an explicit request (--accel, then AUTON_ACCEL) wins
# over the probe. An explicit request the host cannot honour FAILS rather than
# falling back — a caller who asked for kvm and silently got tcg reads a ~10x
# slower run as a regression.

# auton_accel_select <uname-s> <space-separated accels the binary lists> <kvm-usable 0|1>
# Pure: prints "<accel> <reason>" for the best choice. No probing, so every
# platform branch is testable from any host.
auton_accel_select() {
	local os="$1" listed=" $2 " kvm_ok="$3" prefs a
	case "$os" in
		Darwin)               prefs="hvf tcg" ;;
		Linux)                prefs="kvm tcg" ;;
		MINGW*|MSYS*|CYGWIN*) prefs="whpx kvm tcg" ;;
		*)                    prefs="tcg" ;;
	esac
	for a in $prefs; do
		case "$listed" in *" $a "*) ;; *) continue ;; esac
		if [ "$a" = "kvm" ] && [ "$kvm_ok" != "1" ]; then continue; fi
		if [ "$a" = "tcg" ]; then
			echo "tcg no faster accelerator usable (preferred: $prefs; binary lists:$(printf ' %s' $2); kvm device usable: $kvm_ok)"
		else
			echo "$a first available of: $prefs"
		fi
		return 0
	done
	echo "none binary lists none of: $prefs"
	return 1
}

# Accelerators the QEMU binary was built with (`-accel help`, header dropped).
auton_accel_listed() {
	"$QEMU" -accel help 2>/dev/null | awk 'NR>1 && NF {printf "%s ", $1}'
}

# /dev/kvm listed by the binary is not /dev/kvm usable by this user.
auton_kvm_usable() {
	if [ -r /dev/kvm ] && [ -w /dev/kvm ]; then echo 1; else echo 0; fi
}

# auton_accel [requested]
# Sets and exports AUTON_ACCEL and AUTON_ACCEL_REASON. Returns non-zero, naming
# what is available, when an explicit request cannot be honoured.
auton_accel() {
	local requested="${1:-${AUTON_ACCEL:-}}" listed kvm_ok choice
	listed="$(auton_accel_listed)"
	kvm_ok="$(auton_kvm_usable)"
	if [ -n "$requested" ]; then
		case " $listed " in
			*" $requested "*) ;;
			*) echo "accelerator '$requested' is not supported by $QEMU; it lists: ${listed:-nothing}" >&2
			   return 1 ;;
		esac
		if [ "$requested" = "kvm" ] && [ "$kvm_ok" != "1" ]; then
			echo "accelerator 'kvm' is listed by $QEMU but /dev/kvm is not readable and writable by $(id -un)" >&2
			return 1
		fi
		AUTON_ACCEL="$requested"
		AUTON_ACCEL_REASON="requested explicitly"
	else
		choice="$(auton_accel_select "$(uname -s)" "$listed" "$kvm_ok")" || {
			echo "no usable accelerator: $choice" >&2
			return 1
		}
		AUTON_ACCEL="${choice%% *}"
		AUTON_ACCEL_REASON="${choice#* }"
	fi
	export AUTON_ACCEL AUTON_ACCEL_REASON
}
