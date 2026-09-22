"""The review path, as w11's two authorship runs found it broken.

Both runs (.artifacts/authorship/2026-09-21-{f6,v8}) wrote zero lines, and the
model was never the reason:

  Iter 0  tftp-001 → architect → success on branch `main`
          reviewer: review `main` against `main` → "use of malloc is incorrect"
          → BLOCKED
  Iter 1  nothing ready → exit

Four defects, one test class each.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from orchestrator.agents.base_agent import TaskResult
from orchestrator.comms.git_workspace import GitWorkspace
from orchestrator.core.engine import OrchestrationEngine
from orchestrator.core.task_graph import TaskGraph, TaskState


def _repo(tmp_path: Path) -> GitWorkspace:
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    (tmp_path / "a.c").write_text("int a;\n")
    subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.email=t@t", "-c",
                    "user.name=t", "commit", "-qm", "base"], check=True)
    ws = GitWorkspace(tmp_path)
    ws.init()
    return ws


def _engine(ws: GitWorkspace, graph: TaskGraph, max_rounds: int = 3) -> OrchestrationEngine:
    """An engine with only what result handling touches. Building a full one
    needs an LLM client and agents, none of which this path should call."""
    eng = OrchestrationEngine.__new__(OrchestrationEngine)
    eng.workspace = ws
    eng.task_graph = graph
    eng.config = {"orchestrator": {"max_review_rounds": max_rounds}}
    eng.state = MagicMock(tasks_failed=0)
    eng.scheduler = MagicMock()
    reviewer = MagicMock()
    reviewer.agent.review_branch = AsyncMock(return_value={"verdict": "approve"})
    eng.scheduler.get_available_agent.return_value = reviewer
    eng._reviewer = reviewer
    return eng


def _chain() -> TaskGraph:
    g = TaskGraph()
    g.add_tasks([
        {"task_id": "t-1", "title": "first", "assigned_to": "architect", "dependencies": []},
        {"task_id": "t-2", "title": "second", "assigned_to": "developer", "dependencies": ["t-1"]},
    ])
    return g


def _ok(task_id: str, branch: str | None) -> TaskResult:
    return TaskResult(success=True, task_id=task_id, agent_id="x", summary="done",
                      branch=branch)


class TestNoBranchMeansNoReview:
    async def test_a_task_that_created_no_branch_merges_without_review(self, tmp_path):
        """w11: 'Read Architecture Specification' went to review as branch main."""
        ws, g = _repo(tmp_path), _chain()
        eng = _engine(ws, g)

        await eng._handle_result(g.get_task("t-1"), _ok("t-1", None))

        assert g.get_task("t-1").state is TaskState.MERGED
        assert g.get_task("t-2").state is TaskState.READY, (
            "dependents staying PENDING is the symptom that ended both w11 runs")
        assert eng._reviewer.agent.review_branch.await_count == 0


class TestEmptyDiffIsNotReviewable:
    async def test_a_branch_identical_to_main_fails_as_no_output(self, tmp_path):
        """w11: the reviewer, shown nothing, invented `struct page` handling."""
        ws, g = _repo(tmp_path), _chain()
        g.update_state("t-1", TaskState.MERGED)
        ws.create_branch("dev-01", "x", "2")
        eng = _engine(ws, g)

        await eng._handle_result(g.get_task("t-2"), _ok("t-2", "agent/dev-01/x-2"))

        node = g.get_task("t-2")
        assert node.state is TaskState.FAILED
        assert "no output" in node.data["failure_reason"]
        assert eng._reviewer.agent.review_branch.await_count == 0

    async def test_uncommitted_agent_work_is_committed_then_reviewed(self, tmp_path):
        """Agents told to 'commit when everything passes' often do not; the work
        must not be lost to the next checkout_main."""
        ws, g = _repo(tmp_path), _chain()
        g.update_state("t-1", TaskState.MERGED)
        ws.create_branch("dev-01", "x", "2")
        (tmp_path / "b.c").write_text("int b;\n")
        (tmp_path / ".auton").mkdir(exist_ok=True)
        (tmp_path / ".auton" / "state.json").write_text("{}")
        eng = _engine(ws, g)

        await eng._handle_result(g.get_task("t-2"), _ok("t-2", "agent/dev-01/x-2"))

        assert eng._reviewer.agent.review_branch.await_count == 1
        files = subprocess.run(["git", "-C", str(tmp_path), "show", "--name-only",
                                "--format=", "agent/dev-01/x-2"],
                               capture_output=True, text=True).stdout.split()
        assert files == ["b.c"], "engine state under .auton/ must never be committed"


class TestRejectionReturnsToTheAuthor:
    async def _reject_once(self, tmp_path, rounds):
        ws, g = _repo(tmp_path), _chain()
        g.update_state("t-1", TaskState.MERGED)
        ws.create_branch("dev-01", "x", "2")
        (tmp_path / "b.c").write_text("int b;\n")
        eng = _engine(ws, g, max_rounds=rounds)
        eng._reviewer.agent.review_branch = AsyncMock(return_value={
            "verdict": "request_changes", "summary": "b is unused",
            "issues": [{"severity": "warning", "file": "b.c", "description": "unused"}]})
        await eng._handle_result(g.get_task("t-2"), _ok("t-2", "agent/dev-01/x-2"))
        return g.get_task("t-2")

    async def test_request_changes_requeues_with_feedback(self, tmp_path):
        node = await self._reject_once(tmp_path, rounds=3)

        assert node.state is TaskState.READY
        assert node.review_rounds == 1
        assert node.data["review_feedback"][0]["summary"] == "b is unused"

    async def test_the_last_allowed_round_fails_with_the_review_as_reason(self, tmp_path):
        node = await self._reject_once(tmp_path, rounds=1)

        assert node.state is TaskState.FAILED
        assert "b is unused" in node.data["failure_reason"]


class TestFeedbackReachesTheAuthor:
    def test_the_task_prompt_carries_prior_review_feedback(self):
        from orchestrator.agents.base_agent import Agent

        prompt = Agent._format_task_prompt(MagicMock(), {
            "title": "t", "review_feedback": [
                {"summary": "b is unused", "issues": [{"file": "b.c", "description": "unused"}]}]})

        assert "b is unused" in prompt and "b.c" in prompt


class TestReadSpecReachesEverySpecKind:
    @pytest.fixture
    def agent(self):
        from orchestrator.agents.base_agent import Agent

        a = MagicMock()
        a.kernel_spec_path = Path(__file__).resolve().parents[3] / "kernel_spec"
        a._read_spec = Agent._read_spec.__get__(a)
        return a

    @pytest.mark.parametrize("name,needle", [
        ("services/dhcp", "service: dhcp"),
        ("drivers/virtio-net", "driver: virtio-net"),
        ("mitigations/f00f-idt-remap", "mitigation: f00f-idt-remap"),
        ("mm", "subsystem: mm"),
    ])
    def test_kind(self, agent, name, needle):
        assert needle in agent._read_spec(name)

    def test_traversal_is_refused(self, agent):
        out = agent._read_spec("services/../../config/auton")
        assert "refus" in out.lower()


class TestTheManagerPlansDeliverables:
    """w11: 2 of 7 tasks in each run were 'read the spec', with no deliverable,
    and every later task depended on them."""

    def _tasks(self):
        import json
        return json.loads((Path(__file__).resolve().parents[2] / "fixtures"
                           / "w11_f6_tasks.json").read_text())

    def test_tasks_without_a_deliverable_are_dropped(self):
        from orchestrator.agents.manager_agent import drop_undeliverable

        kept = drop_undeliverable(self._tasks())

        assert [t["task_id"] for t in kept] == [
            "tftp-003", "tftp-004", "tftp-005", "tftp-006", "tftp-007"]

    def test_dependencies_on_dropped_tasks_are_remapped_transitively(self):
        from orchestrator.agents.manager_agent import drop_undeliverable

        kept = {t["task_id"]: t for t in drop_undeliverable(self._tasks())}

        assert kept["tftp-003"]["dependencies"] == [], (
            "003 depended on 002, which depended on 001; both were readers")
        assert kept["tftp-004"]["dependencies"] == ["tftp-003"]

    def test_the_prompt_forbids_reading_tasks(self):
        import inspect

        from orchestrator.agents import manager_agent

        src = inspect.getsource(manager_agent.ManagerAgent.decompose_goal)
        assert "produces" in src and "not a task" in src


class TestApprovalMerges:
    async def test_an_approved_task_is_merged_and_its_dependents_become_ready(self, tmp_path):
        """The fifth defect, found writing the end-to-end test: approval left
        the graph node APPROVED forever, so nothing after it could run."""
        ws, g = _repo(tmp_path), TaskGraph()
        g.add_tasks([
            {"task_id": "t-1", "title": "a", "assigned_to": "developer", "dependencies": []},
            {"task_id": "t-2", "title": "b", "assigned_to": "developer", "dependencies": ["t-1"]},
        ])
        ws.create_branch("dev-01", "x", "1")
        (tmp_path / "b.c").write_text("int b;\n")
        eng = _engine(ws, g)
        eng.state = MagicMock(tasks_failed=0, tasks_completed=0)

        await eng._handle_result(g.get_task("t-1"), _ok("t-1", "agent/dev-01/x-1"))
        eng._merge_approved()

        assert g.get_task("t-1").state is TaskState.MERGED
        assert g.get_task("t-2").state is TaskState.READY
        assert (tmp_path / "b.c").exists(), "the change is on main"


class TestDeveloperMessagesSerialise:
    async def test_a_string_message_type_is_accepted(self, tmp_path):
        """The sixth defect: every successful developer task crashed sending its
        review request, because the type was a string and serialisation called
        `.value`."""
        from orchestrator.agents.base_agent import Agent
        from orchestrator.comms.message_bus import MessageBus

        agent = MagicMock()
        agent.agent_id = "dev-01"
        agent.message_bus = MessageBus(tmp_path)
        await Agent.send_message(agent, "reviewer", "review_request", {"task_id": "t"})

        assert list((tmp_path / ".auton").rglob("*.json")), "the message was written"


class TestARejectionMustPointAtTheChange:
    """w12's first live run: a correct one-line change rejected three times over
    a `kmath_add` function that exists nowhere. The reviewer never looked."""

    def test_the_reviewer_is_shown_the_diff(self, tmp_path):
        from orchestrator.agents.reviewer_agent import ReviewerAgent

        ws = _repo(tmp_path)
        ws.create_branch("dev-01", "x", "1")
        (tmp_path / "a.c").write_text("int a; /* documented */\n")
        ws.commit_pending("agent/dev-01/x-1", "change")
        seen = {}

        async def capture(task):
            seen["prompt"] = task["description"]
            return MagicMock(summary='{"verdict": "approve", "summary": "ok"}')

        reviewer = ReviewerAgent.__new__(ReviewerAgent)
        reviewer.agent_id, reviewer.workspace = "reviewer-01", ws
        reviewer.execute_task = capture
        import asyncio
        asyncio.run(reviewer.review_branch("t-1", "agent/dev-01/x-1", "document a"))

        assert "+int a; /* documented */" in seen["prompt"]
        assert "document a" in seen["prompt"]

    def test_a_rejection_citing_no_changed_file_is_discarded(self):
        from orchestrator.agents.reviewer_agent import ground_review

        out = ground_review({"verdict": "request_changes", "summary": "kmath_add lacks checks",
                             "issues": [{"severity": "warning", "file": "kernel/lib/kmath.c",
                                         "description": "kmath_add"}]},
                            ["kernel/include/kmath.h"])

        assert out["verdict"] == "approve"
        assert "unfounded" in out["summary"]

    def test_a_grounded_rejection_stands(self):
        from orchestrator.agents.reviewer_agent import ground_review

        out = ground_review({"verdict": "request_changes", "summary": "s",
                             "issues": [{"severity": "critical", "file": "a.c"}]}, ["a.c"])

        assert out["verdict"] == "request_changes"


class TestWorkStaysOnItsBranch:
    def test_leaving_an_agent_branch_commits_its_untracked_work_there(self, tmp_path):
        """Defect nine, from the third live run: an architect's uncommitted
        header rode `git checkout` onto the developer's branch and was merged
        with a one-line change."""
        ws = _repo(tmp_path)
        ws.create_branch("architect-01", "arch", "architecture")
        (tmp_path / "arch_defs.h").write_text("#define X 1\n")

        ws.checkout_main()
        ws.create_branch("dev-01", "x", "1")

        assert not (tmp_path / "arch_defs.h").exists(), "it must not follow onto another branch"
        shown = subprocess.run(["git", "-C", str(tmp_path), "show", "--name-only", "--format=",
                                "agent/architect-01/arch-architecture"],
                               capture_output=True, text=True).stdout.split()
        assert shown == ["arch_defs.h"], "it stays, committed, on the branch that made it"
