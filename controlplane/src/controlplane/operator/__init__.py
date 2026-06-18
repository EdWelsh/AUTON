"""AUTON operator — the chat-driven agent that operates the computer for you.

Speak a goal; a pluggable brain (local Ollama / cloud / on-device SLM) plans it
and calls real headless tools (download, spreadsheet edit, email) to complete the
task, asking you to confirm before anything irreversible. Entry point: `auton-do`.
"""

from __future__ import annotations

from .runner import Operator, TaskResult

__all__ = ["Operator", "TaskResult"]
