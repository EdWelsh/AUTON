"""Integration tests for agent collaboration via message bus.

Tests the file-based MessageBus using real filesystem I/O (via tmp_path),
verifying that agents can exchange messages, conduct review feedback loops,
receive broadcasts, and retrieve conversation histories.
"""

import pytest
import time
from pathlib import Path

from orchestrator.comms.message_bus import MessageBus, Message, MessageType


@pytest.fixture
def bus(tmp_path):
    """Create a MessageBus backed by a real temp directory."""
    return MessageBus(tmp_path)


def test_send_and_receive_message(bus):
    """A message sent to an agent can be received from that agent's inbox."""
    msg = Message(
        msg_type=MessageType.TASK_COMPLETE,
        from_agent="dev-01",
        to_agent="reviewer-01",
        payload={"task_id": "boot-001", "branch": "agent/dev-01/boot-loader"},
    )
    bus.send(msg)

    received = bus.receive("reviewer-01")
    assert len(received) == 1
    assert received[0].from_agent == "dev-01"
    assert received[0].to_agent == "reviewer-01"
    assert received[0].msg_type == MessageType.TASK_COMPLETE
    assert received[0].payload["task_id"] == "boot-001"
    assert received[0].payload["branch"] == "agent/dev-01/boot-loader"


def test_receive_empty_inbox(bus):
    """Receiving from an agent that has no inbox returns an empty list."""
    received = bus.receive("nonexistent-agent")
    assert received == []


def test_multiple_messages_to_same_agent(bus):
    """Multiple messages to the same agent are all retrievable."""
    for i in range(3):
        bus.send(Message(
            msg_type=MessageType.TASK_ASSIGNMENT,
            from_agent="manager-01",
            to_agent="dev-01",
            payload={"task_id": f"task-{i:03d}"},
        ))

    received = bus.receive("dev-01")
    assert len(received) == 3
    task_ids = {m.payload["task_id"] for m in received}
    assert task_ids == {"task-000", "task-001", "task-002"}


def test_messages_are_agent_specific(bus):
    """Messages sent to different agents do not cross-contaminate inboxes."""
    bus.send(Message(
        msg_type=MessageType.TASK_ASSIGNMENT,
        from_agent="manager-01",
        to_agent="dev-01",
        payload={"task_id": "task-a"},
    ))
    bus.send(Message(
        msg_type=MessageType.TASK_ASSIGNMENT,
        from_agent="manager-01",
        to_agent="dev-02",
        payload={"task_id": "task-b"},
    ))

    dev1_msgs = bus.receive("dev-01")
    dev2_msgs = bus.receive("dev-02")
    assert len(dev1_msgs) == 1
    assert dev1_msgs[0].payload["task_id"] == "task-a"
    assert len(dev2_msgs) == 1
    assert dev2_msgs[0].payload["task_id"] == "task-b"


def test_review_feedback_loop(bus):
    """Developer and reviewer can exchange messages in a review cycle."""
    # Dev sends completion
    bus.send(Message(
        msg_type=MessageType.TASK_COMPLETE,
        from_agent="dev-01",
        to_agent="reviewer-01",
        payload={"task_id": "boot-001"},
    ))

    # Reviewer receives it
    reviewer_msgs = bus.receive("reviewer-01")
    assert len(reviewer_msgs) == 1
    assert reviewer_msgs[0].msg_type == MessageType.TASK_COMPLETE

    # Reviewer sends feedback
    bus.send(Message(
        msg_type=MessageType.REVIEW_RESULT,
        from_agent="reviewer-01",
        to_agent="dev-01",
        payload={"verdict": "changes_requested", "comments": ["Fix memory leak"]},
    ))

    dev_messages = bus.receive("dev-01")
    assert len(dev_messages) == 1
    assert dev_messages[0].payload["verdict"] == "changes_requested"
    assert "Fix memory leak" in dev_messages[0].payload["comments"]


def test_mark_read_filters_on_subsequent_receive(bus):
    """Messages marked as read are excluded when unread_only=True."""
    bus.send(Message(
        msg_type=MessageType.STATUS_UPDATE,
        from_agent="manager-01",
        to_agent="dev-01",
        payload={"status": "update-1"},
    ))
    bus.send(Message(
        msg_type=MessageType.STATUS_UPDATE,
        from_agent="manager-01",
        to_agent="dev-01",
        payload={"status": "update-2"},
    ))

    # Read all messages
    msgs = bus.receive("dev-01", unread_only=True)
    assert len(msgs) == 2

    # Find the "update-1" message and mark it as read
    msg_1 = next(m for m in msgs if m.payload["status"] == "update-1")
    bus.mark_read("dev-01", msg_1.msg_id)

    # Only the second (unread) message should be returned
    unread = bus.receive("dev-01", unread_only=True)
    assert len(unread) == 1
    assert unread[0].payload["status"] == "update-2"


def test_receive_all_ignores_read_flag(bus):
    """receive with unread_only=False returns all messages including read ones."""
    bus.send(Message(
        msg_type=MessageType.STATUS_UPDATE,
        from_agent="manager-01",
        to_agent="dev-01",
        payload={"status": "msg-1"},
    ))

    msgs = bus.receive("dev-01")
    bus.mark_read("dev-01", msgs[0].msg_id)

    all_msgs = bus.receive("dev-01", unread_only=False)
    assert len(all_msgs) == 1
    assert all_msgs[0].read is True


def test_broadcast_reaches_all_agents(bus):
    """Broadcast sends a message to all existing agent inboxes except sender."""
    # Create inboxes by sending initial messages
    for agent in ["dev-01", "dev-02", "reviewer-01"]:
        bus.send(Message(
            msg_type=MessageType.STATUS_UPDATE,
            from_agent="setup",
            to_agent=agent,
            payload={},
        ))
        # Mark setup messages as read so they don't interfere
        for msg in bus.receive(agent):
            bus.mark_read(agent, msg.msg_id)

    # Manager broadcasts
    bus.broadcast(
        from_agent="manager-01",
        msg_type=MessageType.DESIGN_DECISION,
        payload={"decision": "Use 4KB pages for x86_64"},
    )

    # All agents except manager should receive
    for agent in ["dev-01", "dev-02", "reviewer-01"]:
        msgs = bus.receive(agent, unread_only=True)
        design_msgs = [m for m in msgs if m.msg_type == MessageType.DESIGN_DECISION]
        assert len(design_msgs) == 1, f"Agent {agent} should have 1 design decision message"
        assert design_msgs[0].payload["decision"] == "Use 4KB pages for x86_64"


def test_broadcast_excludes_sender(bus):
    """Broadcast does not send to the sender's own inbox, even if it exists."""
    # Create sender's inbox
    bus.send(Message(
        msg_type=MessageType.STATUS_UPDATE,
        from_agent="setup",
        to_agent="manager-01",
        payload={},
    ))
    for msg in bus.receive("manager-01"):
        bus.mark_read("manager-01", msg.msg_id)

    # Create another agent's inbox
    bus.send(Message(
        msg_type=MessageType.STATUS_UPDATE,
        from_agent="setup",
        to_agent="dev-01",
        payload={},
    ))
    for msg in bus.receive("dev-01"):
        bus.mark_read("dev-01", msg.msg_id)

    # Manager broadcasts
    bus.broadcast(
        from_agent="manager-01",
        msg_type=MessageType.DESIGN_DECISION,
        payload={"design": "test"},
    )

    manager_msgs = bus.receive("manager-01", unread_only=True)
    design_msgs = [m for m in manager_msgs if m.msg_type == MessageType.DESIGN_DECISION]
    assert len(design_msgs) == 0


def test_conversation_between_agents(bus):
    """get_conversation returns messages between two agents in time order."""
    # Stagger timestamps so ordering is deterministic
    msg1 = Message(
        msg_type=MessageType.REVIEW_REQUEST,
        from_agent="dev-01",
        to_agent="reviewer-01",
        payload={"branch": "feature-1"},
        timestamp=1000.0,
    )
    bus.send(msg1)

    msg2 = Message(
        msg_type=MessageType.REVIEW_RESULT,
        from_agent="reviewer-01",
        to_agent="dev-01",
        payload={"verdict": "approve"},
        timestamp=2000.0,
    )
    bus.send(msg2)

    convo = bus.get_conversation("dev-01", "reviewer-01")
    assert len(convo) == 2
    assert convo[0].msg_type == MessageType.REVIEW_REQUEST
    assert convo[1].msg_type == MessageType.REVIEW_RESULT
    # Verify time ordering
    assert convo[0].timestamp <= convo[1].timestamp


def test_conversation_empty_when_no_messages(bus):
    """get_conversation returns empty list when agents have not communicated."""
    convo = bus.get_conversation("dev-01", "reviewer-01")
    assert convo == []


def test_conversation_excludes_third_party(bus):
    """get_conversation between A and B should not include messages from C."""
    bus.send(Message(
        msg_type=MessageType.TASK_COMPLETE,
        from_agent="dev-01",
        to_agent="reviewer-01",
        payload={"from": "dev-01"},
        timestamp=1000.0,
    ))
    bus.send(Message(
        msg_type=MessageType.TASK_COMPLETE,
        from_agent="dev-02",
        to_agent="reviewer-01",
        payload={"from": "dev-02"},
        timestamp=2000.0,
    ))

    convo = bus.get_conversation("dev-01", "reviewer-01")
    # Only the message from dev-01 should be included
    senders = {m.from_agent for m in convo}
    assert "dev-02" not in senders


def test_message_serialization_roundtrip(bus):
    """Messages survive JSON serialization/deserialization through the bus."""
    original = Message(
        msg_type=MessageType.BUILD_RESULT,
        from_agent="tester-01",
        to_agent="integrator-01",
        payload={
            "success": True,
            "output": "Build succeeded in 12.3s",
            "artifacts": ["kernel.elf", "kernel.iso"],
        },
    )
    bus.send(original)

    received = bus.receive("integrator-01")
    assert len(received) == 1
    msg = received[0]
    assert msg.msg_type == MessageType.BUILD_RESULT
    assert msg.from_agent == "tester-01"
    assert msg.payload["success"] is True
    assert msg.payload["artifacts"] == ["kernel.elf", "kernel.iso"]
    assert isinstance(msg.msg_id, str) and len(msg.msg_id) > 0
    assert isinstance(msg.timestamp, float)


def test_message_types_cover_workflow():
    """All expected message types exist for the agent workflow."""
    expected_types = {
        "task_assignment",
        "task_complete",
        "review_request",
        "review_result",
        "merge_request",
        "merge_result",
        "build_result",
        "test_result",
        "design_decision",
        "escalation",
        "status_update",
    }
    actual_types = {mt.value for mt in MessageType}
    assert expected_types.issubset(actual_types)


def test_full_dev_review_merge_cycle(bus):
    """Simulate a complete dev -> review -> merge cycle through the message bus."""
    # Step 1: Developer completes task
    bus.send(Message(
        msg_type=MessageType.TASK_COMPLETE,
        from_agent="dev-01",
        to_agent="reviewer-01",
        payload={"task_id": "boot-001", "branch": "agent/dev-01/boot-loader"},
        timestamp=1000.0,
    ))

    # Step 2: Reviewer approves
    bus.send(Message(
        msg_type=MessageType.REVIEW_RESULT,
        from_agent="reviewer-01",
        to_agent="integrator-01",
        payload={"task_id": "boot-001", "verdict": "approve", "branch": "agent/dev-01/boot-loader"},
        timestamp=2000.0,
    ))

    # Step 3: Integrator sends merge request
    bus.send(Message(
        msg_type=MessageType.MERGE_REQUEST,
        from_agent="integrator-01",
        to_agent="manager-01",
        payload={"task_id": "boot-001", "branch": "agent/dev-01/boot-loader"},
        timestamp=3000.0,
    ))

    # Step 4: Integrator sends merge result back to developer
    bus.send(Message(
        msg_type=MessageType.MERGE_RESULT,
        from_agent="integrator-01",
        to_agent="dev-01",
        payload={"task_id": "boot-001", "merged": True},
        timestamp=4000.0,
    ))

    # Verify the developer sees the merge result
    dev_msgs = bus.receive("dev-01")
    assert len(dev_msgs) == 1
    assert dev_msgs[0].msg_type == MessageType.MERGE_RESULT
    assert dev_msgs[0].payload["merged"] is True

    # Verify the integrator received the review approval
    integrator_msgs = bus.receive("integrator-01")
    assert len(integrator_msgs) == 1
    assert integrator_msgs[0].msg_type == MessageType.REVIEW_RESULT
    assert integrator_msgs[0].payload["verdict"] == "approve"
