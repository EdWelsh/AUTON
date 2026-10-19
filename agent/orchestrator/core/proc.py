"""Wait for a child process, and never leave it behind.

`asyncio.wait_for(proc.communicate(), t)` cancels the *wait*, not the child: on
a timeout, or when a pause cancels the run, `make`, `gcc` or `qemu` kept
running. After a pause that meant the WIP commit could race a build still
writing files, and the child outlived the orchestrator (w17 review).
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import signal

REAP_SECONDS = 10.0


def _kill_tree(proc: asyncio.subprocess.Process) -> None:
    """Kill the child and, when it leads its own session, everything it started.

    `make run` starts QEMU in the foreground. Killing `make` alone left QEMU holding the
    stdout pipe, and asyncio's `proc.wait()` does not return until the pipes close: the
    orchestrator sat in it for good (w18 R1, 2026-10-19). Start children with
    `start_new_session=True` so the whole group can be killed.
    """
    with contextlib.suppress(ProcessLookupError, PermissionError):
        if os.getpgid(proc.pid) == proc.pid:
            os.killpg(proc.pid, signal.SIGKILL)
            return
    with contextlib.suppress(ProcessLookupError):
        proc.kill()


async def communicate(proc: asyncio.subprocess.Process, timeout: float) -> tuple[bytes, bytes]:
    """`proc.communicate()` with a timeout; on timeout or cancellation the
    child is killed and reaped before the exception propagates."""
    try:
        return await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        _kill_tree(proc)
        # Shielded: a second cancellation must not abandon the reap. Bounded: a descendant
        # outside the group can still hold the pipes, and an unbounded wait never returns.
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await asyncio.wait_for(asyncio.shield(proc.wait()), timeout=REAP_SECONDS)
        raise
