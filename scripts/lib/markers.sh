#!/usr/bin/env bash
# Serial-marker sets, read from their single source of truth.
#
#   source "$ROOT/scripts/lib/markers.sh"
#   markers_load boot          # -> MARKERS array
#   markers_check "$SERIAL"    # -> PASS/FAIL per marker; sets MARKERS_FAILED
#
# The patterns live in agent/kernel_spec/tests/acceptance_tests.py
# (SERIAL_MARKER_SETS). Shell harnesses used to keep their own copy, which
# drifted — the shell checked markers the Python file had never heard of. Ask
# for them instead of restating them.

# markers_load <set-name>
# Fills the global MARKERS array. Fails loudly: an empty or missing set must
# never read as "zero markers, all passed".
markers_load() {
	local set_name="$1"
	local root py raw
	root="${MARKERS_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/..}"
	root="$(cd "$root" && pwd)"
	py="${PYTHON:-$root/.venv/bin/python}"
	[ -x "$py" ] || py="$(command -v python3)"

	if ! raw="$(cd "$root/agent" && "$py" -m kernel_spec.tests.acceptance_tests \
		--list-patterns "$set_name" 2>&1)"; then
		echo "markers: could not load set '$set_name' via $py" >&2
		echo "$raw" >&2
		return 1
	fi

	MARKERS=()
	local line
	while IFS= read -r line; do
		[ -n "$line" ] && MARKERS+=("$line")
	done <<< "$raw"

	if [ "${#MARKERS[@]}" -eq 0 ]; then
		echo "markers: set '$set_name' is empty — refusing to report a vacuous pass" >&2
		return 1
	fi
}

# markers_check <serial-text>
# Prints "PASS  <pattern>" / "FAIL  <pattern>" per marker, in set order.
# Sets MARKERS_FAILED to the number that did not match.
markers_check() {
	local serial="$1"
	local pattern
	MARKERS_FAILED=0
	for pattern in "${MARKERS[@]}"; do
		if echo "$serial" | grep -qE "$pattern"; then
			echo "PASS  $pattern"
		else
			echo "FAIL  $pattern"
			MARKERS_FAILED=$((MARKERS_FAILED + 1))
		fi
	done
}
