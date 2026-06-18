"""Supervisor for long-running host processes, plus pure utterance parsing.

The :class:`Supervisor` launches processes with :func:`subprocess.Popen`,
records ``name/pid/port/cmd``, supports graceful stop (SIGTERM then SIGKILL),
lists running ones, and persists the table to ``~/.auton/servers.json`` so the
chat's "what servers are running" survives across turns. On load it reconciles
the table against real pid liveness so stale entries never linger.

Parsing (:func:`parse_utterance`) is intentionally pure — no side effects — so
it can be unit-tested in isolation and reused by the capability handler.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import signal
import subprocess
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Literal

Action = Literal["start", "stop", "list", "unknown"]

DEFAULT_STATE_PATH = Path.home() / ".auton" / "servers.json"
DEFAULT_WEB_PORT = 8000
DEFAULT_WEB_COMMAND = f"python3 -m http.server {DEFAULT_WEB_PORT}"

# How long to wait for a graceful SIGTERM before escalating to SIGKILL.
GRACEFUL_STOP_TIMEOUT_S = 5.0
_STOP_POLL_INTERVAL_S = 0.05


# ---------------------------------------------------------------------------
# Records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ServerRecord:
    """One supervised process. Immutable; updates produce new copies."""

    name: str
    pid: int
    command: str
    port: int | None = None
    started_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "pid": self.pid,
            "command": self.command,
            "port": self.port,
            "started_at": self.started_at,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "ServerRecord":
        return cls(
            name=str(raw["name"]),
            pid=int(raw["pid"]),
            command=str(raw["command"]),
            port=raw.get("port"),
            started_at=float(raw.get("started_at", time.time())),
        )


@dataclass(frozen=True)
class ParsedCommand:
    """Pure parse of a server utterance."""

    action: Action
    command: str = ""
    name: str | None = None
    port: int | None = None


# ---------------------------------------------------------------------------
# Pure parsing
# ---------------------------------------------------------------------------

_NAMED_RE = re.compile(r"\bnamed?\s+(['\"]?)(?P<name>[\w.-]+)\1", re.IGNORECASE)
_PORT_RE = re.compile(r"\b(?:port\s+)?(?P<port>\d{2,5})\b")
_RUNNING_RE = re.compile(r"\brunning\s+(?P<cmd>.+)$", re.IGNORECASE)
# Strip leading verbs so the residual command is clean.
_START_VERB_RE = re.compile(
    r"^\s*(?:please\s+)?(?:run|start|launch|spin up)\s+", re.IGNORECASE
)
_AS_SERVICE_RE = re.compile(
    r"\s+as\s+a\s+(?:service|server|background process|daemon)\b.*$",
    re.IGNORECASE,
)


def _extract_name(text: str) -> str | None:
    m = _NAMED_RE.search(text)
    return m.group("name") if m else None


def _extract_port(command: str) -> int | None:
    m = _PORT_RE.search(command)
    if not m:
        return None
    port = int(m.group("port"))
    return port if 1 <= port <= 65535 else None


def _strip_name_clause(text: str) -> str:
    return _NAMED_RE.sub("", text).strip()


def parse_utterance(text: str) -> ParsedCommand:
    """Classify an utterance and extract command/name/port. Pure, no I/O."""
    lowered = text.lower()

    if "stop" in lowered:
        return ParsedCommand(action="stop", name=_extract_name_for_stop(text))

    if any(
        phrase in lowered
        for phrase in ("what servers", "list servers", "servers are running")
    ):
        return ParsedCommand(action="list")

    if _looks_like_start(lowered):
        return _parse_start(text)

    return ParsedCommand(action="unknown")


def _looks_like_start(lowered: str) -> bool:
    return any(
        kw in lowered
        for kw in (
            "start a server",
            "run as a service",
            "background process",
            "as a service",
            "start a web server",
            "start a",
            "run ",
            "launch",
        )
    )


def _extract_name_for_stop(text: str) -> str | None:
    """A name from 'stop the server <name>' or 'stop <name>'."""
    named = _extract_name(text)
    if named:
        return named
    m = re.search(
        r"\bstop\s+(?:the\s+)?(?:server\s+)?(?P<name>[\w.-]+)\s*$",
        text,
        re.IGNORECASE,
    )
    return m.group("name") if m else None


def _parse_start(text: str) -> ParsedCommand:
    name = _extract_name(text)
    work = _strip_name_clause(text)

    # Prefer an explicit "running <cmd>" clause.
    run_match = _RUNNING_RE.search(work)
    if run_match:
        command = run_match.group("cmd").strip()
    else:
        command = _AS_SERVICE_RE.sub("", work)
        command = _START_VERB_RE.sub("", command).strip()

    if not command or _is_bare_web_request(text, command):
        command = DEFAULT_WEB_COMMAND

    port = _extract_port(command)
    return ParsedCommand(action="start", command=command, name=name, port=port)


def _is_bare_web_request(original: str, residual: str) -> bool:
    """True when the user said 'web server' with no real command to run."""
    low = residual.lower()
    return low in ("a web server", "web server", "a server", "server", "")


# ---------------------------------------------------------------------------
# Supervisor
# ---------------------------------------------------------------------------


class Supervisor:
    """Launch, track, and stop real host processes with a persisted table."""

    def __init__(self, state_path: Path | str | None = None) -> None:
        self.state_path = Path(state_path) if state_path else DEFAULT_STATE_PATH
        # Live Popen handles for processes this instance started (best-effort).
        self._procs: dict[str, subprocess.Popen] = {}
        self._records: dict[str, ServerRecord] = {}
        self._load()

    # -- persistence -------------------------------------------------------

    def _load(self) -> None:
        records: dict[str, ServerRecord] = {}
        if self.state_path.exists():
            try:
                raw = json.loads(self.state_path.read_text())
            except (json.JSONDecodeError, OSError):
                raw = []
            for item in raw:
                try:
                    rec = ServerRecord.from_dict(item)
                except (KeyError, ValueError, TypeError):
                    continue
                if self.is_alive(rec.pid):
                    records[rec.name] = rec
        self._records = records
        # Reconciled view (dead entries dropped) is the new source of truth.
        self._save()

    def _save(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        payload = [rec.to_dict() for rec in self._records.values()]
        tmp = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2))
        os.replace(tmp, self.state_path)

    # -- liveness ----------------------------------------------------------

    @staticmethod
    def is_alive(pid: int) -> bool:
        """True if ``pid`` is a live process we can signal."""
        if pid <= 0:
            return False
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            # Exists but owned by another user — still "alive".
            return True
        return True

    # -- lifecycle ---------------------------------------------------------

    def start(
        self,
        command: str,
        name: str | None = None,
        port: int | None = None,
    ) -> ServerRecord:
        """Launch ``command`` as a tracked background process."""
        if not command.strip():
            raise ValueError("command must not be empty")

        self._reconcile()
        name = name or self._auto_name(command)
        if name in self._records:
            raise ValueError(f"a server named {name!r} is already running")

        argv = shlex.split(command)
        proc = subprocess.Popen(  # noqa: S603 - user-directed process launch
            argv,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        rec = ServerRecord(name=name, pid=proc.pid, command=command, port=port)
        self._procs[name] = proc
        self._records[name] = rec
        self._save()
        return rec

    def stop(self, name: str) -> bool:
        """Gracefully stop ``name`` (SIGTERM then SIGKILL). False if unknown."""
        self._reconcile()
        rec = self._records.get(name)
        if rec is None:
            return False

        self._terminate(rec.pid)
        self._procs.pop(name, None)
        self._records.pop(name, None)
        self._save()
        return True

    def stop_all(self) -> None:
        """Stop every tracked process (used for cleanup)."""
        for name in list(self._records):
            self.stop(name)

    def list_running(self) -> list[ServerRecord]:
        """Records for processes still alive (reconciles the table first)."""
        self._reconcile()
        return list(self._records.values())

    # -- internals ---------------------------------------------------------

    def _reconcile(self) -> None:
        """Drop records whose pid is no longer alive, then persist."""
        alive = {
            name: rec
            for name, rec in self._records.items()
            if self.is_alive(rec.pid)
        }
        if len(alive) != len(self._records):
            self._records = alive
            self._save()

    def _terminate(self, pid: int) -> None:
        if not self.is_alive(pid):
            return
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            return

        deadline = time.time() + GRACEFUL_STOP_TIMEOUT_S
        while self.is_alive(pid) and time.time() < deadline:
            time.sleep(_STOP_POLL_INTERVAL_S)

        if self.is_alive(pid):
            try:
                os.kill(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

    def _auto_name(self, command: str) -> str:
        base = "server"
        argv = shlex.split(command)
        if argv:
            base = Path(argv[0]).name or "server"
        candidate = base
        i = 1
        while candidate in self._records:
            i += 1
            candidate = f"{base}-{i}"
        return candidate
