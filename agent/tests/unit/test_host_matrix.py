"""docs/HOST-MATRIX.md keeps its own rule: a host is "exercised" only with a
date or evidence, and the only "Yes" rows are ones this project has run."""

from __future__ import annotations

import re
from pathlib import Path

MATRIX = Path(__file__).resolve().parents[3] / "docs" / "HOST-MATRIX.md"


def _rows(text: str) -> list[list[str]]:
    return [[c.strip() for c in line.strip().strip("|").split("|")]
            for line in text.splitlines()
            if line.startswith("|") and not set(line.replace("|", "").strip()) <= {"-"}]


def test_every_table_with_an_exercised_column_says_how():
    text = MATRIX.read_text()
    tables = re.split(r"\n(?=## )", text)
    checked = 0
    for t in tables:
        rows = _rows(t)
        if not rows or "Exercised?" not in rows[0]:
            continue
        col = rows[0].index("Exercised?")
        for row in rows[1:]:
            cell = row[col]
            checked += 1
            if cell.startswith("**Yes**"):
                assert re.search(r"20\d\d-\d\d-\d\d", cell), f"'Yes' without a date: {row[0]}"
            else:
                assert re.match(r"\*\*(No|Partly|Wired)", cell), f"unclear status: {row[0]}"
    assert checked >= 6


def test_only_this_hosts_class_claims_yes():
    """A row may claim "Yes" only for the machine this project has: the Mac, or
    a container running *on* it (which says so in the same cell — a Linux
    container on Apple Silicon is not evidence about an x86_64 Linux host)."""
    rows = [r for r in _rows(MATRIX.read_text()) if any(c.startswith("**Yes**") for c in r)]
    for row in rows:
        cell = next(c for c in row if c.startswith("**Yes**"))
        assert "Apple" in row[0] or "on this Mac" in row[0] or "on the M4 Pro" in cell, row
