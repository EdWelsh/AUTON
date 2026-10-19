"""A timeout kills the child's whole process group, so a grandchild holding the pipe
cannot hang the orchestrator (w18 R1, 2026-10-19: `make run` left QEMU running and
asyncio's proc.wait() never returned)."""

from __future__ import annotations

import asyncio
import os
import time

import pytest

from orchestrator.core.proc import communicate


async def _run(timeout: float):
    # sh starts a long sleep in the background, then waits: the sleep inherits the pipes.
    proc = await asyncio.create_subprocess_exec(
        "sh", "-c", "sleep 60 & wait",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        start_new_session=True)
    start = time.monotonic()
    with pytest.raises(asyncio.TimeoutError):
        await communicate(proc, timeout)
    return time.monotonic() - start, proc.pid


def test_a_grandchild_holding_the_pipe_does_not_hang_the_timeout():
    elapsed, pid = asyncio.run(asyncio.wait_for(_run(1.0), timeout=20))
    assert elapsed < 8, f"the timeout path took {elapsed:.1f}s"
    with pytest.raises(ProcessLookupError):
        os.killpg(pid, 0)            # nothing of the group is left running
