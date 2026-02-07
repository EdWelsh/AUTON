"""Test validation - runs kernel tests in QEMU and parses results."""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class TestCase:
    name: str
    passed: bool
    message: str = ""
    duration_secs: float = 0.0


@dataclass
class TestResult:
    success: bool
    total: int = 0
    passed: int = 0
    failed: int = 0
    tests: list[TestCase] = field(default_factory=list)
    raw_output: str = ""
    boot_success: bool = False
    duration_secs: float = 0.0


class TestValidator:
    """Runs kernel tests in QEMU and parses serial output for results.

    Tests output results to serial console in the format:
        [TEST] test_name: PASS
        [TEST] test_name: FAIL - reason
        [BOOT] OK
    """

    def __init__(
        self,
        workspace_path: Path,
        qemu: str = "qemu-system-x86_64",
        timeout: int = 60,
        arch_profile=None,
    ):
        self.workspace_path = workspace_path
        self.timeout = timeout
        # Derive QEMU config from arch profile if provided
        if arch_profile is not None:
            self.qemu = qemu if qemu != "qemu-system-x86_64" else arch_profile.qemu
            self.qemu_machine = arch_profile.qemu_machine
            self.qemu_cpu = arch_profile.qemu_cpu
            self.qemu_extra = list(arch_profile.qemu_extra)
        else:
            self.qemu = qemu
            self.qemu_machine = ""
            self.qemu_cpu = ""
            self.qemu_extra = []

    async def run_tests(self, kernel_image: str | None = None) -> TestResult:
        """Boot the kernel in QEMU and capture test results from serial output."""
        image = kernel_image or str(self.workspace_path / "build" / "kernel.bin")
        if not Path(image).exists():
            return TestResult(
                success=False,
                raw_output=f"Kernel image not found: {image}",
            )

        start = time.monotonic()
        try:
            # Build QEMU command with architecture-specific flags
            qemu_cmd = [self.qemu]
            if self.qemu_machine:
                qemu_cmd += ["-machine", self.qemu_machine]
            if self.qemu_cpu:
                qemu_cmd += ["-cpu", self.qemu_cpu]
            qemu_cmd += ["-kernel", image, "-serial", "stdio",
                         "-display", "none", "-no-reboot", "-m", "128M"]
            qemu_cmd += self.qemu_extra

            # Launch QEMU with serial output piped to stdout
            proc = await asyncio.create_subprocess_exec(
                *qemu_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=self.timeout
            )
            duration = time.monotonic() - start

            output = stdout.decode("utf-8", errors="replace")
            tests = self._parse_test_output(output)
            boot_ok = "[BOOT] OK" in output or "kernel initialized" in output.lower()

            passed = sum(1 for t in tests if t.passed)
            failed = sum(1 for t in tests if not t.passed)

            return TestResult(
                success=failed == 0 and (boot_ok or not tests),
                total=len(tests),
                passed=passed,
                failed=failed,
                tests=tests,
                raw_output=output,
                boot_success=boot_ok,
                duration_secs=duration,
            )

        except asyncio.TimeoutError:
            return TestResult(
                success=False,
                raw_output=f"QEMU timed out after {self.timeout}s (possible kernel hang)",
                duration_secs=self.timeout,
            )
        except FileNotFoundError:
            return TestResult(
                success=False,
                raw_output=f"QEMU not found: {self.qemu}. Install {self.qemu}.",
            )

    def _parse_test_output(self, output: str) -> list[TestCase]:
        """Parse [TEST] lines from serial output."""
        tests = []
        pattern = re.compile(r"\[TEST\]\s+(\S+):\s+(PASS|FAIL)(?:\s*-\s*(.*))?")
        for line in output.splitlines():
            match = pattern.search(line)
            if match:
                name, result, message = match.groups()
                tests.append(TestCase(
                    name=name,
                    passed=(result == "PASS"),
                    message=message or "",
                ))
        return tests
