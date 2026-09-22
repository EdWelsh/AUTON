#!/usr/bin/env bash
# FAT32 against an independent oracle: mtools builds the volumes, the FAT32
# under test reads and writes them, and mtools reads back what it wrote.
#
#   tests/kernel/run_fat32_test.sh --self-test         # against fat32_reference/
#   KERNEL_TREE=<dir> tests/kernel/run_fat32_test.sh   # against a generated tree
#
# Requires mtools (brew/apt install mtools); fsck.fat from dosfstools is used
# when present as a second structural check. exit 2 = not generated or tools
# absent, exit 1 = wrong.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
CC="${HOST_CC:-clang}"
FLAGS=(-O1 -g -fsanitize=address,undefined -fno-sanitize-recover=undefined)
PATH="$PATH:/opt/homebrew/sbin:/usr/sbin:/sbin"

for t in mformat mcopy mtype mmd mdel mdir; do
	command -v "$t" >/dev/null || { echo "SKIP: $t not found (install mtools)" >&2; exit 2; }
done
echo "oracle: $(mtools --version 2>&1 | head -1)"

if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/fat32_reference/)"
	INC="$HERE/fat32_reference/include"
	SRCS=("$HERE/fat32_reference/fat32.c" "$HERE/fat32_reference/fat32_write.c")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -f "$KERNEL_TREE/kernel/fs/fat32.c" ]; then
		echo "no kernel/fs/fat32.c in $KERNEL_TREE: FAT32 is specified in fs.md and" >&2
		echo "not generated into this tree. Run --self-test to check the suite." >&2
		exit 2
	fi
	INC="$KERNEL_TREE/kernel/include"
	SRCS=("$KERNEL_TREE/kernel/fs/fat32.c")
	[ -f "$KERNEL_TREE/kernel/fs/fat32_write.c" ] && SRCS+=("$KERNEL_TREE/kernel/fs/fat32_write.c")
fi

W="$(mktemp -d)"
trap 'rm -rf "$W"' EXIT
OUT="$W/fat32_test"
"$CC" "${FLAGS[@]}" -I"$INC" "$HERE/fat32_test.c" "${SRCS[@]}" -o "$OUT" || {
	echo "compile failed: the FAT32 under test does not match fs.md's interface" >&2
	exit 1
}

# --- volumes, built by the oracle --------------------------------------------
mk() { dd if=/dev/zero of="$1" bs=512 count="$2" 2>/dev/null; }
VOL="$W/volume.img"
mk "$VOL" 131072                                 # 64 MiB
mformat -i "$VOL" -T 131072 -F -c 1 :: || exit 1 # FAT32, 1 sector/cluster
python3 - "$W" <<'PY'
import sys, pathlib
w = pathlib.Path(sys.argv[1])
(w/"SEED.TXT").write_bytes(bytes(b"0123456789abcdef"[i % 16] for i in range(1000)))
(w/"long.txt").write_bytes(b"long name content\n")
(w/"NESTED.TXT").write_bytes(b"nested\n")
(w/"BIG.BIN").write_bytes(bytes((i * 7 + 3) & 0xFF for i in range(70000)))
(w/"HOLE.BIN").write_bytes(b"h" * 1536)          # 3 clusters, deleted below
(w/"AFTER.BIN").write_bytes(b"a" * 512)
PY
mcopy -i "$VOL" "$W/SEED.TXT" ::SEED.TXT
mcopy -i "$VOL" "$W/long.txt" "::A long file name.txt"
mmd   -i "$VOL" ::DIR
mcopy -i "$VOL" "$W/NESTED.TXT" ::DIR/NESTED.TXT
mcopy -i "$VOL" "$W/BIG.BIN" ::BIG.BIN
mcopy -i "$VOL" "$W/HOLE.BIN" ::HOLE.BIN
mcopy -i "$VOL" "$W/AFTER.BIN" ::AFTER.BIN
mdel  -i "$VOL" ::HOLE.BIN
cp "$VOL" "$W/scratch.img"
F16="$W/fat16.img"
mk "$F16" 32768                                  # 16 MiB: FAT16 by cluster count
mformat -i "$F16" -T 32768 :: || exit 1

"$OUT" "$VOL" "$W/scratch.img" "$F16"
rc=$?

# --- the oracle reads back what was written ------------------------------------
echo "--- mtools reads the written volume ---"
check() { # name, cmd-output, expected-file
	if cmp -s "$2" "$3"; then echo "PASS  mtools: $1"; else echo "FAIL  mtools: $1"; rc=1; fi
}
printf 'hello from the reference\nsecond line\n' > "$W/want.wrote"
mtype -i "$VOL" ::WROTE.TXT > "$W/got.wrote" 2>/dev/null
check "WROTE.TXT reads back byte for byte" "$W/got.wrote" "$W/want.wrote"
python3 -c "
import sys; n=5*512+100
sys.stdout.buffer.write(bytes((i*13+1)&0xFF for i in range(n)))" > "$W/want.frag"
mcopy -i "$VOL" ::FRAG.BIN "$W/got.frag" 2>/dev/null
check "FRAG.BIN (fragmented chain) reads back intact" "$W/got.frag" "$W/want.frag"
printf 'Subject: hi\r\n\r\nbody\r\n' > "$W/want.eml"
mcopy -i "$VOL" ::MAILDIR/M0000001.EML "$W/got.eml" 2>/dev/null
check "MAILDIR/M0000001.EML in the new directory" "$W/got.eml" "$W/want.eml"
mcopy -i "$VOL" ::SEED.TXT "$W/got.seed" 2>/dev/null
check "SEED.TXT untouched by the writes" "$W/got.seed" "$W/SEED.TXT"
if mdir -i "$VOL" ::TRUNC.BIN 2>/dev/null | grep -Eq "TRUNC +BIN +100 "; then
	echo "PASS  mtools: TRUNC.BIN is 100 bytes"
else
	echo "FAIL  mtools: TRUNC.BIN is 100 bytes"; mdir -i "$VOL" ::TRUNC.BIN; rc=1
fi
if command -v fsck.fat >/dev/null; then
	if fsck.fat -n "$VOL" >"$W/fsck.log" 2>&1; then
		echo "PASS  fsck.fat -n: no errors"
	else
		echo "FAIL  fsck.fat -n"; cat "$W/fsck.log"; rc=1
	fi
else
	echo "NOTE  fsck.fat not found (dosfstools): structural check skipped"
fi
exit "$rc"
