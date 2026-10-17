"""The vendor spec agents' rules, checked without a model."""
from __future__ import annotations

import email
import hashlib
import io
import json
import sys
import urllib.request
import urllib.response
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


@pytest.mark.parametrize("page", ["'2'", "2.0", "two", "true"])
def test_a_page_that_is_not_a_number_is_refused_not_skipped(tmp_path, page):
    # page 2 holds the quote; written as a string or a float it used to skip the check
    cache, sha = _cached(tmp_path)
    errs = vr.check_derived(_derived(sha, page=page, quote="a sentence nobody wrote"), cache)
    assert any("page must be a page number" in e for e in errs), errs


def _forged(where: Path, text: str = "Intel shipped FMA4 on every Core processor since 2008.\n",
            sha: str | None = None) -> str:
    """What a Spec Reader can write in its own workspace: a text and a provenance.json."""
    where.mkdir(parents=True)
    (where / "doc.txt").write_text(text)
    sha = sha or hashlib.sha256(text.encode()).hexdigest()
    (where / "provenance.json").write_text(json.dumps(
        {"sha256": sha, "source": "https://www.intel.com/made-up"}))
    return sha


def _citing(ref: str, sha: str) -> str:
    return f"""format: 1
document: {{ref: '{ref}', sha256: {sha}}}
records:
  - {{kind: fact, key: fma4@intel, page: 1,
     quote: 'Intel shipped FMA4 on every Core processor since 2008', claim: x}}
"""


def test_a_document_outside_the_cache_is_not_a_document(tmp_path):
    cache, _ = _cached(tmp_path / "cache")
    fake = tmp_path / "ws" / "hardware" / "fake"
    sha = _forged(fake)
    for ref in (str(fake), "intel/../../ws/hardware/fake", "../ws/hardware/fake",
                "intel/intel-spec-update-6/..", "hardware/fake/"):
        errs = vr.check_derived(_citing(ref, sha), cache)
        assert errs and "bad document ref" in errs[0], (ref, errs)
        with pytest.raises(vr.ResearchError, match="bad document ref"):
            vr.read_document(ref, cache=cache)
    (cache / "ws").symlink_to(tmp_path / "ws" / "hardware")     # a link out of the cache
    with pytest.raises(vr.ResearchError, match="out of the cache"):
        vr.read_document("ws/fake", cache=cache)


def test_a_cached_document_whose_bytes_changed_is_refused(tmp_path):
    # the provenance sha256 is checked against the bytes, never just believed
    cache, sha = _cached(tmp_path)
    su = cache / "intel" / "intel-spec-update-6" / "su.txt"
    su.write_text(su.read_text().replace("line 3\n", "Intel shipped FMA4 on every Core "
                                         "processor since 2008\n"))
    errs = vr.check_derived(_citing("intel/intel-spec-update-6", sha), cache)
    assert errs and "does not hash" in errs[0], errs
    with pytest.raises(vr.ResearchError, match="does not hash"):
        vr.read_document("intel/intel-spec-update-6", cache=cache)
    # nor does a provenance.json that names a made-up sha256 make a document of a text
    sha = _forged(cache / "_scout" / "0123456789abcdef", sha="f" * 64)
    errs = vr.check_derived(_citing("_scout/0123456789abcdef", sha), cache)
    assert errs and "does not hash" in errs[0], errs


class Resp(io.BytesIO):
    def __init__(self, body: bytes, url: str | None = None, headers: dict | None = None):
        super().__init__(body)
        self.headers = headers or {}
        if url:
            self.geturl = lambda: url

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def test_fetch_is_https_and_allowlisted_and_lands_untracked(tmp_path):
    with pytest.raises(vr.ResearchError, match="allowed hosts"):
        vr.fetch_url("https://evil.example/x.pdf", cache=tmp_path)
    with pytest.raises(vr.ResearchError, match="allowed hosts"):
        vr.fetch_url("http://www.intel.com/x.pdf", cache=tmp_path)

    r = vr.fetch_url("https://www.intel.com/docs/su.txt", cache=tmp_path,
                     opener=lambda u: Resp(b"Specification Update\n"))
    assert r["ref"].startswith("_scout/")
    text = vr.read_document(r["ref"], cache=tmp_path)
    assert text.startswith(vr.UNTRUSTED) and "Specification Update" in text


class FakeNet(urllib.request.BaseHandler):
    """The network, for the real opener: url -> (status, Location or None, body)."""
    handler_order = 50          # ahead of urllib's own http(s) and proxy handlers

    def __init__(self, routes: dict):
        self.routes = routes

    def _open(self, req):
        status, location, body = self.routes[req.full_url]
        hdrs = email.message_from_string(f"Location: {location}\n" if location else "")
        resp = urllib.response.addinfourl(io.BytesIO(body), hdrs, req.full_url, status)
        resp.msg = "Found" if location else "OK"
        return resp

    http_open = https_open = _open


def _staged(cache: Path) -> list[Path]:
    return [p for p in (cache / "_scout").rglob("*") if p.is_file()] \
        if (cache / "_scout").exists() else []


@pytest.mark.parametrize("hop", ["https://objects.example.net/x.txt",  # an unlisted host
                                 "http://www.intel.com/x.txt"])       # a downgrade to http
def test_the_allowlist_holds_on_every_redirect_hop(tmp_path, hop):
    net = FakeNet({"https://github.com/rel/x.txt": (302, hop, b""),
                   hop: (200, None, b"bytes from somewhere nobody allowed\n")})
    with pytest.raises(vr.ResearchError, match=f"redirects to {hop}"):
        vr.fetch_url("https://github.com/rel/x.txt", cache=tmp_path,
                     opener=vr._opener(vr.DEFAULT_HOSTS, net))
    assert _staged(tmp_path) == []


def test_an_allowed_redirect_is_followed_and_its_target_is_the_source(tmp_path):
    net = FakeNet({"https://www.intel.com/su": (302, "/docs/su.txt", b""),
                   "https://www.intel.com/docs/su.txt": (200, None, b"Specification Update\n")})
    r = vr.fetch_url("https://www.intel.com/su", cache=tmp_path,
                     opener=vr._opener(vr.DEFAULT_HOSTS, net))
    prov = json.loads((tmp_path / r["ref"] / "provenance.json").read_text())
    assert prov["source"] == "https://www.intel.com/docs/su.txt"
    assert prov["requested"] == "https://www.intel.com/su"


def test_the_url_the_bytes_came_from_must_be_allowed_too(tmp_path):
    with pytest.raises(vr.ResearchError, match="came from https://evil.example/x"):
        vr.fetch_url("https://www.intel.com/x", cache=tmp_path,
                     opener=lambda u: Resp(b"forged\n", url="https://evil.example/x"))
    assert _staged(tmp_path) == []


def test_a_fetch_stops_at_the_size_limit_and_leaves_nothing(tmp_path):
    with pytest.raises(vr.ResearchError, match="100-byte limit"):
        vr.fetch_url("https://www.intel.com/big.txt", cache=tmp_path, max_bytes=100,
                     opener=lambda u: Resp(b"x" * 1000))
    with pytest.raises(vr.ResearchError, match="100-byte limit"):
        vr.fetch_url("https://www.intel.com/big.txt", cache=tmp_path, max_bytes=100,
                     opener=lambda u: Resp(b"x", headers={"Content-Length": "5000000000"}))
    assert _staged(tmp_path) == []


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
