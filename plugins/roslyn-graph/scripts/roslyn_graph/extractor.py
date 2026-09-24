"""Locate and fingerprint the installed RoslynToRdf extractor, and run it.

The extractor is an installed tool, like Oxigraph. Resolution order:

1. ``ROSLYN_GRAPH_EXTRACTOR``: path to ``RoslynToRdf.Cli.dll``;
2. the ``RoslynToRdf`` .NET global tool store (``~/.dotnet/tools/.store/roslyntordf``).

The extractor identity hashes every DLL beside the entry point, the .NET runtime it rolls forward
to (framework types resolve from that runtime) and the fixed extraction flags, so any change to
the extractor produces new artifact IDs.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from .result import RgError
from .util import run, sha256_file, sha256_text

ENTRY = "RoslynToRdf.Cli.dll"
FLAGS = ("--format", "Turtle", "--include-private", "--quiet")
INSTALL_HINT = (
    "Install the extractor: from a roslyn-graph checkout run "
    "'dotnet pack src/RoslynToRdf.Cli -c Release -o <dir>' then "
    "'dotnet tool install --global RoslynToRdf --add-source <dir>', "
    "or set ROSLYN_GRAPH_EXTRACTOR to a built RoslynToRdf.Cli.dll. See reference/setup.md."
)


@dataclass(frozen=True)
class Extractor:
    entry: Path
    id: str
    runtime: str
    files_hash: str
    source: str

    def to_json(self) -> dict:
        return {
            "entry": str(self.entry),
            "id": self.id,
            "runtime": self.runtime,
            "filesHash": self.files_hash,
            "flags": list(FLAGS),
            "source": self.source,
        }


def _find_entry() -> tuple[Path, str]:
    override = os.environ.get("ROSLYN_GRAPH_EXTRACTOR")
    if override:
        path = Path(override)
        if not path.is_file() or path.name != ENTRY:
            raise RgError.of("EXTRACTOR_NOT_FOUND", f"ROSLYN_GRAPH_EXTRACTOR does not point to {ENTRY}: {override}", INSTALL_HINT)
        return path.resolve(), "ROSLYN_GRAPH_EXTRACTOR"
    store = Path.home() / ".dotnet" / "tools" / ".store" / "roslyntordf"
    found = sorted(store.glob(f"*/roslyntordf/*/tools/*/any/{ENTRY}")) if store.is_dir() else []
    if len(found) != 1:
        raise RgError.of(
            "EXTRACTOR_NOT_FOUND",
            f"Expected one installed RoslynToRdf tool under {store}, found {len(found)}.",
            INSTALL_HINT,
            candidates=[str(p) for p in found],
        )
    return found[0].resolve(), "dotnet global tool"


def _runtime_version(entry: Path) -> str:
    config_path = entry.with_name(entry.name.replace(".dll", ".runtimeconfig.json"))
    try:
        framework = json.loads(config_path.read_text(encoding="utf-8"))["runtimeOptions"]["framework"]
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        raise RgError.of("EXTRACTOR_RUNTIMECONFIG", f"Cannot read {config_path}: {exc}", INSTALL_HINT) from exc
    major_minor = ".".join(framework["version"].split(".")[:2])
    listing = run(["dotnet", "--list-runtimes"]).stdout
    versions = re.findall(rf"^{re.escape(framework['name'])} ({re.escape(major_minor)}\.\d+)\s", listing, re.MULTILINE)
    if not versions:
        raise RgError.of(
            "EXTRACTOR_RUNTIME_MISSING",
            f"The extractor needs {framework['name']} {major_minor}.x, which is not installed.",
            f"Install the .NET {major_minor} runtime.",
        )
    return f"{framework['name']} {max(versions, key=lambda v: tuple(map(int, v.split('.'))))}"


@lru_cache(maxsize=1)
def resolve() -> Extractor:
    entry, source = _find_entry()
    files = sorted(entry.parent.glob("*.dll"), key=lambda p: p.name.lower())
    files_hash = sha256_text("\n".join(f"{p.name.lower()}:{sha256_file(p)}" for p in files))
    runtime = _runtime_version(entry)
    identity = f"extractor/v1|{files_hash}|{runtime}|{' '.join(FLAGS)}"
    return Extractor(entry, sha256_text(identity)[:16], runtime, files_hash, source)


def extract(extractor: Extractor, assembly: Path, output: Path, search_dirs: list[Path]) -> list[str]:
    args = ["dotnet", str(extractor.entry), str(assembly), "--output", str(output), *FLAGS]
    for directory in search_dirs:
        args += ["--search-dir", str(directory)]
    completed = run(args)
    if completed.returncode != 0 or not output.is_file():
        raise RgError.of(
            "EXTRACTION_FAILED",
            f"RoslynToRdf failed for {assembly.name} (exit {completed.returncode}).",
            "Usually a dependency the extractor cannot resolve: check the search directories, "
            "and that the build output and restore assets belong to the same build.",
            assembly=str(assembly),
            stderr=completed.stderr.splitlines()[-20:],
            searchDirs=[str(d) for d in search_dirs],
        )
    return [line for line in completed.stderr.splitlines() if line.strip()]
