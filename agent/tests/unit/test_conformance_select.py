"""Intent-scoped conformance selection (H10c).

An image carries checks for the instructions its own code executes. Two ways
that goes wrong, and both are tested here: selecting checks for instructions
the image never runs (noise nobody reads), and silently covering none of what
it does run (a suite that proves nothing while looking green).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from conformance_select import (MNEMONICS, SelectionError, corpus_entries,  # noqa: E402
                                instructions_in, select, uncovered)

CORPUS = ROOT / "agent" / "kernel_spec" / "conformance"

# objdump's own output shape, AT&T spelling and all.
DISASM = """
kernel.bin:     file format elf64-x86-64

Disassembly of section .text:

0000000000100000 <_start>:
  100000:\t48 89 e5             \tmov    %rsp,%rbp
  100003:\tf2 0f 5e c1          \tdivsd  %xmm1,%xmm0
  100007:\t66 90                \tdata16 xchg %ax,%ax
  100009:\t0f 0b                \tud2
  10000b:\td8 35 00 00 00 00    \tfdivs  0x0(%rip)
  100011:\t0f 1f 44 00 00       \tnopl   0x0(%rax,%rax,1)
"""


def test_mnemonics_are_normalised_to_sdm_names():
    found = instructions_in(DISASM)
    assert found == {"DIVSD", "UD2", "FDIV", "NOP"}


def test_every_att_spelling_of_fdiv_is_the_same_instruction():
    """objdump prints five spellings depending on operand size and popping."""
    for spelling in ("fdiv", "fdivl", "fdivs", "fdivp"):
        assert MNEMONICS[spelling] == "FDIV"
    assert MNEMONICS["fdivr"] == "FDIVR", "reverse divide is a different instruction"


def test_single_and_double_precision_are_not_confused():
    assert MNEMONICS["divsd"] != MNEMONICS["divss"]
    assert MNEMONICS["sqrtsd"] != MNEMONICS["sqrtss"]


def test_prefixes_and_padding_are_not_instructions():
    assert "DATA16" not in instructions_in(DISASM)
    assert instructions_in("  1000:\tf0 90  \tlock\n") == set()


def test_an_image_that_divides_doubles_gets_the_division_checks():
    chosen = select({"DIVSD"}, CORPUS)
    ids = {e["id"] for e in chosen}
    assert "fp-div-fdiv-historical" in ids
    assert all("fp-div" in i for i in ids)


def test_an_image_that_divides_nothing_gets_no_fp_checks():
    """A kernel that never divides has nothing to learn from a division check,
    and a suite full of checks it cannot exercise is one nobody reads."""
    assert select(set(), CORPUS) == []
    only_faults = select({"UD2"}, CORPUS)
    assert only_faults and all(e["class"] == "fault" for e in only_faults)


def test_the_single_precision_gap_is_closed():
    """The base kernel executes DIVSS and SQRTSS (the SLM's arithmetic is
    float). Before fp-single.yaml existed, selection for that image produced
    no FP check at all while the image divided floats on every inference."""
    chosen = select({"DIVSS", "SQRTSS"}, CORPUS)
    assert chosen, "an image using DIVSS must get single-precision checks"
    assert {"fp-div-single-one-third", "fp-sqrt-single-two"} <= {e["id"] for e in chosen}
    assert uncovered({"DIVSS", "SQRTSS"}, CORPUS) == set()


def test_an_instruction_no_entry_covers_is_reported_not_hidden():
    gap = uncovered({"DIVSD", "VFMADD213PD"}, CORPUS)
    assert gap == {"VFMADD213PD"}, "this is how the corpus learns what to grow"


def test_every_corpus_entry_names_its_instruction(tmp_path):
    for e in corpus_entries(CORPUS):
        assert e["instructions"], f"{e['id']} names no instruction"
    (tmp_path / "x.yaml").write_text(
        "entries:\n  - id: x\n    clause: 'SDM 1'\n    class: semantic\n"
        "    guarantee: architectural\n    a: 1.0\n")
    with pytest.raises(SelectionError, match="names no instruction"):
        corpus_entries(tmp_path)
