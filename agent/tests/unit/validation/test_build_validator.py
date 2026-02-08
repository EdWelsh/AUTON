"""Unit tests for orchestrator.validation.build_validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.validation.build_validator import BuildResult, BuildValidator
from orchestrator.arch_registry import ArchProfile


# ---------------------------------------------------------------------------
# BuildResult dataclass
# ---------------------------------------------------------------------------

class TestBuildResult:
    """Tests for the BuildResult dataclass."""

    def test_creation_with_defaults(self):
        result = BuildResult(success=True)
        assert result.success is True
        assert result.stdout == ""
        assert result.stderr == ""
        assert result.duration_secs == 0.0
        assert result.errors == []
        assert result.warnings == []

    def test_success_state(self):
        result = BuildResult(
            success=True,
            stdout="CC kernel/main.o",
            stderr="",
            duration_secs=2.5,
        )
        assert result.success is True
        assert result.stdout == "CC kernel/main.o"
        assert result.duration_secs == 2.5

    def test_failure_state(self):
        result = BuildResult(
            success=False,
            stderr="make: *** [Makefile:12: kernel.o] Error 1",
            errors=[{"file": "kernel/main.c", "line": 5, "column": 1, "message": "syntax error"}],
        )
        assert result.success is False
        assert len(result.errors) == 1
        assert result.errors[0]["file"] == "kernel/main.c"

    def test_errors_list_is_independent(self):
        """Each BuildResult should get its own errors/warnings lists."""
        r1 = BuildResult(success=False)
        r2 = BuildResult(success=False)
        r1.errors.append({"message": "err"})
        assert r2.errors == []

    def test_warnings_list_is_independent(self):
        r1 = BuildResult(success=True)
        r2 = BuildResult(success=True)
        r1.warnings.append({"message": "warn"})
        assert r2.warnings == []

    def test_full_construction(self):
        errors = [{"file": "a.c", "line": 1, "column": 2, "message": "bad"}]
        warnings = [{"file": "b.c", "line": 3, "column": 4, "message": "unused"}]
        result = BuildResult(
            success=False,
            stdout="compiling...",
            stderr="error output",
            duration_secs=12.3,
            errors=errors,
            warnings=warnings,
        )
        assert result.success is False
        assert result.stdout == "compiling..."
        assert result.stderr == "error output"
        assert result.duration_secs == 12.3
        assert result.errors is errors
        assert result.warnings is warnings


# ---------------------------------------------------------------------------
# BuildValidator.__init__
# ---------------------------------------------------------------------------

class TestBuildValidatorInit:
    """Tests for BuildValidator initialisation."""

    def test_default_cc_and_asm(self, tmp_path: Path):
        bv = BuildValidator(workspace_path=tmp_path)
        assert bv.workspace_path == tmp_path
        assert bv.cc == "x86_64-elf-gcc"
        assert bv.asm == "nasm"

    def test_custom_cc_and_asm(self, tmp_path: Path):
        bv = BuildValidator(tmp_path, cc="gcc", asm="as")
        assert bv.cc == "gcc"
        assert bv.asm == "as"

    def test_arch_profile_overrides_defaults(self, tmp_path: Path):
        profile = ArchProfile(
            name="aarch64",
            display_name="AArch64",
            cc="aarch64-elf-gcc",
            asm="aarch64-elf-as",
            ld="aarch64-elf-ld",
            asm_syntax="gas",
            asm_format="",
        )
        bv = BuildValidator(tmp_path, arch_profile=profile)
        assert bv.cc == "aarch64-elf-gcc"
        assert bv.asm == "aarch64-elf-as"

    def test_arch_profile_does_not_override_explicit_values(self, tmp_path: Path):
        profile = ArchProfile(
            name="aarch64",
            display_name="AArch64",
            cc="aarch64-elf-gcc",
            asm="aarch64-elf-as",
            ld="aarch64-elf-ld",
            asm_syntax="gas",
            asm_format="",
        )
        bv = BuildValidator(tmp_path, cc="my-gcc", asm="my-asm", arch_profile=profile)
        assert bv.cc == "my-gcc"
        assert bv.asm == "my-asm"

    def test_arch_profile_partial_override_cc_only(self, tmp_path: Path):
        """When only cc is non-default, asm should come from the profile."""
        profile = ArchProfile(
            name="riscv64",
            display_name="RISC-V 64",
            cc="riscv64-elf-gcc",
            asm="riscv64-elf-as",
            ld="riscv64-elf-ld",
            asm_syntax="gas",
            asm_format="",
        )
        bv = BuildValidator(tmp_path, cc="custom-cc", arch_profile=profile)
        assert bv.cc == "custom-cc"
        # asm was left at default, so the profile should supply it
        assert bv.asm == "riscv64-elf-as"


# ---------------------------------------------------------------------------
# BuildValidator.build  (missing Makefile)
# ---------------------------------------------------------------------------

class TestBuildValidatorBuild:
    """Tests for BuildValidator.build — specifically the no-Makefile path."""

    async def test_returns_failure_when_no_makefile(self, tmp_path: Path):
        bv = BuildValidator(tmp_path)
        result = await bv.build()
        assert result.success is False
        assert "No Makefile found" in result.stderr

    async def test_no_makefile_result_has_empty_errors(self, tmp_path: Path):
        bv = BuildValidator(tmp_path)
        result = await bv.build()
        assert result.errors == []
        assert result.warnings == []


# ---------------------------------------------------------------------------
# BuildValidator._parse_gcc_diagnostics
# ---------------------------------------------------------------------------

class TestParseGccDiagnostics:
    """Tests for the GCC diagnostic output parser."""

    def setup_method(self):
        self.bv = BuildValidator(workspace_path=Path("/tmp"))

    def test_parse_error_line(self):
        line = "kernel/boot.c:15:3: error: implicit declaration of function 'foo'"
        errors = self.bv._parse_gcc_diagnostics(line, "error")
        assert len(errors) == 1
        assert errors[0]["file"] == "kernel/boot.c"
        assert errors[0]["line"] == 15
        assert errors[0]["column"] == 3
        assert "implicit declaration" in errors[0]["message"]

    def test_parse_warning_line(self):
        line = "kernel/mm.c:42:10: warning: unused variable 'x'"
        warnings = self.bv._parse_gcc_diagnostics(line, "warning")
        assert len(warnings) == 1
        assert warnings[0]["file"] == "kernel/mm.c"
        assert warnings[0]["line"] == 42
        assert warnings[0]["column"] == 10
        assert "unused variable" in warnings[0]["message"]

    def test_error_parse_ignores_warning_lines(self):
        line = "kernel/mm.c:42:10: warning: unused variable 'x'"
        errors = self.bv._parse_gcc_diagnostics(line, "error")
        assert errors == []

    def test_warning_parse_ignores_error_lines(self):
        line = "kernel/boot.c:15:3: error: implicit declaration of function 'foo'"
        warnings = self.bv._parse_gcc_diagnostics(line, "warning")
        assert warnings == []

    def test_malformed_line_no_diagnostic(self):
        line = "some random line with no diagnostic"
        errors = self.bv._parse_gcc_diagnostics(line, "error")
        warnings = self.bv._parse_gcc_diagnostics(line, "warning")
        assert errors == []
        assert warnings == []

    def test_multiple_diagnostics_mixed(self):
        output = (
            "kernel/boot.c:15:3: error: implicit declaration of function 'foo'\n"
            "kernel/mm.c:42:10: warning: unused variable 'x'\n"
            "some random line with no diagnostic\n"
        )
        errors = self.bv._parse_gcc_diagnostics(output, "error")
        warnings = self.bv._parse_gcc_diagnostics(output, "warning")
        assert len(errors) == 1
        assert len(warnings) == 1
        assert errors[0]["file"] == "kernel/boot.c"
        assert warnings[0]["file"] == "kernel/mm.c"

    def test_multiple_errors(self):
        output = (
            "a.c:1:1: error: first error\n"
            "b.c:2:2: error: second error\n"
        )
        errors = self.bv._parse_gcc_diagnostics(output, "error")
        assert len(errors) == 2
        assert errors[0]["file"] == "a.c"
        assert errors[1]["file"] == "b.c"

    def test_empty_output(self):
        errors = self.bv._parse_gcc_diagnostics("", "error")
        assert errors == []

    def test_malformed_line_with_error_keyword_but_wrong_format(self):
        """A line containing ': error:' but with fewer than 5 colon-parts
        should produce a fallback dict with just the message."""
        line = "ld: error: cannot find -lc"
        errors = self.bv._parse_gcc_diagnostics(line, "error")
        # The line contains ": error:" so it matches, but split(":", 4) yields
        # fewer than 5 parts, so the fallback branch is taken.
        assert len(errors) == 1
        assert "message" in errors[0]

    def test_non_numeric_line_column(self):
        """When line/column fields are non-numeric, they should default to 0."""
        line = "file.c:abc:xyz: error: something wrong"
        errors = self.bv._parse_gcc_diagnostics(line, "error")
        assert len(errors) == 1
        assert errors[0]["line"] == 0
        assert errors[0]["column"] == 0
        assert "something wrong" in errors[0]["message"]
