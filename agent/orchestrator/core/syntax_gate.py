"""The compile check a branch passes before a model reviews it.

A reviewer model approved a header with seven syntax errors (w13, generate-mm:
`ttypedef enum`), and nothing mechanical stood between that approval and main.
Whether C compiles is not a judgement call, so a compiler answers it, and a
branch that fails goes back to its author with the compiler's words as the
review.

Every changed `.c` and `.h` under `kernel/` is checked with `-fsyntax-only`
against the tree's own include directories. A header is checked as a C file,
so a header that cannot stand alone (it uses a type it neither declares nor
includes) fails here, which is the point: the next file to include it would.

Driver decision records get the same treatment for the same reason (w13 V8:
the reviewer approved a record with no front matter): every changed
`drivers/<name>.md` must pass `agent/tools/driver_spec.py`'s loader.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CHECKED_SUFFIXES = (".c", ".h")
MAX_ERROR_LINES = 30
FLAGS = ("-fsyntax-only", "-ffreestanding", "-std=gnu11", "-x", "c")


def compiler() -> str | None:
    """The kernel compiler the run was started with (toolchain.sh sets CC)."""
    for name in (os.environ.get("CC"), "x86_64-elf-gcc", "cc"):
        if name and shutil.which(name):
            return name
    return None


def include_dirs(tree: Path) -> list[Path]:
    dirs = [tree / "kernel" / "include"]
    dirs += sorted(tree.glob("kernel/arch/*/include"))
    return [d for d in dirs if d.is_dir()]


TOOLS = Path(__file__).resolve().parents[2] / "tools"
NOT_RECORDS = {"README.md", "STRATEGY.md"}


def record_errors(tree: Path, changed: list[str]) -> list[str]:
    """driver_spec's refusal for each changed driver record."""
    paths = [p for p in changed
             if p.endswith(".md") and Path(p).parent.name == "drivers"
             and Path(p).name not in NOT_RECORDS and (tree / p).is_file()]
    if not paths:
        return []
    if str(TOOLS) not in sys.path:
        sys.path.insert(0, str(TOOLS))
    from driver_spec import DriverError, load

    errors = []
    for rel in paths:
        try:
            load(tree / rel)
        except DriverError as exc:
            errors.append(f"{rel}: {exc} (format: drivers/README.md)")
    return errors


def check(tree: Path, changed: list[str], cc: str | None = None) -> str | None:
    """None when every changed C file compiles and every changed driver record
    loads; otherwise the errors, trimmed."""
    rec_errors = record_errors(tree, changed)
    c_errors = _c_errors(tree, changed, cc)
    errors = rec_errors + c_errors
    if not errors:
        return None
    shown = errors[:MAX_ERROR_LINES]
    more = len(errors) - len(shown)
    return "\n".join(shown) + (f"\n... and {more} more" if more > 0 else "")


def _c_errors(tree: Path, changed: list[str], cc: str | None) -> list[str]:
    cc = cc or compiler()
    targets = [p for p in changed
               if p.startswith("kernel/") and p.endswith(CHECKED_SUFFIXES) and (tree / p).is_file()]
    if not targets:
        return []
    if cc is None:
        logger.warning("syntax gate skipped: no C compiler on PATH")
        return []
    incs = [f"-I{d}" for d in include_dirs(tree)]
    errors: list[str] = []
    for rel in targets:
        r = subprocess.run([cc, *FLAGS, *incs, str(tree / rel)], cwd=tree,
                           capture_output=True, text=True, timeout=60)
        if r.returncode != 0:
            text = r.stderr.replace(str(tree) + "/", "")
            errors += [ln for ln in text.splitlines() if "error" in ln] or [f"{rel}: compile failed"]
    return errors
