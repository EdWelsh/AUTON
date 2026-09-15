"""Manifest to service spec — the handoff between intent-B and the factory.

Two properties carry the weight.

A spec that fails validation must never reach disk. One sitting in
`kernel_spec/services/` looks authoritative, and the next reader has no way to
tell it was rejected.

And the body must be an unmistakable stub. `dhcp.md` cites RFC 2131
normatively; a generator that writes plausible protocol prose produces a
document an agent implements confidently and wrongly — the phantom-PCI-id
failure one layer up, and worse here because a spec is treated as true.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from intent_manifest import IntentError  # noqa: E402
from intent_service import STUB_MARKER, emit  # noqa: E402
from service_spec import ServiceSpecError, load as load_service  # noqa: E402


@pytest.fixture
def out(tmp_path):
    return tmp_path / "services"


class TestEmission:
    @pytest.mark.parametrize("sentence", [
        "I want to play Doom",
        "I want to host this repo",
        "hand out addresses",
        "make it a file server",
        "what hardware is in this machine",
    ])
    def test_every_known_intent_emits_a_valid_spec(self, sentence, out):
        path = emit(sentence, out_dir=out)

        spec = load_service(path)
        spec.resolve()

    def test_the_service_name_matches_the_filename(self, out):
        """service_spec rejects a mismatch, because a build would act on the
        wrong service. The generator must not produce one."""
        path = emit("I want to play Doom", out_dir=out)

        assert load_service(path).service == path.stem

    def test_the_entry_point_is_named(self, out):
        spec = load_service(emit("hand out addresses", out_dir=out))

        assert spec.entry.endswith("_serve")

    def test_markers_and_assets_carry_through_from_the_manifest(self, out):
        spec = load_service(emit("I want to play Doom", out_dir=out))

        assert "doom.wad" in spec.assets
        assert any("DOOM" in m for m in spec.markers)

    def test_excludes_carry_through(self, out):
        spec = load_service(emit("I want to play Doom", out_dir=out))

        assert "net" in spec.excludes

    def test_an_explicit_name_overrides_the_rule_name(self, out):
        path = emit("I want to play Doom", name="doom-image", out_dir=out)

        assert path.stem == "doom-image"
        assert load_service(path).service == "doom-image"


class TestNothingInvalidReachesDisk:
    def test_an_unknown_intent_writes_nothing(self, out):
        with pytest.raises(IntentError):
            emit("make me a sandwich", out_dir=out)

        assert not out.exists() or not list(out.glob("*.md"))

    def test_validation_runs_before_the_file_is_written(self, out, monkeypatch):
        """Forced failure: if validation were done after writing, a rejected
        spec would be left behind looking authoritative."""
        import intent_service

        def reject(_path):
            raise ServiceSpecError("forced")

        monkeypatch.setattr(intent_service, "load_service", reject)
        with pytest.raises(ServiceSpecError):
            emit("I want to play Doom", out_dir=out)

        assert not out.exists() or not list(out.glob("*.md"))


class TestTheBodyIsAStub:
    def test_it_says_so_unmistakably(self, out):
        text = emit("I want to play Doom", out_dir=out).read_text()

        assert STUB_MARKER in text
        assert "empty on purpose" in text

    def test_it_fabricates_no_protocol_behaviour(self, out):
        """The specific failure guarded against: an RFC citation, a wire field,
        or a state machine that nobody verified."""
        text = emit("hand out addresses", out_dir=out).read_text().lower()

        for invention in ("rfc ", "§", "bootrequest", "magic cookie",
                          "state machine", "wire format"):
            assert invention not in text, f"fabricated: {invention!r}"

    def test_it_carries_every_section_a_subsystem_spec_has(self, out):
        """A human fills gaps rather than inventing a structure."""
        text = emit("I want to play Doom", out_dir=out).read_text()

        for heading in ("## Overview", "## Data Structures", "## Interface",
                        "## Behavior", "## Files", "## Dependencies",
                        "## Acceptance Criteria"):
            assert heading in text, heading

    def test_assumptions_from_the_intent_are_recorded_in_the_spec(self, out):
        """intent-B records an applied default. It must survive the handoff, or
        the assumption is lost exactly where an implementer would read it."""
        text = emit("what hardware is in this machine", out_dir=out).read_text()

        assert "## Assumptions carried from the intent" in text
        assert "serial console" in text

    def test_an_intent_with_no_assumptions_says_none(self, out):
        text = emit("I want to play Doom", out_dir=out).read_text()

        assert "- none" in text


class TestAgainstTheHandWrittenSpec:
    def test_the_generated_front_matter_has_the_same_fields_as_dhcp(self, out):
        """dhcp.md was written by hand and reviewed. A generated spec must be
        the same shape, or the factory has two formats."""
        generated = load_service(emit("hand out addresses", out_dir=out))
        hand = load_service(ROOT / "agent" / "kernel_spec" / "services" / "dhcp.md")

        assert set(vars(generated)) == set(vars(hand))

    def test_the_generated_dhcp_spec_resolves_near_the_hand_written_one(self, out):
        """Same purpose, so the slices should be comparable. A large divergence
        means the intent rule and the hand-written spec disagree about what a
        DHCP server needs."""
        generated = load_service(emit("hand out addresses", out_dir=out)).resolve()
        hand = load_service(
            ROOT / "agent" / "kernel_spec" / "services" / "dhcp.md").resolve()

        assert set(generated.subsystems) == set(hand.subsystems)
