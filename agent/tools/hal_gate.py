"""The HAL boundary, checked: no architecture code in portable kernel code.

    python agent/tools/hal_gate.py --tree <kernel tree>

kernel_spec/arch/hal.md: "All kernel subsystems call HAL interfaces — never raw
architecture instructions or registers directly." Until w12 nothing checked it,
and the base broke it six times: inline `hlt` in net/ and server/, `cli; hlt`
in boot/, and PCI config space through x86 port I/O in dev/. A second
architecture (windows-linux D2) is impossible while portable code contains x86.

Architecture territory is `kernel/arch/**` and `kernel/drivers/arch/**`
(drivers for devices only one architecture has, such as the 16550 UART).
Everything else is portable. Comments are stripped first, so prose about
"hlt-yielding poll loops" is not a violation: a gate that cries wolf gets ignored.
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path

ARCH_TERRITORY = ("kernel/arch/", "kernel/drivers/arch/")

# Each rule: (name, pattern, why). Patterns run on comment-stripped source.
RULES = (
    ("inline assembly", re.compile(r"\b(__asm__|asm)\s*(volatile\s*|__volatile__\s*)?\("),
     "instructions are architecture code; call the HAL (arch_halt, arch_disable_interrupts, ...)"),
    ("architecture header", re.compile(r'#\s*include\s*[<"][^>"]*\barch/'),
     "portable code includes kernel/include/hal.h, never an arch directory"),
    ("port I/O", re.compile(r"\bio_(read|write)(8|16|32)\s*\("),
     "port I/O exists on x86 only; use the HAL (arch_pci_config_read32, ...)"),
)


@dataclass(frozen=True)
class Violation:
    path: str
    line: int
    rule: str
    text: str
    why: str

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.rule}: {self.text.strip()}  ({self.why})"


def strip_comments(src: str) -> str:
    """Blank out comments and the contents of string and character literals,
    keeping line numbers and preprocessor lines (#include paths) intact."""
    out: list[str] = []
    i, n = 0, len(src)
    line_start = True
    while i < n:
        c = src[i]
        if line_start and c == "#":
            # A preprocessor line is kept verbatim: an include path is a string
            # literal that the header rule needs to see.
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(src[i:j])
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i + 2)
            j = n if j < 0 else j + 2
            out.append("".join(ch if ch == "\n" else " " for ch in src[i:j]))
            i = j
        elif src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            out.append(" " * (j - i))
            i = j
        elif c in ('"', "'"):
            j = i + 1
            while j < n and src[j] != c and src[j] != "\n":
                j += 2 if src[j] == "\\" else 1
            j = min(j + 1, n)
            out.append(c + " " * max(0, j - i - 2) + (c if j - i >= 2 else ""))
            i = j
        else:
            out.append(c)
            i += 1
            if c == "\n":
                line_start = True
                continue
            if not c.isspace():
                line_start = False
            continue
        line_start = out[-1].endswith("\n") if out else True
    return "".join(out)


def is_portable(rel: str) -> bool:
    return rel.startswith("kernel/") and not rel.startswith(ARCH_TERRITORY)


def scan(tree: Path, files: list[str] | None = None) -> list[Violation]:
    """Violations in `files` (tree-relative), or in every portable .c/.h/.S."""
    if files is None:
        files = sorted(str(p.relative_to(tree)) for p in (tree / "kernel").rglob("*")
                       if p.suffix in (".c", ".h", ".S"))
    found: list[Violation] = []
    for rel in files:
        if not is_portable(rel) or rel.endswith(".S"):
            if is_portable(rel) and rel.endswith(".S"):
                found.append(Violation(rel, 1, "assembly source", rel,
                                       "assembly files belong under kernel/arch/"))
            continue
        path = tree / rel
        if not path.is_file():
            continue
        raw = path.read_text(encoding="utf-8", errors="replace").splitlines()
        clean = strip_comments("\n".join(raw)).splitlines()
        for no, line in enumerate(clean, 1):
            for name, pat, why in RULES:
                if pat.search(line):
                    found.append(Violation(rel, no, name, raw[no - 1], why))
    return found


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("--tree", required=True, type=Path)
    args = ap.parse_args(argv)
    found = scan(args.tree)
    for v in found:
        print(v)
    print(f"{'REFUSED' if found else 'OK'}: {len(found)} HAL violation(s) in portable code")
    return 1 if found else 0


if __name__ == "__main__":
    raise SystemExit(main())
