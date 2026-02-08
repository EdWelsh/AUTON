"""Unit tests for orchestrator.cli module."""

import sys
from pathlib import Path

import pytest
from click.testing import CliRunner

from orchestrator.cli import cli, _load_config


class TestLoadConfig:
    """Tests for the _load_config helper function."""

    def test_load_valid_toml(self, tmp_path):
        """_load_config should parse a valid TOML file and return a dict."""
        config_file = tmp_path / "auton.toml"
        config_file.write_text(
            '[llm]\nmodel = "anthropic/claude-opus-4-6"\n\n'
            "[llm.api_keys]\n"
            'anthropic = "sk-test-key"\n',
            encoding="utf-8",
        )
        result = _load_config(config_file)
        assert isinstance(result, dict)
        assert "llm" in result
        assert result["llm"]["model"] == "anthropic/claude-opus-4-6"

    def test_load_empty_toml(self, tmp_path):
        """_load_config should return an empty dict for an empty TOML file."""
        config_file = tmp_path / "empty.toml"
        config_file.write_text("", encoding="utf-8")
        result = _load_config(config_file)
        assert result == {}

    def test_load_missing_config_raises_system_exit(self, tmp_path):
        """_load_config should raise SystemExit when the config file is missing."""
        missing = tmp_path / "nonexistent.toml"
        with pytest.raises(SystemExit) as exc_info:
            _load_config(missing)
        assert exc_info.value.code == 1

    def test_load_missing_config_with_example(self, tmp_path):
        """_load_config should mention the example when a .toml.example exists."""
        example_file = tmp_path / "auton.toml.example"
        example_file.write_text('[llm]\nmodel = "test"\n', encoding="utf-8")
        config_file = tmp_path / "auton.toml"
        with pytest.raises(SystemExit) as exc_info:
            _load_config(config_file)
        assert exc_info.value.code == 1

    def test_load_nested_toml(self, tmp_path):
        """_load_config should handle nested TOML tables correctly."""
        config_file = tmp_path / "nested.toml"
        config_file.write_text(
            "[llm]\n"
            'model = "openai/gpt-4"\n'
            "\n"
            "[llm.api_keys]\n"
            'openai = "sk-key"\n'
            "\n"
            "[orchestrator]\n"
            "max_iterations = 10\n",
            encoding="utf-8",
        )
        result = _load_config(config_file)
        assert result["llm"]["api_keys"]["openai"] == "sk-key"
        assert result["orchestrator"]["max_iterations"] == 10


class TestCliGroup:
    """Tests for the CLI group and its subcommands."""

    def test_cli_help(self):
        """cli --help should succeed and mention AUTON."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "AUTON" in result.output

    def test_cli_has_run_command(self):
        """The CLI group should have a 'run' subcommand."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "run" in result.output

    def test_cli_has_status_command(self):
        """The CLI group should have a 'status' subcommand."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "status" in result.output

    def test_cli_has_agents_command(self):
        """The CLI group should have an 'agents' subcommand."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "agents" in result.output

    def test_cli_has_tasks_command(self):
        """The CLI group should have a 'tasks' subcommand."""
        runner = CliRunner()
        result = runner.invoke(cli, ["--help"])
        assert "tasks" in result.output

    def test_cli_all_commands_present(self):
        """All expected subcommands should be registered on the CLI group."""
        expected = {"run", "status", "agents", "tasks"}
        actual = set(cli.commands.keys()) if hasattr(cli, "commands") else set()
        assert expected.issubset(actual), f"Missing commands: {expected - actual}"


class TestStatusCommand:
    """Tests for the 'status' subcommand."""

    def test_status_no_run(self, tmp_path):
        """status with an empty workspace should report no active run."""
        runner = CliRunner()
        result = runner.invoke(cli, ["status", "--workspace", str(tmp_path)])
        assert result.exit_code == 0
        assert "No active run" in result.output


class TestAgentsCommand:
    """Tests for the 'agents' subcommand."""

    def test_agents_no_run(self, tmp_path):
        """agents with an empty workspace should report no active run."""
        runner = CliRunner()
        result = runner.invoke(cli, ["agents", "--workspace", str(tmp_path)])
        assert result.exit_code == 0
        assert "No active run" in result.output


class TestTasksCommand:
    """Tests for the 'tasks' subcommand."""

    def test_tasks_no_tasks(self, tmp_path):
        """tasks with an empty workspace should report no tasks found."""
        runner = CliRunner()
        result = runner.invoke(cli, ["tasks", "--workspace", str(tmp_path)])
        assert result.exit_code == 0
        assert "No tasks" in result.output


class TestCliOptions:
    """Tests for global CLI options."""

    def test_verbose_flag_accepted(self):
        """The --verbose / -v flag should be accepted without error."""
        runner = CliRunner()
        result = runner.invoke(cli, ["-v", "--help"])
        assert result.exit_code == 0

    def test_config_option_accepted(self, tmp_path):
        """The --config / -c option should be accepted."""
        runner = CliRunner()
        result = runner.invoke(cli, ["-c", str(tmp_path / "test.toml"), "--help"])
        assert result.exit_code == 0
