#!/usr/bin/env bash
# Verify this host can build and boot AUTON natively, before anything long runs.
# Checks the cross toolchain, the ISO tooling, QEMU, and free disk space.
#
#   scripts/preflight.sh              # kernel loop; default floor: 5 GiB
#   CHECK_E2E=1 scripts/preflight.sh  # also clang/torch/corpus; floor 10 GiB
#   MIN_FREE_GB=20 scripts/preflight.sh
#
# No -e: every check reports before we exit, so one run lists everything missing.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

PY="${PYTHON:-$ROOT/.venv/bin/python}"
case "$PY" in /*) ;; *) PY="$ROOT/$PY";; esac

# A full e2e run writes a checkpoint and an exported model (~56 MB each here,
# far more at larger rungs) on top of the ISO, so it asks for a higher floor
# than the kernel-only loop.
MIN_FREE_GB="${MIN_FREE_GB:-$([ "${CHECK_E2E:-0}" = "1" ] && echo 10 || echo 5)}"
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

# --- e2e extras ------------------------------------------------------------ #
# Only checked when asked (scripts/e2e.sh stage 0). The kernel-only loop needs
# neither clang nor torch, so a plain preflight must not fail without them.
if [ "${CHECK_E2E:-0}" = "1" ]; then
	if have clang; then pass "clang ($(clang --version | head -1 | sed 's/ version.*//'))"
	else bad "clang" "needed by neural_parity.sh; install Xcode command line tools"; fi

	if [ -x "$PY" ]; then
		if "$PY" -c 'import torch' >/dev/null 2>&1; then
			pass "torch ($("$PY" -c 'import torch; print(torch.__version__)' 2>/dev/null))"
		else
			bad "torch (via $PY)" "parity compares against the PyTorch reference; pip install torch"
		fi
	else
		bad "python ($PY)" "no interpreter; set PYTHON= or create the venv"
	fi

	for f in "$ROOT/SLM/datasets/os_tasks.jsonl" "$ROOT/SLM/configs/tiny_10M.yaml"; do
		if [ -f "$f" ]; then pass "corpus/config ($(basename "$f"))"
		else bad "corpus/config ($(basename "$f"))" "missing; rung 3a cannot train"; fi
	done
fi

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

# --- accelerator ------------------------------------------------------------ #
# Boot timings are only comparable if the run says what it ran under. TCG is
# slow, not broken, so it is a NOTE — failing on it would make this Mac unusable.
accel_err="$(mktemp)"
if auton_accel 2>"$accel_err"; then
	case "$AUTON_ACCEL" in
		tcg)
			echo "NOTE  accelerator (tcg) — $AUTON_ACCEL_REASON"
			echo "      -> every boot here is software-emulated; expect roughly 10x a KVM"
			echo "         host. Timings from this host are one end of B1's ratio, not"
			echo "         a regression. See docs/HOST-MATRIX.md" ;;
		*)  pass "accelerator ($AUTON_ACCEL — $AUTON_ACCEL_REASON)" ;;
	esac
else
	bad "accelerator" "$(cat "$accel_err")"
fi
rm -f "$accel_err"

# --- what this host cannot verify ------------------------------------------ #
# A cross toolchain lets any host BUILD an x86 kernel. It does not let one
# execute x86 instructions natively, so checks that read the running CPU are
# unavailable here — and they must say so. tests/kernel/identity_test.c prints
# SKIP for its live CPUID cross-check, and a SKIP inside a passing suite is
# easy to read as a pass.
HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
	x86_64|amd64)
		pass "host arch ($HOST_ARCH) — silicon identity can be cross-checked live"
		;;
	*)
		echo "NOTE  host arch ($HOST_ARCH) cannot run x86 CPUID"
		echo "      -> tests/kernel/run_identity_test.sh verifies the folding formula"
		echo "         against documented parts, but its live cross-check against"
		echo "         this machine's own CPU is SKIPPED. Silicon identity is"
		echo "         unverified against real hardware on this host."
		echo "         See .claude/PRPs/reports/w2-portability-start.md"
		;;
esac

if [ "$fail" -eq 0 ]; then
	echo "ALL PASS"
else
	echo "FAILURES"
	exit 1
fi
