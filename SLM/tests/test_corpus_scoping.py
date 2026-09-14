"""Manifest scoping: an image ships corpus records only for what it can do.

The hypothesis under test (`auton-intent-to-os-compiler.prd.md`) is that the
model is bad because it is *general*. The measured garbage was cross-intent
mis-routing — `i need gpu access` answered with the NIC, `can i run nginx`
answered with the kubernetes roadmap — and intent classes that cannot coexist
in an image cannot mis-route into each other.

`excludes` is the load-bearing field: without it "minimal" is unfalsifiable.
These check it on the built artifact, which is the only place a leak is real.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "SLM" / "tools"))

from build_corpus import (  # noqa: E402
    CAP_MARKERS,
    Manifest,
    build,
    mentions,
)

MANIFESTS = ROOT / "SLM" / "manifests"


@pytest.fixture(scope="module")
def doom() -> Manifest:
    return Manifest.load(MANIFESTS / "doom.json")


@pytest.fixture(scope="module")
def webserver() -> Manifest:
    return Manifest.load(MANIFESTS / "webserver.json")


# --- the manifest itself ---------------------------------------------------- #

def test_excludes_is_required():
    """A manifest without excludes cannot be checked, so it is rejected rather
    than defaulted to empty."""
    import tempfile

    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"requires": ["boot"]}, f)
    with pytest.raises(ValueError, match="excludes"):
        Manifest.load(f.name)


def test_a_contradictory_manifest_is_rejected():
    with pytest.raises(ValueError, match="both requires and excludes"):
        Manifest(requires=["net"], excludes=["net"])


def test_parenthesised_features_reduce_to_a_base_capability():
    """The PRD writes `drivers(framebuffer, input)`; scoping keys off `drivers`."""
    m = Manifest(requires=["drivers(framebuffer, input)"], excludes=["fs(writable)"])

    assert m.requires == {"drivers"}
    assert m.excludes == {"fs"}


# --- scoping --------------------------------------------------------------- #

def test_two_manifests_produce_different_corpora(doom, webserver):
    d, w = build(0, doom), build(0, webserver)

    assert len(d) < len(w), f"doom {len(d)} should be smaller than webserver {len(w)}"
    assert {r["fact"] for r in d} != {r["fact"] for r in w}


def test_scoping_only_removes(doom):
    """A scoped corpus is a subset. Scoping must not invent records, or the
    garbage measurement is comparing two different things."""
    scoped = {r["text"] for r in build(0, doom)}
    unscoped = {r["text"] for r in build(0, None)}

    assert scoped <= unscoped, f"scoping invented: {sorted(scoped - unscoped)[:3]}"


@pytest.mark.parametrize("name", ["doom", "webserver"])
def test_no_excluded_capability_leaks(name):
    """The acceptance check, run on the artifact rather than the intent.

    An image with no network must not ship a single record that mentions one —
    not in an answer, not in a question, not in the refusal it uses to decline
    everything else.
    """
    manifest = Manifest.load(MANIFESTS / f"{name}.json")
    rows = build(0, manifest)

    leaks = [
        (cap, word, r["fact"], r["response"][:60])
        for r in rows
        for cap in manifest.excludes
        for word in CAP_MARKERS.get(cap, ())
        if mentions(r["text"] + " " + r["response"], word)
    ]
    assert not leaks, f"{name} leaks {len(leaks)} excluded mentions: {leaks[:3]}"


def test_an_image_with_no_network_ships_no_dhcp_record(doom):
    """The PRD's own example of what scoping is for."""
    rows = build(0, doom)

    assert not [r for r in rows if "dhcp" in r["response"].lower()]
    assert not [r for r in rows if r["fact"] == "sys:ip"]


def test_core_behaviour_ships_in_every_image(doom, webserver):
    """Declining an out-of-domain question is not a capability. An image that
    cannot say no is worse than one that cannot do much."""
    for manifest in (doom, webserver):
        rows = build(0, manifest)
        assert [r for r in rows if r["intent"] == "OUT_OF_DOMAIN"]


# --- truthfulness under scoping --------------------------------------------- #

def test_the_refusal_does_not_advertise_a_missing_capability(doom, webserver):
    """The decline names what the machine *can* answer about. Offering network
    questions on an image with no network is the same defect as citing a PCI id
    that is not on the bus."""
    doom_refusal = next(r["response"] for r in build(0, doom)
                        if r["intent"] == "OUT_OF_DOMAIN")
    web_refusal = next(r["response"] for r in build(0, webserver)
                       if r["intent"] == "OUT_OF_DOMAIN")

    assert not mentions(doom_refusal, "network")
    assert mentions(web_refusal, "network")


def test_a_device_is_annotated_with_a_driver_only_if_the_image_ships_it(doom, webserver):
    """The NIC is on the bus of a Doom image too. Writing `8086:100e(e1000)`
    there claims a binding that does not exist."""
    doom_devices = next(r["response"] for r in build(0, doom)
                        if r["fact"] == "sys:devices")
    web_devices = next(r["response"] for r in build(0, webserver)
                       if r["fact"] == "sys:devices")

    assert "8086:100e" in doom_devices, "the device is still physically present"
    assert "e1000" not in doom_devices, "but no driver is bound for it"
    assert "8086:100e(e1000)" in web_devices


def test_the_status_line_does_not_claim_an_address_it_lacks(doom, webserver):
    """`status` is a composite. Shipped unchanged to an image with no network,
    it teaches the model to state an IP the machine never had."""
    doom_status = next(r["response"] for r in build(0, doom)
                       if r["fact"] == "sys:status")
    web_status = next(r["response"] for r in build(0, webserver)
                      if r["fact"] == "sys:status")

    assert "10.0.2.15" not in doom_status
    assert "255 MB RAM" in doom_status
    assert "10.0.2.15" in web_status


# --- the guarantees scoping must not weaken --------------------------------- #

def test_eval_contamination_filter_stays_on_under_scoping(doom):
    """Scoping narrows the corpus. It must not become a way to smuggle an eval
    prompt back in — the filter is unconditional."""
    eval_prompts = ROOT / "tests" / "eval" / "prompts.jsonl"
    import re

    def norm(t: str) -> str:
        return re.sub(r"[^a-z0-9: ]+", "", t.lower()).strip()

    held_out = {norm(json.loads(l)["prompt"])
                for l in eval_prompts.read_text().splitlines() if l.strip()}
    scoped = {norm(r["text"]) for r in build(0, doom)}

    assert not (scoped & held_out), f"contaminated: {sorted(scoped & held_out)[:3]}"


def test_a_scoped_corpus_is_still_big_enough_to_train(doom):
    """Rung 3a produced 61 tokens and train.py rejected the batch. Scoping makes
    that much more likely, so the floor is asserted rather than discovered three
    stages later."""
    rows = build(0, doom)
    approx = sum(len(r["text"].split()) + len(r["response"].split()) for r in rows)

    assert approx >= 2048, f"~{approx} tokens is below a 64x32 batch"
