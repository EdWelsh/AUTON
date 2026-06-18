"""The operator: turn a natural-language goal into completed work.

Picks a brain (LLM with fallback to the deterministic planner), runs it against
the real headless tools inside a sandboxed workspace, records the turn to the
shared AUTON session, and returns a structured result.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from pathlib import Path

from .approval import always_deny
from .brain import BrainUnavailable, LLMBrain, resolve_model
from .planner import RuleBrain
from .tools import Approval, SMTPConfig, ToolExecutor

DEFAULT_WORKSPACE_ROOT = Path.home() / ".auton" / "operator"


@dataclass
class TaskResult:
    goal: str
    brain: str  # "llm:<model>" | "rule"
    summary: str
    actions: list[dict] = field(default_factory=list)
    workspace: str = ""


class Operator:
    def __init__(
        self,
        approval: Approval | None = None,
        smtp: SMTPConfig | None = None,
        workspace_root: Path | None = None,
    ) -> None:
        self.approval = approval or always_deny
        self.smtp = smtp
        self.workspace_root = workspace_root or DEFAULT_WORKSPACE_ROOT

    def run(self, goal: str, brain: str = "auto", model_request: str | None = None) -> TaskResult:
        ws = self.workspace_root / f"task-{int(time.time() * 1000)}"
        executor = ToolExecutor(workspace=ws, approval=self.approval, smtp=self.smtp)

        used, summary = self._drive(goal, executor, brain, model_request)
        self._record(goal, summary)
        return TaskResult(goal=goal, brain=used, summary=summary, actions=executor.actions, workspace=str(ws))

    # --- internals ----------------------------------------------------------

    def _drive(self, goal, executor, brain, model_request) -> tuple[str, str]:
        if brain == "rule":
            return "rule", RuleBrain().run(goal, executor)
        if brain in ("llm", "auto"):
            model = resolve_model(model_request)
            try:
                return f"llm:{model}", LLMBrain(model=model).run(goal, executor)
            except BrainUnavailable:
                if brain == "llm":
                    raise
                # auto: fall back to the deterministic planner.
                return "rule", RuleBrain().run(goal, executor)
        raise ValueError(f"unknown brain {brain!r}")

    def _record(self, goal: str, summary: str) -> None:
        try:
            from controlplane.core import ChatTurn, SessionStore

            store = SessionStore()
            store.append(ChatTurn(role="user", text=goal, surface="operator"))
            store.append(ChatTurn(role="auton", text=summary, surface="operator"))
        except Exception:  # noqa: BLE001 - session logging must never fail a task
            pass
