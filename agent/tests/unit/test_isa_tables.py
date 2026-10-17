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


ZVL = """
def FeatureStdExtZvl32b : RISCVExtension<1, 0, "Minimum Vector Length 32", [],
                                         "ZvlLen", "32">;
foreach i = { 6-8 } in {
  defvar I = !shl(1, i);
  def FeatureStdExtZvl#I#b :
      RISCVExtension<1, 0, "Minimum Vector Length "#I,
                     [!cast<RISCVExtension>("FeatureStdExtZvl"#!srl(I, 1)#"b")],
                     "ZvlLen", !cast<string>(I)>;
}
foreach i = {1-2} in
  def FeatureReserveX#i : SubtargetFeature<"reserve-x"#i, "Reserved[X"#i#"]", "true",
                                           "Reserve X"#i>;
def VEC : RISCVProcessorModel<"vec256", M, [FeatureStdExtZvl256b]>;
"""


def test_foreach_loops_are_read_like_the_defs_they_stand_for():
    """RISC-V's Zvl64b..Zvl65536b chain is a foreach; unread, every vector part
    lost its vector-length guarantee."""
    tg = it.TableGen([ZVL])
    feats = {k: tg.feature(k) for k, (c, _) in tg.defs.items() if c in it.FEATURE_CLASSES}
    procs, _ = tg.processors()
    assert {feats[i]["name"] for f in procs["vec256"] for i in it.closure(f, feats)} == \
        {"zvl256b", "zvl128b", "zvl64b", "zvl32b"}
    assert feats["FeatureStdExtZvl128b"]["description"] == "Minimum Vector Length 128"
    assert feats["FeatureReserveX2"]["name"] == "reserve-x2"
    assert not tg.unresolved


RV_FEATURES = """
def Feature64Bit : SubtargetFeature<"64bit", "IsRV64", "true", "Implements RV64">;
def FeatureStdExtI : RISCVExtension<2, 1, "Base Integer Instruction Set">;
def FeatureStdExtM : RISCVExtension<2, 0, "Integer Multiplication and Division">;
def FeatureStdExtV : RISCVExtension<1, 0, "Vector Extension for Application Processors">;
"""
RV_PROFILES = "defvar RVA23U64Features = [Feature64Bit, FeatureStdExtI, FeatureStdExtM];\n"
RV_PROCESSORS = """
def PART : RISCVProcessorModel<"part-x", M, !listconcat(RVA23U64Features, [FeatureStdExtV])>;
"""


def _riscv_cache(tmp_path: Path, profiles: str) -> Path:
    import json
    for doc, text in zip(it.ARCH_SOURCES["riscv"], (RV_FEATURES, profiles, RV_PROCESSORS)):
        d = tmp_path / "llvm-project" / doc
        d.mkdir(parents=True)
        (d / f"{doc}.td").write_text(text)
        (d / "provenance.json").write_text(json.dumps({"sha256": "0" * 64, "source": "t"}))
    return tmp_path


def test_riscv_profile_bases_are_read(tmp_path):
    t = it.build_arch("riscv", _riscv_cache(tmp_path, RV_PROFILES))
    assert t["processors"]["part-x"] == ["64bit", "i", "m", "v"]
    assert "llvm-riscv-profiles-td" in [s["document"] for s in t["generated_from"]]


def test_a_part_naming_an_undefined_list_fails_the_build(tmp_path):
    """Without RISCVProfiles.td, part-x would be written as lacking I, M and 64bit."""
    with pytest.raises(it.IsaError, match=r"RVA23U64Features \(used by part-x\)"):
        it.build_arch("riscv", _riscv_cache(tmp_path, "// no profiles\n"))


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


TRANSMETA_AND_CENTAUR = """
/* Transmeta-defined CPU features, CPUID level 0x80860001, word 2 */
#define X86_FEATURE_LONGRUN		( 2*32+ 1) /* "longrun" Longrun power control */
/* VIA/Cyrix/Centaur-defined CPU features, CPUID level 0xC0000001, word 5 */
#define X86_FEATURE_XSTORE		( 5*32+ 2) /* "rng" RNG present (xstore) */
/* BUG word 2 */
#define X86_BUG_SRSO			X86_BUG( 1*32+ 0) /* "srso" AMD SRSO bug */
"""


def test_the_bug_words_do_not_replace_feature_words():
    """'/* BUG word 2 */' numbers X86_BUG(); feature word 2 is still Transmeta's."""
    c = it.parse_cpufeatures(TRANSMETA_AND_CENTAUR)
    assert (c["longrun"]["leaf"], c["longrun"]["register"], c["longrun"]["linux_defined"]) == \
        ("0x80860001", "EDX", False)
    assert (c["xstore"]["leaf"], c["xstore"]["register"]) == ("0xc0000001", "EDX")


TABLES = {"x86": {"processors": {"haswell": ["avx", "fma"], "bdver1": ["fma4"],
                                 "alderlake": ["avx2"], "c86-4g-m7": ["avx2"]},
                  "aliases": {}}}


def test_an_exception_for_every_intel_part_does_not_touch_amd():
    ex = [{"arch": "x86", "feature": "fma4", "vendor": "intel", "kind": "never-shipped",
           "applies_to": [], "source": "s"}]
    assert it.has(TABLES, "x86", "haswell", "fma4", ex)["verdict"] == "absent: never-shipped"
    assert it.has(TABLES, "x86", "bdver1", "fma4", ex)["exceptions"] == []


def test_hygon_parts_are_not_intel():
    ex = [{"arch": "x86", "feature": "fma4", "vendor": "intel", "kind": "never-shipped",
           "applies_to": [], "source": "s"}]
    assert it.vendor_of("x86", "c86-4g-m7") == "hygon"
    assert it.has(TABLES, "x86", "c86-4g-m7", "fma4", ex)["exceptions"] == []
    assert it.vendor_of("x86", "a-name-llvm-adds-later") is None     # not "intel"


def test_every_committed_x86_processor_has_a_vendor():
    """A new LLVM part with no vendor would silently escape vendor-wide exceptions."""
    procs = it.load_tables()["x86"]["processors"]
    assert [p for p in procs if p not in it._X86_GENERIC and not it.vendor_of("x86", p)] == []


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
    # profile-based parts keep their base ISA and their vector length
    x60 = t["riscv"]["processors"]["spacemit-x60"]
    assert {"i", "m", "a", "c", "64bit", "v", "zvl256b", "zvl128b"} <= set(x60)
    assert all(not t[a]["unresolved"] for a in t)
