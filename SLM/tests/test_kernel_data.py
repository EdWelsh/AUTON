"""The data a kernel model trains on must fit the model the kernel runs (SLM/DATA.md)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SLM" / "tools"))
sys.path.insert(0, str(ROOT / "agent" / "tools"))

import build_hardware_corpus as bhc  # noqa: E402
import fetch_domain_text as fdt  # noqa: E402
import qemu_cpu  # noqa: E402
import vocab_budget as vb  # noqa: E402

D = ROOT / "SLM" / "datasets"


def test_the_kernel_training_set_fits_the_kernel_vocabulary():
    m = vb.measure([D / "os_chat.jsonl", D / "hardware_kernel.jsonl"], vb.KERNEL_VOCAB)
    assert m["answer_unk"] == 0.0 and m["prompt_unk"] == 0.0 and m["fits"]


def test_the_reference_corpus_does_not_and_says_why():
    m = vb.measure([D / "hardware_reference.jsonl"], vb.KERNEL_VOCAB)
    assert not m["fits"] and m["answer_unk"] > 0.05


def test_the_kernel_corpus_is_what_the_committed_cpu_table_generates():
    rows = [json.loads(line) for line in (D / "hardware_kernel.jsonl").read_text().splitlines()]
    assert rows == bhc.build_kernel()


def test_kernel_cpu_answers_follow_qemu64():
    qemu = qemu_cpu.load()
    have = set(qemu["models"]["qemu64"]["features"])
    by_q = {json.loads(line)["text"]: json.loads(line)["response"]
            for line in (D / "hardware_kernel.jsonl").read_text().splitlines()}
    assert "sse2" in have and "avx" not in have
    assert by_q["does this cpu support sse2"] == "Yes. This CPU reports sse2."
    assert by_q["does this cpu support avx2"] == "No. This CPU does not report avx2."


def test_no_kernel_row_is_an_eval_prompt():
    for line in (D / "hardware_kernel.jsonl").read_text().splitlines():
        assert not bhc._is_eval_prompt(json.loads(line)["text"])


CPU_C = r'''
#define PPRO_FEATURES (CPUID_FP87 | CPUID_DE | \
          CPUID_SSE | CPUID_SSE2)
static const X86CPUDefinition builtin_x86_defs[] = {
    {
        .name = "tiny64",
        .vendor = CPUID_VENDOR_AMD,
        .family = 15,
        .model = 107,
        .stepping = 1,
        .features[FEAT_1_EDX] =
            PPRO_FEATURES | CPUID_MTRR,
        .features[FEAT_8000_0001_EDX] =
            CPUID_EXT2_LM | CPUID_EXT2_NX,
    },
};
'''


def test_qemu_group_macros_expand_across_continuation_lines(tmp_path):
    (tmp_path / "cpu.c").write_text(CPU_C)
    m = qemu_cpu.model("tiny64", tmp_path)
    assert m["vendor"] == "AuthenticAMD" and m["family"] == 15
    assert m["features"] == ["64bit", "de", "fpu", "mtrr", "nx", "sse", "sse2"]


def test_domain_text_markup_is_stripped():
    roff = '.TH OPEN 2\n.SH NAME\nopen \\- open and possibly create a file\n.\\" comment\n'
    assert "comment" not in fdt.strip_markup(roff, "man2/open.2")
    rst = ".. SPDX-License-Identifier: GPL-2.0\n\nTitle\n=====\n\nUse :c:func:`kmalloc` here.\n"
    out = fdt.strip_markup(rst, "Documentation/x.rst")
    assert "SPDX" not in out and "kmalloc" in out and "=====" not in out


def test_domain_text_stats_record_licence_and_commit():
    stats = json.loads((D / "domain_text.stats.json").read_text())["sources"]
    assert {s["id"] for s in stats} >= {"linux-docs", "man-pages"}
    assert all(s["licence"] and len(s["commit"]) == 40 and s["kernel_vocab_coverage"] < 0.9
               for s in stats)
