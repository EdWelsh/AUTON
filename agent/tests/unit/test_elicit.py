"""Asking about a target — only what derivation and probing could not answer.

The PRD's hypothesis is that most hardware definitions can be derived, and the
ones that cannot should be a short conversation rather than a form. This phase
is as much a measurement of that claim as a feature, and it was built last on
purpose: the metric is how rarely it is reached.

The risk it exists to avoid is named in the PRD as **H** — "elicitation becomes
a 40-question form nobody finishes" — so several of these tests are about
question *counts*, not just answers.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from elicit import (  # noqa: E402
    CONTAINER_WORDS,
    Draft,
    answer,
    measure,
    next_question,
    run,
    to_target,
)
from target_spec import TargetError, load, missing_facts  # noqa: E402

MICROVM = {"class": "microvm", "hypervisor": "firecracker", "machine": "default",
           "firmware": "none", "silicon": "unknown"}


def _written(tmp_path, draft):
    path = tmp_path / f"{draft.name}.md"
    path.write_text(to_target(draft))
    return path


class TestQuestionsComeFromTheValidator:
    def test_the_question_list_tracks_missing_facts(self):
        """`missing_facts` already computes what a definition needs, per class,
        each with its reason. A second list of questions would drift — and the
        drift shows up as asking for something the format does not need, or
        failing to ask for something it does."""
        draft = Draft(klass="microvm", firmware="none",
                      silicon={"vendor": "x", "family": "6", "model": "1",
                               "stepping": "0", "source": "user-stated"})

        gaps = {one
                for f, _ in missing_facts(draft.as_target())
                for one in f.split(".")[-1].strip("{}").split(",")}
        q = next_question(draft)

        assert q is not None
        assert q.field.split(".")[-1] in gaps

    def test_a_target_missing_one_fact_asks_one_question(self):
        draft = Draft(klass="microvm",
                      platform={"hypervisor": "firecracker", "machine": "default"},
                      silicon={"vendor": "x", "family": "6", "model": "1",
                               "stepping": "0", "source": "user-stated"})

        q = next_question(draft)
        assert q.field == "firmware"

        answer(draft, q, "none")
        assert next_question(draft) is None

    def test_a_complete_draft_asks_nothing(self):
        draft, _ = run(MICROVM)
        assert next_question(draft) is None

    def test_questions_are_asked_one_at_a_time(self):
        """A form asks everything up front and therefore asks things later
        answers would have made unnecessary — the probe offer removes every
        device question, and cannot if they were already on the page."""
        draft = Draft()
        first = next_question(draft)

        assert isinstance(first, type(next_question(Draft())))
        assert first.field == "class"

    def test_a_multi_field_platform_gap_is_split(self):
        """`missing_facts` names them together — `platform.{hypervisor,machine}`.
        One at a time is the rule, so the first unanswered one is the question."""
        draft = Draft(klass="microvm")

        q = next_question(draft)
        assert q.field == "platform.hypervisor"

        answer(draft, q, "firecracker")
        assert next_question(draft).field == "platform.machine"


class TestTheCheaperPathIsOfferedFirst:
    def test_a_probe_is_offered_before_any_device_question(self):
        """A tool that asks twelve device questions when one paste would do has
        made the form the product."""
        draft = Draft(klass="bare-metal")

        assert next_question(draft).field == "probe"

    def test_accepting_the_probe_removes_the_device_questions(self):
        accepted, _ = run({"class": "bare-metal", "probe": "yes",
                           "firmware": "uefi", "silicon": "GenuineIntel 6 142 10"})
        refused, _ = run({"class": "bare-metal", "probe": "no",
                          "firmware": "uefi", "silicon": "GenuineIntel 6 142 10",
                          "devices": "8086:100e network"})

        assert accepted.asked < refused.asked
        assert accepted.devices == []

    def test_questions_name_the_command_that_would_answer_them(self):
        """A question that could have been a paste is a question that should not
        have been asked, and the prompt says so."""
        draft = Draft(klass="bare-metal", probe_offered=True)

        q = next_question(draft)
        assert q.cheaper == "lspci -nn"

    def test_the_class_question_offers_a_command_too(self):
        assert next_question(Draft()).cheaper == "dmidecode -t system"


class TestTheContainerCaseIsSurfacedNeverResolved:
    @pytest.mark.parametrize("word", CONTAINER_WORDS)
    def test_every_container_word_surfaces_the_distinction(self, word):
        """A kernel cannot run inside a container — a container shares the
        host's kernel, which is what a container is."""
        draft = Draft()
        note = answer(draft, next_question(draft), f"put it in a {word}")

        assert "cannot run inside a container" in note
        assert draft.klass == ""

    def test_neither_branch_is_chosen_without_an_answer(self):
        """Guessing produces either an unbootable image or a useless one, and
        the user cannot tell which they got until it fails."""
        draft = Draft()
        answer(draft, next_question(draft), "docker container")

        assert draft.klass == ""
        assert next_question(draft).field == "container_meaning"

    def test_the_microvm_reading_is_not_preferred_silently(self):
        """It is the more common reading, which is exactly why picking it would
        be the easy mistake. The PRD names this risk as H."""
        draft, _ = run({"class": "docker container"})

        assert draft.klass == ""

    def test_answering_microvm_proceeds(self):
        draft, _ = run(dict(MICROVM, **{"class": "in a k8s pod",
                                        "container_meaning": "microvm"}))

        assert draft.klass == "microvm"

    def test_answering_artifact_produces_no_target_class(self):
        """An OCI image shipping the ISO is a packaging job — there is no
        machine to describe."""
        draft, notes = run({"class": "docker", "container_meaning": "artifact"})

        assert draft.klass == ""
        assert any("packaging job" in n for n in notes)

    def test_the_question_is_asked_once_not_repeatedly(self):
        """Re-asking `class` on a container answer never advances the loop. It
        did, until the disambiguation became its own question."""
        draft, _ = run({"class": "docker container"})

        assert draft.asked == 2          # class, then the disambiguation

    def test_declining_the_class_ends_the_conversation(self):
        """Every remaining question is per-class — what a microVM needs and what
        bare metal needs share almost nothing — so asking them of a machine
        nobody has named collects answers to the wrong questions."""
        draft, _ = run({"class": "docker container"})

        assert draft.klass == ""
        assert "firmware" not in draft.declined
        assert "silicon" not in draft.declined


class TestEveryAnswerIsUserStated:
    def test_no_elicited_fact_claims_to_be_probed_or_derived(self, tmp_path):
        """D3 forbids a derivation writing `probed`; D4 is the only tool that
        may. This is the third leg — a stated fact must be distinguishable from
        an observed one."""
        draft, _ = run({"class": "bare-metal", "probe": "no", "firmware": "uefi",
                        "silicon": "GenuineIntel 6 142 10",
                        "devices": "8086:100e network"}, name="box")
        text = to_target(draft)

        assert "source: probed" not in text
        assert "source: derived" not in text

    def test_devices_carry_user_stated(self, tmp_path):
        draft, _ = run({"class": "bare-metal", "probe": "no", "firmware": "uefi",
                        "silicon": "GenuineIntel 6 142 10",
                        "devices": "8086:100e network"}, name="box")
        t = load(_written(tmp_path, draft))

        assert [d.source for d in t.devices] == ["user-stated"]

    def test_the_provenance_records_how_many_questions_it_took(self, tmp_path):
        draft, _ = run(MICROVM, name="m")
        t = load(_written(tmp_path, draft))

        assert int(t.provenance["questions_asked"]) == draft.asked


class TestIDontKnowIsAnAnswer:
    @pytest.mark.parametrize("reply", ["", "idk", "skip", "?"])
    def test_a_declined_question_leaves_the_fact_unstated(self, reply):
        """A form that will not let you say "I don't know" collects a guess and
        records it as a statement."""
        draft = Draft(klass="bare-metal", probe_offered=True)
        q = next_question(draft)
        answer(draft, q, reply)

        assert draft.devices == []
        assert "devices" in draft.declined

    def test_declining_is_recorded_not_silent(self, tmp_path):
        draft, _ = run({"class": "bare-metal", "probe": "no", "devices": "skip",
                        "firmware": "skip", "silicon": "skip"}, name="nothing")

        assert "declined" in to_target(draft)

    def test_declining_everything_yields_a_refused_target(self, tmp_path):
        draft, _ = run({"class": "bare-metal", "probe": "no", "devices": "skip",
                        "firmware": "skip", "silicon": "skip"}, name="nothing")

        with pytest.raises(TargetError) as exc:
            load(_written(tmp_path, draft))

        assert "firmware" in str(exc.value)
        assert "silicon" in str(exc.value)

    def test_unknown_silicon_is_a_statement_not_a_decline(self, tmp_path):
        """For a microVM guest, "nobody can know, the host chooses the CPU" is a
        statement — and it is the one D3's derivation makes for the same reason.
        Declining is saying nothing; asserting unknowability is saying
        something."""
        draft, _ = run(MICROVM, name="m")
        t = load(_written(tmp_path, draft))

        assert t.silicon["source"] == "assumed"
        assert "silicon" not in draft.declined

    def test_that_target_validates(self, tmp_path):
        from target_spec import validate

        draft, _ = run(MICROVM, name="m")
        assert validate(_written(tmp_path, draft)).target.klass == "microvm"


class TestTheHypothesisIsMeasured:
    def test_derivation_and_probing_ask_nothing(self):
        """"Most hardware definitions can be derived rather than elicited." If
        this row is ever non-zero, the hypothesis has failed and the elicitation
        UX is the product."""
        rows = dict(measure())

        for label, count in rows.items():
            if "derived" in label or "probed" in label:
                assert count == 0, label

    def test_elicitation_is_a_short_conversation_not_a_form(self):
        """The PRD's stated risk is a 40-question form. The ceiling asserted
        here is deliberately far below that: if it is ever approached, the
        design has drifted."""
        rows = dict(measure())

        for label, count in rows.items():
            assert count <= 8, f"{label} took {count} questions"

    def test_refusing_the_probe_costs_more_questions(self):
        rows = dict(measure())
        accepted = next(v for k, v in rows.items() if "probe accepted" in k)
        refused = next(v for k, v in rows.items() if "probe refused" in k)

        assert refused > accepted

    def test_every_class_in_the_prd_is_measured(self):
        labels = " ".join(label for label, _ in measure())

        for klass in ("microvm", "auton-hosted", "vm", "bare-metal"):
            assert klass in labels


class TestEveryClassIsReachable:
    """The PRD's first success metric: five classes, each with a validated
    definition. A class the format admits but no path can produce is a class
    that exists only in an enum."""

    @pytest.mark.parametrize("klass", ["bare-metal", "vm", "microvm",
                                       "k8s-pod", "auton-hosted"])
    def test_naming_a_class_exactly_is_never_intercepted(self, klass):
        """`k8s-pod` contains "k8s" and was intercepted by the container
        question — the one class you could not reach by naming it. An exact
        class name is a choice from the offered list, not a description."""
        draft = Draft()
        answer(draft, next_question(draft), klass)

        assert draft.klass == klass

    def test_the_offered_options_are_the_ones_that_work(self):
        """A question that offers an option it then refuses is worse than one
        that offers nothing."""
        from target_spec import CLASSES

        assert next_question(Draft()).options == CLASSES

    def test_a_k8s_pod_elicits_to_a_valid_target(self, tmp_path):
        from target_spec import validate

        draft, _ = run({"class": "k8s-pod", "runtime": "containerd",
                        "firmware": "none", "silicon": "unknown"}, name="pod")

        assert validate(_written(tmp_path, draft)).target.klass == "k8s-pod"

    def test_prose_about_containers_is_still_disambiguated(self):
        """Letting an exact class name through must not have opened a hole: a
        description is still a description."""
        draft = Draft()
        note = answer(draft, next_question(draft), "run it in a k8s cluster")

        assert "cannot run inside a container" in note
        assert draft.klass == ""
