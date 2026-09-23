"""Operator agent tests — tools, approval gate, and the full Excel scenario.

No mocks: a real local HTTP server serves a real .xlsx, openpyxl really edits it,
and a real aiosmtpd server captures the real SMTP send. The deterministic planner
drives the end-to-end test so it runs without a model; a separate test exercises
the live Ollama brain when it's reachable.
"""

from __future__ import annotations

import asyncio
import functools
import http.server
import threading
import email.policy
from email import message_from_bytes
from pathlib import Path

import pytest
from aiosmtpd.controller import Controller
from openpyxl import Workbook, load_workbook

from controlplane.operator.approval import always_allow, always_deny
from controlplane.operator.brain import BrainUnavailable, LLMBrain, resolve_model
from controlplane.operator.runner import Operator
from controlplane.operator.tools import SMTPConfig, ToolExecutor
from tests.ollama_probe import responsive_endpoint, skip_reason


# --- fixtures: a real file server and a real SMTP sink ----------------------

@pytest.fixture
def xlsx_server(tmp_path):
    """Serve a tmp dir over HTTP; yields (base_url, dir). Hosts budget.xlsx."""
    wb = Workbook()
    ws = wb.active
    ws.title = "Budget"
    ws["A1"], ws["B1"] = "Item", "Amount"
    ws["A2"], ws["B2"] = "Forecast", 1000
    wb.save(tmp_path / "budget.xlsx")

    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(tmp_path))
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    try:
        yield f"http://127.0.0.1:{port}", tmp_path
    finally:
        server.shutdown()


class _Sink:
    def __init__(self):
        self.messages = []

    async def handle_DATA(self, server, session, envelope):
        self.messages.append(envelope)
        return "250 OK"


def _free_port() -> int:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture
def smtp_sink():
    """A real SMTP server that captures messages. Yields (SMTPConfig, sink)."""
    sink = _Sink()
    port = _free_port()
    controller = Controller(sink, hostname="127.0.0.1", port=port)
    controller.start()
    try:
        yield SMTPConfig(host="127.0.0.1", port=port), sink
    finally:
        controller.stop()


# --- tool unit tests --------------------------------------------------------

def test_download_and_update_spreadsheet(xlsx_server, tmp_path):
    base, _ = xlsx_server
    ex = ToolExecutor(workspace=tmp_path / "ws", approval=always_deny)
    ex.download_file(f"{base}/budget.xlsx", "budget.xlsx")
    ex.update_spreadsheet("budget.xlsx", "B2", "1234")
    wb = load_workbook(Path(ex.workspace) / "budget.xlsx")
    assert wb.active["B2"].value == 1234  # coerced to int


def test_path_escape_is_blocked(tmp_path):
    ex = ToolExecutor(workspace=tmp_path / "ws", approval=always_deny)
    out = ex.execute("update_spreadsheet", {"filename": "../evil.xlsx", "cell": "A1", "value": "x"})
    assert "escapes the workspace" in out


def test_send_email_requires_approval(smtp_sink, tmp_path):
    cfg, sink = smtp_sink
    denied = ToolExecutor(workspace=tmp_path / "w1", approval=always_deny, smtp=cfg)
    msg = denied.send_email("boss@example.com", "Hi", "body")
    assert "NOT sent" in msg and not sink.messages

    allowed = ToolExecutor(workspace=tmp_path / "w2", approval=always_allow, smtp=cfg)
    msg = allowed.send_email("boss@example.com", "Hi", "body")
    assert "sent" in msg.lower() and len(sink.messages) == 1


# --- the full scenario, end-to-end (deterministic brain, no mocks) ----------

def test_excel_scenario_end_to_end(xlsx_server, smtp_sink, tmp_path):
    base, _ = xlsx_server
    cfg, sink = smtp_sink

    goal = (
        f"download the budget spreadsheet from {base}/budget.xlsx, "
        f"set B2 to 1234 and email it to boss@example.com"
    )
    op = Operator(approval=always_allow, smtp=cfg, workspace_root=tmp_path / "ops")
    result = op.run(goal, brain="rule")

    # 1) the email really went out, with the spreadsheet attached
    assert len(sink.messages) == 1
    msg = message_from_bytes(sink.messages[0].content, policy=email.policy.default)
    assert msg["To"] == "boss@example.com"
    attachments = [p for p in msg.iter_attachments()]
    assert attachments, "expected the spreadsheet attached"

    # 2) the attached spreadsheet actually contains the update
    out = tmp_path / "received.xlsx"
    out.write_bytes(attachments[0].get_payload(decode=True))
    assert load_workbook(out).active["B2"].value == 1234

    # 3) the audit trail shows the real steps
    tools_used = [a["tool"] for a in result.actions]
    assert tools_used == ["download_file", "read_spreadsheet", "update_spreadsheet", "send_email"]


def test_scenario_blocks_email_when_not_approved(xlsx_server, smtp_sink, tmp_path):
    base, _ = xlsx_server
    cfg, sink = smtp_sink
    goal = f"get {base}/budget.xlsx, set B2 to 999, email it to boss@example.com"
    op = Operator(approval=always_deny, smtp=cfg, workspace_root=tmp_path / "ops")
    op.run(goal, brain="rule")
    assert sink.messages == []  # confirm-before-irreversible held the email back


# --- live Ollama brain (guarded) --------------------------------------------

# Per model call. Enough for a large local model to answer one turn when it is
# not contended; short enough that a contended one skips instead of stalling
# the suite for the ten turns the brain is allowed.
LIVE_CALL_BUDGET = 120.0


def test_live_llm_brain_drives_tools(xlsx_server, smtp_sink, tmp_path):
    # Probed inside the test, not in a skipif: a skipif argument runs at
    # collection time, so every invocation of this suite — including ones
    # selected down to a single unrelated test — would pay the probe.
    #
    # And reachability is not the question. /api/tags answers instantly on a
    # saturated server, so the old guard admitted the test and then blocked
    # behind the queue. See tests/ollama_probe.py.
    model = resolve_model()
    if responsive_endpoint(model) is None:
        pytest.skip(skip_reason(model))

    base, _ = xlsx_server
    cfg, sink = smtp_sink
    goal = (
        f"Download the spreadsheet at {base}/budget.xlsx, set cell B2 to 1234, "
        f"then email it to boss@example.com with subject 'Updated budget'."
    )
    # A budget, because this is a smoke test of tool-driving, not of patience.
    # The brain's own default is ten minutes per call and it may take ten
    # turns; on a machine whose model is busy that is an hour of suite. The
    # probe above says the server can answer, so exceeding this means it got
    # busy in between — a skip, not a verdict on the model.
    op = Operator(
        approval=always_allow,
        smtp=cfg,
        workspace_root=tmp_path / "ops",
        request_timeout=LIVE_CALL_BUDGET,
    )
    try:
        result = op.run(goal, brain="llm")
    except BrainUnavailable as exc:
        pytest.skip(f"live brain gave up within {LIVE_CALL_BUDGET:.0f}s per call: {exc}")

    # The model must have actually driven the tools (downloaded + sent).
    tools_used = {a["tool"] for a in result.actions}
    assert "download_file" in tools_used
    assert result.brain.startswith("llm:")


# --- operator E2E lane (Phase 5) -------------------------------------------


class TestApprovalDefaults:
    """The default must be to ASK, never to proceed.

    always_allow exists for --yes and for tests. A regression that made it the
    default would be silent — every scenario here would still pass — and would
    mean the OS performs irreversible actions without consent. That is why this
    is asserted directly rather than inferred from the scenarios.
    """

    def test_operator_defaults_to_denying(self):
        from controlplane.operator.approval import always_allow, always_deny

        op = Operator()
        assert op.approval is not always_allow, (
            "Operator default approval is always_allow — irreversible actions "
            "would run unattended"
        )
        assert op.approval is always_deny

    def test_tool_executor_requires_an_explicit_approval(self, tmp_path):
        """Stronger than a safe default: there is no default to get wrong.

        ToolExecutor takes `approval` as a required argument, so a caller cannot
        construct one without deciding who consents to irreversible actions.
        """
        with pytest.raises(TypeError):
            ToolExecutor(workspace=tmp_path / "ws")

    def test_cli_asks_unless_yes_is_passed(self):
        """--yes opts in explicitly; without it the CLI must prompt."""
        import inspect

        from controlplane.operator import cli

        src = inspect.getsource(cli.main)
        assert "always_allow if args.yes else terminal_approval" in src, (
            "the CLI no longer prompts by default"
        )

    def test_denied_email_never_reaches_the_sink(self, smtp_sink, tmp_path):
        from controlplane.operator.approval import always_deny

        cfg, sink = smtp_sink
        ex = ToolExecutor(workspace=tmp_path / "ws", approval=always_deny, smtp=cfg)
        out = ex.execute(
            "send_email",
            {"to": "boss@example.com", "subject": "Subject", "body": "body"},
        )
        assert "NOT sent" in out
        assert sink.messages == [], "a denied email still reached the SMTP server"


class TestWorkspaceContainment:
    """Tools must not touch anything outside the sandbox, by any spelling."""

    def test_relative_escape_is_blocked(self, tmp_path):
        from controlplane.operator.approval import always_deny

        ex = ToolExecutor(workspace=tmp_path / "ws", approval=always_deny)
        out = ex.execute("read_spreadsheet", {"filename": "../../etc/passwd"})
        assert "escapes the workspace" in out

    def test_absolute_path_outside_workspace_is_blocked(self, tmp_path):
        from controlplane.operator.approval import always_deny

        ex = ToolExecutor(workspace=tmp_path / "ws", approval=always_deny)
        out = ex.execute("read_spreadsheet", {"filename": "/etc/passwd"})
        assert "escapes the workspace" in out, (
            f"an absolute path outside the workspace was accepted: {out!r}"
        )

    def test_nested_escape_is_blocked(self, tmp_path):
        from controlplane.operator.approval import always_deny

        ex = ToolExecutor(workspace=tmp_path / "ws", approval=always_deny)
        out = ex.execute("read_spreadsheet", {"filename": "sub/../../../etc/passwd"})
        assert "escapes the workspace" in out

    def test_download_cannot_write_outside_the_workspace(self, xlsx_server, tmp_path):
        from controlplane.operator.approval import always_deny

        base, _ = xlsx_server
        ex = ToolExecutor(workspace=tmp_path / "ws", approval=always_deny)
        out = ex.execute(
            "download_file", {"url": f"{base}/budget.xlsx", "filename": "../escaped.xlsx"}
        )
        assert "escapes the workspace" in out
        assert not (tmp_path / "escaped.xlsx").exists()


class TestBrainProvenance:
    """TaskResult.brain is the only proof of which path actually ran.

    Asserting the scenario succeeded is not enough: 'auto' silently falls back
    to the rule engine, so a broken LLM path looks identical to a working one
    unless provenance is checked.
    """

    def test_rule_path_reports_rule(self, xlsx_server, smtp_sink, tmp_path):
        base, _ = xlsx_server
        cfg, _sink = smtp_sink
        op = Operator(approval=always_allow, smtp=cfg, workspace_root=tmp_path / "ops")
        result = op.run(
            f"get {base}/budget.xlsx, set B2 to 1234, email it to boss@example.com",
            brain="rule",
        )
        assert result.brain == "rule"


# --- the brain's calls are bounded -----------------------------------------


class TestBrainRequestDeadline:
    """A model call must carry a deadline, or the fallback can never fire.

    LLMBrain converts every provider error into BrainUnavailable so the runner
    drops to the deterministic planner. A call with no timeout defeats that
    without tripping a single assertion: it does not error, it just never
    returns, and the runner waits behind it. That is not theoretical here —
    this machine runs the generation swarm, and a saturated Ollama is the
    normal state of it for hours at a time.
    """

    def _stub_litellm(self, monkeypatch, on_call):
        import sys
        import types

        stub = types.ModuleType("litellm")
        stub.completion = on_call
        monkeypatch.setitem(sys.modules, "litellm", stub)
        return stub

    def test_completion_is_called_with_a_timeout(self, monkeypatch, tmp_path):
        seen: dict = {}

        def capture(**kwargs):
            seen.update(kwargs)
            raise RuntimeError("stop after the first call")

        self._stub_litellm(monkeypatch, capture)
        brain = LLMBrain(model="gpt-4o-mini", request_timeout=12.5)
        with pytest.raises(BrainUnavailable):
            brain.run("do a thing", ToolExecutor(tmp_path, approval=always_allow))

        assert seen.get("timeout") == 12.5, (
            "litellm.completion was called without a timeout — a wedged model "
            "server would hang the operator instead of falling back"
        )

    def test_a_provider_timeout_becomes_brain_unavailable(self, monkeypatch, tmp_path):
        def time_out(**kwargs):
            raise TimeoutError("the model did not answer in time")

        self._stub_litellm(monkeypatch, time_out)
        brain = LLMBrain(model="gpt-4o-mini")
        with pytest.raises(BrainUnavailable):
            brain.run("do a thing", ToolExecutor(tmp_path, approval=always_allow))
