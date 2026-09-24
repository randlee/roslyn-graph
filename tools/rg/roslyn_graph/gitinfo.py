"""Repository provenance for source components."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .result import RgError
from .util import full_path, run, sha256_text


@dataclass(frozen=True)
class RepoState:
    root: Path
    name: str
    branch: str
    commit: str
    commit_time: str
    dirty: bool
    dirty_hash: str

    def to_json(self) -> dict:
        return {
            "root": str(self.root),
            "name": self.name,
            "branch": self.branch,
            "commit": self.commit,
            "commitTime": self.commit_time,
            "dirty": self.dirty,
            "dirtyHash": self.dirty_hash,
        }


def _git(root: Path, *args: str) -> str:
    completed = run(["git", "-C", str(root), *args])
    if completed.returncode != 0:
        raise RgError.of(
            "GIT_FAILED",
            f"git {' '.join(args)} failed in {root}: {completed.stderr.strip()}",
            "Source components must live in a git repository so the artifact can record its commit.",
            path=str(root),
        )
    return completed.stdout.strip()


@lru_cache(maxsize=None)
def repo_state(path: Path) -> RepoState:
    start = path if path.is_dir() else path.parent
    root = full_path(_git(start, "rev-parse", "--show-toplevel"))
    branch = _git(root, "branch", "--show-current") or "(detached)"
    commit = _git(root, "rev-parse", "HEAD")
    commit_time = _git(root, "log", "-1", "--format=%cI")
    status = _git(root, "status", "--porcelain=v1", "--untracked-files=all")
    dirty_hash = ""
    if status:
        diff = run(["git", "-C", str(root), "diff", "HEAD", "--binary"]).stdout
        dirty_hash = sha256_text(status + "\n" + diff)[:16]
    return RepoState(root, root.name, branch, commit, commit_time, bool(status), dirty_hash)
