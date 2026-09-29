"""Wait for a child process, and never leave it behind.

`asyncio.wait_for(proc.communicate(), t)` cancels the *wait*, not the child: on
a timeout, or when a pause cancels the run, `make`, `gcc` or `qemu` kept
running. After a pause that meant the WIP commit could race a build still
writing files, and the child outlived the orchestrator (w17 review).
"""

from __future__ import annotations

import asyncio
import contextlib


async def communicate(proc: asyncio.subprocess.Process, timeout: float) -> tuple[bytes, bytes]:
    """`proc.communicate()` with a timeout; on timeout or cancellation the
    child is killed and reaped before the exception propagates."""
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        with contextlib.suppress(ProcessLookupError):
            proc.kill()
        # Shielded: a second cancellation must not abandon the reap.
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await asyncio.shield(proc.wait())
        raise
