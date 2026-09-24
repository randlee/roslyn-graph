"""Small deterministic helpers: hashing, IRI and N-Triples encoding, subprocesses."""

from __future__ import annotations

import hashlib
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .result import RgError

DT = "http://dotnet.example/ontology/"
RG = "http://roslyn-graph.example/ontology/"
RDF_TYPE = "http://www.w3.org/1999/02/22-rdf-syntax-ns#type"
OWL_SAME_AS = "http://www.w3.org/2002/07/owl#sameAs"
DOTNET_BASE = "http://dotnet.example"


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def iri_escape(value: str) -> str:
    """Mirror of RoslynToRdf.Core.Model.IriMinter.Escape."""
    out = []
    for char in value:
        if char.isalnum() or char in "-_.~":
            out.append(char)
        else:
            out.extend(f"%{byte:02X}" for byte in char.encode("utf-8"))
    return "".join(out)


def assembly_iri(name: str, version: str) -> str:
    return f"{DOTNET_BASE}/assembly/{iri_escape(name)}/{iri_escape(version)}"


def nt_literal(value: str) -> str:
    escaped = (
        value.replace("\\", "\\\\").replace('"', '\\"').replace("\r", "\\r").replace("\n", "\\n").replace("\t", "\\t")
    )
    return f'"{escaped}"'


def nt_iri(value: str) -> str:
    if any(c in value for c in '<>"{}|^`\\ ') or any(ord(c) < 0x20 for c in value):
        raise RgError.of("INVALID_IRI", f"Cannot write IRI containing forbidden characters: {value!r}")
    return f"<{value}>"


def skill_root() -> Path:
    """The skill folder running this copy of rg.py (<skill>/scripts/roslyn_graph/util.py -> <skill>).

    Each skill ships its own copy, so resources (ontology/, visualizers/) are found beside it whatever way
    the skill was installed. ROSLYN_GRAPH_RESOURCES overrides it; the master copy in tools/rg uses it to
    point at the explore skill.
    """
    override = os.environ.get("ROSLYN_GRAPH_RESOURCES")
    return Path(override).resolve() if override else Path(__file__).resolve().parents[2]


def resource(*parts: str) -> Path:
    path = skill_root().joinpath(*parts)
    if not path.exists():
        raise RgError.of(
            "RESOURCE_MISSING",
            f"{'/'.join(parts)} is not part of this skill ({skill_root()}).",
            "Run this command with the roslyn-graph-explore skill's copy of rg.py, which carries the ontology and visualizers.",
            path=str(path),
        )
    return path


def full_path(path: str | Path, base: Path | None = None) -> Path:
    candidate = Path(path)
    if not candidate.is_absolute() and base is not None:
        candidate = base / candidate
    return Path(os.path.normpath(os.path.abspath(candidate)))


def rel_posix(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path, base)).as_posix()


@dataclass
class Completed:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def run(args: list[str], cwd: Path | None = None, env: dict[str, str] | None = None, timeout: int | None = None) -> Completed:
    try:
        proc = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RgError.of(
            "TOOL_NOT_FOUND",
            f"Cannot start '{args[0]}': {exc}",
            "Install the tool or put it on PATH; see reference/troubleshooting.md.",
            command=args[0],
        ) from exc
    return Completed(args, proc.returncode, proc.stdout, proc.stderr)
