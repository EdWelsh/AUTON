"""Adversarial tests: command injection through an agent's tool arguments.

Every string exercised here arrives as model output in production — a test
name, a make target, a workspace path, a shell command. Each was previously
interpolated into a string handed to ``/bin/sh``, so a semicolon, a newline or
a ``$(...)`` anywhere in one ran a second command with the agent's privileges.

These assert the **absence of a side effect** — a sentinel file must not exist
after the call — rather than the shape of a command string. A string assertion
would pass against a quoting scheme that still executes; only the filesystem
settles it. Every test here fails on the commit before the argv conversion.

They run real subprocesses on purpose. A mocked `create_subprocess_exec` can
only prove what we asked for, not what the operating system would have done.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from orchestrator.agents.base_agent import Agent, AgentRole
from orchestrator.arch_registry import get_arch_profile

pytestmark = pytest.mark.skipif(
    shutil.which("make") is None,
    reason="injection is proven by running a real `make`; none on PATH",
)


def _agent(workspace_path: Path) -> Agent:
    """An Agent wired to a real directory. Only `workspace.path` is exercised —
    nothing here reaches the LLM client or the message bus."""
    workspace = MagicMock()
    workspace.path = workspace_path
    return Agent(
        agent_id="inject-01",
        role=AgentRole.DEVELOPER,
        system_prompt="test",
        tools=[],
        client=MagicMock(),
        workspace=workspace,
        message_bus=MagicMock(),
        kernel_spec_path=Path("/nonexistent/specs"),
        arch_profile=get_arch_profile("x86_64"),
    )


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """A workspace with a Makefile, so `build_kernel` gets past its own guard
    and the build actually runs."""
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "Makefile").write_text("all:\n\t@true\n")
    return ws


class TestInternalCallersCannotBeInjected:
    """`run_test` and `build_kernel` build their own command from model input."""

    async def test_test_name_cannot_chain_a_second_command(self, workspace, tmp_path):
        sentinel = tmp_path / "pwned-by-test-name"

        out = await _agent(workspace)._execute_tool(
            "run_test", {"test_name": f"x; touch {sentinel}", "timeout": 30}
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    async def test_build_target_cannot_chain_with_a_newline(self, workspace, tmp_path):
        """A newline needs no metacharacter — in a shell string it simply ends
        the first command and starts the next."""
        sentinel = tmp_path / "pwned-by-newline"

        out = await _agent(workspace)._execute_tool(
            "build_kernel", {"target": f"all\ntouch {sentinel}"}
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    async def test_build_target_cannot_substitute_a_command(self, workspace, tmp_path):
        sentinel = tmp_path / "pwned-by-substitution"

        out = await _agent(workspace)._execute_tool(
            "build_kernel", {"target": f"$(touch {sentinel})"}
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    async def test_workspace_path_cannot_substitute_a_command(self, tmp_path):
        """The path is not model output, but it is interpolated into the same
        string, so a workspace named from a task title carried the same hole.
        A directory name cannot contain `/`, so the payload is relative and
        lands in the cwd — which is the workspace itself."""
        ws = tmp_path / "ws$(touch pwned-by-path)"
        ws.mkdir()
        (ws / "Makefile").write_text("all:\n\t@true\n")
        sentinel = ws / "pwned-by-path"

        out = await _agent(ws)._execute_tool("build_kernel", {"target": "all"})

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    async def test_a_legitimate_build_still_succeeds(self, workspace):
        """The fix is worthless if it also breaks the ordinary path."""
        out = await _agent(workspace)._execute_tool("build_kernel", {"target": "all"})

        assert "[exit code: 0]" in out, out


class TestShellToolAllowlist:
    """The `shell` tool takes a whole command from the model. It survives only
    behind an allowlist, and only as argv."""

    async def test_a_program_outside_the_allowlist_is_refused(self, workspace, tmp_path):
        sentinel = tmp_path / "pwned-by-shell"

        out = await _agent(workspace)._execute_tool(
            "shell", {"command": f"touch {sentinel}"}
        )

        assert not sentinel.exists()
        assert "not permitted" in out

    async def test_refusal_names_the_program_and_the_alternative(self, workspace):
        """A silent denial teaches an agent nothing. The refusal has to say
        what was blocked and what to use instead, or a real need never
        surfaces."""
        out = await _agent(workspace)._execute_tool("shell", {"command": "curl http://x"})

        assert "'curl'" in out
        assert "build_kernel" in out

    async def test_a_path_prefix_does_not_bypass_the_allowlist(self, workspace, tmp_path):
        """`/usr/bin/touch` and `touch` are the same program. The check is on
        the basename for exactly this reason."""
        sentinel = tmp_path / "pwned-by-abspath"

        out = await _agent(workspace)._execute_tool(
            "shell", {"command": f"/usr/bin/touch {sentinel}"}
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"
        assert "not permitted" in out

    async def test_an_allowed_program_cannot_chain_a_second_one(self, workspace, tmp_path):
        """`make` is allowed; `make all; touch ...` must not become two
        commands. shlex splits it, and the remainder is passed to make as
        nonsense targets rather than to a shell as syntax."""
        sentinel = tmp_path / "pwned-by-chain"

        out = await _agent(workspace)._execute_tool(
            "shell", {"command": f"make all; touch {sentinel}"}
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    async def test_an_allowed_program_cannot_substitute_a_command(self, workspace, tmp_path):
        sentinel = tmp_path / "pwned-by-shell-substitution"

        out = await _agent(workspace)._execute_tool(
            "shell", {"command": f"make $(touch {sentinel})"}
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    async def test_an_allowed_program_still_runs(self, workspace):
        out = await _agent(workspace)._execute_tool("shell", {"command": "make all"})

        assert "[exit code: 0]" in out, out

    async def test_an_unparseable_command_is_reported_not_raised(self, workspace):
        """An unbalanced quote is a shlex error, not a crash — the agent needs
        the message back so it can correct itself."""
        out = await _agent(workspace)._execute_tool("shell", {"command": 'make "all'})

        assert "could not parse" in out

    async def test_an_empty_command_is_reported(self, workspace):
        out = await _agent(workspace)._execute_tool("shell", {"command": "   "})

        assert "empty command" in out

    async def test_a_missing_workspace_is_not_reported_as_a_missing_program(
        self, tmp_path
    ):
        """FileNotFoundError covers both causes. Reporting `make` as missing
        when the workspace is what vanished sends the agent after the wrong
        thing entirely."""
        out = await _agent(tmp_path / "gone")._execute_tool(
            "shell", {"command": "make all"}
        )

        assert "gone" in out, out


class TestSlmToolsCannotBeInjected:
    """The SLM tools build a `python ...` command from model-supplied paths.
    They are dispatched through the same `except Exception` that turns any
    internal breakage into a plain string, so a broken one looks to the agent
    exactly like a tool that ran and failed — these check both properties."""

    async def test_dataset_path_cannot_chain_a_second_command(self, workspace, tmp_path):
        sentinel = tmp_path / "pwned-by-dataset-path"

        out = await _agent(workspace)._execute_tool(
            "analyze_dataset", {"dataset_path": f"d.jsonl; touch {sentinel}"}
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    async def test_checkpoint_path_cannot_substitute_a_command(self, workspace, tmp_path):
        sentinel = tmp_path / "pwned-by-checkpoint-path"

        out = await _agent(workspace)._execute_tool(
            "quantize_model",
            {
                "checkpoint_path": f"$(touch {sentinel})",
                "output_path": "out.bin",
                "bits": 8,
            },
        )

        assert not sentinel.exists(), f"injection executed; tool said: {out}"

    @pytest.mark.parametrize(
        "tool_name,tool_input",
        [
            ("analyze_dataset", {"dataset_path": "d.jsonl"}),
            ("tokenize_data", {"input_path": "i", "output_path": "o"}),
            ("train_model", {"config_path": "c", "dataset_path": "d", "max_steps": 1}),
            ("evaluate_model", {"checkpoint_path": "c", "test_dataset": "d"}),
            ("quantize_model", {"checkpoint_path": "c", "output_path": "o", "bits": 8}),
            ("export_gguf", {"model_path": "m", "output_path": "o"}),
            ("export_onnx", {"model_path": "m", "output_path": "o"}),
        ],
    )
    async def test_tool_reaches_a_subprocess_rather_than_an_internal_error(
        self, workspace, tool_name, tool_input
    ):
        """Each must fail as a *command* — a missing script, a nonzero exit —
        never as an AttributeError dressed up as a tool result."""
        out = await _agent(workspace)._execute_tool(tool_name, tool_input)

        assert "object has no attribute" not in out, out
        assert not out.startswith(f"Error executing {tool_name}:"), out


class TestSchemaMatchesEnforcement:
    """What the model is told it may run and what the executor accepts are one
    set. If they drift, an agent spends turns attempting what it was invited to
    attempt and is then refused."""

    def test_the_executor_uses_the_advertised_allowlist(self):
        from orchestrator.llm.tools import SHELL_ALLOWLIST

        assert Agent.SHELL_ALLOWLIST is SHELL_ALLOWLIST

    def test_every_allowed_program_is_named_in_the_description(self):
        from orchestrator.llm.tools import SHELL_ALLOWLIST, TOOL_SHELL

        description = TOOL_SHELL["function"]["description"]
        missing = [p for p in SHELL_ALLOWLIST if p not in description]
        assert not missing, f"allowed but undocumented: {missing}"

    def test_the_description_does_not_promise_a_shell(self):
        """It was advertised as 'Execute a shell command'. It no longer is one,
        and a model that believes the old description writes pipes."""
        from orchestrator.llm.tools import TOOL_SHELL

        assert "NOT a shell" in TOOL_SHELL["function"]["description"]


class TestOutputShapeIsUnchanged:
    """Agents parse this text. The argv conversion had to leave it byte-identical
    to the shell path it replaced — verified against the pre-fix implementation,
    pinned here so it cannot drift."""

    @pytest.fixture
    def workspace(self, tmp_path: Path) -> Path:
        ws = tmp_path / "ws"
        ws.mkdir()
        (ws / "Makefile").write_text(
            "all:\n\t@echo building\nbad:\n\t@echo oops >&2; exit 3\n"
        )
        return ws

    async def test_success_is_stdout_then_exit_code(self, workspace):
        out = await _agent(workspace)._execute_tool("build_kernel", {"target": "all"})

        assert out == "building\n\n[exit code: 0]"

    async def test_failure_carries_a_stderr_section_and_a_nonzero_code(self, workspace):
        out = await _agent(workspace)._execute_tool("build_kernel", {"target": "bad"})

        assert out.startswith("\n[stderr]\noops\n")
        assert out.endswith("[exit code: 2]")
