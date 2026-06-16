#!/usr/bin/env bash
# Build the seed kernel ISO, boot it, and verify the acceptance serial markers
# (the strings kernel_spec/tests/acceptance_tests.py greps for).
set -uo pipefail

ARCH="${1:-x86_64}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/kernels/$ARCH"

make CC="${CC:-gcc}" iso >/dev/null 2>&1 || { echo "build failed"; exit 1; }

OUT="$(timeout "${BOOT_TIMEOUT:-45}" qemu-system-x86_64 -cdrom build/auton.iso \
	-serial stdio -display none -no-reboot -m "${MEM:-128M}" 2>/dev/null || true)"

echo "----- serial output -----"
echo "$OUT"
echo "-------------------------"

fail=0
check() {
	if echo "$OUT" | grep -qE "$1"; then
		echo "PASS  $1"
	else
		echo "FAIL  $1"
		fail=1
	fi
}

check "AUTON Kernel booting"
check "\[BOOT\] Multiboot2 magic valid"
check "\[BOOT\] Long mode enabled"
check "\[BOOT\] 64-bit GDT loaded"
check "\[BOOT\] Interrupts initialized"
check "\[DRV\] Serial .+ initialized"
check "\[MM\] PMM initialized"
check "\[SCHED\] Scheduler initialized"
check "\[DEV\] PCI scan: [0-9]+ devices found"
check "\[SLM\] Rule engine initialized"
check "\[SLM\] Ready"
check "\[BOOT\] OK"

# ----- networking acceptance: net_dhcp_ip + http_get ------------------------
# Boot once more with a SLIRP-backed e1000 and a host port-forward, drive the
# chat to start the web server, then confirm a DHCP lease and a real HTTP 200.
# Set SKIP_NET=1 to skip (e.g. environments without user-mode networking).
if [ "${SKIP_NET:-0}" != "1" ]; then
	NET_LOG="$(mktemp)"
	HOST_PORT="${HTTP_PORT:-8080}"
	# Drive the REPL: blank line (absorbs the dropped first byte), then the
	# web-server command; keep stdin open while we probe.
	( printf '\nbe a web server\n'; sleep "${NET_SERVE_SECS:-40}" ) | \
		timeout "${NET_TIMEOUT:-70}" qemu-system-x86_64 -cdrom build/auton.iso \
		-serial stdio -display none -no-reboot -m "${MEM:-128M}" \
		-nic "user,model=e1000,hostfwd=tcp::${HOST_PORT}-:80" \
		>"$NET_LOG" 2>/dev/null &
	QPID=$!

	# Probe the forwarded port until the server answers (or we give up).
	# Use bash /dev/tcp (no curl dependency in the base image).
	http_get() {
		exec 3<>"/dev/tcp/127.0.0.1/${HOST_PORT}" 2>/dev/null || return 1
		printf 'GET / HTTP/1.0\r\n\r\n' >&3
		timeout 5 cat <&3
		exec 3>&- 2>/dev/null || true
	}
	BODY=""
	for _ in $(seq 1 12); do
		sleep 4
		BODY="$(http_get || true)"
		[ -n "$BODY" ] && break
	done
	kill "$QPID" 2>/dev/null || true
	wait "$QPID" 2>/dev/null || true

	NET_OUT="$(cat "$NET_LOG")"
	rm -f "$NET_LOG"
	echo "----- net serial (tail) -----"
	echo "$NET_OUT" | grep -E '\[NET\]|\[HTTP\]|auton>' || true
	echo "-----------------------------"

	# net_dhcp_ip: a DHCP-assigned address appeared.
	if echo "$NET_OUT" | grep -qE "\[NET\] IP [0-9]+\.[0-9]+\.[0-9]+\.[0-9]+"; then
		echo "PASS  net_dhcp_ip"
	else
		echo "FAIL  net_dhcp_ip"; fail=1
	fi

	# http_get: the in-kernel web server returned a page over real TCP.
	if printf '%s' "$BODY" | grep -qi "AUTON"; then
		echo "PASS  http_get"
	else
		echo "FAIL  http_get (body='$(printf '%s' "$BODY" | head -c 80)')"; fail=1
	fi
fi

if [ "$fail" -eq 0 ]; then
	echo "ALL PASS"
else
	echo "FAILURES"
	exit 1
fi
