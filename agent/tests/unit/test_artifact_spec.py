"""The artifact record and its validator (application-to-environment A1).

The contract an Analyst writes into and everything downstream reads. Every test
here is a refusal, because the failure this exists to prevent is a record that
*looks* complete: a fact with no source, a capability nobody indexed, a port
somebody guessed. Each refusal must name what is wrong and what would fix it —
an agent that cannot tell why it was refused retries the same thing.
"""

from __future__ import annotations

import copy
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

import artifact_spec  # noqa: E402
from artifact_spec import ArtifactError, known, load_bridge, load_index, validate  # noqa: E402
from capability_slice import capability_owner, load_specs  # noqa: E402

VALID = ROOT / "agent" / "tests" / "fixtures" / "artifacts" / "valid.artifact.yaml"


def _record() -> dict:
    return yaml.safe_load(VALID.read_text())


def _write(tmp_path: Path, data: dict, name="app.artifact.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.safe_dump(data, sort_keys=False))
    return p


def _problems(tmp_path, data) -> list[str]:
    return validate(_write(tmp_path, data)).problems


# --------------------------------------------------------------------------- #
# The valid record
# --------------------------------------------------------------------------- #

def test_the_fixture_is_valid():
    report = validate(VALID)
    assert report.ok, report.problems
    assert report.artifact.application == "flask-hello"
    assert len(report.artifact.facts) == 4


def test_a_declared_only_port_is_an_assumption_not_a_fact():
    """`EXPOSE 8000` is a hint. It is used, and it is recorded as an assumption —
    the same thing intent_manifest does with its e1000 default."""
    report = validate(VALID)
    assert any("listen:tcp/8000" in a and "Dockerfile:6" in a for a in report.assumptions)


def test_an_unknown_fact_is_an_assumption_too():
    assert any("path:/etc/ssl/certs" in a for a in validate(VALID).assumptions)


def test_an_observed_port_is_not_an_assumption(tmp_path):
    data = _record()
    data["facts"].append({"capability": "listen:tcp/8000", "source": "observed",
                          "observation": "obs-1"})
    report = validate(_write(tmp_path, data), allow_observed=True)
    assert report.ok, report.problems
    assert not any("listen:tcp/8000" in a for a in report.assumptions)


# --------------------------------------------------------------------------- #
# Provenance
# --------------------------------------------------------------------------- #

def test_a_fact_with_no_source_is_refused(tmp_path):
    data = _record()
    del data["facts"][0]["source"]
    [problem] = _problems(tmp_path, data)
    assert "lib:libssl.so.3" in problem and "no source" in problem
    assert "observed, declared, inferred, unknown" in problem


def test_a_source_outside_the_four_is_refused(tmp_path):
    data = _record()
    data["facts"][0]["source"] = "probed"
    [problem] = _problems(tmp_path, data)
    assert "'probed'" in problem and "observed, declared, inferred, unknown" in problem


@pytest.mark.parametrize("source", ["declared", "inferred"])
def test_a_claim_with_no_evidence_is_refused(tmp_path, source):
    data = _record()
    data["facts"][0]["source"] = source
    data["facts"][0]["evidence"] = []
    [problem] = _problems(tmp_path, data)
    assert "evidence" in problem and "file, line and quote" in problem


@pytest.mark.parametrize("missing", ["file", "line", "quote"])
def test_evidence_missing_a_part_is_refused(tmp_path, missing):
    data = _record()
    del data["facts"][0]["evidence"][0][missing]
    [problem] = _problems(tmp_path, data)
    assert missing in problem


def test_evidence_line_must_be_a_positive_integer(tmp_path):
    data = _record()
    data["facts"][0]["evidence"][0]["line"] = "two"
    [problem] = _problems(tmp_path, data)
    assert "line" in problem


def test_unknown_must_say_where_it_looked(tmp_path):
    data = _record()
    del data["facts"][2]["looked_at"]
    [problem] = _problems(tmp_path, data)
    assert "unknown" in problem and "looked_at" in problem


def test_observed_must_name_its_observation(tmp_path):
    """observed is written by observe.py alone, which always records the run it
    came from. An observed fact without one was written by something else."""
    data = _record()
    data["facts"].append({"capability": "lib:libz.so.1", "source": "observed"})
    [problem] = validate(_write(tmp_path, data), allow_observed=True).problems
    assert "observe.py" in problem and "observation" in problem


def test_a_port_is_never_inferred(tmp_path):
    data = _record()
    data["facts"][1]["source"] = "inferred"
    [problem] = _problems(tmp_path, data)
    assert "listen:tcp/8000" in problem and "inferred" in problem
    assert "declared, observed, unknown" in problem


# --------------------------------------------------------------------------- #
# The closed vocabulary
# --------------------------------------------------------------------------- #

def test_a_name_absent_from_a_closed_kind_lists_the_known_ones(tmp_path):
    data = _record()
    data["facts"][0]["capability"] = "lib:libmagic-unicorn.so"
    [problem] = _problems(tmp_path, data)
    assert "lib:libmagic-unicorn.so" in problem
    assert "libssl.so.3" in problem and "libz.so.1" in problem, \
        "the refusal lists what is known, as intent_manifest's DECLINED does"


def test_a_parametric_name_that_does_not_match_shows_the_example(tmp_path):
    data = _record()
    data["facts"][1]["capability"] = "listen:http/eight-thousand"
    [problem] = _problems(tmp_path, data)
    assert "listen:tcp/8000" in problem


def test_an_unknown_kind_lists_the_kinds(tmp_path):
    data = _record()
    data["facts"][0]["capability"] = "package:openssl"
    [problem] = _problems(tmp_path, data)
    assert "'package'" in problem and "lib" in problem and "runtime" in problem


def test_an_untyped_name_is_refused(tmp_path):
    data = _record()
    data["facts"][0]["capability"] = "libssl"
    [problem] = _problems(tmp_path, data)
    assert "kind:name" in problem


def test_a_disabled_kind_is_refused_with_its_reason(tmp_path):
    data = _record()
    data["facts"].append({"capability": "syscalls:network", "source": "unknown",
                          "looked_at": ["app.py"]})
    [problem] = _problems(tmp_path, data)
    assert "syscall-scope.md" in problem


def test_the_runtime_must_be_a_runtime(tmp_path):
    data = _record()
    data["runtime"]["capability"] = "lib:libc.so.6"
    [problem] = _problems(tmp_path, data)
    assert "runtime" in problem


def test_a_path_outside_the_allowed_roots_is_refused(tmp_path):
    data = _record()
    data["facts"][2]["capability"] = "path:../../etc/passwd"
    [problem] = _problems(tmp_path, data)
    assert "path:" in problem


def test_problems_are_all_reported_not_just_the_first(tmp_path):
    data = _record()
    del data["facts"][0]["source"]
    data["facts"][1]["source"] = "inferred"
    assert len(_problems(tmp_path, data)) == 2


# --------------------------------------------------------------------------- #
# Structure
# --------------------------------------------------------------------------- #

def test_a_missing_tree_hash_is_refused(tmp_path):
    """The hash ties the record to the exact subject analysed; without it a
    record can be replayed against a different tree."""
    data = _record()
    del data["subject"]["tree_hash"]
    [problem] = _problems(tmp_path, data)
    assert "tree_hash" in problem


@pytest.mark.parametrize("key", ["application", "subject", "runtime", "facts"])
def test_a_missing_top_level_key_is_refused(tmp_path, key):
    data = _record()
    del data[key]
    with pytest.raises(ArtifactError, match=key):
        validate(_write(tmp_path, data))


def test_an_unknown_format_is_refused(tmp_path):
    data = _record()
    data["format"] = 9
    with pytest.raises(ArtifactError, match="format"):
        validate(_write(tmp_path, data))


def test_unreadable_yaml_is_refused(tmp_path):
    p = tmp_path / "bad.artifact.yaml"
    p.write_text("facts: [unclosed\n")
    with pytest.raises(ArtifactError, match="YAML"):
        validate(p)


# --------------------------------------------------------------------------- #
# The index and the bridge
# --------------------------------------------------------------------------- #

def test_every_parametric_pattern_is_anchored():
    for kind, spec in load_index().kinds.items():
        if spec.pattern:
            assert spec.pattern.pattern.startswith("^") and spec.pattern.pattern.endswith("$"), kind


def test_known_lists_a_kind_or_explains_a_pattern():
    assert "libssl.so.3" in known("lib")
    assert "listen:tcp/8000" in known("listen")
    with pytest.raises(ArtifactError, match="kinds"):
        known("nope")


def test_every_bridge_target_is_a_real_kernel_capability():
    """A bridge naming a phantom kernel capability would turn a refusal on the
    AUTON substrate into a silent mapping to nothing."""
    specs = load_specs()
    real = set(specs) | set(capability_owner(specs))
    for entry in load_bridge():
        for cap in entry["kernel"]:
            assert cap in real, f"{entry['match']} -> {cap} is not a kernel capability"


def test_the_bridge_maps_a_port_and_refuses_a_library():
    assert artifact_spec.kernel_capabilities("listen:tcp/80") == ["tcp", "sockets"]
    assert artifact_spec.kernel_capabilities("lib:libssl.so.3") is None


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #

def test_cli_exit_codes(tmp_path, capsys):
    assert artifact_spec.main(["--validate", str(VALID)]) == 0
    data = copy.deepcopy(_record())
    del data["facts"][0]["source"]
    assert artifact_spec.main(["--validate", str(_write(tmp_path, data))]) == 1
    assert artifact_spec.main(["--validate", str(tmp_path / "missing.yaml")]) == 2
    assert artifact_spec.main(["--known", "device"]) == 0
    assert "urandom" in capsys.readouterr().out


def test_a_yaml_keyword_in_the_index_is_refused(tmp_path):
    """`- null` in a names list parses as None: the device `null` silently
    became unknowable. Found writing this suite."""
    bad = tmp_path / "caps.yaml"
    bad.write_text("kinds:\n  device:\n    names: [null, zero]\n")
    with pytest.raises(ArtifactError, match="quote"):
        load_index(bad)
    assert "null" in known("device")


# --------------------------------------------------------------------------- #
# w17 review findings
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("cap", ["listen:tcp/80\n", "dial:tcp/example.com:80\n",
                                 "listen:tcp/99999", "dial:tcp/db:70000",
                                 "path:/etc/../root/.ssh", "path:/etc/./x", "path:/etc/.."])
def test_review_bypasses_are_refused(cap):
    assert load_index().refusal(cap) is not None, cap


def test_a_dotfile_path_is_still_fine():
    assert load_index().refusal("path:/etc/ssl/.hidden") is None


def test_observed_is_refused_by_default(tmp_path):
    data = _record()
    data["facts"].append({"capability": "lib:libz.so.1", "source": "observed",
                          "observation": "x"})
    p = _write(tmp_path, data)
    assert not validate(p).ok, "the safe setting is the default"
    assert validate(p, allow_observed=True).ok


def test_a_blank_quote_is_not_evidence(tmp_path):
    data = _record()
    data["facts"][0]["evidence"][0]["quote"] = "   "
    [problem] = _problems(tmp_path, data)
    assert "blank" in problem


@pytest.mark.parametrize("key,value", [("subject", ["x"]), ("runtime", "python")])
def test_a_malformed_section_is_unreadable_not_a_crash(tmp_path, key, value):
    data = _record()
    data[key] = value
    with pytest.raises(ArtifactError, match=key):
        validate(_write(tmp_path, data))


def test_a_non_string_capability_is_a_problem_not_a_crash(tmp_path):
    data = _record()
    data["facts"][1]["capability"] = 8000
    problems = _problems(tmp_path, data)
    assert any("8000" in p for p in problems)


def test_the_cli_says_when_quotes_were_not_checked(capsys):
    assert artifact_spec.main(["--validate", str(VALID)]) == 0
    assert "NOT checked" in capsys.readouterr().out
