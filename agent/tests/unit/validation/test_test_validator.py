"""Unit tests for orchestrator.validation.test_validator."""

from __future__ import annotations

from pathlib import Path

import pytest

from orchestrator.validation.test_validator import TestCase, TestResult, TestValidator
from orchestrator.arch_registry import ArchProfile


# ---------------------------------------------------------------------------
# TestCase dataclass
# ---------------------------------------------------------------------------

class TestTestCase:
    """Tests for the TestCase dataclass."""

    def test_creation_minimal(self):
        tc = TestCase(name="test_boot", passed=True)
        assert tc.name == "test_boot"
        assert tc.passed is True
        assert tc.message == ""
        assert tc.duration_secs == 0.0

    def test_passed_state(self):
        tc = TestCase(name="test_serial", passed=True, message="")
        assert tc.passed is True
        assert tc.name == "test_serial"

    def test_failed_state(self):
        tc = TestCase(name="test_mm_alloc", passed=False, message="out of memory")
        assert tc.passed is False
        assert tc.message == "out of memory"

    def test_with_duration(self):
        tc = TestCase(name="test_long", passed=True, duration_secs=1.5)
        assert tc.duration_secs == 1.5


# ---------------------------------------------------------------------------
# TestResult dataclass
# ---------------------------------------------------------------------------

class TestTestResult:
    """Tests for the TestResult dataclass."""

    def test_creation_with_defaults(self):
        tr = TestResult(success=True)
        assert tr.success is True
        assert tr.total == 0
        assert tr.passed == 0
        assert tr.failed == 0
        assert tr.tests == []
        assert tr.raw_output == ""
        assert tr.boot_success is False
        assert tr.duration_secs == 0.0

    def test_success_calculation_all_pass(self):
        cases = [
            TestCase(name="test_a", passed=True),
            TestCase(name="test_b", passed=True),
        ]
        tr = TestResult(
            success=True,
            total=2,
            passed=2,
            failed=0,
            tests=cases,
            boot_success=True,
        )
        assert tr.success is True
        assert tr.total == 2
        assert tr.passed == 2
        assert tr.failed == 0

    def test_failure_state(self):
        cases = [
            TestCase(name="test_a", passed=True),
            TestCase(name="test_b", passed=False, message="segfault"),
        ]
        tr = TestResult(
            success=False,
            total=2,
            passed=1,
            failed=1,
            tests=cases,
            boot_success=True,
        )
        assert tr.success is False
        assert tr.failed == 1

    def test_tests_list_is_independent(self):
        r1 = TestResult(success=True)
        r2 = TestResult(success=True)
        r1.tests.append(TestCase(name="x", passed=True))
        assert r2.tests == []

    def test_full_construction(self):
        tr = TestResult(
            success=False,
            total=3,
            passed=2,
            failed=1,
            tests=[],
            raw_output="[BOOT] OK\n[TEST] a: PASS",
            boot_success=True,
            duration_secs=4.2,
        )
        assert tr.raw_output.startswith("[BOOT]")
        assert tr.duration_secs == 4.2
        assert tr.boot_success is True


# ---------------------------------------------------------------------------
# TestValidator.__init__
# ---------------------------------------------------------------------------

class TestTestValidatorInit:
    """Tests for TestValidator initialisation."""

    def test_default_qemu(self, tmp_path: Path):
        tv = TestValidator(workspace_path=tmp_path)
        assert tv.workspace_path == tmp_path
        assert tv.qemu == "qemu-system-x86_64"
        assert tv.timeout == 60
        assert tv.qemu_machine == ""
        assert tv.qemu_cpu == ""
        assert tv.qemu_extra == []

    def test_custom_qemu(self, tmp_path: Path):
        tv = TestValidator(tmp_path, qemu="qemu-system-aarch64", timeout=30)
        assert tv.qemu == "qemu-system-aarch64"
        assert tv.timeout == 30

    def test_arch_profile_overrides_defaults(self, tmp_path: Path):
        profile = ArchProfile(
            name="aarch64",
            display_name="AArch64",
            cc="aarch64-elf-gcc",
            asm="aarch64-elf-as",
            ld="aarch64-elf-ld",
            asm_syntax="gas",
            asm_format="",
            qemu="qemu-system-aarch64",
            qemu_machine="virt",
            qemu_cpu="cortex-a53",
            qemu_extra=["-nographic"],
        )
        tv = TestValidator(tmp_path, arch_profile=profile)
        assert tv.qemu == "qemu-system-aarch64"
        assert tv.qemu_machine == "virt"
        assert tv.qemu_cpu == "cortex-a53"
        assert tv.qemu_extra == ["-nographic"]

    def test_arch_profile_does_not_override_explicit_qemu(self, tmp_path: Path):
        profile = ArchProfile(
            name="aarch64",
            display_name="AArch64",
            cc="aarch64-elf-gcc",
            asm="aarch64-elf-as",
            ld="aarch64-elf-ld",
            asm_syntax="gas",
            asm_format="",
            qemu="qemu-system-aarch64",
            qemu_machine="virt",
            qemu_cpu="cortex-a53",
            qemu_extra=["-nographic"],
        )
        tv = TestValidator(tmp_path, qemu="my-qemu", arch_profile=profile)
        assert tv.qemu == "my-qemu"
        # machine/cpu/extra should still come from the profile
        assert tv.qemu_machine == "virt"
        assert tv.qemu_cpu == "cortex-a53"

    def test_no_arch_profile_leaves_empty_machine_cpu(self, tmp_path: Path):
        tv = TestValidator(tmp_path)
        assert tv.qemu_machine == ""
        assert tv.qemu_cpu == ""
        assert tv.qemu_extra == []


# ---------------------------------------------------------------------------
# TestValidator._parse_test_output
# ---------------------------------------------------------------------------

class TestParseTestOutput:
    """Tests for the serial output parser."""

    def setup_method(self):
        self.tv = TestValidator(workspace_path=Path("/tmp"))

    def test_parse_pass_line(self):
        output = "[TEST] test_boot: PASS"
        tests = self.tv._parse_test_output(output)
        assert len(tests) == 1
        assert tests[0].name == "test_boot"
        assert tests[0].passed is True
        assert tests[0].message == ""

    def test_parse_fail_line_with_reason(self):
        output = "[TEST] test_mm_alloc: FAIL - out of memory"
        tests = self.tv._parse_test_output(output)
        assert len(tests) == 1
        assert tests[0].name == "test_mm_alloc"
        assert tests[0].passed is False
        assert tests[0].message == "out of memory"

    def test_parse_full_example_output(self):
        output = (
            "[BOOT] OK\n"
            "[TEST] test_boot: PASS\n"
            "[TEST] test_mm_alloc: FAIL - out of memory\n"
            "[TEST] test_serial: PASS\n"
        )
        tests = self.tv._parse_test_output(output)
        assert len(tests) == 3

        assert tests[0].name == "test_boot"
        assert tests[0].passed is True

        assert tests[1].name == "test_mm_alloc"
        assert tests[1].passed is False
        assert tests[1].message == "out of memory"

        assert tests[2].name == "test_serial"
        assert tests[2].passed is True

    def test_boot_line_is_ignored(self):
        """[BOOT] OK lines should not produce TestCase entries."""
        output = "[BOOT] OK"
        tests = self.tv._parse_test_output(output)
        assert tests == []

    def test_empty_output(self):
        tests = self.tv._parse_test_output("")
        assert tests == []

    def test_random_text_ignored(self):
        output = "Booting kernel...\nInitializing memory manager\nDone."
        tests = self.tv._parse_test_output(output)
        assert tests == []

    def test_fail_without_reason(self):
        """[TEST] name: FAIL with no dash-reason should still parse."""
        output = "[TEST] test_x: FAIL"
        tests = self.tv._parse_test_output(output)
        assert len(tests) == 1
        assert tests[0].name == "test_x"
        assert tests[0].passed is False
        assert tests[0].message == ""

    def test_mixed_output_with_noise(self):
        output = (
            "Serial port initialized\n"
            "[BOOT] OK\n"
            "Running tests...\n"
            "[TEST] test_a: PASS\n"
            "some debug spew\n"
            "[TEST] test_b: FAIL - assertion failed at line 42\n"
        )
        tests = self.tv._parse_test_output(output)
        assert len(tests) == 2
        assert tests[0].name == "test_a"
        assert tests[0].passed is True
        assert tests[1].name == "test_b"
        assert tests[1].passed is False
        assert "assertion failed" in tests[1].message


# ---------------------------------------------------------------------------
# TestValidator.run_tests (missing kernel image)
# ---------------------------------------------------------------------------

class TestRunTests:
    """Tests for TestValidator.run_tests — specifically the missing-image path."""

    async def test_returns_failure_when_kernel_image_not_found(self, tmp_path: Path):
        tv = TestValidator(tmp_path)
        result = await tv.run_tests()
        assert result.success is False
        assert "Kernel image not found" in result.raw_output

    async def test_returns_failure_for_explicit_missing_image(self, tmp_path: Path):
        tv = TestValidator(tmp_path)
        missing = str(tmp_path / "nonexistent" / "kernel.bin")
        result = await tv.run_tests(kernel_image=missing)
        assert result.success is False
        assert missing in result.raw_output

    async def test_missing_image_result_has_empty_tests(self, tmp_path: Path):
        tv = TestValidator(tmp_path)
        result = await tv.run_tests()
        assert result.tests == []
        assert result.total == 0
        assert result.passed == 0
        assert result.failed == 0
