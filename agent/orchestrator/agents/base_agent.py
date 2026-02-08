"""Base agent class - foundation for all specialized agents."""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from orchestrator.arch_registry import ArchProfile
from orchestrator.comms.git_workspace import GitWorkspace
from orchestrator.comms.message_bus import Message, MessageBus
from orchestrator.llm.client import LLMClient

logger = logging.getLogger(__name__)


class AgentRole(str, Enum):
    MANAGER = "manager"
    ARCHITECT = "architect"
    DEVELOPER = "developer"
    REVIEWER = "reviewer"
    TESTER = "tester"
    INTEGRATOR = "integrator"
    # SLM agents
    DATA_SCIENTIST = "data_scientist"
    MODEL_ARCHITECT = "model_architect"
    TRAINING = "training"


class AgentState(str, Enum):
    IDLE = "idle"
    THINKING = "thinking"
    EXECUTING = "executing"
    WAITING = "waiting"
    DONE = "done"
    ERROR = "error"


@dataclass
class TaskResult:
    """Result of an agent executing a task."""

    success: bool
    task_id: str
    agent_id: str
    summary: str
    artifacts: list[str] = field(default_factory=list)  # Files created/modified
    branch: str | None = None
    build_status: str = "unknown"
    test_status: str = "unknown"
    error: str | None = None


class Agent:
    """Base agent that wraps Claude API with tool-use capabilities.

    Each agent has:
    - A role (manager, developer, etc.) with a specialized system prompt
    - Access to a shared git workspace
    - A set of tools it can invoke
    - A message bus for inter-agent communication
    """

    def __init__(
        self,
        agent_id: str,
        role: AgentRole,
        system_prompt: str,
        tools: list[dict[str, Any]],
        client: LLMClient,
        workspace: GitWorkspace,
        message_bus: MessageBus,
        kernel_spec_path: Path,
        model_override: str | None = None,
        arch_profile: ArchProfile | None = None,
    ):
        self.agent_id = agent_id
        self.role = role
        self.system_prompt = system_prompt
        self.tools = tools
        self.client = client
        self.workspace = workspace
        self.message_bus = message_bus
        self.kernel_spec_path = kernel_spec_path
        self.model_override = model_override
        self.arch_profile = arch_profile
        self.state = AgentState.IDLE
        self._conversation: list[dict[str, Any]] = []

    async def execute_task(self, task: dict[str, Any]) -> TaskResult:
        """Execute a task using the Claude agentic loop.

        The agent sends the task to Claude along with its tools, and
        Claude iteratively calls tools until the task is complete.
        """
        self.state = AgentState.THINKING
        logger.info("[%s] Starting task: %s", self.agent_id, task.get("title", "untitled"))

        # Build the initial message
        task_prompt = self._format_task_prompt(task)
        messages = [{"role": "user", "content": task_prompt}]

        try:
            self.state = AgentState.EXECUTING
            result_messages = await self.client.send_with_tools(
                agent_id=self.agent_id,
                system=self.system_prompt,
                messages=messages,
                tools=self.tools,
                tool_executor=self._execute_tool,
                model_override=self.model_override,
            )

            self._conversation = result_messages
            self.state = AgentState.DONE

            # Extract the final text response
            summary = self._extract_final_text(result_messages)
            artifacts = self._extract_artifacts(result_messages)

            return TaskResult(
                success=True,
                task_id=task.get("task_id", "unknown"),
                agent_id=self.agent_id,
                summary=summary,
                artifacts=artifacts,
                branch=self._current_branch(),
            )

        except Exception as e:
            self.state = AgentState.ERROR
            logger.error("[%s] Task failed: %s", self.agent_id, e)
            return TaskResult(
                success=False,
                task_id=task.get("task_id", "unknown"),
                agent_id=self.agent_id,
                summary=f"Task failed: {e}",
                error=str(e),
            )

    async def check_messages(self) -> list[Message]:
        """Check for new messages from other agents."""
        return self.message_bus.receive(self.agent_id)

    async def send_message(self, to_agent: str, msg_type: Any, payload: dict) -> None:
        """Send a message to another agent."""
        msg = Message(
            msg_type=msg_type,
            from_agent=self.agent_id,
            to_agent=to_agent,
            payload=payload,
        )
        self.message_bus.send(msg)

    async def _execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool call from Claude. Returns the result as a string."""
        logger.debug("[%s] Tool call: %s(%s)", self.agent_id, tool_name, tool_input)

        try:
            match tool_name:
                case "read_file":
                    return self.workspace.read_file(tool_input["path"])

                case "write_file":
                    self.workspace.write_file(tool_input["path"], tool_input["content"])
                    return f"Written {len(tool_input['content'])} bytes to {tool_input['path']}"

                case "search_code":
                    results = self.workspace.search_code(
                        tool_input["pattern"],
                        tool_input.get("glob", "*"),
                    )
                    if not results:
                        return "No matches found."
                    lines = [
                        f"{r['file']}:{r['line']}: {r['content']}" for r in results[:50]
                    ]
                    return "\n".join(lines)

                case "list_files":
                    files = self.workspace.list_files(
                        tool_input.get("path", "."),
                        tool_input.get("recursive", False),
                    )
                    return "\n".join(files) if files else "No files found."

                case "build_kernel":
                    return await self._run_build(tool_input.get("target", "all"))

                case "run_test":
                    return await self._run_test(
                        tool_input["test_name"],
                        tool_input.get("timeout", 60),
                    )

                case "git_commit":
                    sha = self.workspace.commit(
                        tool_input["message"],
                        tool_input.get("files"),
                    )
                    return f"Committed: {sha[:8]}"

                case "git_diff":
                    diff = self.workspace.diff(tool_input.get("branch"))
                    return diff if diff else "No changes."

                case "read_spec":
                    return self._read_spec(tool_input["subsystem"])

                case "shell":
                    return await self._run_shell(
                        tool_input["command"],
                        tool_input.get("timeout", 120),
                    )

                # SLM tools
                case "analyze_dataset":
                    return await self._analyze_dataset(tool_input["dataset_path"])

                case "tokenize_data":
                    return await self._tokenize_data(
                        tool_input["input_path"],
                        tool_input["output_path"],
                        tool_input.get("vocab_size", 32000),
                    )

                case "validate_architecture":
                    return self._validate_architecture(tool_input["config_path"])

                case "estimate_flops":
                    return self._estimate_flops(tool_input["config_path"])

                case "train_model":
                    return await self._train_model(
                        tool_input["config_path"],
                        tool_input["dataset_path"],
                        tool_input.get("max_steps", 10000),
                    )

                case "evaluate_model":
                    return await self._evaluate_model(
                        tool_input["checkpoint_path"],
                        tool_input["test_dataset"],
                    )

                case "quantize_model":
                    return await self._quantize_model(
                        tool_input["checkpoint_path"],
                        tool_input["output_path"],
                        tool_input.get("bits", 4),
                    )

                case "export_gguf":
                    return await self._export_gguf(
                        tool_input["model_path"],
                        tool_input["output_path"],
                    )

                case "export_onnx":
                    return await self._export_onnx(
                        tool_input["model_path"],
                        tool_input["output_path"],
                    )

                case "integrate_slm":
                    return await self._integrate_slm(
                        tool_input["model_path"],
                        tool_input["kernel_arch"],
                    )

                case _:
                    return f"Unknown tool: {tool_name}"

        except Exception as e:
            return f"Error executing {tool_name}: {e}"

    def _read_spec(self, subsystem: str) -> str:
        """Read a kernel specification document.

        Supports subsystem names like 'boot', 'mm', 'sched', etc.
        Also supports 'architecture', 'hal', and arch-specific specs
        like 'arch/x86_64', 'arch/aarch64', 'arch/riscv64'.
        """
        if subsystem == "architecture":
            path = self.kernel_spec_path / "architecture.md"
        elif subsystem == "hal":
            path = self.kernel_spec_path / "arch" / "hal.md"
        elif subsystem.startswith("arch/"):
            # e.g. "arch/x86_64" -> kernel_spec/arch/x86_64.md
            arch_name = subsystem.split("/", 1)[1]
            path = self.kernel_spec_path / "arch" / f"{arch_name}.md"
        else:
            path = self.kernel_spec_path / "subsystems" / f"{subsystem}.md"

        if not path.exists():
            return f"Specification not found: {subsystem}"
        return path.read_text(encoding="utf-8")

    async def _run_build(self, target: str) -> str:
        """Run the kernel build. Delegates to the build system."""
        makefile = self.workspace.path / "Makefile"
        if not makefile.exists():
            return "No Makefile found in workspace. Cannot build."

        cmd = ["make", "-C", str(self.workspace.path), target]
        return await self._run_shell(" ".join(cmd), timeout=120)

    async def _run_test(self, test_name: str, timeout: int) -> str:
        """Run a kernel test."""
        return await self._run_shell(
            f"make -C {self.workspace.path} test-{test_name}",
            timeout=timeout,
        )

    async def _run_shell(self, command: str, timeout: int = 120) -> str:
        """Execute a shell command and return stdout+stderr."""
        try:
            proc = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(self.workspace.path),
            )
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(), timeout=timeout
            )
            output = ""
            if stdout:
                output += stdout.decode("utf-8", errors="replace")
            if stderr:
                output += "\n[stderr]\n" + stderr.decode("utf-8", errors="replace")
            output += f"\n[exit code: {proc.returncode}]"
            return output
        except asyncio.TimeoutError:
            return f"Command timed out after {timeout}s: {command}"
        except Exception as e:
            return f"Shell error: {e}"

    def _format_task_prompt(self, task: dict[str, Any]) -> str:
        """Format a task as a user prompt for Claude."""
        parts = [f"## Task: {task.get('title', 'Unnamed task')}"]

        if desc := task.get("description"):
            parts.append(f"\n{desc}")

        if subsystem := task.get("subsystem"):
            parts.append(f"\n**Subsystem**: {subsystem}")

        if spec_ref := task.get("spec_reference"):
            parts.append(f"**Specification**: {spec_ref}")

        if deps := task.get("dependencies"):
            parts.append(f"**Dependencies**: {', '.join(deps)}")

        if criteria := task.get("acceptance_criteria"):
            parts.append("\n**Acceptance Criteria**:")
            for c in criteria:
                parts.append(f"- {c}")

        if context := task.get("context"):
            parts.append(f"\n**Additional Context**:\n{context}")

        parts.append(
            "\nExecute this task using the tools available to you. "
            "Build and test your code. Commit when everything passes."
        )
        return "\n".join(parts)

    def _extract_final_text(self, messages: list[dict[str, Any]]) -> str:
        """Extract the final text response from the conversation."""
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content")
                if isinstance(content, str) and content:
                    return content
        return "No text response."

    def _extract_artifacts(self, messages: list[dict[str, Any]]) -> list[str]:
        """Extract file paths from write_file tool calls."""
        artifacts = []
        for msg in messages:
            if msg.get("role") == "assistant":
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    if func.get("name") == "write_file":
                        try:
                            args = json.loads(func.get("arguments", "{}"))
                        except (json.JSONDecodeError, TypeError):
                            args = {}
                        path = args.get("path", "")
                        if path:
                            artifacts.append(path)
        return artifacts

    def _current_branch(self) -> str | None:
        """Get the current git branch name."""
        try:
            return self.workspace.repo.active_branch.name
        except Exception:
            return None

    # SLM tool executors
    async def _analyze_dataset(self, dataset_path: str) -> str:
        """Analyze dataset statistics."""
        cmd = f"python SLM/tools/dataset_builder.py analyze {dataset_path}"
        return await self._run_shell(cmd)

    async def _tokenize_data(self, input_path: str, output_path: str, vocab_size: int) -> str:
        """Tokenize dataset."""
        cmd = f"python SLM/tools/tokenizer.py --input {input_path} --output {output_path} --vocab-size {vocab_size}"
        return await self._run_shell(cmd)

    def _validate_architecture(self, config_path: str) -> str:
        """Validate model config YAML."""
        import yaml
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            required = ["model", "architecture", "training"]
            missing = [k for k in required if k not in config]
            if missing:
                return f"Invalid config: missing {missing}"
            return f"Config valid: {config['model']['name']}"
        except Exception as e:
            return f"Config validation error: {e}"

    def _estimate_flops(self, config_path: str) -> str:
        """Estimate model FLOPs."""
        import yaml
        try:
            with open(config_path) as f:
                config = yaml.safe_load(f)
            arch = config["architecture"]
            params = config["model"]["parameters"]
            return f"Estimated {params:,} parameters, ~{params * 6 / 1e9:.2f}B FLOPs per token"
        except Exception as e:
            return f"FLOP estimation error: {e}"

    async def _train_model(self, config_path: str, dataset_path: str, max_steps: int) -> str:
        """Train SLM model."""
        cmd = f"python SLM/scripts/train.py --config {config_path} --dataset {dataset_path} --max-steps {max_steps}"
        return await self._run_shell(cmd, timeout=3600)

    async def _evaluate_model(self, checkpoint_path: str, test_dataset: str) -> str:
        """Evaluate model checkpoint."""
        cmd = f"python SLM/scripts/evaluate.py --checkpoint {checkpoint_path} --dataset {test_dataset}"
        return await self._run_shell(cmd, timeout=600)

    async def _quantize_model(self, checkpoint_path: str, output_path: str, bits: int) -> str:
        """Quantize model."""
        cmd = f"python SLM/scripts/quantize.py --checkpoint {checkpoint_path} --bits {bits} --output {output_path}"
        return await self._run_shell(cmd, timeout=1800)

    async def _export_gguf(self, model_path: str, output_path: str) -> str:
        """Export to GGUF format."""
        cmd = f"python SLM/scripts/export_gguf.py --model {model_path} --output {output_path}"
        return await self._run_shell(cmd, timeout=600)

    async def _export_onnx(self, model_path: str, output_path: str) -> str:
        """Export to ONNX format."""
        cmd = f"python SLM/scripts/export_onnx.py --model {model_path} --output {output_path}"
        return await self._run_shell(cmd, timeout=600)

    async def _integrate_slm(self, model_path: str, kernel_arch: str) -> str:
        """Integrate SLM into kernel workspace."""
        import shutil
        from pathlib import Path
        
        try:
            src = Path(model_path)
            dst = Path(f"kernels/{kernel_arch}/kernel/slm/models/auton-slm.gguf")
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(src, dst)
            return f"Integrated {src.name} into {kernel_arch} kernel at {dst}"
        except Exception as e:
            return f"Integration error: {e}"
