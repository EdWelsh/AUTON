#!/usr/bin/env bash
# Host suite for the repository server (agent/kernel_spec/services/host-repo.md).
#
#   tests/kernel/run_host_repo_test.sh --self-test   # index, query string, traversal
#   tests/kernel/run_host_repo_test.sh --clone       # the layout, proved by git itself
#   KERNEL_TREE=<dir> tests/kernel/run_host_repo_test.sh
#
# Both modes build a REAL bare repository with git and pack it the way the
# packaging step does. Testing a CPIO reader against an archive the test wrote
# itself would prove only self-consistency.
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${TMPDIR:-/tmp}/auton_host_repo_test"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT
CC="${CC_HOST:-clang}"
command -v "$CC" >/dev/null 2>&1 || CC=cc
command -v git >/dev/null || { echo "git is required" >&2; exit 2; }

# ---- a real repository, packed the way the image will carry it -------------
build_archive() {
	local src="$WORK/src" bare="$WORK/repo.git"
	mkdir -p "$src"
	git -C "$src" init -q -b main
	printf 'hello\n' >"$src/README.md"
	mkdir -p "$src/dir"
	printf 'nested\n' >"$src/dir/file.txt"
	git -C "$src" add -A
	git -C "$src" -c user.email=t@auton -c user.name=auton commit -qm "first"
	git clone -q --bare "$src" "$bare"
	# Without this there is no info/refs or objects/info/packs, and a dumb
	# clone cannot enumerate anything.
	git -C "$bare" update-server-info
	( cd "$bare" && find . -type f | sed 's|^\./||' | cpio -o -H newc --quiet ) \
		>"$WORK/repo.cpio" 2>/dev/null
	echo "$WORK/repo.cpio"
}

# A second archive holding what a BROKEN resolver would reach, so the traversal
# and decode tests are not vacuous: with a strict archive every hostile path is
# simply absent, and a resolver with no checks at all still returns -1.
#
#   ../outside.txt      a member whose name escapes the archive root
#   %2e%2e.txt          a member whose NAME contains percent escapes: decoding
#                       once finds it, decoding twice turns it into ...txt
build_hostile_archive() {
	local d="$WORK/hostile"
	mkdir -p "$d/sub"
	printf 'secret\n' >"$d/outside.txt"
	# A literal filename, not a printf format: single %, hence quoted.
	printf 'legal\n' >"$d/sub/%2e%2e.txt"
	( cd "$d/sub" && printf '../outside.txt\n%%2e%%2e.txt\n' | cpio -o -H newc --quiet ) \
		>"$WORK/hostile.cpio" 2>/dev/null
	echo "$WORK/hostile.cpio"
}

# A bare repo that nobody ran update-server-info on: not clonable over dumb
# HTTP, and init must say so rather than serving it.
build_unservable_archive() {
	local bare="$WORK/repo.git" d="$WORK/unservable"
	rm -rf "$d"; mkdir -p "$d"
	( cd "$bare" && find . -type f | sed 's|^\./||' | grep -v '^info/refs$' \
		| cpio -o -H newc --quiet ) >"$WORK/unservable.cpio" 2>/dev/null
	echo "$WORK/unservable.cpio"
}

# ---- --clone: the layout, graded by git ------------------------------------
if [ "${1:-}" = "--clone" ]; then
	build_archive >/dev/null
	SERVE="$WORK/serve"
	mkdir -p "$SERVE"
	( cd "$SERVE" && cpio -idm --quiet <"$WORK/repo.cpio" )
	PORT="$(python3 -c 'import socket;s=socket.socket();s.bind(("127.0.0.1",0));print(s.getsockname()[1]);s.close()')"
	( cd "$SERVE" && python3 -m http.server "$PORT" --bind 127.0.0.1 >/dev/null 2>&1 ) &
	SRV=$!
	# `wait` after the kill keeps the shell's "Terminated" notice off the output.
	trap 'kill $SRV 2>/dev/null; wait $SRV 2>/dev/null; rm -rf "$WORK"' EXIT
	for _ in $(seq 1 40); do
		curl -fsS "http://127.0.0.1:$PORT/info/refs" >/dev/null 2>&1 && break
		sleep 0.25
	done
	if ! git clone -q "http://127.0.0.1:$PORT/" "$WORK/clone" 2>"$WORK/clone.log"; then
		echo "FAIL  git clone over dumb HTTP:"
		sed 's/^/      /' "$WORK/clone.log" | head -10
		exit 1
	fi
	want="$(git -C "$WORK/repo.git" rev-parse HEAD)"
	got="$(git -C "$WORK/clone" rev-parse HEAD)"
	echo "clone HEAD $got"
	[ "$want" = "$got" ] || { echo "FAIL  clone HEAD $got != origin $want"; exit 1; }
	grep -q hello "$WORK/clone/README.md" && [ -f "$WORK/clone/dir/file.txt" ] || {
		echo "FAIL  the working tree does not match"; exit 1; }
	echo "PASS  git clone over the dumb-HTTP layout, HEAD and files match"
	exit 0
fi

# ---- the C suite ------------------------------------------------------------
if [ "${1:-}" = "--self-test" ]; then
	echo "self-test: reference implementation (tests/kernel/host_repo_reference/)"
	SOURCES=("$HERE/host_repo_reference/host_repo.c")
	INC=(-I"$HERE/host_repo_reference/include")
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	case "$KERNEL_TREE" in /*) ;; *) KERNEL_TREE="$ROOT/$KERNEL_TREE";; esac
	if [ ! -d "$KERNEL_TREE/kernel" ]; then
		echo "no kernel tree at $KERNEL_TREE — nothing to verify." >&2
		exit 2
	fi
	SOURCES=()
	for c in kernel/services/host-repo/host_repo.c kernel/services/host_repo/host_repo.c; do
		[ -f "$KERNEL_TREE/$c" ] && SOURCES+=("$KERNEL_TREE/$c")
	done
	if [ "${#SOURCES[@]}" -eq 0 ]; then
		echo "not generated: no kernel/services/host-repo/host_repo.c in $KERNEL_TREE." >&2
		exit 2
	fi
	INC=(-I"$KERNEL_TREE/kernel/include" -I"$HERE/host_repo_reference/include")
fi

ARCHIVE="$(build_archive)"
HOSTILE="$(build_hostile_archive)"
UNSERVABLE="$(build_unservable_archive)"
"$CC" -O1 -g -fsanitize=address,undefined "${INC[@]}" \
	"$HERE/host_repo_test.c" "${SOURCES[@]}" -o "$OUT" || {
		echo "compile failed — the implementation does not match host-repo.md" >&2
		exit 1
	}
exec "$OUT" "$ARCHIVE" "$HOSTILE" "$UNSERVABLE"
