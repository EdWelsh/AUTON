"""Target definition format: validation, refusal, and three-valued identity.

A target says what an image will run on. Until it existed the answer was a
hardcoded literal — QEMU's default PC, baked into `SLM/tools/build_corpus.py`
and into every eval expectation written against it. The failure that costs most
here is a definition that validates while meaning a different machine, because
a driver decision is made from it and the image boots into nothing.

So the tests are mostly about what is *refused*, and about the difference
between "checked and unknown" and "never checked".
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from target_spec import (  # noqa: E402
    EXIT_REFUSED,
    EXIT_UNVERIFIABLE,
    Identification,
    TargetError,
    check_completeness,
    check_devices,
    identify,
    load,
    validate,
)

TARGETS = ROOT / "agent" / "kernel_spec" / "targets"

BASE = {
    "target": "widget",
    "class": "vm",
    "arch": "x86_64",
    "firmware": "bios",
}


@pytest.fixture
def target_file(tmp_path):
    """Write a target definition with fields overridden, named so `target`
    matches the filename — the same trick test_service_spec.py uses."""
    def _write(name="widget", silicon=None, devices=None, platform=None, **overrides):
        fields = dict(BASE, target=name)
        fields.update(overrides)
        sil = silicon if silicon is not None else {
            "vendor": "GenuineIntel", "family": "6", "model": "6",
            "stepping": "3", "source": "probed",
        }
        devs = devices if devices is not None else [
            {"id": "8086:100e", "role": "network", "source": "probed"},
        ]

        lines = ["---"]
        lines += [f"{k}: {v}" for k, v in fields.items()]
        lines.append("silicon:")
        lines += [f"  {k}: {v}" for k, v in sil.items()]
        lines.append("devices:")
        for d in devs:
            lines.append(f'  - id: "{d["id"]}"')
            lines.append(f'    role: {d["role"]}')
            lines.append(f'    source: {d["source"]}')
        if platform:
            lines.append("platform:")
            lines += [f"  {k}: {v}" for k, v in platform.items()]
        lines += ["provenance:", "  stated_by: test", "---", "", "# Widget", ""]

        path = tmp_path / f"{name}.md"
        path.write_text("\n".join(lines))
        return path
    return _write


# --- the shipped definitions ------------------------------------------------ #

def test_both_shipped_targets_load():
    """The format was proven against two structurally different machines. If
    either stops parsing, the format has drifted to fit only one of them."""
    for name in ("qemu-pc", "firecracker"):
        t = load(TARGETS / f"{name}.md")
        assert t.target == name


def test_firecracker_records_silicon_as_assumed():
    """A microVM guest cannot choose its CPU. The value being a guess is not the
    problem; a guess indistinguishable from a probe would be."""
    t = load(TARGETS / "firecracker.md")
    assert t.silicon["source"] == "assumed"
    assert "silicon" in t.assumed_facts


def test_qemu_pc_claims_nothing_as_assumed():
    t = load(TARGETS / "qemu-pc.md")
    assert t.assumed_facts == []


# --- refusals name the field ------------------------------------------------ #

def test_missing_field_is_named(target_file, tmp_path):
    path = target_file()
    path.write_text(path.read_text().replace("firmware: bios\n", ""))
    with pytest.raises(TargetError, match="firmware"):
        load(path)


def test_filename_and_target_must_agree(target_file):
    path = target_file(name="widget")
    path.write_text(path.read_text().replace("target: widget", "target: gadget"))
    with pytest.raises(TargetError, match="they address the same thing"):
        load(path)


def test_unknown_class_is_refused(target_file):
    with pytest.raises(TargetError, match="class 'toaster'"):
        load(target_file(**{"class": "toaster"}))


def test_silicon_without_source_is_refused(target_file):
    """The whole point of the field. An absent source reads exactly like a
    confident one, which is how an assumption survives into a build."""
    sil = {"vendor": "GenuineIntel", "family": "6", "model": "6", "stepping": "3"}
    with pytest.raises(TargetError, match="source"):
        load(target_file(silicon=sil))


def test_source_outside_the_enum_is_refused(target_file):
    sil = {"vendor": "x", "family": "6", "model": "6", "stepping": "3",
           "source": "probably"}
    with pytest.raises(TargetError, match="not one of"):
        load(target_file(silicon=sil))


def test_device_source_outside_the_enum_is_refused(target_file):
    devs = [{"id": "8086:100e", "role": "network", "source": "guessed"}]
    with pytest.raises(TargetError, match="8086:100e"):
        load(target_file(devices=devs))


def test_malformed_device_id_is_refused(target_file):
    devs = [{"id": "8086-100e", "role": "network", "source": "probed"}]
    with pytest.raises(TargetError, match="vvvv:dddd"):
        load(target_file(devices=devs))


# --- underspecified is refused, never defaulted ----------------------------- #

def test_bare_metal_with_no_devices_is_refused(target_file):
    """Nothing is implied by real hardware. Silence means nobody looked, and
    the cost of guessing is an image with no driver for the disk it boots from."""
    path = target_file(**{"class": "bare-metal"}, devices=[])
    with pytest.raises(TargetError, match="devices"):
        validate(path)


def test_microvm_with_a_named_platform_and_no_devices_is_accepted(target_file):
    """A Firecracker guest gets virtio-mmio and nothing else. An empty list is a
    fact — but only once the platform that implies it is on record."""
    path = target_file(**{"class": "microvm", "firmware": "none"}, devices=[],
                       platform={"hypervisor": "firecracker", "machine": "default"})
    assert load(path).devices == []
    check_completeness(load(path))          # does not raise


def test_microvm_without_a_machine_type_is_refused(target_file):
    """Nothing has said which devices are implied, so the empty list is blank
    rather than implied. This is the hole D1 left and D6 closes."""
    path = target_file(**{"class": "microvm", "firmware": "none"}, devices=[],
                       platform={"hypervisor": "firecracker"})
    with pytest.raises(TargetError, match="machine"):
        validate(path)


def test_microvm_with_no_platform_at_all_is_refused(target_file):
    path = target_file(**{"class": "microvm", "firmware": "none"}, devices=[])
    with pytest.raises(TargetError, match="platform"):
        validate(path)


def test_auton_hosted_must_name_its_host_image(target_file):
    """An AUTON-hosted target inherits its device view from the image hosting
    it. Which image that is cannot be inferred from anything else in the file."""
    path = target_file(**{"class": "auton-hosted", "firmware": "none"}, devices=[])
    with pytest.raises(TargetError, match="host_image"):
        validate(path)


def test_refusal_says_how_to_supply_the_missing_facts(target_file):
    """A refusal that only names the gap leaves the reader to guess which of the
    four sources is even available to them."""
    path = target_file(**{"class": "bare-metal"}, devices=[])
    with pytest.raises(TargetError, match="probe the machine, state the fact, or derive it"):
        validate(path)


def test_bare_metal_with_assumed_silicon_is_refused(target_file):
    """CPUID is readable on real silicon, so an assumption here is a guess
    nobody had to make — and errata applicability keys on exactly these fields."""
    sil = {"vendor": "unknown", "family": "0", "model": "0", "stepping": "0",
           "source": "assumed"}
    path = target_file(**{"class": "bare-metal"}, silicon=sil)
    with pytest.raises(TargetError, match="silicon"):
        validate(path)


def test_refusal_names_every_missing_fact_at_once(target_file):
    """One run, the whole list. Naming them one per run turns a thin definition
    into a guessing game."""
    sil = {"vendor": "unknown", "family": "0", "model": "0", "stepping": "0",
           "source": "assumed"}
    path = target_file(**{"class": "bare-metal", "firmware": "none"},
                       silicon=sil, devices=[])
    with pytest.raises(TargetError) as exc:
        validate(path)
    for fact in ("devices", "silicon", "firmware"):
        assert fact in str(exc.value)


def test_refusal_says_it_did_not_default(target_file):
    path = target_file(**{"class": "bare-metal"}, devices=[])
    with pytest.raises(TargetError, match="not the QEMU PC"):
        validate(path)


# --- identification is three-valued ----------------------------------------- #

def test_known_device_identifies_from_the_registry():
    """A table lookup with provenance, never an inference. A model asked to name
    a device produces a plausible one, which is the phantom-id defect."""
    state, detail = identify("8086:100e")
    if state is Identification.UNAVAILABLE:
        pytest.skip("pci.ids not cached on this host")
    assert state is Identification.IDENTIFIED
    assert detail


def test_unlisted_device_is_unknown_not_identified():
    state, _ = identify("ffff:fffe")
    if state is Identification.UNAVAILABLE:
        pytest.skip("pci.ids not cached on this host")
    assert state is Identification.UNKNOWN


def test_probed_device_absent_from_registry_is_accepted(target_file):
    """QEMU's Bochs VGA is vendor 1234, an id QEMU invented. It is genuinely
    present on the machine and genuinely absent from pci.ids, and refusing it
    would make the registry the arbiter of what exists."""
    devs = [{"id": "1234:1111", "role": "display", "source": "probed"}]
    report = check_devices(load(target_file(devices=devs)))
    if report.unverifiable:
        pytest.skip("pci.ids not cached on this host")
    assert report.unlisted == ["1234:1111"]


def test_unprobed_device_absent_from_registry_is_refused(target_file):
    """Backed by neither the registry nor the machine, so backed by nothing."""
    if identify("8086:100e")[0] is Identification.UNAVAILABLE:
        pytest.skip("pci.ids not cached on this host")
    devs = [{"id": "ffff:ffff", "role": "network", "source": "user-stated"}]
    with pytest.raises(TargetError, match="ffff:ffff"):
        check_devices(load(target_file(devices=devs)))


def test_missing_registry_is_unverifiable_not_valid(target_file, monkeypatch):
    """The distinction run_leakage_test.sh draws between 'not generated' and
    'clean'. A target nothing was checked against must not read as checked."""
    import target_spec

    monkeypatch.setattr(
        target_spec, "identify",
        lambda _id: (Identification.UNAVAILABLE, "registry not cached"))

    devs = [{"id": "ffff:ffff", "role": "network", "source": "user-stated"}]
    report = target_spec.check_devices(load(target_file(devices=devs)))
    assert report.unverifiable == ["ffff:ffff"]
    assert not report.ok                  # never reported as valid
    assert report.unlisted == []          # nor as checked-and-known


def test_cli_exits_nonzero_when_nothing_could_be_verified(target_file, monkeypatch, capsys):
    """Exit status is what a build script reads. Unverifiable must not exit 0."""
    import target_spec

    monkeypatch.setattr(
        target_spec, "identify",
        lambda _id: (Identification.UNAVAILABLE, "registry not cached"))
    rc = target_spec.main(["--validate", str(target_file())])
    assert rc == EXIT_UNVERIFIABLE
    assert "UNVERIFIED" in capsys.readouterr().out


# --- the defect this phase exists for --------------------------------------- #

def test_no_code_path_substitutes_a_default_device_set():
    """The regression test for the whole phase.

    `SLM/tools/build_corpus.py` hardcodes QEMU's PC as `BUS_DEVICES`, and that
    literal is why every image so far has been built for one machine without
    anyone deciding to. If a table of device ids ever appears in the target
    tooling, an underspecified target can quietly acquire devices nobody stated
    — and it will validate. A defect with no test is an intention.
    """
    import re

    src = (ROOT / "agent" / "tools" / "target_spec.py").read_text()
    code = "\n".join(
        line for line in src.splitlines() if not line.lstrip().startswith("#"))
    # Strip the module docstring's example invocation before scanning.
    code = code.split('"""', 2)[-1]
    literals = re.findall(r'["\'][0-9a-fA-F]{4}:[0-9a-fA-F]{4}["\']', code)
    assert literals == [], (
        f"device id literal(s) {literals} in target_spec.py — a default device "
        f"set is exactly what this phase refuses")


def test_an_empty_device_list_stays_empty(target_file):
    """Nothing is filled in on the way through. The QEMU PC is a target like any
    other and must be named, never assumed."""
    path = target_file(**{"class": "microvm", "firmware": "none"}, devices=[],
                       platform={"hypervisor": "firecracker", "machine": "default"})
    assert validate(path).target.devices == []


def test_exit_codes_are_three_distinct_values(target_file, monkeypatch, capsys):
    """valid / refused / unverifiable, and none of them collide with argparse's
    own exit 2 for a usage error."""
    import target_spec

    # Pin identification, because this test is about the three exit codes and
    # not about the registry. .cache/vendor/ is gitignored, so on a fresh clone
    # every id came back UNAVAILABLE and a "valid" target exited 3 — the test
    # passed only on a machine where someone had run the ingest.
    monkeypatch.setattr(
        target_spec, "identify",
        lambda _id: (Identification.IDENTIFIED, "pinned for this test"))

    good = target_file(**{"class": "vm"})
    assert target_spec.main(["--validate", str(good)]) == 0

    thin = target_file(name="thin", **{"class": "bare-metal"}, devices=[])
    assert target_spec.main(["--validate", str(thin)]) == EXIT_REFUSED

    monkeypatch.setattr(
        target_spec, "identify",
        lambda _id: (Identification.UNAVAILABLE, "registry not cached"))
    assert target_spec.main(["--validate", str(good)]) == EXIT_UNVERIFIABLE
    assert EXIT_UNVERIFIABLE != 2          # argparse owns 2
    capsys.readouterr()
