"""Mock LLM client for testing."""

from typing import Any


class MockLLMClient:
    """Mock LLM client that returns predefined responses."""

    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or ["Mock response"]
        self.call_count = 0
        self.calls = []

    async def send_with_tools(
        self,
        agent_id: str,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        tool_executor: Any,
        model_override: str | None = None,
    ) -> list[dict[str, Any]]:
        """Mock send_with_tools."""
        self.calls.append({
            "agent_id": agent_id,
            "system": system,
            "messages": messages,
            "tools": tools,
            "model_override": model_override,
        })
        response = self.responses[min(self.call_count, len(self.responses) - 1)]
        self.call_count += 1
        return [{"role": "assistant", "content": response}]
