"""Tests for file-based message bus."""

import json
import time

import pytest

from orchestrator.comms.message_bus import Message, MessageBus, MessageType


# ---------------------------------------------------------------------------
# MessageType enum
# ---------------------------------------------------------------------------

class TestMessageType:
    def test_task_assignment(self):
        assert MessageType.TASK_ASSIGNMENT == "task_assignment"
        assert MessageType.TASK_ASSIGNMENT.value == "task_assignment"

    def test_task_complete(self):
        assert MessageType.TASK_COMPLETE.value == "task_complete"

    def test_review_request(self):
        assert MessageType.REVIEW_REQUEST.value == "review_request"

    def test_review_result(self):
        assert MessageType.REVIEW_RESULT.value == "review_result"

    def test_merge_request(self):
        assert MessageType.MERGE_REQUEST.value == "merge_request"

    def test_merge_result(self):
        assert MessageType.MERGE_RESULT.value == "merge_result"

    def test_build_result(self):
        assert MessageType.BUILD_RESULT.value == "build_result"

    def test_test_result(self):
        assert MessageType.TEST_RESULT.value == "test_result"

    def test_design_decision(self):
        assert MessageType.DESIGN_DECISION.value == "design_decision"

    def test_escalation(self):
        assert MessageType.ESCALATION.value == "escalation"

    def test_status_update(self):
        assert MessageType.STATUS_UPDATE.value == "status_update"

    def test_is_str_subclass(self):
        assert isinstance(MessageType.TASK_ASSIGNMENT, str)


# ---------------------------------------------------------------------------
# Message dataclass
# ---------------------------------------------------------------------------

class TestMessage:
    def test_creation(self):
        msg = Message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            from_agent="manager",
            to_agent="dev-1",
            payload={"task_id": "t-1"},
        )
        assert msg.msg_type == MessageType.TASK_ASSIGNMENT
        assert msg.from_agent == "manager"
        assert msg.to_agent == "dev-1"
        assert msg.payload == {"task_id": "t-1"}

    def test_default_msg_id_generated(self):
        msg = Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="a",
            to_agent="b",
        )
        assert isinstance(msg.msg_id, str)
        assert len(msg.msg_id) == 12  # uuid4().hex[:12]

    def test_unique_msg_ids(self):
        msgs = [
            Message(msg_type=MessageType.STATUS_UPDATE, from_agent="a", to_agent="b")
            for _ in range(50)
        ]
        ids = [m.msg_id for m in msgs]
        assert len(set(ids)) == 50

    def test_default_timestamp(self):
        before = time.time()
        msg = Message(msg_type=MessageType.STATUS_UPDATE, from_agent="a", to_agent="b")
        after = time.time()
        assert before <= msg.timestamp <= after

    def test_default_read_is_false(self):
        msg = Message(msg_type=MessageType.STATUS_UPDATE, from_agent="a", to_agent="b")
        assert msg.read is False

    def test_default_payload_is_empty_dict(self):
        msg = Message(msg_type=MessageType.STATUS_UPDATE, from_agent="a", to_agent="b")
        assert msg.payload == {}

    def test_to_json(self):
        msg = Message(
            msg_type=MessageType.REVIEW_REQUEST,
            from_agent="dev-1",
            to_agent="reviewer-1",
            payload={"branch": "feature/x"},
            msg_id="abc123def456",
        )
        raw = msg.to_json()
        data = json.loads(raw)
        assert data["msg_type"] == "review_request"
        assert data["from_agent"] == "dev-1"
        assert data["to_agent"] == "reviewer-1"
        assert data["payload"] == {"branch": "feature/x"}
        assert data["msg_id"] == "abc123def456"

    def test_from_json(self):
        original = Message(
            msg_type=MessageType.BUILD_RESULT,
            from_agent="tester",
            to_agent="dev-1",
            payload={"status": "pass"},
            msg_id="test12345678",
        )
        raw = original.to_json()
        restored = Message.from_json(raw)
        assert restored.msg_type == MessageType.BUILD_RESULT
        assert restored.from_agent == "tester"
        assert restored.to_agent == "dev-1"
        assert restored.payload == {"status": "pass"}
        assert restored.msg_id == "test12345678"

    def test_to_json_from_json_round_trip(self):
        original = Message(
            msg_type=MessageType.ESCALATION,
            from_agent="dev-2",
            to_agent="manager",
            payload={"reason": "blocked on dependency"},
        )
        restored = Message.from_json(original.to_json())
        assert restored.msg_type == original.msg_type
        assert restored.from_agent == original.from_agent
        assert restored.to_agent == original.to_agent
        assert restored.payload == original.payload
        assert restored.msg_id == original.msg_id
        assert restored.read == original.read
        assert restored.timestamp == pytest.approx(original.timestamp)

    def test_round_trip_preserves_read_flag(self):
        msg = Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="a",
            to_agent="b",
            read=True,
        )
        restored = Message.from_json(msg.to_json())
        assert restored.read is True


# ---------------------------------------------------------------------------
# MessageBus
# ---------------------------------------------------------------------------

@pytest.fixture
def bus(tmp_path):
    """Create a MessageBus in a temporary workspace."""
    return MessageBus(tmp_path)


class TestMessageBusSend:
    def test_send_creates_file(self, bus):
        msg = Message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            from_agent="manager",
            to_agent="dev-1",
            payload={"task": "implement boot"},
            msg_id="msg000000001",
        )
        bus.send(msg)
        expected_path = bus.base_path / "dev-1" / "msg000000001.json"
        assert expected_path.exists()

    def test_send_file_is_valid_json(self, bus):
        msg = Message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            from_agent="manager",
            to_agent="dev-1",
            msg_id="msg000000002",
        )
        bus.send(msg)
        path = bus.base_path / "dev-1" / "msg000000002.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["msg_type"] == "task_assignment"
        assert data["from_agent"] == "manager"


class TestMessageBusReceive:
    def test_receive_reads_messages(self, bus):
        msg = Message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            from_agent="manager",
            to_agent="dev-1",
        )
        bus.send(msg)
        received = bus.receive("dev-1")
        assert len(received) == 1
        assert received[0].msg_type == MessageType.TASK_ASSIGNMENT
        assert received[0].from_agent == "manager"

    def test_receive_returns_empty_for_no_inbox(self, bus):
        assert bus.receive("nonexistent-agent") == []

    def test_receive_unread_only_by_default(self, bus):
        msg = Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="a",
            to_agent="dev-1",
            msg_id="already_read",
            read=True,
        )
        bus.send(msg)
        received = bus.receive("dev-1", unread_only=True)
        assert len(received) == 0

    def test_receive_all_includes_read(self, bus):
        msg = Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="a",
            to_agent="dev-1",
            read=True,
        )
        bus.send(msg)
        received = bus.receive("dev-1", unread_only=False)
        assert len(received) == 1

    def test_receive_multiple_messages(self, bus):
        for i in range(3):
            msg = Message(
                msg_type=MessageType.STATUS_UPDATE,
                from_agent=f"agent-{i}",
                to_agent="dev-1",
            )
            bus.send(msg)
        received = bus.receive("dev-1")
        assert len(received) == 3


class TestMessageBusMarkRead:
    def test_mark_read_updates_message(self, bus):
        msg = Message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            from_agent="manager",
            to_agent="dev-1",
            msg_id="to_mark_read",
        )
        bus.send(msg)
        bus.mark_read("dev-1", "to_mark_read")

        # Re-read from disk
        path = bus.base_path / "dev-1" / "to_mark_read.json"
        reloaded = Message.from_json(path.read_text(encoding="utf-8"))
        assert reloaded.read is True

    def test_mark_read_filters_from_unread_receive(self, bus):
        msg = Message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            from_agent="manager",
            to_agent="dev-1",
            msg_id="will_be_read",
        )
        bus.send(msg)
        bus.mark_read("dev-1", "will_be_read")

        unread = bus.receive("dev-1", unread_only=True)
        assert len(unread) == 0

    def test_mark_read_nonexistent_is_noop(self, bus):
        # Should not raise
        bus.mark_read("dev-1", "does_not_exist")


class TestMessageBusBroadcast:
    def test_broadcast_sends_to_all_inboxes(self, bus):
        # Create inboxes for several agents by sending them initial messages
        for agent in ["dev-1", "dev-2", "reviewer-1"]:
            init_msg = Message(
                msg_type=MessageType.STATUS_UPDATE,
                from_agent="setup",
                to_agent=agent,
            )
            bus.send(init_msg)

        # Broadcast from manager (not in existing inboxes)
        bus.broadcast(
            from_agent="manager",
            msg_type=MessageType.DESIGN_DECISION,
            payload={"decision": "use microkernel"},
        )

        # Each agent should have received the broadcast
        for agent in ["dev-1", "dev-2", "reviewer-1"]:
            msgs = bus.receive(agent, unread_only=True)
            broadcast_msgs = [m for m in msgs if m.msg_type == MessageType.DESIGN_DECISION]
            assert len(broadcast_msgs) == 1
            assert broadcast_msgs[0].payload == {"decision": "use microkernel"}
            assert broadcast_msgs[0].from_agent == "manager"

    def test_broadcast_excludes_sender(self, bus):
        # Create inbox for the sender too
        bus.send(Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="x",
            to_agent="dev-1",
        ))
        bus.send(Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="x",
            to_agent="dev-2",
        ))

        bus.broadcast("dev-1", MessageType.STATUS_UPDATE, {"info": "done"})

        # dev-1 (sender) should NOT get the broadcast
        dev1_msgs = bus.receive("dev-1", unread_only=True)
        broadcast_from_dev1 = [m for m in dev1_msgs if m.from_agent == "dev-1"]
        assert len(broadcast_from_dev1) == 0

        # dev-2 should get it
        dev2_msgs = bus.receive("dev-2", unread_only=True)
        broadcast_for_dev2 = [
            m for m in dev2_msgs
            if m.from_agent == "dev-1" and m.msg_type == MessageType.STATUS_UPDATE
        ]
        assert len(broadcast_for_dev2) == 1


class TestMessageBusGetConversation:
    def test_get_conversation_returns_ordered_messages(self, bus):
        # Send messages in both directions with controlled timestamps
        t_base = time.time()

        msg1 = Message(
            msg_type=MessageType.REVIEW_REQUEST,
            from_agent="dev-1",
            to_agent="reviewer-1",
            msg_id="conv_msg_001",
            timestamp=t_base,
        )
        msg2 = Message(
            msg_type=MessageType.REVIEW_RESULT,
            from_agent="reviewer-1",
            to_agent="dev-1",
            msg_id="conv_msg_002",
            timestamp=t_base + 1,
        )
        msg3 = Message(
            msg_type=MessageType.REVIEW_REQUEST,
            from_agent="dev-1",
            to_agent="reviewer-1",
            msg_id="conv_msg_003",
            timestamp=t_base + 2,
        )

        bus.send(msg1)
        bus.send(msg2)
        bus.send(msg3)

        convo = bus.get_conversation("dev-1", "reviewer-1")
        assert len(convo) == 3
        # Should be ordered by timestamp
        assert convo[0].msg_id == "conv_msg_001"
        assert convo[1].msg_id == "conv_msg_002"
        assert convo[2].msg_id == "conv_msg_003"

    def test_get_conversation_excludes_unrelated_agents(self, bus):
        bus.send(Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="dev-1",
            to_agent="reviewer-1",
            msg_id="relevant",
        ))
        bus.send(Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="dev-3",
            to_agent="reviewer-1",
            msg_id="irrelevant",
        ))

        convo = bus.get_conversation("dev-1", "reviewer-1")
        ids = [m.msg_id for m in convo]
        assert "relevant" in ids
        assert "irrelevant" not in ids

    def test_get_conversation_empty_when_no_messages(self, bus):
        convo = bus.get_conversation("agent-a", "agent-b")
        assert convo == []
