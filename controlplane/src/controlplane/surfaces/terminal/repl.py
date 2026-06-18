"""Terminal chat REPL — the ``auton-chat`` console entrypoint.

Prints the shared :class:`~controlplane.core.ChatEngine` banner, then loops on an
``auton> `` prompt: read a line, exit on ``quit``, otherwise hand it to the engine
and print the reply. The engine owns banner text, help/quit detection, routing,
and turn recording; this module is only the terminal I/O shell around it.

``run()`` takes explicit input/output streams so it can be unit-tested with
in-memory streams. ``main()`` wraps it with real stdin/stdout for the CLI.
"""

from __future__ import annotations

import sys
from typing import TextIO

from rich.console import Console

from controlplane.core import ChatEngine
from controlplane.core.chat import is_quit

PROMPT = "auton> "


def run(engine: ChatEngine, in_stream: TextIO, out_stream: TextIO) -> None:
    """Drive the chat loop against explicit streams.

    Reads one line at a time from ``in_stream``; blank lines are ignored; a quit
    word ends the loop, as does EOF (a closed pipe). Every non-quit line is routed
    through ``engine.handle`` (which records the turn) and its reply is printed.
    """
    console = Console(file=out_stream, highlight=False, soft_wrap=True)

    console.print(engine.banner())

    while True:
        console.print(PROMPT, end="")
        line = in_stream.readline()
        if line == "":  # EOF / closed pipe
            break

        text = line.strip()
        if not text:
            continue
        if is_quit(text):
            break

        result = engine.handle(text)
        console.print(result.text)


def main() -> None:
    """Console-script entrypoint for ``auton-chat``.

    Builds a terminal :class:`ChatEngine` with the default discovering Registry
    and the shared persistent SessionStore, then runs the loop on stdin/stdout.
    """
    engine = ChatEngine(surface="terminal")
    run(engine, sys.stdin, sys.stdout)


if __name__ == "__main__":
    main()
