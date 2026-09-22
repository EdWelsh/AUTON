#!/usr/bin/env bash
# The errata module reader, on the host.
#   tests/kernel/run_errata_lookup_test.sh --self-test        # against errata_lookup_reference/
#   KERNEL_TREE=<dir> tests/kernel/run_errata_lookup_test.sh  # against kernel/slm/errata_lookup.c
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HERE="$(cd "$(dirname "$0")" && pwd)"
PY="${PYTHON:-$ROOT/.venv/bin/python}"
CC="${HOST_CC:-clang}"
W="$(mktemp -d)"; trap 'rm -rf "$W"' EXIT
if [ "${1:-}" = "--self-test" ]; then
	INC="$HERE/errata_lookup_reference/include"; SRC="$HERE/errata_lookup_reference/errata_lookup.c"
else
	KERNEL_TREE="${KERNEL_TREE:-$ROOT/kernels/x86_64}"
	SRC="$KERNEL_TREE/kernel/slm/errata_lookup.c"; INC="$KERNEL_TREE/kernel/include"
	[ -f "$SRC" ] || { echo "no kernel/slm/errata_lookup.c: specified in slm.md, not generated" >&2; exit 2; }
fi
PYTHONPATH="$ROOT/SLM/tools" "$PY" - "$W/synthetic.bin" <<'PY'
import sys
from errata_format import Key, Rec, pack
t = {Key(1, 6, 151, 2): [Rec("ADL001: X87 FDP Value May be Saved Incorrectly", 1, 1, 0, 14),
                          Rec("ADL002: something else", 0, 2, 0, 15)],
     Key(2, 25, 33, 0): [Rec("AMD1: synthetic", 2, 3, 1, 0)]}
open(sys.argv[1], "wb").write(pack([("intel/x", "1"), ("amd/y", "2")], t))
PY
REAL=""
if "$PY" "$ROOT/SLM/tools/build_errata_table.py" --out "$W/real.bin" >/dev/null 2>&1 \
   && [ "$(wc -c < "$W/real.bin")" -gt 64 ]; then REAL="$W/real.bin"; fi
"$CC" -O1 -g -fsanitize=address,undefined -fno-sanitize-recover=undefined -I"$INC" \
	"$HERE/errata_lookup_test.c" "$SRC" -o "$W/t" || { echo "compile failed" >&2; exit 1; }
"$W/t" "$W/synthetic.bin" ${REAL:+"$REAL"}
