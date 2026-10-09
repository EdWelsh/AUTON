#!/usr/bin/env bash
# Deploy a built AUTON ISO as a container (Rancher/Docker), and talk to it from outside.
#
#   scripts/auton-container.sh build <iso> [tag]        # -> image `auton-os:<tag>`
#   scripts/auton-container.sh run   <tag> [name]       # detached; serial in `docker logs`, QMP on :4444
#   scripts/auton-container.sh wait  <name> <regex> [s] # exit 0 when the serial log matches
#   scripts/auton-container.sh stop  <name>
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HERE="$ROOT/scripts/auton-container"
cmd="${1:?build|run|wait|stop}"; shift
case "$cmd" in
build)
	iso="${1:?iso}"; tag="${2:-latest}"
	ctx="$(mktemp -d)"; cp "$HERE/Dockerfile" "$HERE/run.sh" "$ctx/"; cp "$iso" "$ctx/auton.iso"
	docker build -q -t "auton-os:$tag" "$ctx" >/dev/null && echo "auton-os:$tag"
	rc=$?; rm -rf "$ctx"; exit $rc ;;
run)
	tag="${1:?tag}"; name="${2:-auton-$$}"
	args=(-d --name "$name" -p 127.0.0.1::4444 -p 127.0.0.1::5900)
	[ -e /dev/kvm ] && args+=(--device /dev/kvm)
	docker run "${args[@]}" "auton-os:${tag#auton-os:}" >/dev/null || exit 2
	echo "$name qmp=$(docker port "$name" 4444 | head -1)" ;;
wait)
	name="${1:?name}"; re="${2:?regex}"; limit="${3:-120}"; t=0
	while [ "$t" -lt "$limit" ]; do
		docker logs "$name" 2>&1 | grep -Eq "$re" && exit 0
		[ "$(docker inspect -f '{{.State.Running}}' "$name" 2>/dev/null)" = "true" ] || exit 1
		sleep 2; t=$((t+2))
	done; exit 1 ;;
stop) docker rm -f "${1:?name}" >/dev/null ;;
*) echo "unknown command $cmd" >&2; exit 2 ;;
esac
