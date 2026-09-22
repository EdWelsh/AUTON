#!/usr/bin/env bash
# Storage acceptance (factory F7): the booted kernel writes a file the host reads back.
#
#   scripts/run-storage-acceptance.sh <kernel tree>
#
# 1. build the tree's ISO
# 2. mformat a 512 MiB FAT32 image (1048576 sectors: what the [BLK] marker asserts)
#    and mcopy SEED.TXT onto it
# 3. boot with the image as a virtio-blk disk; wait for the markers in fs.md and
#    virtio-blk.md, then stop QEMU and WAIT for it to exit, so the image on disk is
#    the one QEMU flushed (reading it mid-run reads a stale image)
# 4. mtype ::AUTON.TXT must equal AUTON_TXT below, byte for byte
#
# Exit 0 pass; 1 wrong (a marker's value, or the host read-back); 2 not generated
# (no tree, no build, or a marker never printed: the component is absent).
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=lib/toolchain.sh
source "$ROOT/scripts/lib/toolchain.sh"

TREE="${1:-}"
[ -n "$TREE" ] && [ -d "$TREE/kernel" ] || { echo "usage: $0 <kernel tree>" >&2; exit 2; }
TREE="$(cd "$TREE" && pwd)"
for tool in mformat mcopy mtype; do
	command -v "$tool" >/dev/null || { echo "missing $tool (brew install mtools)" >&2; exit 2; }
done

SEED_TXT='AUTON storage seed: the kernel reads this file.'
# The exact bytes the kernel writes to /AUTON.TXT (fs.md, "Markers").
AUTON_TXT='written by AUTON'
SECTORS=1048576
BOOT_TIMEOUT="${BOOT_TIMEOUT:-90}"

WORK="$(mktemp -d)"
[ -n "${KEEP_WORK:-}" ] && echo "work: $WORK" || trap 'rm -rf "$WORK"' EXIT

( cd "$TREE" && make iso >"$WORK/build.log" 2>&1 ) || {
	echo "NOT GENERATED  the tree does not build (tail of the log follows)"
	tail -15 "$WORK/build.log"
	exit 2
}

IMG="$WORK/disk.img"
dd if=/dev/zero of="$IMG" bs=512 count=0 seek="$SECTORS" 2>/dev/null
mformat -F -T "$SECTORS" -i "$IMG" :: || { echo "mformat failed" >&2; exit 2; }
printf '%s' "$SEED_TXT" >"$WORK/SEED.TXT"
mcopy -i "$IMG" "$WORK/SEED.TXT" ::SEED.TXT || { echo "mcopy failed" >&2; exit 2; }

SERIAL="$WORK/serial.log"
: >"$SERIAL"
# cache=writethrough: a write the guest completed is in the host file.
# -boot d: the firmware tries the disk before the CD otherwise, and mformat's
# boot sector is a stub that prints "not a bootable disk" and hangs.
auton_timeout "$BOOT_TIMEOUT" "$QEMU" -boot d -cdrom "$TREE/build/auton.iso" \
	-serial "file:$SERIAL" -display none -no-reboot -m "${MEM:-256M}" \
	-drive "file=$IMG,if=virtio,format=raw,cache=writethrough" \
	</dev/null >/dev/null 2>&1 &
QPID=$!
for _ in $(seq 1 "$BOOT_TIMEOUT"); do
	grep -q '\[FS\] wrote AUTON.TXT' "$SERIAL" && break
	kill -0 "$QPID" 2>/dev/null || break
	sleep 1
done
sleep 1
kill "$QPID" 2>/dev/null
wait "$QPID" 2>/dev/null
# auton_timeout's QEMU child may outlive the wrapper for a moment.
pkill -f "file=$IMG" 2>/dev/null
for _ in 1 2 3 4 5; do pgrep -f "file=$IMG" >/dev/null || break; sleep 1; done

echo "----- serial ([BLK] [FS] [BOOT]) -----"
grep -aE '\[BLK\]|\[FS\]|\[BOOT\]' "$SERIAL" || true
echo "--------------------------------------"

absent=0 wrong=0
need() {    # need <fixed marker prefix> <full expected line, regex>
	if ! grep -aqF "$1" "$SERIAL"; then
		echo "NOT GENERATED  $1"; absent=1
	elif grep -aqE "$2" "$SERIAL"; then
		echo "PASS  $1"
	else
		echo "WRONG  $1: expected /$2/"; wrong=1
	fi
}
need "[BLK] virtio-blk up" '\[BLK\] virtio-blk up'
need "[BLK] capacity" "\[BLK\] capacity $SECTORS sectors"
need "[FS] mounted" '\[FS\] mounted fat32'
need "[FS] read SEED.TXT" "\[FS\] read SEED.TXT ${#SEED_TXT} bytes"
need "[FS] wrote AUTON.TXT" '\[FS\] wrote AUTON.TXT'

if [ "$absent" -eq 0 ]; then
	got="$(mtype -i "$IMG" ::AUTON.TXT 2>&1)"
	if [ "$got" = "$AUTON_TXT" ]; then
		echo "PASS  host read-back: mtype ::AUTON.TXT = '$AUTON_TXT'"
	else
		echo "WRONG  host read-back: mtype ::AUTON.TXT = '$got', expected '$AUTON_TXT'"; wrong=1
	fi
	if command -v fsck.fat >/dev/null; then
		fsck.fat -n "$IMG" >"$WORK/fsck.log" 2>&1 && echo "PASS  fsck.fat -n" \
			|| { echo "WRONG  fsck.fat -n:"; cat "$WORK/fsck.log"; wrong=1; }
	fi
fi

# Wrong outranks absent: a component that printed a wrong value exists.
[ "$wrong" -eq 1 ] && exit 1
[ "$absent" -eq 1 ] && exit 2
echo "storage acceptance: PASS"
exit 0
