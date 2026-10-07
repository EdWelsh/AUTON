"""Installing the pause handlers must not cost the caller its own (w23 C4).

`asyncio.run` installs a SIGINT handler of its own for the duration of the run.
Restoring with `remove_signal_handler` alone left the interpreter default behind,
so a Ctrl-C after `run()` returned no longer reached the Runner.
"""

from __future__ import annotations

import asyncio
import signal

from orchestrator.core.engine import OrchestrationEngine


def test_the_previous_handlers_are_put_back():
    seen = {}

    async def scenario():
        engine = OrchestrationEngine.__new__(OrchestrationEngine)
        before = {s: signal.getsignal(s) for s in (signal.SIGINT, signal.SIGTERM)}
        restore = engine._install_pause_handlers()
        seen["during"] = signal.getsignal(signal.SIGINT)
        restore()
        seen["before"], seen["after"] = before, {
            s: signal.getsignal(s) for s in before}

    asyncio.run(scenario())
    assert seen["after"] == seen["before"]
    # The Runner's handler is not the interpreter default; that is the point.
    assert seen["before"][signal.SIGINT] is not signal.default_int_handler
