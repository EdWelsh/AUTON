"""File-based message bus for inter-agent communication."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path


class MessageType(str, Enum):
    TASK_ASSIGNMENT = "task_assignment"
    TASK_COMPLETE = "task_complete"
    REVIEW_REQUEST = "review_request"
    REVIEW_RESULT = "review_result"
    MERGE_REQUEST = "merge_request"
    MERGE_RESULT = "merge_result"
    BUILD_RESULT = "build_result"
    TEST_RESULT = "test_result"
    DESIGN_DECISION = "design_decision"
    ESCALATION = "escalation"
    STATUS_UPDATE = "status_update"


@dataclass
class Message:
    """A message between agents, persisted as a JSON file."""

    msg_type: MessageType
    from_agent: str
    to_agent: str
    payload: dict = field(default_factory=dict)
    msg_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    timestamp: float = field(default_factory=time.time)
    read: bool = False

    def to_json(self) -> str:
        data = asdict(self)
        data["msg_type"] = self.msg_type.value
        return json.dumps(data, indent=2)

    @classmethod
    def from_json(cls, raw: str) -> Message:
        data = json.loads(raw)
        data["msg_type"] = MessageType(data["msg_type"])
        return cls(**data)


class MessageBus:
    """File-based message passing between agents.

    Messages are stored as JSON files in:
        .auton/messages/<to_agent>/<msg_id>.json

    Agents poll their inbox directory for new messages.
    """

    def __init__(self, workspace_path: Path):
        self.base_path = workspace_path / ".auton" / "messages"
        self.base_path.mkdir(parents=True, exist_ok=True)

    def send(self, message: Message) -> None:
        """Send a message to an agent's inbox."""
        inbox = self.base_path / message.to_agent
        inbox.mkdir(parents=True, exist_ok=True)
        path = inbox / f"{message.msg_id}.json"
        path.write_text(message.to_json(), encoding="utf-8")

    def receive(self, agent_id: str, unread_only: bool = True) -> list[Message]:
        """Read messages from an agent's inbox."""
        inbox = self.base_path / agent_id
        if not inbox.exists():
            return []

        messages = []
        for path in sorted(inbox.glob("*.json")):
            msg = Message.from_json(path.read_text(encoding="utf-8"))
            if unread_only and msg.read:
                continue
            messages.append(msg)
        return messages

    def mark_read(self, agent_id: str, msg_id: str) -> None:
        """Mark a message as read."""
        path = self.base_path / agent_id / f"{msg_id}.json"
        if path.exists():
            msg = Message.from_json(path.read_text(encoding="utf-8"))
            msg.read = True
            path.write_text(msg.to_json(), encoding="utf-8")

    def broadcast(self, from_agent: str, msg_type: MessageType, payload: dict) -> None:
        """Send a message to all agent inboxes."""
        for inbox in self.base_path.iterdir():
            if inbox.is_dir() and inbox.name != from_agent:
                msg = Message(
                    msg_type=msg_type,
                    from_agent=from_agent,
                    to_agent=inbox.name,
                    payload=payload,
                )
                self.send(msg)

    def get_conversation(
        self, agent_a: str, agent_b: str
    ) -> list[Message]:
        """Get all messages between two agents, ordered by time."""
        messages = []
        for agent_id in (agent_a, agent_b):
            inbox = self.base_path / agent_id
            if not inbox.exists():
                continue
            for path in inbox.glob("*.json"):
                msg = Message.from_json(path.read_text(encoding="utf-8"))
                if msg.from_agent in (agent_a, agent_b):
                    messages.append(msg)
        return sorted(messages, key=lambda m: m.timestamp)
