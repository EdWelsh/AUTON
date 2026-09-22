#!/usr/bin/env bash
# Materialise an agreed kernel base into a directory, outside the repo's index.
#
#   scripts/kernel-base.sh <dir> [--git] [--rev TAG]
#
# This project does not contain a kernel; the agents write it. But a service or
# driver experiment needs a starting tree, and which one decides what a gate
# refusal means. w11's F6 was seeded from kernel-reference-v1, which predates
# F4's static-IP setup.c and weak service_main, and got a [gate: link closure]
# refusal no agent could have avoided. kernel-base-v2 is that tree plus F4's
# hooks, and v3 adds the model-format-v3 loader; see agent/kernel_spec/reference/README.md "Bases".
#
#   --git        initialise <dir> as a git repo on `main` (GitWorkspace needs one)
#   --rev TAG    another base (default: kernel-base-v3)
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

DIR="" GIT=0 REV="kernel-base-v3"
while [ $# -gt 0 ]; do
	case "$1" in
		--git) GIT=1; shift ;;
		--rev) REV="${2:?--rev needs a tag}"; shift 2 ;;
		--rev=*) REV="${1#*=}"; shift ;;
		-h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
		-*) echo "unknown argument: $1" >&2; exit 2 ;;
		*) DIR="$1"; shift ;;
	esac
done
[ -n "$DIR" ] || { echo "usage: $0 <dir> [--git] [--rev TAG]" >&2; exit 2; }

if ! git -C "$ROOT" rev-parse -q --verify "refs/tags/$REV" >/dev/null; then
	echo "no tag $REV in this clone. A shallow or tagless clone has no bases:" >&2
	echo "  git fetch --tags" >&2
	exit 2
fi
if [ -e "$DIR" ] && [ -n "$(ls -A "$DIR" 2>/dev/null)" ]; then
	echo "$DIR exists and is not empty; refusing to extract a base over it" >&2
	exit 2
fi

mkdir -p "$DIR"
git -C "$ROOT" archive "$REV" kernels/x86_64 | tar -x -C "$DIR" --strip-components=2 || {
	echo "extracting $REV failed" >&2; exit 1; }

if [ "$GIT" = 1 ]; then
	git -C "$DIR" init -q -b main
	git -C "$DIR" add -A
	git -C "$DIR" -c user.email=base@auton -c user.name=kernel-base \
		commit -qm "base: $REV" || exit 1
fi
echo "$DIR: $REV ($(git -C "$ROOT" rev-parse --short "$REV^{commit}")), $(find "$DIR" -type f -not -path '*/.git/*' | wc -l | tr -d ' ') files"
