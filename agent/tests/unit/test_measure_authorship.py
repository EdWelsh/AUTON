"""The authorship harness: one way of counting, for controls and experiments.

Its own acceptance test is the plans' (F6 Task 2, V8 Task 2): it must reproduce
the controls' figures from their own artifacts, or say exactly where it cannot.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "agent" / "tools"))

from measure_authorship import (  # noqa: E402
    added_lines,
    count_cases,
    load_subjects,
    main,
    measure,
    section,
)

SUBJECTS = load_subjects()


def _has_history(rev: str) -> bool:
    import subprocess

    return subprocess.run(["git", "-C", str(ROOT), "cat-file", "-e", rev],
                          capture_output=True).returncode == 0


needs_history = pytest.mark.skipif(not _has_history("2b1b1f4"),
                                   reason="shallow clone: control history absent")


class TestCountingRules:
    def test_the_ok_helper_definition_is_not_a_case(self):
        src = "static void ok(const char *n, int c)\n{\n}\nok(\"a\", 1);\nok(\"b\", 0);\n"
        assert count_cases(src) == 2

    def test_a_section_ends_at_the_next_heading_of_its_level(self):
        md = "## Top\n### A\na1\na2\n### B\nb1\n## Next\n"
        assert section(md, "A") == "### A\na1\na2\n"
        assert section(md, "B") == "### B\nb1\n"
        assert section(md, "missing") is None

    def test_an_edit_to_a_given_file_counts_only_what_was_added(self):
        assert added_lines("a\nb\n", "a\nx\nb\ny\n") == 2


class TestTheControlsReproduce:
    @needs_history
    def test_f4_spec_is_its_f2_text(self):
        assert measure("dhcp", SUBJECTS["dhcp"], ROOT).measured["spec_lines"] == 175

    @needs_history
    def test_f4_cases_match_the_record(self):
        assert measure("dhcp", SUBJECTS["dhcp"], ROOT).measured["test_cases"] == 24

    @needs_history
    def test_f4_implementation_comes_from_the_only_artifact_left(self):
        """The text is gone (kernels/ was gitignored); the graph at 9571384 is
        what survives, and it disagrees with the hand count. Shown, not hidden."""
        row = measure("dhcp", SUBJECTS["dhcp"], ROOT)
        assert row.measured["implementation_lines"] == 401
        assert row.recorded["implementation_lines"] == 372

    def test_v5_spec_section_matches(self):
        assert measure("virtio-net", SUBJECTS["virtio-net"], ROOT).measured["spec_lines"] == 113

    def test_v6_counts_only_what_it_wrote_into_an_existing_section(self):
        row = measure("virtio-blk", SUBJECTS["virtio-blk"], ROOT)
        assert row.measured["test_cases"] == 16
        # 85 against a recorded 84: the section's growth over HEAD, not its size.
        assert abs(row.measured["spec_lines"] - 84) <= 1


class TestAnExperimentThatProducedNothing:
    def test_missing_output_is_reported_not_zeroed_silently(self, tmp_path, capsys):
        (tmp_path / "spec").mkdir()
        (tmp_path / "spec" / "tftp.md").write_text("x\n" * 10)

        rc = main(["--service", "tftp", "--root", str(tmp_path)])

        out = capsys.readouterr().out
        assert rc == 1
        assert "MISSING implementation kernel/services/tftp/server.c" in out
        assert "MISSING test tests/kernel/tftp_test.c" in out

    def test_an_unknown_subject_is_refused(self, capsys):
        assert main(["--service", "nosuch"]) == 2
