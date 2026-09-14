"""Dispatch tests for the scheduler.

The defect these exist for: every design task was assigned to the role
"architect", `Scheduler.__init__` pre-seeds an "architect" pool key, and
`engine._init_agents` never registered an architect into it. The pool existed,
was empty, and `get_available_agent` returned None — silently, on every
iteration, for the life of the run. Zero assignments is indistinguishable from
no work to do, which is why it survived.
"""

from __future__ import annotations

import pytest

from orchestrator.agents.base_agent import AgentState
from orchestrator.core.scheduler import Scheduler
from orchestrator.core.task_graph import TaskGraph


class _FakeAgent:
    def __init__(self, agent_id: str, state: AgentState = AgentState.IDLE):
        self.agent_id = agent_id
        self.state = state


def _graph(role: str = "developer") -> TaskGraph:
    g = TaskGraph()
    g.add_task({"task_id": "t-1", "title": "do a thing", "assigned_to": role,
                "dependencies": []})
    return g


class TestDispatch:
    def test_ready_task_with_idle_agent_is_assigned(self):
        g = _graph("developer")
        s = Scheduler(g)
        s.register_agent("developer", _FakeAgent("dev-01"))
        assert len(s.get_assignments()) == 1

    def test_role_with_an_empty_pool_assigns_nothing(self, caplog):
        """The actual defect: the pool key exists but nothing is registered."""
        g = _graph("architect")
        s = Scheduler(g)
        s.register_agent("developer", _FakeAgent("dev-01"))
        assert s.get_assignments() == []
        assert "no registered agents" in caplog.text, (
            "an unsatisfiable role must say so — silence is what hid this for "
            "nine iterations"
        )

    def test_unknown_role_assigns_nothing_and_says_so(self, caplog):
        g = _graph("wizard")
        s = Scheduler(g)
        s.register_agent("developer", _FakeAgent("dev-01"))
        assert s.get_assignments() == []
        assert "No agent pool for role" in caplog.text

    def test_busy_agent_is_not_reassigned(self, caplog):
        g = _graph("developer")
        s = Scheduler(g)
        s.register_agent("developer", _FakeAgent("dev-01"))
        first = s.get_assignments()
        assert len(first) == 1
        assert s.get_assignments() == [], "a busy slot must not take a second task"

    def test_non_idle_agent_is_unavailable_and_reported(self, caplog):
        """Logged at INFO, not WARNING, and that severity split is deliberate:
        every agent being busy is normal operation, whereas an empty or unknown
        pool is a configuration error that can never resolve itself."""
        import logging

        caplog.set_level(logging.INFO)
        g = _graph("developer")
        s = Scheduler(g)
        s.register_agent("developer", _FakeAgent("dev-01", AgentState.ERROR))
        assert s.get_assignments() == []
        assert "unavailable" in caplog.text

    def test_released_agent_becomes_available_again(self):
        g = _graph("developer")
        s = Scheduler(g)
        s.register_agent("developer", _FakeAgent("dev-01"))
        s.get_assignments()
        assert s.get_available_agent("developer") is None, "slot should be busy"
        s.release_agent("dev-01")
        assert s.get_available_agent("developer") is not None


class TestEngineRegistersEverySchedulableRole:
    def test_architect_is_registered_not_merely_constructed(self):
        """The manager's prompt advertises 'architect' as assignable.

        A role the manager is told to use, that the scheduler cannot satisfy,
        is a configuration error that produces silence rather than an error.
        """
        import inspect

        from orchestrator.core import engine

        src = inspect.getsource(engine.OrchestrationEngine._init_agents)
        assert 'register_agent("architect"' in src, (
            "the architect is created but never registered — every design task "
            "routes to an empty pool"
        )

    def test_every_advertised_role_has_a_registration(self):
        import inspect

        from orchestrator.agents import manager_agent
        from orchestrator.core import engine

        advertised = {"developer", "tester", "architect"}   # manager_agent.py:70
        src = inspect.getsource(engine.OrchestrationEngine._init_agents)
        missing = {r for r in advertised if f'register_agent("{r}"' not in src}
        assert not missing, f"roles the manager may assign but nothing serves: {missing}"
