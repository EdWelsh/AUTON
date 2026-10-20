#!/usr/bin/env bash
# Build the operator-authored fallback tree for R1 (docs/campaign/runs.yaml, r1-mm `fallback`).
#
#   scripts/make-r1-fallback.sh [dest]      # default .artifacts/campaign/r1-mm-operator-fallback
#
# kernel-base-v5 plus the memory managers in tests/kernel/mm_operator/, wired into kernel_main.
# NOT model output: R1 failed twice (w25), and R2 and later runs need a working allocator and VMM
# to build on. The tree is a campaign artifact (gitignored); this script and its sources are not
# a generated kernel. RESULT.json in the tree says so, and campaign.py reports it as a fallback.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$ROOT/.artifacts/campaign/r1-mm-operator-fallback}"
SRC="$ROOT/tests/kernel/mm_operator"
WS="$DEST/ws"

rm -rf "$DEST"
mkdir -p "$DEST"
bash "$ROOT/scripts/kernel-base.sh" "$WS" --git --rev kernel-base-v5 >/dev/null

mkdir -p "$WS/kernel/mm"
cp "$SRC/mm.h" "$SRC/boot.h" "$WS/kernel/include/"
cp "$SRC/pmm.c" "$SRC/vmm.c" "$SRC/vmm_arch.c" "$SRC/vmm_as.c" "$WS/kernel/mm/"

# The kernel image's bounds, which the PMM reserves (mm.md "Reserved Regions").
python3 - "$WS" <<'PY'
import sys, pathlib
ws = pathlib.Path(sys.argv[1])
ld = ws / "kernel/arch/x86_64/linker.ld"
s = ld.read_text()
s = s.replace("\t. = 1M;\n", "\t. = 1M;\n\t__kernel_start = .;\n", 1)
s = s.replace("\t/DISCARD/", "\t. = ALIGN(4K);\n\t__kernel_end = .;\n\n\t/DISCARD/", 1)
ld.write_text(s)

km = ws / "kernel/boot/kernel_main.c"
s = km.read_text()
s = s.replace('#include "hal.h"\n\n#define PAGE_SIZE 4096u\n', '#include "hal.h"\n#include "mm.h"\n', 1)
old = s[s.index("\t/* Minimal physical memory accounting"):s.index("\t/* Scheduler is a stub")]
new = '''\t/* The memory managers. The map is RAM as one available region, with each boot module
\t * carved out as reserved: the firmware reports a module as available RAM. */
\tboot_mmap_t map;
\tkmemset(&map, 0, sizeof map);
\tmap.entries[0].base_addr = 0;
\tmap.entries[0].length = hw.total_ram_bytes;
\tmap.entries[0].type = 1;
\tmap.count = 1;
\tfor (uint32_t m = 0; m < hw.module_count && map.count < 128; m++) {
\t\tmap.entries[map.count].base_addr = hw.modules[m].start;
\t\tmap.entries[map.count].length = hw.modules[m].end - hw.modules[m].start;
\t\tmap.entries[map.count].type = 2;
\t\tmap.count++;
\t}
\tmap.total_available = hw.total_ram_bytes;
\tmap.highest_address = hw.total_ram_bytes;
\tpmm_init(&map);
\tslab_init();
\tvmm_init();

'''
s = s.replace(old, new, 1)
km.write_text(s)
PY

git -C "$WS" rm -q kernel/lib/phys.c         # dma_alloc moves to the PMM (mm.md "dma_alloc")
git -C "$WS" add -A
git -C "$WS" -c user.email=operator@auton.local -c user.name="campaign operator" \
    commit -q -m "operator fallback for R1: PMM, slab and VMM from tests/kernel/mm_operator (not model output)"
echo "$WS"

# Judge the tree with R1's own gates and record the verdicts, so the fallback is evidence, not
# assertion. campaign.py reads this as the fallback attempt's RESULT.json.
python3 - "$ROOT" "$DEST" <<'PY'
import json, os, subprocess, sys, time
root, dest = sys.argv[1:3]
ws = os.path.join(dest, "ws")
gates = ["tests/kernel/run_mm_test.sh", "tests/kernel/run_vmm_test.sh",
         "scripts/boot-marker.sh \"$KERNEL_TREE\" '^\\[MM\\] PMM initialized: [0-9]+ pages total, [0-9]+ reserved, [0-9]+ free'"]
out = []
for g in gates:
    t0 = time.monotonic()
    r = subprocess.run(["bash", "-c", g], cwd=root, env={**os.environ, "KERNEL_TREE": ws},
                       capture_output=True, text=True, timeout=3600)
    out.append({"gate": g, "rc": r.returncode, "meaning": {0: "pass", 1: "generated wrong",
                2: "not generated"}.get(r.returncode, f"exit {r.returncode}"),
                "seconds": round(time.monotonic() - t0),
                "tail": (r.stdout + r.stderr).strip().splitlines()[-4:]})
json.dump({"finished": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
           "label": "operator-authored fallback for r1-mm (not model output): see scripts/make-r1-fallback.sh",
           "base": "kernel-base-v5", "sessions": [], "gates": out},
          open(os.path.join(dest, "RESULT.json"), "w"), indent=1)
print([g["rc"] for g in out])
PY
