"""Sentence to capability manifest.

The behaviour that matters most is the refusal. An intent the table does not
cover must be declined, not mapped to a nearest neighbour — an image that boots
and does the wrong thing is discovered by a user, where a refusal is discovered
at build time.

Second is that defaults are recorded. An image arriving without the input
device its user assumed fails at boot, and by then the manifest that caused it
looks innocent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from capability_slice import capability_owner, capability_slice, load_specs  # noqa: E402
from intent_manifest import (  # noqa: E402
    BASE_REQUIRES,
    INTENTS,
    IntentError,
    build,
    derive_excludes,
    match_intent,
)


class TestMatching:
    @pytest.mark.parametrize("sentence,rule", [
        ("I want to play Doom", "play-doom"),
        ("play doom please", "play-doom"),
        ("I want to host this repo", "host-repo"),
        ("set this box up as a web server", "host-repo"),
        ("hand out addresses on this network", "serve-dhcp"),
        ("make it a file server", "serve-files"),
        ("what hardware is in this machine", "identify-hardware"),
    ])
    def test_a_known_intent_matches(self, sentence, rule):
        assert match_intent(sentence).name == rule

    def test_matching_ignores_case_and_punctuation(self):
        assert match_intent("PLAY DOOM!!!").name == "play-doom"

    def test_the_longest_phrase_wins(self):
        """`doom` and `play doom` both match; the specific one must win, or
        adding a broader phrase later silently changes older sentences."""
        assert match_intent("I want to play doom").name == "play-doom"

    def test_an_unknown_intent_is_declined(self):
        with pytest.raises(IntentError, match="do not know how to build"):
            match_intent("make me a sandwich")

    def test_the_refusal_lists_what_is_known(self):
        """A bare 'unknown intent' leaves the user guessing at the vocabulary."""
        with pytest.raises(IntentError) as exc:
            match_intent("something else entirely")

        message = str(exc.value)
        for rule in INTENTS:
            assert rule.name in message

    def test_a_near_miss_is_declined_not_guessed(self):
        """`doomsday` is not `doom`. Whole-word matching, because a substring
        match is how an unrelated sentence acquires an image."""
        with pytest.raises(IntentError):
            match_intent("prepare for the doomsday scenario")


class TestTheRuleTable:
    def test_every_rule_names_capabilities_in_the_index(self):
        """A typo here would produce a silently narrower image rather than an
        error, because an unmatched capability maps to no sources."""
        specs = load_specs()
        known = set(specs) | set(capability_owner(specs))
        for rule in INTENTS:
            unknown = [c for c in rule.requires if c not in known]
            assert not unknown, f"{rule.name}: {unknown}"

    def test_every_rule_resolves_to_a_closed_slice(self):
        for rule in INTENTS:
            capability_slice(list(BASE_REQUIRES) + list(rule.requires), [])

    def test_every_rule_declares_markers(self):
        """Without markers the image cannot be verified — the same rule the
        service-spec format enforces."""
        for rule in INTENTS:
            assert rule.markers, rule.name


class TestGeneratedManifests:
    def test_doom_excludes_the_network(self):
        m = build("I want to play Doom")

        assert "net" in m.excludes
        assert "fs" in m.excludes
        assert "sched" in m.excludes

    def test_the_webserver_does_not_exclude_the_network(self):
        m = build("I want to host this repo")

        assert "net" not in m.excludes
        assert "fs" in m.excludes

    def test_excludes_are_derived_not_declared(self):
        """Nothing in the rule table names an exclude. They come from what the
        slice does not reach, so a capability nobody thought of cannot be
        silently omitted from the list."""
        for rule in INTENTS:
            assert not hasattr(rule, "excludes")

    def test_an_exclude_implied_by_a_broader_one_is_not_repeated(self):
        """Excluding `net` already excludes `tcp`. Listing both reads as two
        decisions where one was made."""
        m = build("I want to play Doom")

        assert "net" in m.excludes
        assert "tcp" not in m.excludes

    def test_a_generated_manifest_resolves(self):
        for rule in INTENTS:
            m = build(rule.phrases[0])
            capability_slice(m.requires, m.excludes)

    def test_assets_come_from_the_rule(self):
        assert build("I want to play Doom").assets == ["doom.wad"]
        assert build("hand out addresses").assets == []


class TestDefaultsAreRecorded:
    def test_an_applied_default_is_surfaced(self):
        """Silently defaulting is how an image arrives without the input device
        its user assumed."""
        m = build("what hardware is in this machine")

        assert m.assumptions, "a default was applied with nothing recorded"
        assert any("input" in a for a in m.assumptions)

    def test_naming_the_input_records_no_assumption(self):
        m = build("what hardware is in this machine", input_device="keyboard")

        assert m.assumptions == []
        assert "keyboard" in m.requires

    def test_an_intent_that_names_its_own_input_assumes_nothing(self):
        m = build("I want to play Doom")

        assert m.assumptions == []
        assert "input" in m.requires


class TestAgainstTheHandWrittenManifests:
    """The hand-written pair is the only reviewed ground truth. A generator
    that disagrees with both is wrong; one that disagrees defensibly means the
    hand-written manifest was."""

    @staticmethod
    def _flat(entries):
        out = set()
        for e in entries:
            base, _, feats = e.partition("(")
            out.add(base.strip())
            out.update(f.strip() for f in feats.rstrip(")").split(",") if f.strip())
        return sorted(out)

    @pytest.mark.parametrize("sentence,path", [
        ("I want to play Doom", "doom.json"),
        ("I want to host this repo", "webserver.json"),
    ])
    def test_generated_and_hand_written_resolve_to_the_same_subsystems(self, sentence, path):
        hand = json.loads((ROOT / "SLM" / "manifests" / path).read_text())
        gen = build(sentence)

        hs = capability_slice(self._flat(hand["requires"]), self._flat(hand["excludes"]))
        gs = capability_slice(gen.requires, gen.excludes)

        assert set(hs.subsystems) == set(gs.subsystems)

    def test_the_webserver_manifest_ships_what_its_markers_promise(self):
        """The bug this round-trip found: requiring `net` wholesale gets none of
        its optional capabilities, so the image could not serve HTTP or take a
        lease while its markers claimed both."""
        hand = json.loads((ROOT / "SLM" / "manifests" / "webserver.json").read_text())
        sl = capability_slice(self._flat(hand["requires"]), self._flat(hand["excludes"]))

        assert "http-server" in sl.capabilities
        assert "dhcp-client" in sl.capabilities
        assert "tcp" in sl.capabilities
