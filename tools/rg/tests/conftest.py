import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPTS = Path(__file__).resolve().parents[1]          # tools/rg (the master copy)
REPO = SCRIPTS.parents[1]
PLUGIN = REPO / "plugins" / "roslyn-graph"
EXPLORE_SKILL = PLUGIN / "skills" / "roslyn-graph-explore"
sys.path.insert(0, str(SCRIPTS))
# The master copy has no ontology/ or visualizers/ beside it; use the explore skill's synced copies.
os.environ["ROSLYN_GRAPH_RESOURCES"] = str(EXPLORE_SKILL)

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
