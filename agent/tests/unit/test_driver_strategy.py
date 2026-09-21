"""Choosing a driver strategy — reuse, port, synthesize, or none.

The ordering is not the intuitive one. Synthesis looks like the natural fit for
a project that generates its own OS, and it is the most dangerous option
available: a synthesized DMA programming error is an arbitrary-write primitive
that no prior execution has ever exercised. So the default is reuse > port >
synthesize, and synthesis carries the heaviest verification burden.

The distinction these tests exist to hold is between *available* and
*preferred*. Synthesize is almost always available — there is usually some
document — which is exactly why availability cannot be the criterion.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from driver_strategy import (  # noqa: E402
    NORMATIVE_KINDS,
    ORDER,
    Availability,
    StrategyError,
    _licence_permits,
    licence_table,
    select,
)
from device_registry import Outcome, identify  # noqa: E402

CACHED = identify("8086:100e").outcome is not Outcome.UNAVAILABLE
needs_registry = pytest.mark.skipif(not CACHED, reason="pci.ids not cached")


class TestTheOrderingIsTheSecurityArgument:
    def test_reuse_beats_port_beats_synthesize(self):
        assert ORDER == ("reuse", "port", "synthesize")

    @needs_registry
    def test_an_implemented_driver_is_reused(self):
        """Nothing beats code that has been run."""
        d = select("8086:100e")

        assert d.chosen.strategy == "reuse"
        assert "e1000" in d.chosen.reason

    @needs_registry
    def test_every_option_is_recorded_not_just_the_winner(self):
        """A decision that records only its conclusion cannot be reviewed, and
        this is ring-0 code."""
        d = select("8086:100e")

        assert {o.strategy for o in d.options} == set(ORDER)

    @needs_registry
    def test_the_rationale_names_what_was_beaten(self):
        d = select("virtio-mmio:1")
        # Nothing is chosen here, but when something is, the rationale explains
        # why the preferred options lost.
        assert d.refused
        assert "no strategy is defensible" in d.rationale()


class TestAvailableIsNotPreferred:
    def test_a_registry_is_not_a_normative_basis(self):
        """`pci.ids` tells you a device exists, not how to program it."""
        assert "device-registry" not in NORMATIVE_KINDS
        assert "security-advisory" not in NORMATIVE_KINDS

    def test_an_uningested_specification_does_not_make_synthesis_available(self):
        """Not "does a document exist" but "is it inventoried *and* ingestable".
        A datasheet nobody can fetch is a citation, not a basis."""
        d = select("virtio-mmio:1")
        synth = next(o for o in d.options if o.strategy == "synthesize")

        assert synth.availability is Availability.BLOCKED
        assert not synth.usable

    def test_that_state_is_actionable_and_says_so(self):
        """"Not inventoried" and "not ingested" are different, and the second
        has a command that fixes it."""
        synth = next(o for o in select("virtio-mmio:1").options
                     if o.strategy == "synthesize")

        assert "vendor_fetch.py" in synth.reason
        assert synth.basis == "oasis-virtio/virtio-spec"

    def test_three_availability_states_not_two(self):
        assert len(set(Availability)) == 3


class TestLicencesAreATableNotAJudgement:
    def test_unknown_makes_reuse_and_port_unavailable(self):
        """Not a neutral state. An unrecorded licence is a defect that surfaces
        at distribution, long after anyone can answer it cheaply."""
        for act in ("reuse", "port"):
            ok, why = _licence_permits(None, act)
            assert not ok
            assert "unavailable" in why

    def test_a_licence_absent_from_the_table_is_refused_by_name(self):
        ok, why = _licence_permits("WTFPL-1.0", "reuse")

        assert not ok
        assert "not in licences.yaml" in why

    @pytest.mark.parametrize("licence", ["GPL-2.0-only", "GPL-2.0-or-later"])
    def test_a_combination_dependent_licence_refuses_rather_than_decides(self, licence):
        """Where the answer depends on how code is combined, the table says so
        and the selector refuses. It does not characterise what is safe."""
        ok, why = _licence_permits(licence, "port")

        assert not ok
        assert "a human must decide" in why

    def test_a_documentation_licence_is_not_a_code_licence(self):
        """CC-BY is a basis for synthesize, never for reuse or port."""
        ok, why = _licence_permits("CC-BY-4.0", "reuse")

        assert not ok
        assert "documentation licence" in why

    def test_permissive_licences_permit_both_acts(self):
        for licence in ("MIT", "BSD-3-Clause", "Apache-2.0"):
            for act in ("reuse", "port"):
                ok, _ = _licence_permits(licence, act)
                assert ok, f"{licence}/{act}"

    def test_no_entry_claims_a_licence_is_safe(self):
        """The table records obligations. "Safe" is a judgement it must not make."""
        import json

        text = json.dumps(licence_table()).lower()
        assert "safe" not in text
        assert "compatible" not in text

    def test_every_entry_records_what_it_requires(self):
        for name, entry in licence_table().items():
            assert "requires" in entry, name
            assert "depends_on_use" in entry, name


class TestRefusingRatherThanGuessing:
    def test_no_defensible_option_refuses(self):
        d = select("virtio-mmio:1")

        assert d.refused
        assert d.chosen is None

    def test_the_refusal_names_all_three_options(self):
        d = select("virtio-mmio:1")

        assert len(d.options) == 3
        assert all(o.reason for o in d.options)

    @needs_registry
    def test_a_device_in_no_inventory_refuses_naming_that(self):
        """QEMU's Bochs VGA: vendor 1234 is an id QEMU invented, and no
        publisher in vendors.yaml speaks for it."""
        d = select("1234:1111")
        synth = next(o for o in d.options if o.strategy == "synthesize")

        assert d.refused
        assert synth.availability is Availability.ABSENT
        assert "no vendor" in synth.reason

    def test_an_unreadable_registry_is_undecidable_not_undrivable(self, monkeypatch):
        """An unidentified device is not the same as an undrivable one. On a
        fresh checkout `.cache/` is empty, and refusing every device there would
        be refusing for a reason that is false."""
        import device_registry
        from device_registry import Identification

        monkeypatch.setattr(
            device_registry, "identify",
            lambda _id: Identification(_id, Outcome.UNAVAILABLE,
                                       reason="no registry cached"))

        with pytest.raises(StrategyError, match="no pci.ids registry cached"):
            select("8086:100e")


class TestTheInventoryGapThisFound:
    def test_virtio_is_inventoried(self):
        """The selector refused `synthesize` for virtio-net because its cited
        specification was in no inventory — a citation rather than a basis."""
        from vendor_inventory import load

        names = {v.vendor for v in load()}
        assert "oasis-virtio" in names

    def test_its_specification_is_normative(self):
        from vendor_inventory import load

        v = next(x for x in load() if x.vendor == "oasis-virtio")
        assert any(d.kind in NORMATIVE_KINDS for d in v.documents)

    def test_it_is_not_committed_and_the_fetch_plan_says_where(self):
        """Freely downloadable is not freely redistributable. `.cache/` is
        gitignored and `fetch_plan` refuses a tracked destination."""
        from vendor_inventory import fetch_plan, is_tracked_path

        plan = fetch_plan("oasis-virtio", ".cache/vendor")
        assert plan and not is_tracked_path(plan[0]["into"])
        assert plan[0]["redistributable"] is False

    def test_a_tracked_destination_is_refused(self):
        from vendor_inventory import InventoryError, fetch_plan

        with pytest.raises(InventoryError, match="tracked"):
            fetch_plan("oasis-virtio", "agent/hardware")

    def test_the_record_and_the_inventory_now_agree(self):
        """`virtio-net.md` cites VIRTIO; the inventory now says who publishes it
        and under what access. Before this, the two did not meet anywhere."""
        from driver_spec import load
        from vendor_inventory import load as load_inventory

        rec = load(ROOT / "agent" / "kernel_spec" / "drivers" / "virtio-net.md")
        v = next(x for x in load_inventory() if x.vendor == "oasis-virtio")

        assert "VIRTIO" in rec.specification
        assert any("VIRTIO" in d.title for d in v.documents)
