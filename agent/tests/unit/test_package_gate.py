"""The package gate's pure parts (A8): base, inventory, diff."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from image_inventory import inventory_from_names  # noqa: E402
from package_gate import base_problems, check, diff, load_bases  # noqa: E402

BASES = load_bases()
PY = BASES["runtime:python-3.12"]


def test_the_listed_base_passes():
    assert base_problems(f"FROM {PY}\nRUN x\n", "runtime:python-3.12", BASES) == []


def test_a_moving_tag_is_refused_with_the_pinned_line():
    [p] = base_problems("FROM python:3.12-slim\n", "runtime:python-3.12", BASES)
    assert PY in p


def test_a_base_of_the_models_choosing_is_refused():
    problems = base_problems("FROM ubuntu:24.04\n", "runtime:python-3.12", BASES)
    assert any("ubuntu:24.04" in p for p in problems)


def test_a_multistage_build_ends_on_the_base():
    good = f"FROM {BASES['runtime:glibc-elf']} AS build\nRUN x\nFROM {PY}\nCOPY --from=build /a /a\n"
    assert base_problems(good, "runtime:python-3.12", BASES) == []
    bad = f"FROM {PY} AS build\nFROM {BASES['runtime:glibc-elf']}\n"
    assert any("final stage" in p for p in base_problems(bad, "runtime:python-3.12", BASES))


def test_an_unlisted_runtime_is_refused():
    [p] = base_problems(f"FROM {PY}\n", "runtime:cobol-85", BASES)
    assert "no base is listed" in p


def test_every_base_is_pinned_by_digest():
    for runtime, image in BASES.items():
        assert image == "scratch" or "@sha256:" in image, runtime


def test_inventory_reads_sonames_and_programs():
    inv = inventory_from_names([
        "usr/lib/aarch64-linux-gnu/libssl.so.3", "lib/x86_64-linux-gnu/libz.so.1",
        "usr/local/lib/libpython3.12.so.1.0", "usr/share/doc/libz.so.1",
        "usr/bin/python3", "usr/local/bin/python", "usr/bin/sub/dir/not"])
    assert inv["libs"] == ["libpython3.12.so.1.0", "libssl.so.3", "libz.so.1"]
    assert inv["execs"] == ["python", "python3"]


def test_missing_fails_and_extras_are_only_reported():
    missing, extras = diff(["lib:libssl.so.3", "lib:libpq.so.5", "listen:tcp/8000"],
                           {"libs": ["libssl.so.3", "libacl.so.1"], "execs": []})
    assert missing == ["lib:libpq.so.5"]
    assert extras == ["lib:libacl.so.1"]


def test_no_manifest_is_refused(tmp_path):
    assert "no manifest" in check(tmp_path).problems[0]


def test_a_listed_builder_may_compile_but_never_run():
    from package_gate import load_builders
    go = sorted(load_builders())[0]
    ok = f"FROM {go} AS build\nRUN go build\nFROM scratch\nCOPY --from=build /w /w\n"
    assert base_problems(ok, "runtime:static-elf", BASES) == []
    bad = f"FROM {go}\nRUN go build\n"
    assert base_problems(bad, "runtime:static-elf", BASES)


def test_other_ways_to_bring_in_an_image_are_refused():
    """w18 review M8: FROM is not the only door."""
    for recipe, why in [
        (f"# syntax=evil/frontend\nFROM {PY}\n", "syntax"),
        (f"FROM {PY}\nCOPY --from=alpine:3 /bin/sh /x\n", "--from=alpine:3"),
        (f"FROM {PY}\nRUN --mount=type=bind,from=busybox,target=/b true\n", "busybox"),
        (f"FROM {PY}\nADD https://example.com/x.tgz /x\n", "ADD <url>"),
    ]:
        problems = base_problems(recipe, "runtime:python-3.12", BASES)
        assert any(why in p for p in problems), (why, problems)


def test_the_manifest_is_revalidated_whoever_wrote_it(tmp_path):
    (tmp_path / "package").mkdir()
    (tmp_path / "package" / "Dockerfile").write_text(f"FROM {PY}\n")
    report = check(tmp_path, manifest={"application": {"runtime": "runtime:python-3.12",
                                                       "requires": ["lib:x\nRUN y"]}})
    assert report.problems and "lib:x" in report.problems[0]
