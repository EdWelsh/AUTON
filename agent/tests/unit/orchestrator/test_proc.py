"""A child process is killed when its wait times out or is cancelled (w17 review).

`wait_for(proc.communicate())` cancelled the wait and left `make` or `qemu`
running: on a timeout, and on a pause, where the WIP commit then raced a build
still writing files.
"""

from __future__ import annotations

import asyncio
import sys

import pytest

from orchestrator.core.proc import communicate

pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="uses sleep")


async def _sleeper():
    return await asyncio.create_subprocess_exec(
        "sleep", "30", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)


async def test_a_timeout_kills_the_child():
    proc = await _sleeper()
    with pytest.raises(asyncio.TimeoutError):
        await communicate(proc, 0.2)
    assert proc.returncode is not None, "the child was reaped, not abandoned"


async def test_a_cancellation_kills_the_child():
    proc = await _sleeper()
    task = asyncio.ensure_future(communicate(proc, 60))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert proc.returncode is not None


async def test_a_normal_exit_returns_output():
    proc = await asyncio.create_subprocess_exec(
        "echo", "hi", stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    out, _ = await communicate(proc, 5)
    assert out.strip() == b"hi"
