"""Provider-agnostic response types for the LLM layer."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolCall:
    """A single tool call from the model."""

    id: str
    name: str
    arguments: dict[str, Any]


@dataclass
class LLMResponse:
    """Provider-agnostic LLM response."""

    text: str | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str = "stop"
    model: str = ""
    raw: Any = None

    @classmethod
    def from_litellm(cls, response) -> LLMResponse:
        """Construct from a LiteLLM ModelResponse."""
        choice = response.choices[0]
        message = choice.message

        text = message.content or None

        tool_calls = []
        if message.tool_calls:
            for tc in message.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, TypeError):
                    args = {}
                tool_calls.append(ToolCall(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        return cls(
            text=text,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            model=getattr(response, "model", ""),
            raw=response,
        )
