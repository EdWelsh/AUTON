#!/usr/bin/env python3
"""Measure what the Doom engine needs from the system under it (w23 R12.1).

    .venv/bin/python scripts/doom_surface.py [--write agent/kernel_spec/reference/doom-surface.yaml]

Compiles every engine unit doomgeneric's Makefile lists (less its Xlib front end) and
takes the undefined symbols that no engine unit defines. That set is the whole contract
between the engine and a kernel: nothing here is read from documentation.

Platform artefacts of the measuring host (macOS names, stack protector, compiler
idioms) are folded onto the portable symbol they stand for, and reported as folded.
Needs `.cache/third_party/doomgeneric` (GPL-2.0, never committed) and clang.
"""
from __future__ import annotations

import argparse
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / ".cache/third_party/doomgeneric/doomgeneric"

# measuring-host name -> portable meaning (None: a compiler/host artefact, not a need)
FOLD = {"__error": "errno", "__toupper": "toupper", "__stderrp": "stderr", "__stdoutp": "stdout",
        "memset_pattern16": "memset", "__stack_chk_fail": None, "__stack_chk_guard": None}

GROUPS = {
    "platform (the six DG_* functions)": r"^DG_",
    "sound (compiled out; the engine still calls these)": r"^(I_.*(Sound|Music|Song|Sfx)|snd_musicdevice)",
    "memory": r"^(malloc|calloc|realloc|free)$",
    "string and memory ops": r"^(mem|str|bzero)",
    "formatting": r"^(printf|snprintf|vsnprintf|vfprintf|fprintf|sscanf|puts|putchar|atoi|atof|toupper)$",
    "stdio and files (fs is excluded from play-doom)": r"^(f(open|close|read|write|seek|tell|flush)|stdout|stderr|mkdir|remove|rename|system)$",
    "process": r"^(exit|errno)$",
}


def _bare(sym: str) -> str:
    """Mach-O prefixes C names with one underscore; ELF does not."""
    return sym[1:] if sym.startswith("_") else sym


def measure(extra_defs: list[str]) -> tuple[list[str], list[str]]:
    mk = (ENGINE / "Makefile").read_text()
    objs = re.search(r"^SRC_DOOM\s*=\s*(.*)$", mk, re.M).group(1).split()
    units = [o[:-2] + ".c" for o in objs if o != "doomgeneric_xlib.o"]
    undef: set[str] = set()
    defined: set[str] = set()
    skipped: list[str] = []
    with tempfile.TemporaryDirectory() as d:
        for u in units:
            out = Path(d) / (u[:-2] + ".o")
            r = subprocess.run(["clang", "-O2", "-w", *extra_defs, "-c", str(ENGINE / u), "-o", str(out)],
                               capture_output=True, text=True)
            if r.returncode:
                skipped.append(u)   # i_sound.c wants SDL_mixer: the sound module is replaced
                continue
            for line in subprocess.run(["nm", str(out)], capture_output=True, text=True).stdout.splitlines():
                parts = line.split()
                if len(parts) == 2 and parts[0] == "U":
                    undef.add(_bare(parts[1]))
                elif len(parts) == 3 and parts[1] in "TDBSRC":
                    defined.add(_bare(parts[2]))
    return sorted(undef - defined), skipped


def report() -> dict:
    external, skipped = measure([])
    folded, needs = {}, set()
    for s in external:
        if s in FOLD:
            tgt = FOLD[s]
            folded[s] = tgt
            if tgt:
                needs.add(tgt)
        else:
            needs.add(s)
    groups = {g: sorted(n for n in needs if re.search(p, n)) for g, p in GROUPS.items()}
    seen = {n for v in groups.values() for n in v}
    groups["other"] = sorted(needs - seen)
    return {"engine": "doomgeneric (not committed; .cache/third_party/doomgeneric)",
            "measured_by": "scripts/doom_surface.py",
            "units_not_compiled_on_the_measuring_host": skipped,
            "folded_host_artefacts": folded,
            "needs": {g: v for g, v in groups.items() if v},
            "count": len(needs)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write")
    a = ap.parse_args()
    if not ENGINE.is_dir():
        print(f"no engine at {ENGINE}", file=sys.stderr)
        return 2
    rep = report()
    text = yaml.safe_dump(rep, sort_keys=False, width=100)
    if a.write:
        Path(a.write).write_text(text)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
