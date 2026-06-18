"""Server/process capability plugin.

Exposes a single WORKING ``server`` capability whose handler parses the
utterance, then starts / stops / lists real host processes via a shared
:class:`Supervisor`. The supervisor persists its table under ``~/.auton/`` so
listings survive across chat turns.
"""

from __future__ import annotations

from controlplane.core import Capability, CapabilityResult, CapabilityStatus

from .supervisor import ParsedCommand, Supervisor, parse_utterance

# One shared supervisor for the process lifetime; tests swap it via monkeypatch.
_SUPERVISOR = Supervisor()

_KEYWORDS = (
    "start a server",
    "run as a service",
    "as a service",
    "background process",
    "stop the server",
    "what servers",
    "start a web server",
)


def _handle(text: str) -> CapabilityResult:
    parsed = parse_utterance(text)
    if parsed.action == "start":
        return _do_start(parsed)
    if parsed.action == "stop":
        return _do_stop(parsed)
    if parsed.action == "list":
        return _do_list()
    return CapabilityResult.fail(
        "I couldn't tell whether to start, stop, or list a server.",
    )


def _do_start(parsed: ParsedCommand) -> CapabilityResult:
    try:
        rec = _SUPERVISOR.start(
            command=parsed.command, name=parsed.name, port=parsed.port
        )
    except ValueError as exc:
        return CapabilityResult.fail(str(exc))
    except (FileNotFoundError, OSError) as exc:
        return CapabilityResult.fail(f"failed to start process: {exc}")

    port_note = f" on port {rec.port}" if rec.port else ""
    return CapabilityResult.ok(
        f"Started '{rec.name}' (pid {rec.pid}){port_note}: {rec.command}",
        name=rec.name,
        pid=rec.pid,
        port=rec.port,
        command=rec.command,
    )


def _do_stop(parsed: ParsedCommand) -> CapabilityResult:
    if not parsed.name:
        return CapabilityResult.fail(
            "Which server? Try 'stop the server <name>'.",
        )
    if _SUPERVISOR.stop(parsed.name):
        return CapabilityResult.ok(f"Stopped '{parsed.name}'.", name=parsed.name)
    return CapabilityResult.fail(f"No running server named '{parsed.name}'.")


def _do_list() -> CapabilityResult:
    running = _SUPERVISOR.list_running()
    if not running:
        return CapabilityResult.ok("No servers are running.", servers=[])

    lines = [
        f"- {r.name} (pid {r.pid}"
        + (f", port {r.port}" if r.port else "")
        + f"): {r.command}"
        for r in running
    ]
    return CapabilityResult.ok(
        "Running servers:\n" + "\n".join(lines),
        servers=[r.to_dict() for r in running],
    )


def get_capabilities() -> list[Capability]:
    return [
        Capability(
            name="server",
            keywords=_KEYWORDS,
            status=CapabilityStatus.WORKING,
            note=(
                "Start/stop/list real long-running host processes "
                "(e.g. 'run python3 -m http.server 8000 as a service')."
            ),
            handler=_handle,
        )
    ]
