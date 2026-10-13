#!/usr/bin/env bash
# w24 F-2: name inline assembly in portable kernel code before the host compiler does.
# The host suites build portable files with the Mac's clang (arm64), where `cli; hlt` is an
# "unrecognized instruction mnemonic" error that hides the real cause. Portable code halts
# through arch_halt() (hal.h). Prints file:line per hit; exit 1 if any.
# Usage: portable_asm_check.sh <kernel-tree>
TREE="${1:?kernel tree}"
hits=0
for dir in mm fs net services; do
	[ -d "$TREE/kernel/$dir" ] || continue
	while IFS= read -r line; do
		echo "inline assembly in portable code: $line" >&2
		hits=1
	done < <(grep -rnE '(__asm__|\basm[[:space:]]*(volatile)?[[:space:]]*\()' --include='*.c' --include='*.h' "$TREE/kernel/$dir" 2>/dev/null)
done
exit $hits
