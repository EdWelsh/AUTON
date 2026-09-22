#!/usr/bin/env bash
# Storage acceptance: what a booted image keeps, checked by clients this
# project did not write.
#
#   scripts/run-storage-acceptance.sh <tree>                       # F7: disk read-back
#   scripts/run-storage-acceptance.sh <tree> --service kvstore     # F9: two boots, redis-cli
#   scripts/run-storage-acceptance.sh <tree> --service smtp        # F11: two boots, smtplib
#   scripts/run-storage-acceptance.sh <tree> --service fileserver  # F8: curl what mcopy put there
#
# The service modes boot the SAME disk image twice, untouched in between. That
# is the whole point: "it stored the value" is not worth claiming until the
# value is still there after the machine stopped.
#
# Exit 0 pass; 1 wrong (a marker's value, or the read-back); 2 not generated
# (no tree, no build, or a marker never printed: the component is absent).
#
# NOTE: the positive path of each --service mode is unexercised until a tree
# implements that service. What IS exercised today is every refusal: against
# kernel-base-v5 each mode exits 2 naming exactly what is missing.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

TREE="${1:-}"
shift || true
SERVICE=""
while [ $# -gt 0 ]; do
	case "$1" in
		--service) SERVICE="${2:-}"; shift 2 ;;
		*) echo "unknown argument $1" >&2; exit 2 ;;
	esac
done
[ -n "$TREE" ] && [ -d "$TREE/kernel" ] || {
	echo "usage: $0 <kernel tree> [--service kvstore|smtp|fileserver]" >&2; exit 2; }
TREE="$(cd "$TREE" && pwd)"
for tool in mformat mcopy mtype; do
	command -v "$tool" >/dev/null || { echo "missing $tool (brew install mtools)" >&2; exit 2; }
done

SEED_TXT='AUTON storage seed: the kernel reads this file.'
# The exact bytes the kernel writes to /AUTON.TXT (fs.md, "Markers").
AUTON_TXT='written by AUTON'
SECTORS=1048576
BOOT_TIMEOUT="${BOOT_TIMEOUT:-90}"
PY="${PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY=python3

WORK="$(mktemp -d)"
[ -n "${KEEP_WORK:-}" ] && echo "work: $WORK" || trap 'rm -rf "$WORK"' EXIT
IMG="$WORK/disk.img"
QPID=""

fail=0
absent=0

note()    { printf '%s\n' "$*"; }
wrong()   { printf 'WRONG  %s\n' "$*"; fail=1; }
missing() { printf 'NOT GENERATED  %s\n' "$*"; absent=1; }

# ---- the disk ---------------------------------------------------------------
make_disk() {
	dd if=/dev/zero of="$IMG" bs=512 count=0 seek="$SECTORS" 2>/dev/null
	mformat -F -T "$SECTORS" -i "$IMG" :: || { echo "mformat failed" >&2; exit 2; }
	printf '%s' "$SEED_TXT" >"$WORK/SEED.TXT"
	mcopy -i "$IMG" "$WORK/SEED.TXT" ::SEED.TXT || { echo "mcopy failed" >&2; exit 2; }
}

# ---- building ---------------------------------------------------------------
build_plain() {
	( cd "$TREE" && make iso >"$WORK/build.log" 2>&1 ) || {
		missing "the tree does not build (tail of the log follows)"
		tail -15 "$WORK/build.log"
		exit 2
	}
	echo "$TREE/build/auton.iso"
}

build_service() {
	local name="$1"
	"$PY" "$ROOT/agent/tools/build_service.py" "$name" --tree "$TREE" --iso \
		>"$WORK/build-$name.log" 2>&1 || {
			missing "build_service.py $name failed: the service is not in this tree"
			tail -12 "$WORK/build-$name.log"
			exit 2
		}
	local iso="$TREE/build-$name/auton.iso"
	[ -f "$iso" ] || iso="$TREE/build/auton.iso"
	echo "$iso"
}

# ---- booting ----------------------------------------------------------------
# boot <iso> <serial log> <marker regex> [hostfwd spec]
boot() {
	local iso="$1" serial="$2" marker="$3" fwd="${4:-}"
	: >"$serial"
	local net=()
	[ -n "$fwd" ] && net=(-nic "user,model=e1000,$fwd")
	# -boot d: the firmware tries the disk first otherwise, and mformat's boot
	# sector is a stub that prints "not a bootable disk" and hangs.
	auton_timeout "$BOOT_TIMEOUT" "$QEMU" -boot d -cdrom "$iso" \
		-serial "file:$serial" -display none -no-reboot -m "${MEM:-256M}" \
		-drive "file=$IMG,if=virtio,format=raw,cache=writethrough" \
		"${net[@]+${net[@]}}" </dev/null >/dev/null 2>&1 &
	QPID=$!
	local i
	for i in $(seq 1 "$BOOT_TIMEOUT"); do
		grep -qaE "$marker" "$serial" && return 0
		kill -0 "$QPID" 2>/dev/null || return 1
		sleep 1
	done
	return 1
}

# Stop QEMU and WAIT for it, so the image on disk is the one it flushed.
stop_qemu() {
	sleep 1
	[ -n "$QPID" ] && kill "$QPID" 2>/dev/null
	[ -n "$QPID" ] && wait "$QPID" 2>/dev/null
	pkill -f "file=$IMG" 2>/dev/null
	local i
	for i in 1 2 3 4 5; do pgrep -f "file=$IMG" >/dev/null || break; sleep 1; done
	QPID=""
}

free_port() {
	"$PY" -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()'
}

show_serial() {
	echo "----- serial -----"
	grep -aE '\[BLK\]|\[FS\]|\[KV\]|\[SMTP\]|\[HTTP\]|\[NET\]|\[BOOT\]' "$1" || true
	echo "------------------"
}

need() {    # need <serial> <fixed marker> <expected line, regex>
	local serial="$1" fixed="$2" want="$3"
	if ! grep -aqF "$fixed" "$serial"; then
		missing "$fixed"
	elif grep -aqE "$want" "$serial"; then
		note "PASS  $fixed"
	else
		wrong "$fixed: expected /$want/"
	fi
}

# ---- F7: the disk read-back --------------------------------------------------
mode_disk() {
	local iso serial="$WORK/serial.log"
	iso="$(build_plain)"
	make_disk
	boot "$iso" "$serial" '\[FS\] wrote AUTON.TXT' || true
	stop_qemu
	show_serial "$serial"

	need "$serial" "[BLK] virtio-blk up" '\[BLK\] virtio-blk up'
	need "$serial" "[BLK] capacity" "\[BLK\] capacity $SECTORS sectors"
	need "$serial" "[FS] mounted" '\[FS\] mounted fat32'
	need "$serial" "[FS] read SEED.TXT" "\[FS\] read SEED.TXT ${#SEED_TXT} bytes"
	need "$serial" "[FS] wrote AUTON.TXT" '\[FS\] wrote AUTON.TXT'

	if [ "$absent" -eq 0 ]; then
		local got
		got="$(mtype -i "$IMG" ::AUTON.TXT 2>&1)"
		[ "$got" = "$AUTON_TXT" ] && note "PASS  host read-back: '$AUTON_TXT'" \
			|| wrong "host read-back: '$got', expected '$AUTON_TXT'"
		if command -v fsck.fat >/dev/null; then
			fsck.fat -n "$IMG" >"$WORK/fsck.log" 2>&1 && note "PASS  fsck.fat -n" \
				|| { wrong "fsck.fat -n:"; cat "$WORK/fsck.log"; }
		fi
	fi
}

# ---- F9: the KV store, twice -------------------------------------------------
mode_kvstore() {
	command -v redis-cli >/dev/null || {
		echo "missing redis-cli: this mode's oracle is a client we did not write" >&2
		exit 2; }
	local iso port serial1="$WORK/boot1.log" serial2="$WORK/boot2.log"
	iso="$(build_service kvstore)"
	make_disk
	port="$(free_port)"

	boot "$iso" "$serial1" '\[KV\] listening on :6379' "hostfwd=tcp::$port-:6379" || {
		show_serial "$serial1"; stop_qemu; missing "[KV] listening on :6379"; exit 2; }

	redis-cli -h 127.0.0.1 -p "$port" SET alpha one   >"$WORK/c1.log" 2>&1
	redis-cli -h 127.0.0.1 -p "$port" SET beta  two   >>"$WORK/c1.log" 2>&1
	redis-cli -h 127.0.0.1 -p "$port" SET gamma three >>"$WORK/c1.log" 2>&1
	redis-cli -h 127.0.0.1 -p "$port" DEL beta        >>"$WORK/c1.log" 2>&1
	# SHUTDOWN flushes and halts: that is how the image is left consistent.
	redis-cli -h 127.0.0.1 -p "$port" SHUTDOWN        >>"$WORK/c1.log" 2>&1 || true
	stop_qemu
	show_serial "$serial1"
	grep -qa '\[KV\] clean shutdown' "$serial1" || wrong "no [KV] clean shutdown"

	# The same image, untouched, booted again.
	port="$(free_port)"
	boot "$iso" "$serial2" '\[KV\] listening on :6379' "hostfwd=tcp::$port-:6379" \
		|| wrong "the image did not boot a second time"
	need "$serial2" "[KV] replayed" '\[KV\] replayed 4 records'

	local alpha gamma beta
	alpha="$(redis-cli -h 127.0.0.1 -p "$port" --no-raw GET alpha 2>&1)"
	gamma="$(redis-cli -h 127.0.0.1 -p "$port" --no-raw GET gamma 2>&1)"
	beta="$(redis-cli -h 127.0.0.1 -p "$port" --no-raw GET beta 2>&1)"
	stop_qemu
	[ "$alpha" = '"one"' ]   || wrong "alpha after reboot: $alpha"
	[ "$gamma" = '"three"' ] || wrong "gamma after reboot: $gamma"
	case "$beta" in *nil*) note "PASS  the deleted key is still deleted" ;;
	                *) wrong "beta should be nil after reboot: $beta" ;; esac
	[ "$fail" -eq 0 ] && note "PASS  values written by redis-cli survived a reboot"
}

# ---- F11: mail, twice --------------------------------------------------------
mode_smtp() {
	local iso port serial1="$WORK/boot1.log" serial2="$WORK/boot2.log"
	iso="$(build_service smtp)"
	make_disk
	port="$(free_port)"

	boot "$iso" "$serial1" '\[SMTP\] listening on :25' "hostfwd=tcp::$port-:25" || {
		show_serial "$serial1"; stop_qemu; missing "[SMTP] listening on :25"; exit 2; }

	# smtplib is the oracle: a standard client, not ours.
	if ! "$PY" - "$port" <<'EOF' >"$WORK/mail.log" 2>&1
import smtplib, sys
port = int(sys.argv[1])
with smtplib.SMTP("127.0.0.1", port, timeout=30) as s:
    for i in range(3):
        s.sendmail("sender@example.com", ["you@auton.local"],
                   f"Subject: message {i}\r\n\r\nbody {i}\r\n")
EOF
	then
		wrong "smtplib could not deliver: $(tail -3 "$WORK/mail.log")"
	fi
	stop_qemu
	show_serial "$serial1"

	port="$(free_port)"
	boot "$iso" "$serial2" '\[SMTP\] listening on :25' "hostfwd=tcp::$port-:25" \
		|| wrong "the image did not boot a second time"
	need "$serial2" "[SMTP] 3 message(s) on disk" '\[SMTP\] 3 message\(s\) on disk'
	stop_qemu
	# The files are on the volume, so the host reads them without the guest.
	local listing
	listing="$(mdir -i "$IMG" ::/MAIL 2>&1 || true)"
	case "$listing" in *M0000001*) note "PASS  /MAIL/M0000001.EML is on the volume" ;;
	                   *) wrong "no numbered mail on the volume: $listing" ;; esac
	[ "$fail" -eq 0 ] && note "PASS  mail delivered by smtplib survived a reboot"
}

# ---- F8: the file server -----------------------------------------------------
mode_fileserver() {
	local iso port body serial="$WORK/serial.log"
	iso="$(build_service fileserver)"
	make_disk
	# The content is put there by the HOST, which is the F8 signal: adding a
	# file to the site is an mcopy, not a rebuild.
	printf '<h1>served from the disk</h1>\n' >"$WORK/index.html"
	mcopy -i "$IMG" "$WORK/index.html" ::index.html

	port="$(free_port)"
	boot "$iso" "$serial" '\[HTTP\] listening on :80' "hostfwd=tcp::$port-:80" || {
		show_serial "$serial"; stop_qemu; missing "[HTTP] listening on :80"; exit 2; }
	body="$(curl -fsS "http://127.0.0.1:$port/index.html" 2>&1)"
	stop_qemu
	show_serial "$serial"
	[ "$body" = "$(cat "$WORK/index.html")" ] \
		&& note "PASS  curl retrieved the bytes mcopy put on the disk" \
		|| wrong "curl returned: $body"
}

case "$SERVICE" in
	"")          mode_disk ;;
	kvstore)     mode_kvstore ;;
	smtp)        mode_smtp ;;
	fileserver)  mode_fileserver ;;
	*) echo "unknown service '$SERVICE' (kvstore, smtp, fileserver)" >&2; exit 2 ;;
esac

# Wrong outranks absent: a component that printed a wrong value exists.
[ "$fail" -eq 1 ] && exit 1
[ "$absent" -eq 1 ] && exit 2
echo "acceptance${SERVICE:+ ($SERVICE)}: PASS"
exit 0
