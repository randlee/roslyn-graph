import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SCRIPTS))

requires_oxigraph = pytest.mark.skipif(shutil.which("oxigraph") is None, reason="oxigraph is not on PATH")


class RepoPath(type(Path())):
    """A Path to a temporary git repository with a git() helper."""

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self), *args], check=True, capture_output=True)


@pytest.fixture
def git_repo(tmp_path: Path) -> RepoPath:
    repo = RepoPath(tmp_path / "repo")
    repo.mkdir()
    repo.git("init", "-q", "-b", "main")
    repo.git("config", "user.email", "test@example.invalid")
    repo.git("config", "user.name", "Test")
    (repo / "README.md").write_text("x\n")
    repo.git("add", ".")
    repo.git("commit", "-q", "-m", "init")
    return repo
