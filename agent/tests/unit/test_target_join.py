"""Choosing a driver from the machine rather than from the intent.

`e1000` was hardcoded into three of the five intent rules, so every network
image AUTON could build was built for an Intel 82540EM whatever machine it was
going to run on — including a Firecracker microVM whose own definition records
`absent: "PCI bus — enumeration finds nothing"`.

`[gate: capabilities]` does not catch it: `e1000` has a source mapping, so the
slice resolves, the gate passes, and the image builds with a driver bound to
nothing. V1 catches *required but unimplementable*. This is *implemented but not
on this machine*, which is the mirror case.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from device_drivers import driver_for_device  # noqa: E402
from intent_manifest import (  # noqa: E402
    DEFAULTS,
    INTENTS,
    IntentError,
    TargetMismatch,
    build,
)
from target_spec import load as load_target  # noqa: E402

TARGETS = ROOT / "agent" / "kernel_spec" / "targets"


@pytest.fixture
def target_file(tmp_path):
    """A target with the devices and absences a test needs, and nothing else."""
    def _write(name="widget", devices=(("8086:100e", "network"),), absent=(),
               klass="vm", source="probed"):
        lines = ["---", f"target: {name}", f"class: {klass}", "arch: x86_64",
                 "firmware: bios", "silicon:", "  vendor: GenuineIntel",
                 "  family: 6", "  model: 6", "  stepping: 3",
                 "  source: probed", "devices:"]
        for dev_id, role in devices:
            lines += [f'  - id: "{dev_id}"', f"    role: {role}",
                      f"    source: {source}"]
        if absent:
            lines.append("absent:")
            lines += [f'  - "{a}"' for a in absent]
        lines += ["provenance:", "  stated_by: test", "---", "", "# Widget", ""]
        path = tmp_path / f"{name}.md"
        path.write_text("\n".join(lines))
        return load_target(path)
    return _write


class TestNoIntentRuleNamesADriver:
    def test_no_rule_requires_a_driver(self):
        """An intent is about purpose. "Hand out addresses" says nothing about
        which NIC, and encoding one there is how a purpose became a hardware
        decision nobody made."""
        drivers = {"e1000", "e1000e", "virtio-net", "virtio-blk"}
        for rule in INTENTS:
            assert not (set(rule.requires) & drivers), rule.name

    def test_the_three_network_rules_declare_a_role_instead(self):
        by_name = {r.name: r for r in INTENTS}
        for name in ("host-repo", "serve-dhcp", "serve-files"):
            assert by_name[name].roles == ("network",)

    def test_a_role_is_not_put_in_requires(self):
        """`net` is a subsystem name, not an index capability:
        capability_slice(["boot","net"]) and capability_slice(["boot","udp"])
        resolve to the same six subsystems. A role in `requires` would be an
        alias for a capability and would break services/README.md rule 2."""
        for rule in INTENTS:
            assert not (set(rule.requires) & set(rule.roles))


class TestTheMachineChoosesTheDriver:
    def test_the_qemu_pc_gets_e1000(self):
        m = build("hand out addresses", None, load_target(TARGETS / "qemu-pc.md"))

        assert "e1000" in m.requires
        assert "virtio-net" not in m.requires

    def test_the_selection_mechanism_picks_the_device_s_own_driver(self, target_file):
        """Exercised against an index that contains the driver, because the
        shipped one does not. `_drivers_from_target` takes the known-capability
        set as an argument precisely so the mechanism can be tested apart from
        what the tree happens to provide today."""
        from intent_manifest import INTENTS, _drivers_from_target

        rule = next(r for r in INTENTS if r.name == "serve-dhcp")
        t = target_file(devices=(("1af4:1000", "network"),))

        drivers, _assumptions, decisions = _drivers_from_target(
            rule, t, {"virtio-net", "e1000"})

        assert drivers == ["virtio-net"]
        assert decisions[0]["device"] == "1af4:1000"

    def test_a_second_network_driver_is_now_selectable(self):
        """This join's original finding was that `drivers.md` `provides` listed
        exactly one network driver, so the only machines AUTON could build a
        network image for were machines with an Intel e1000. V5 added
        `virtio-net`, which is what unblocked every microVM.

        The old assertion was written to fail the moment a second driver
        appeared. It did, and this replaces it."""
        from capability_slice import load_specs

        provided = {c for s in load_specs().values() for c in s.provides}
        net_drivers = {d for d in ("e1000", "e1000e", "virtio-net") if d in provided}

        assert net_drivers == {"e1000", "virtio-net"}

    def test_the_join_is_on_role_not_on_id(self, target_file):
        """A microVM's network device is `virtio-mmio:1` — no vendor:device pair
        exists anywhere in the transport, so a lookup keyed on `vvvv:dddd`
        cannot see it at all."""
        assert driver_for_device("virtio-mmio:1") == "virtio-net"
        assert driver_for_device("1af4:1041") == "virtio-net"   # modern virtio-pci

    def test_a_device_with_no_driver_is_named(self, target_file):
        """QEMU's Bochs VGA is on the bus and nothing drives it. Reporting the
        role as unsatisfiable without naming the device leaves the reader to
        guess which one."""
        t = target_file(devices=(("1234:1111", "network"),))

        with pytest.raises(TargetMismatch, match="1234:1111"):
            build("hand out addresses", None, t)


class TestAMachineThatCannotServeTheIntentIsRefused:
    def test_no_device_for_the_role_refuses(self, target_file):
        t = target_file(devices=(("8086:1237", "host-bridge"),))

        with pytest.raises(TargetMismatch, match="role 'network'"):
            build("hand out addresses", None, t)

    def test_the_refusal_names_the_role_not_the_driver(self, target_file):
        """"No driver for e1000" is a different and less useful sentence than
        "this machine has no network device" — and the second is the true one."""
        t = target_file(devices=(("8086:1237", "host-bridge"),))

        with pytest.raises(TargetMismatch) as exc:
            build("hand out addresses", None, t)

        assert "e1000" not in str(exc.value)

    def test_a_recorded_absence_is_quoted_back(self, target_file):
        t = target_file(devices=(("8086:1237", "host-bridge"),),
                        absent=("network — the host manifest excludes 'net'",))

        with pytest.raises(TargetMismatch, match="excludes 'net'"):
            build("hand out addresses", None, t)

    def test_a_driver_no_subsystem_provides_is_refused_by_name(self, target_file):
        """The mechanism, exercised against a driver the index still does not
        provide. Firecracker used to be this case — V5 fixed it by specifying
        `virtio-net`, so the test now uses `e1000e`, which `device_drivers` can
        resolve and `drivers.md` does not provide."""
        t = target_file(devices=(("8086:10d3", "network"),))

        with pytest.raises(TargetMismatch) as exc:
            build("hand out addresses", None, t)

        assert "e1000e" in str(exc.value)
        assert "capability index" in str(exc.value)

    def test_that_refusal_does_not_blame_the_rule_table(self, target_file):
        """The rule table no longer names a driver at all, so an index error
        reported against it would send the reader to an innocent file."""
        t = target_file(devices=(("8086:10d3", "network"),))

        with pytest.raises(TargetMismatch) as exc:
            build("hand out addresses", None, t)

        assert "rule table and the specs disagree" not in str(exc.value)

    def test_firecracker_is_no_longer_refused(self):
        """V5's headline outcome. This target was refused outright until
        `virtio-net` entered the capability index."""
        t = load_target(TARGETS / "firecracker.md")

        m = build("hand out addresses", None, t)

        assert "virtio-net" in m.requires
        assert m.decisions[0]["device"] == "virtio-mmio:1"


class TestATargetReplacesAnAssumptionRatherThanImprovingIt:
    def test_without_a_target_the_driver_is_an_assumption(self):
        """Still `e1000`, because a caller with no target has said nothing about
        the machine. The change is that it is recorded rather than invisible."""
        m = build("hand out addresses")

        assert "e1000" in m.requires
        assert any(a.startswith("network:") for a in m.assumptions)

    def test_with_a_target_it_is_a_decision(self):
        m = build("hand out addresses", None, load_target(TARGETS / "qemu-pc.md"))

        assert not any(a.startswith("network:") for a in m.assumptions)
        assert any(d["role"] == "network" for d in m.decisions)

    def test_a_recorded_absence_settles_the_input_question(self):
        """Not a better guess — a fact. `firecracker.md` records that the
        machine has no display at all, which settles the question the assumption
        existed to paper over."""
        before = build("what hardware is this")
        after = build("what hardware is this", None,
                      load_target(TARGETS / "firecracker.md"))

        assert len(before.assumptions) == 1
        assert after.assumptions == []
        assert any(d["role"] == "input" for d in after.decisions)

    def test_the_network_default_is_declared_not_buried(self):
        assert DEFAULTS["network"][0] == "e1000"


class TestTheJoinIsRecorded:
    def test_the_decision_names_the_device_that_chose_the_driver(self):
        m = build("hand out addresses", None, load_target(TARGETS / "qemu-pc.md"))

        d = next(x for x in m.decisions if x["role"] == "network")
        assert d["device"] == "8086:100e"
        assert d["driver"] == "e1000"
        assert d["target"] == "qemu-pc"

    @pytest.mark.parametrize("source", ["probed", "derived", "user-stated"])
    def test_the_decision_carries_the_device_s_own_source(self, target_file, source):
        """A driver chosen from a probed device rests on different evidence from
        one chosen from a device somebody merely stated, and the record must say
        which. Parameterised because a single `probed` fixture lets a hardcoded
        "probed" pass — it did, until this test was widened."""
        t = target_file(source=source)

        m = build("hand out addresses", None, t)

        assert next(x for x in m.decisions
                    if x["role"] == "network")["device_source"] == source

    def test_the_manifest_names_its_target(self):
        m = build("hand out addresses", None, load_target(TARGETS / "qemu-pc.md"))
        assert m.target == "qemu-pc"

    def test_a_manifest_with_no_target_says_so(self):
        assert build("hand out addresses").target == ""

    def test_decisions_survive_serialisation(self):
        import json

        m = build("hand out addresses", None, load_target(TARGETS / "qemu-pc.md"))
        parsed = json.loads(m.to_json())

        assert parsed["target"] == "qemu-pc"
        assert parsed["decisions"][0]["driver"] == "e1000"


class TestNothingBrokeThatWorked:
    def test_an_intent_with_no_roles_needs_no_target(self):
        assert build("I want to play Doom").requires

    def test_an_unknown_sentence_is_still_declined_not_mismatched(self):
        with pytest.raises(IntentError) as exc:
            build("make me a sandwich")
        assert not isinstance(exc.value, TargetMismatch)
