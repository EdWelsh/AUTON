"""Instruction availability: derived nominal lists, cited exceptions, CPUID as the truth."""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

import isa_tables as it  # noqa: E402

TD = """
def FeatureSSE2 : SubtargetFeature<"sse2", "X86SSELevel", "SSE2", "Enable SSE2", []>;
def FeatureAVX  : SubtargetFeature<"avx", "X86SSELevel", "AVX", "Enable AVX", [FeatureSSE2]>;
def FeatureFMA4 : SubtargetFeature<"fma4", "HasFMA4", "true", "Four-operand FMA",
                                   [FeatureAVX]>;  // a comment
def FeatureXOP  : SubtargetFeature<"xop", "HasXOP", "true", "XOP", [FeatureFMA4]>;
def ProcessorFeatures {
  list<SubtargetFeature> BdVer1Features = [FeatureXOP];
  list<SubtargetFeature> ZNFeatures = !listremove(!listconcat(BdVer1Features, [FeatureAVX]),
                                                  [FeatureXOP]);
}
def : ProcModel<"bdver1", M, ProcessorFeatures.BdVer1Features, []>;
def : ProcModel<"znver1", M, ProcessorFeatures.ZNFeatures, [TuningFast]>;
def : ProcessorAlias<"opteron-ish", "bdver1">;
"""


def test_features_are_closed_under_implication():
    tg = it.TableGen([TD])
    feats = {k: tg.feature(k) for k, (c, _) in tg.defs.items() if c in it.FEATURE_CLASSES}
    procs, aliases = tg.processors()
    names = lambda p: {feats[i]["name"] for f in procs[p] for i in it.closure(f, feats)}
    assert names("bdver1") == {"xop", "fma4", "avx", "sse2"}
    assert names("znver1") == {"avx", "sse2"}          # listremove took XOP, not its implications
    assert aliases == {"opteron-ish": "bdver1"}
    assert "TuningFast" not in tg.unresolved


CPUFEATURES = """
/* AMD-defined CPU features, CPUID level 0x80000001, word 1 */
/* More extended AMD flags: CPUID level 0x80000001, ECX, word 6 */
#define X86_FEATURE_FMA4		( 6*32+16) /* "fma4" 4 operands MAC instructions */
/* Intel-defined CPU features, CPUID level 0x00000007:0 (EBX), word 9 */
#define X86_FEATURE_AVX512F		( 9*32+16) /* "avx512f" AVX-512 Foundation */
"""


def test_cpuid_location_comes_from_the_header():
    c = it.parse_cpufeatures(CPUFEATURES)
    assert c["fma4"] | {} == {**c["fma4"], "leaf": "0x80000001", "register": "ECX", "bit": 16}
    assert (c["avx512f"]["leaf"], c["avx512f"]["subleaf"], c["avx512f"]["register"]) == \
        ("0x00000007", 0, "EBX")


TABLES = {"x86": {"processors": {"haswell": ["avx", "fma"], "bdver1": ["fma4"],
                                 "alderlake": ["avx2"]},
                  "aliases": {}}}


def test_an_exception_for_every_intel_part_does_not_touch_amd():
    ex = [{"arch": "x86", "feature": "fma4", "vendor": "intel", "kind": "never-shipped",
           "applies_to": [], "source": "s"}]
    assert it.has(TABLES, "x86", "haswell", "fma4", ex)["verdict"] == "absent: never-shipped"
    assert it.has(TABLES, "x86", "bdver1", "fma4", ex)["exceptions"] == []


def test_fused_off_means_ask_the_cpu():
    ex = [{"arch": "x86", "feature": "avx512f", "vendor": "intel", "kind": "fused-off",
           "applies_to": ["alderlake"], "source": "s"}]
    assert it.has(TABLES, "x86", "alderlake", "avx512f", ex)["verdict"].startswith(
        "check at runtime")


def test_an_exception_without_a_source_is_refused(tmp_path):
    p = tmp_path / "e.yaml"
    p.write_text("exceptions:\n  - {arch: x86, feature: fma4, kind: removed, applies_to: []}\n")
    with pytest.raises(it.IsaError, match="source"):
        it.load_exceptions(p)


def test_the_committed_exceptions_are_valid_and_unverified_rows_say_so():
    rows = it.load_exceptions()
    assert rows
    assert all(isinstance(r["verified"], bool) and r.get("verify_with") for r in rows)


def test_the_committed_tables_agree_with_known_silicon():
    t = it.load_tables()
    x86 = t["x86"]["processors"]
    assert "fma4" in x86["bdver1"] and "fma4" not in x86["znver1"]
    assert "avx512f" in x86["sapphirerapids"] and "avx512f" not in x86["alderlake"]
    assert "fma" in x86["haswell"]
    assert "vector" in t["systemz"]["processors"]["z16"]
    assert "m" in t["riscv"]["processors"]["sifive-u74"]
