"""The vendor spec agents' rules, checked without a model."""
from __future__ import annotations

import hashlib
import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))
sys.path.insert(0, str(ROOT / "agent"))

import vendor_research as vr  # noqa: E402

PAGE_TEXT = "\n".join(f"line {i}" for i in range(vr.PAGE_LINES)) + \
    "\nHSW136 Software Using Intel TSX May Result in Unpredictable System Behavior\n"


def _cached(tmp_path: Path, text: str = PAGE_TEXT) -> tuple[Path, str]:
    d = tmp_path / "intel" / "intel-spec-update-6"
    d.mkdir(parents=True)
    (d / "su.txt").write_text(text)
    sha = hashlib.sha256(text.encode()).hexdigest()
    (d / "provenance.json").write_text(json.dumps({"sha256": sha, "source": "test"}))
    return tmp_path, sha


def _derived(sha: str, page: int = 2, quote: str = "Software Using Intel TSX May Result") -> str:
    return f"""format: 1
document: {{ref: intel/intel-spec-update-6, sha256: {sha}}}
records:
  - kind: erratum
    key: HSW136
    page: {page}
    quote: '{quote}'
    claim: TSX use may lead to unpredictable behaviour on these parts.
"""


def test_a_quote_on_its_page_passes(tmp_path):
    cache, sha = _cached(tmp_path)
    assert vr.check_derived(_derived(sha), cache) == []


def test_a_quote_on_another_page_is_refused(tmp_path):
    cache, sha = _cached(tmp_path)
    errs = vr.check_derived(_derived(sha, page=1), cache)
    assert any("not on page 1" in e for e in errs)


def test_a_paraphrase_is_refused(tmp_path):
    cache, sha = _cached(tmp_path)
    errs = vr.check_derived(_derived(sha, quote="TSX can cause unpredictable behaviour"), cache)
    assert any("paraphrase" in e for e in errs)


def test_citing_other_bytes_is_refused(tmp_path):
    cache, _ = _cached(tmp_path)
    errs = vr.check_derived(_derived("0" * 64), cache)
    assert any("sha256 does not match" in e for e in errs)


def test_fetch_is_https_and_allowlisted_and_lands_untracked(tmp_path):
    with pytest.raises(vr.ResearchError, match="allowed hosts"):
        vr.fetch_url("https://evil.example/x.pdf", cache=tmp_path)
    with pytest.raises(vr.ResearchError, match="allowed hosts"):
        vr.fetch_url("http://www.intel.com/x.pdf", cache=tmp_path)

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    r = vr.fetch_url("https://www.intel.com/docs/su.txt", cache=tmp_path,
                     opener=lambda u: Resp(b"Specification Update\n"))
    assert r["ref"].startswith("_scout/")
    text = vr.read_document(r["ref"], cache=tmp_path)
    assert text.startswith(vr.UNTRUSTED) and "Specification Update" in text


def test_a_proposal_must_be_a_new_valid_inventory_entry():
    good = """vendors:
  - vendor: zhaoxin
    category: cpu
    identity_keys: [family, model, stepping]
    documents: []
    gaps:
      - kind: errata
        reason: No public specification updates found.
"""
    assert vr.check_proposal(good) == []
    dup = good.replace("zhaoxin", "intel")
    assert any("already in vendors.yaml" in e for e in vr.check_proposal(dup))
    unsourced = good.replace("documents: []", """documents:
      - {id: zx-manual, title: Manual, kind: architecture-manual, access: public-download,
         redistributable: false, form: pdf}""")
    assert any("say where it is" in e for e in vr.check_proposal(unsourced))


def test_the_queue_puts_cpu_vendors_first():
    q = vr.queue(5)
    assert q and all(any(i.startswith("x86-cpuid-vendor:") for i in r["ids"]) for r in q[:3])


def test_the_roles_get_only_their_tools():
    from orchestrator.llm.tools import SPEC_READER_TOOLS, VENDOR_SCOUT_TOOLS
    names = lambda ts: {t["function"]["name"] for t in ts}
    assert "fetch_url" in names(VENDOR_SCOUT_TOOLS) and "shell" not in names(VENDOR_SCOUT_TOOLS)
    assert "check_hardware_record" in names(SPEC_READER_TOOLS)
    assert "build_kernel" not in names(SPEC_READER_TOOLS) | names(VENDOR_SCOUT_TOOLS)


def _engine(tmp_path, hardware):
    from orchestrator.core.engine import OrchestrationEngine
    eng = OrchestrationEngine(
        workspace_path=tmp_path / "ws", kernel_spec_path=ROOT / "agent" / "kernel_spec",
        config={"llm": {"model": "anthropic/scripted"},
                "agents": {"developer_count": 1, "reviewer_count": 1, "tester_count": 1},
                "validation": {"composition_checks": False}, "hardware": hardware})
    eng.workspace.init()
    eng._init_agents()
    return eng


def test_research_roles_are_registered_and_advertised_only_when_asked(tmp_path):
    eng = _engine(tmp_path, {"research": True, "scout_count": 1, "reader_count": 1,
                             "fetch_hosts": ["docs.example.org"]})
    assert eng.scheduler.status()["vendor_scout"]["total"] == 1
    assert eng.scheduler.status()["spec_reader"]["total"] == 1
    assert {"vendor_scout", "spec_reader"} <= set(eng._agents["manager"].assignable_roles)
    assert eng._agents["vendor_scout-01"].fetch_hosts == ("docs.example.org",)

    plain = _engine(tmp_path / "b", {})
    assert "vendor_scout" not in plain._agents["manager"].assignable_roles
