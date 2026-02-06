"""Build validation - compiles kernel code and reports errors."""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class BuildResult:
    success: bool
    stdout: str = ""
    stderr: str = ""
    duration_secs: float = 0.0
    errors: list[dict] = field(default_factory=list)
    warnings: list[dict] = field(default_factory=list)


class BuildValidator:
    """Validates kernel code by invoking the cross-compiler.

    Parses GCC output to extract structured error/warning information
    that can be fed back to developer agents.
    """

    def __init__(self, workspace_path: Path, cc: str = "x86_64-elf-gcc", asm: str = "nasm"):
        self.workspace_path = workspace_path
        self.cc = cc
        self.asm = asm

    async def build(self, target: str = "all", timeout: int = 120) -> BuildResult:
        """Run the kernel build and return structured results."""
        makefile = self.workspace_path / "Makefile"
        if not makefile.exists():
            return BuildResult(
                success=False,
                stderr="No Makefile found in workspace",
            )

        start = time.monotonic()
        try:
            proc = await asyncio.create_subprocess_exec(
                "make", "-C", str(self.workspace_path), target,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            duration = time.monotonic() - start

            stdout_str = stdout.decode("utf-8", errors="replace")
            stderr_str = stderr.decode("utf-8", errors="replace")

            errors = self._parse_gcc_diagnostics(stderr_str, "error")
            warnings = self._parse_gcc_diagnostics(stderr_str, "warning")

            result = BuildResult(
                success=proc.returncode == 0,
                stdout=stdout_str,
                stderr=stderr_str,
                duration_secs=duration,
                errors=errors,
                warnings=warnings,
            )

            if result.success:
                logger.info("Build succeeded in %.1fs", duration)
            else:
                logger.warning("Build failed with %d errors", len(errors))

            return result

        except asyncio.TimeoutError:
            return BuildResult(
                success=False,
                stderr=f"Build timed out after {timeout}s",
                duration_secs=timeout,
            )
        except FileNotFoundError:
            return BuildResult(
                success=False,
                stderr=f"Build tool not found. Ensure '{self.cc}' and 'make' are installed.",
            )

    def _parse_gcc_diagnostics(self, output: str, level: str) -> list[dict]:
        """Parse GCC error/warning messages into structured format."""
        diagnostics = []
        for line in output.splitlines():
            if f": {level}:" in line:
                parts = line.split(":", 4)
                if len(parts) >= 5:
                    diagnostics.append({
                        "file": parts[0].strip(),
                        "line": int(parts[1]) if parts[1].strip().isdigit() else 0,
                        "column": int(parts[2]) if parts[2].strip().isdigit() else 0,
                        "message": parts[4].strip(),
                    })
                else:
                    diagnostics.append({"message": line.strip()})
        return diagnostics
