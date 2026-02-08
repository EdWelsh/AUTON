"""Mock Git workspace for testing."""

from pathlib import Path


class MockGitWorkspace:
    """Mock workspace without actual git operations."""

    def __init__(self, path: Path, agent_id: str):
        self.path = path
        self.agent_id = agent_id
        self.files = {}
        self.commits = []
        self.branches = ["main"]
        self.current_branch = "main"
        self.repo = None

    def init(self):
        """Mock init."""
        pass

    def read_file(self, path: str) -> str:
        """Mock read."""
        return self.files.get(path, f"Mock content of {path}")

    def write_file(self, path: str, content: str):
        """Mock write."""
        self.files[path] = content

    def commit(self, message: str, files: list[str] | None = None) -> str:
        """Mock commit."""
        sha = f"abc{len(self.commits):04d}"
        self.commits.append({"sha": sha, "message": message, "files": files})
        return sha

    def diff(self, branch: str | None = None) -> str:
        """Mock diff."""
        return "Mock diff output"

    def list_files(self, path: str = ".", recursive: bool = False) -> list[str]:
        """Mock list files."""
        return list(self.files.keys())

    def search_code(self, pattern: str, glob: str = "*") -> list[dict]:
        """Mock search."""
        return []
