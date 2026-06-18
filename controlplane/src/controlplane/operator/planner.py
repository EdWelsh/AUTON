"""Deterministic fallback planner — the operator's rule-engine brain.

When no LLM is reachable, AUTON still completes the canonical
download → edit → email task by parsing the goal directly. Mirrors the kernel's
neural→rule-engine fallback: predictable, offline, no model required.
"""

from __future__ import annotations

import re

from .tools import ToolExecutor

_URL = re.compile(r"https?://[^\s'\"]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# "set B2 to 1234", "change B2 to 1234", "update B2 to 1234", "B2 = 1234"
_CELL_TO = re.compile(r"\b(?:set|change|update)\s+([A-Za-z]{1,3}\d{1,7})\s+to\s+([^\s,.;]+)", re.I)
_CELL_EQ = re.compile(r"\b([A-Za-z]{1,3}\d{1,7})\s*=\s*([^\s,.;]+)")


class RuleBrain:
    """Parse a download/edit/email goal into a concrete tool sequence."""

    def run(self, goal: str, executor: ToolExecutor) -> str:
        steps: list[str] = []

        url_m = _URL.search(goal)
        filename = "document.xlsx"
        if url_m:
            url = url_m.group(0).rstrip(".,;)")
            tail = url.rsplit("/", 1)[-1]
            if tail:
                filename = tail
            steps.append(executor.execute("download_file", {"url": url, "filename": filename}))
            steps.append(executor.execute("read_spreadsheet", {"filename": filename}))

        cell_m = _CELL_TO.search(goal) or _CELL_EQ.search(goal)
        cell_desc = ""
        if cell_m:
            cell, value = cell_m.group(1).upper(), cell_m.group(2)
            steps.append(
                executor.execute("update_spreadsheet", {"filename": filename, "cell": cell, "value": value})
            )
            cell_desc = f" {cell}={value}"

        email_m = _EMAIL.search(goal)
        if email_m:
            to = email_m.group(0)
            steps.append(
                executor.execute(
                    "send_email",
                    {
                        "to": to,
                        "subject": f"Updated {filename}",
                        "body": (
                            f"Hi,\n\nAttached is the updated spreadsheet"
                            f"{(' with' + cell_desc) if cell_desc else ''}.\n\n— sent by AUTON"
                        ),
                        "attachment": filename if url_m else None,
                    },
                )
            )

        if not steps:
            return (
                "I couldn't find an actionable step (a URL to fetch, a cell to set, "
                "or an email address) in that request."
            )
        return "Completed the task:\n- " + "\n- ".join(steps)
