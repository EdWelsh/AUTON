"""The run event log: what happened in a run, one JSON line each, for a person to read afterwards.

`AUTON_EVENTS` names the file (generation_run.py sets it to `<run>/events.jsonl`). Unset, nothing
is written. The log observes and never decides: a failure to write is swallowed, so it cannot
change what a run does.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

TEXT_LIMIT = 2000      # a field's longest text; the cut field also gets `<name>_chars`
_warned = False


def _bounded(fields: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if isinstance(value, str) and len(value) > TEXT_LIMIT:
            out[key] = value[:TEXT_LIMIT]
            out[f"{key}_chars"] = len(value)
        else:
            out[key] = value
    return out


def emit(kind: str, **fields: Any) -> None:
    """Append one event to the run's log."""
    global _warned
    dest = os.environ.get("AUTON_EVENTS")
    if not dest:
        return
    row = {"t": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"), "kind": kind,
           **_bounded(fields)}
    try:
        with open(dest, "a") as fh:
            fh.write(json.dumps(row, default=str) + "\n")
    except OSError as exc:
        if not _warned:
            _warned = True
            logger.warning("run events are not being written to %s: %s", dest, exc)
