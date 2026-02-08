"""Tests for agent scheduler."""

import pytest
from unittest.mock import MagicMock

from orchestrator.core.scheduler import AgentSlot, Scheduler
from orchestrator.core.task_graph import TaskGraph
from orchestrator.agents.base_agent import AgentState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_agent(agent_id: str = "agent-1", state: AgentState = AgentState.IDLE):
    """Return a MagicMock that behaves like an Agent for scheduling purposes."""
    agent = MagicMock()
    agent.agent_id = agent_id
    agent.state = state
    return agent


def _make_scheduler() -> Scheduler:
    """Return a Scheduler backed by an empty TaskGraph."""
    return Scheduler(TaskGraph())


# ---------------------------------------------------------------------------
# AgentSlot
# ---------------------------------------------------------------------------

class TestAgentSlot:
    def test_creation_with_mock_agent(self):
        agent = _make_mock_agent("slot-agent")
        slot = AgentSlot(agent=agent)
        assert slot.agent is agent
        assert slot.agent.agent_id == "slot-agent"

    def test_defaults(self):
        slot = AgentSlot(agent=_make_mock_agent())
        assert slot.busy is False
        assert slot.current_task is None

    def test_busy_can_be_set(self):
        slot = AgentSlot(agent=_make_mock_agent(), busy=True, current_task="t-1")
        assert slot.busy is True
        assert slot.current_task == "t-1"


# ---------------------------------------------------------------------------
# Scheduler.__init__
# ---------------------------------------------------------------------------

class TestSchedulerInit:
    def test_creates_default_pools(self):
        sched = _make_scheduler()
        expected_roles = {"developer", "reviewer", "tester", "architect", "integrator"}
        assert set(sched._agents.keys()) == expected_roles

    def test_default_pools_are_empty(self):
        sched = _make_scheduler()
        for role, slots in sched._agents.items():
            assert slots == [], f"Expected empty pool for {role}"


# ---------------------------------------------------------------------------
# register_agent
# ---------------------------------------------------------------------------

class TestRegisterAgent:
    def test_adds_agent_to_correct_pool(self):
        sched = _make_scheduler()
        agent = _make_mock_agent("dev-1")
        sched.register_agent("developer", agent)

        assert len(sched._agents["developer"]) == 1
        assert sched._agents["developer"][0].agent.agent_id == "dev-1"

    def test_multiple_agents_same_role(self):
        sched = _make_scheduler()
        sched.register_agent("developer", _make_mock_agent("dev-1"))
        sched.register_agent("developer", _make_mock_agent("dev-2"))

        assert len(sched._agents["developer"]) == 2
        ids = [s.agent.agent_id for s in sched._agents["developer"]]
        assert ids == ["dev-1", "dev-2"]

    def test_creates_new_pool_for_unknown_role(self):
        sched = _make_scheduler()
        agent = _make_mock_agent("custom-1")
        sched.register_agent("custom_role", agent)

        assert "custom_role" in sched._agents
        assert len(sched._agents["custom_role"]) == 1
        assert sched._agents["custom_role"][0].agent.agent_id == "custom-1"


# ---------------------------------------------------------------------------
# get_available_agent
# ---------------------------------------------------------------------------

class TestGetAvailableAgent:
    def test_returns_idle_agent(self):
        sched = _make_scheduler()
        agent = _make_mock_agent("dev-idle", AgentState.IDLE)
        sched.register_agent("developer", agent)

        slot = sched.get_available_agent("developer")
        assert slot is not None
        assert slot.agent.agent_id == "dev-idle"

    def test_returns_done_agent(self):
        sched = _make_scheduler()
        agent = _make_mock_agent("dev-done", AgentState.DONE)
        sched.register_agent("developer", agent)

        slot = sched.get_available_agent("developer")
        assert slot is not None
        assert slot.agent.agent_id == "dev-done"

    def test_returns_none_when_all_busy(self):
        sched = _make_scheduler()
        agent = _make_mock_agent("dev-busy", AgentState.IDLE)
        sched.register_agent("developer", agent)
        # Mark the slot as busy
        sched._agents["developer"][0].busy = True

        assert sched.get_available_agent("developer") is None

    def test_returns_none_when_agent_in_non_schedulable_state(self):
        sched = _make_scheduler()
        agent = _make_mock_agent("dev-exec", AgentState.EXECUTING)
        sched.register_agent("developer", agent)

        assert sched.get_available_agent("developer") is None

    def test_returns_none_for_empty_role(self):
        sched = _make_scheduler()
        assert sched.get_available_agent("developer") is None

    def test_returns_none_for_nonexistent_role(self):
        sched = _make_scheduler()
        assert sched.get_available_agent("nonexistent") is None

    def test_skips_busy_returns_idle(self):
        sched = _make_scheduler()
        busy_agent = _make_mock_agent("dev-busy", AgentState.IDLE)
        idle_agent = _make_mock_agent("dev-idle", AgentState.IDLE)
        sched.register_agent("developer", busy_agent)
        sched.register_agent("developer", idle_agent)
        sched._agents["developer"][0].busy = True

        slot = sched.get_available_agent("developer")
        assert slot is not None
        assert slot.agent.agent_id == "dev-idle"


# ---------------------------------------------------------------------------
# release_agent
# ---------------------------------------------------------------------------

class TestReleaseAgent:
    def test_marks_agent_as_available(self):
        sched = _make_scheduler()
        agent = _make_mock_agent("dev-1", AgentState.IDLE)
        sched.register_agent("developer", agent)

        slot = sched._agents["developer"][0]
        slot.busy = True
        slot.current_task = "task-42"

        sched.release_agent("dev-1")

        assert slot.busy is False
        assert slot.current_task is None

    def test_release_nonexistent_agent_is_noop(self):
        sched = _make_scheduler()
        # Should not raise
        sched.release_agent("does-not-exist")

    def test_release_correct_agent_among_multiple(self):
        sched = _make_scheduler()
        a1 = _make_mock_agent("dev-1", AgentState.IDLE)
        a2 = _make_mock_agent("dev-2", AgentState.IDLE)
        sched.register_agent("developer", a1)
        sched.register_agent("developer", a2)

        # Make both busy
        for s in sched._agents["developer"]:
            s.busy = True
            s.current_task = "some-task"

        sched.release_agent("dev-2")

        # dev-1 should still be busy
        assert sched._agents["developer"][0].busy is True
        # dev-2 should be released
        assert sched._agents["developer"][1].busy is False
        assert sched._agents["developer"][1].current_task is None


# ---------------------------------------------------------------------------
# busy_count / idle_count
# ---------------------------------------------------------------------------

class TestCounts:
    def test_all_idle_initially(self):
        sched = _make_scheduler()
        sched.register_agent("developer", _make_mock_agent("d1"))
        sched.register_agent("reviewer", _make_mock_agent("r1"))

        assert sched.idle_count == 2
        assert sched.busy_count == 0

    def test_counts_after_marking_busy(self):
        sched = _make_scheduler()
        sched.register_agent("developer", _make_mock_agent("d1"))
        sched.register_agent("developer", _make_mock_agent("d2"))
        sched.register_agent("reviewer", _make_mock_agent("r1"))

        sched._agents["developer"][0].busy = True

        assert sched.busy_count == 1
        assert sched.idle_count == 2

    def test_counts_with_no_agents(self):
        sched = _make_scheduler()
        assert sched.idle_count == 0
        assert sched.busy_count == 0


# ---------------------------------------------------------------------------
# status
# ---------------------------------------------------------------------------

class TestStatus:
    def test_returns_correct_structure(self):
        sched = _make_scheduler()
        a1 = _make_mock_agent("dev-1", AgentState.IDLE)
        a2 = _make_mock_agent("dev-2", AgentState.IDLE)
        sched.register_agent("developer", a1)
        sched.register_agent("developer", a2)

        # Mark one busy with an assignment
        sched._agents["developer"][0].busy = True
        sched._agents["developer"][0].current_task = "task-abc"

        status = sched.status()

        # Check developer pool
        dev_status = status["developer"]
        assert dev_status["total"] == 2
        assert dev_status["busy"] == 1
        assert dev_status["idle"] == 1
        assert dev_status["assignments"] == {"dev-1": "task-abc"}

    def test_status_includes_all_default_roles(self):
        sched = _make_scheduler()
        status = sched.status()
        expected_roles = {"developer", "reviewer", "tester", "architect", "integrator"}
        assert set(status.keys()) == expected_roles

    def test_empty_role_status(self):
        sched = _make_scheduler()
        status = sched.status()
        for role in status:
            assert status[role]["total"] == 0
            assert status[role]["busy"] == 0
            assert status[role]["idle"] == 0
            assert status[role]["assignments"] == {}
