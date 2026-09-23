#!/usr/bin/env bash
# Grade a built image by an EXTERNAL probe (intent-to-OS-compiler I1/I2).
#
#   scripts/run-intent-probe.sh host-repo <package dir>
#   scripts/run-intent-probe.sh doom      <package dir>
#
# The PRD's rubric, lifted from the chat evaluation to whole deployments:
#
#   WORKED           the probe passed: the image did the thing
#   HONESTLY REFUSED the image named the capability it lacks and stopped
#   FAILED           it claimed success, or produced nothing, and the probe says so
#
# The probe is deliberately outside the image: `git clone` for a repository
# server, a framebuffer dump for Doom. An image grading itself is the failure
# this rubric exists to prevent — "[HTTP] listening" proves a log line, not a
# clone.
#
# Exit 0 worked, 1 failed, 2 honestly refused or the probe could not run (it
# says which, and why).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

INTENT="${1:-}"
PKG="${2:-}"
[ -n "$INTENT" ] && [ -n "$PKG" ] || {
	echo "usage: $0 {host-repo|doom} <package dir>" >&2; exit 2; }
[ -d "$PKG" ] || { echo "no package at $PKG" >&2; exit 2; }
PKG="$(cd "$PKG" && pwd)"
PY="${PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY=python3

WORK="$(mktemp -d)"
QPID=""
cleanup() {
	[ -n "$QPID" ] && kill "$QPID" 2>/dev/null
	[ -n "$QPID" ] && wait "$QPID" 2>/dev/null
	[ -n "${KEEP_WORK:-}" ] || rm -rf "$WORK"
}
trap cleanup EXIT

worked()  { echo "WORKED           $*"; exit 0; }
refused() { echo "HONESTLY REFUSED $*"; exit 2; }
failed()  { echo "FAILED           $*"; exit 1; }

iso_of() {
	local iso
	for iso in "$PKG"/*.iso "$PKG"/build/*.iso "$PKG"/image/*.iso; do
		[ -f "$iso" ] && { echo "$iso"; return 0; }
	done
	return 1
}

free_port() {
	"$PY" -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()'
}

# boot <iso> <serial> <marker regex> [extra qemu args...]
boot() {
	local iso="$1" serial="$2" marker="$3"
	shift 3
	: >"$serial"
	auton_timeout "${BOOT_TIMEOUT:-90}" "$QEMU" -cdrom "$iso" -serial "file:$serial" \
		-display none -no-reboot -m "${MEM:-256M}" "$@" </dev/null >/dev/null 2>&1 &
	QPID=$!
	local i
	for i in $(seq 1 "${BOOT_TIMEOUT:-90}"); do
		grep -qaE "$marker" "$serial" && return 0
		kill -0 "$QPID" 2>/dev/null || return 1
		sleep 1
	done
	return 1
}

# A refusal the image states itself is a different grade from silence.
refusal_in() {
	grep -aoE '\[[A-Z]+\] (not built|no volume|unavailable|refus[a-z]*|absent)[^\r\n]*' "$1" |
		head -1
}

case "$INTENT" in

host-repo)
	command -v git >/dev/null || { echo "git is required" >&2; exit 2; }
	iso="$(iso_of)" || failed "no ISO in $PKG: nothing was built to probe"
	[ -f "$PKG/assets/repo.cpio" ] || \
		refused "the package carries no assets/repo.cpio, so it never claimed to serve a repository"

	port="$(free_port)"
	serial="$WORK/serial.log"
	if ! boot "$iso" "$serial" '\[HTTP\] listening on :80' \
			-nic "user,model=e1000,hostfwd=tcp::$port-:80"; then
		reason="$(refusal_in "$serial")"
		[ -n "$reason" ] && refused "$reason"
		failed "no [HTTP] listening on :80 within ${BOOT_TIMEOUT:-90}s; serial: $(tail -3 "$serial" | tr '\n' ' ')"
	fi

	# The probe: a clone, by git itself.
	if ! git clone -q "http://127.0.0.1:$port/" "$WORK/clone" 2>"$WORK/clone.log"; then
		failed "the image served, but git clone failed: $(tail -2 "$WORK/clone.log" | tr '\n' ' ')"
	fi
	head_in_clone="$(git -C "$WORK/clone" rev-parse HEAD 2>/dev/null)"
	[ -n "$head_in_clone" ] || failed "the clone has no HEAD"

	# `git diff --stat HEAD` empty: the working tree matches what was committed.
	dirty="$(git -C "$WORK/clone" status --porcelain)"
	[ -z "$dirty" ] || failed "the clone is not clean: $dirty"
	worked "git clone over the image's dumb-HTTP layout, HEAD $head_in_clone, tree clean"
	;;

doom)
	iso="$(iso_of)" || failed "no ISO in $PKG: nothing was built to probe"
	[ -f "$PKG/assets/doom.wad" ] || \
		refused "the package carries no assets/doom.wad, so it never claimed to run Doom"

	serial="$WORK/serial.log"
	qmp="$WORK/qmp.sock"
	if ! boot "$iso" "$serial" '\[DOOM\] frame 1' \
			-qmp "unix:$qmp,server,nowait" -vga std; then
		reason="$(refusal_in "$serial")"
		[ -n "$reason" ] && refused "$reason"
		failed "no [DOOM] frame 1 within ${BOOT_TIMEOUT:-90}s"
	fi

	# The probe is the framebuffer, not the log: a non-blank frame, and input
	# that changes it. A log line saying "frame 1" is the image grading itself.
	"$PY" "$ROOT/scripts/qmp_probe.py" "$qmp" "$WORK" || {
		rc=$?
		[ "$rc" -eq 3 ] && failed "the frame never changed when keys were sent: input is not reaching the game"
		failed "the frame was a single colour: nothing was drawn"
	}
	worked "a non-blank frame, and sending keys changed it"
	;;

*)
	echo "unknown intent '$INTENT' (host-repo, doom)" >&2
	exit 2
	;;
esac
