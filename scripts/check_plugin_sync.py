#!/usr/bin/env python3
"""Guarantee every roslyn-graph skill carries exact copies of its master sources.

Each skill is self-contained (it works when its folder is installed alone), so it carries copies of files
authored elsewhere in this repository:

    tools/rg/rg.py, tools/rg/roslyn_graph/*.py  ->  <every skill>/scripts/        (master CLI; tests stay in tools/rg)
    ontology/*.ttl                              ->  roslyn-graph-explore/ontology/
    viewer/explorer.html, rdf-graph-parser.js,  ->  roslyn-graph-explore/visualizers/explorer/
      graph-selection.js

The check fails when a copy differs from its master (compared as git blobs, so line-ending conversion does
not matter), when a skill's scripts/ holds a file the master does not, when the generated ontology reference
is stale, or when the extractor emits an ontology term the ontology does not declare.

    python scripts/check_plugin_sync.py          # check (CI and the pre-commit hook)
    python scripts/check_plugin_sync.py --fix    # copy masters into the skills and regenerate the reference

Prints one JSON object: {"type": "plugin-sync", "inSync": true} or {"type": "error", "errors": [...]}.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
MASTER = REPO / "tools" / "rg"
SKILLS = REPO / "plugins" / "roslyn-graph" / "skills"
SKILLS_WITH_CLI = ["roslyn-graph-create", "roslyn-graph-explore"]
EXPLORE = SKILLS / "roslyn-graph-explore"
EXTRACTOR_SOURCES = ["src/RoslynToRdf.Core/Model/DotNetOntology.cs", "src/RoslynToRdf.Core/Extraction"]
_STANDARD_PREFIXES = {"dt", "http"}


def copies() -> dict[Path, Path]:
    """copy -> master, for every file a skill must carry."""
    mapping: dict[Path, Path] = {}
    masters = [MASTER / "rg.py", *sorted((MASTER / "roslyn_graph").glob("*.py"))]
    for skill in SKILLS_WITH_CLI:
        for master in masters:
            mapping[SKILLS / skill / "scripts" / master.relative_to(MASTER)] = master
    for ttl in sorted((REPO / "ontology").glob("*.ttl")):
        mapping[EXPLORE / "ontology" / ttl.name] = ttl
    for name in ("explorer.html", "rdf-graph-parser.js", "graph-selection.js"):
        mapping[EXPLORE / "visualizers" / "explorer" / name] = REPO / "viewer" / name
    return mapping


def blob(path: Path) -> str:
    """git's hash of the file as it would be committed (clean filters and EOL normalization applied)."""
    rel = path.relative_to(REPO).as_posix()
    result = subprocess.run(["git", "-C", str(REPO), "hash-object", f"--path={rel}", str(path)], capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"git hash-object failed for {rel}: {result.stderr.strip()}")
    return result.stdout.strip()


def emitted_terms() -> set[str]:
    terms: set[str] = set()
    for source in EXTRACTOR_SOURCES:
        path = REPO / source
        files = [path] if path.is_file() else sorted(path.glob("*.cs"))
        for file in files:
            text = file.read_text(encoding="utf-8")
            if file.name == "DotNetOntology.cs":
                terms.update(v for v in re.findall(r'const string \w+ = "([A-Za-z]+)"', text) if v not in _STANDARD_PREFIXES)
            terms.update(re.findall(r'(?:Prop|Class)\("([A-Za-z]+)"\)', text))
    return terms


def _problem(code: str, message: str, hint: str = "Run: python scripts/check_plugin_sync.py --fix", **context) -> dict:
    return {"code": code, "message": message, "hint": hint, "context": context}


def check(fix: bool) -> list[dict]:
    problems = []
    mapping = copies()
    for copy, master in mapping.items():
        if not master.is_file():
            problems.append(_problem("SYNC_SOURCE_MISSING", f"{master.relative_to(REPO).as_posix()} does not exist", ""))
            continue
        if not copy.is_file() or blob(master) != blob(copy):
            if fix:
                copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(master, copy)
            else:
                problems.append(_problem("SYNC_COPY_DIFFERS", f"{copy.relative_to(REPO).as_posix()} differs from {master.relative_to(REPO).as_posix()}"))

    expected = set(mapping)
    for skill in SKILLS_WITH_CLI:
        scripts = SKILLS / skill / "scripts"
        for path in sorted(scripts.rglob("*")) if scripts.is_dir() else []:
            if path.is_file() and "__pycache__" not in path.parts and path not in expected:
                if fix:
                    path.unlink()
                else:
                    problems.append(_problem("SYNC_STRAY_FILE", f"{path.relative_to(REPO).as_posix()} has no master in tools/rg"))

    os.environ["ROSLYN_GRAPH_RESOURCES"] = str(EXPLORE)
    sys.path.insert(0, str(MASTER))
    from roslyn_graph import ontology  # noqa: E402  (after the copies are fixed)

    undeclared = sorted(emitted_terms() - ontology.declared())
    if undeclared:
        problems.append(_problem("ONTOLOGY_TERM_UNDECLARED", f"the extractor emits undeclared dt: terms: {undeclared}",
                                 "Declare them in ontology/dotnet-types.ttl, then run with --fix.", terms=undeclared))

    reference = EXPLORE / "reference" / "ontology.md"
    generated = ontology.markdown()
    current = reference.read_text(encoding="utf-8").replace("\r\n", "\n") if reference.is_file() else ""
    if current != generated:
        if fix:
            reference.write_text(generated, encoding="utf-8", newline="\n")
        else:
            problems.append(_problem("SYNC_ONTOLOGY_DOC_STALE", f"{reference.relative_to(REPO).as_posix()} is out of date"))
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()
    try:
        problems = check(args.fix)
    except Exception as exc:  # noqa: BLE001 - always one JSON object
        problems = [_problem("SYNC_INTERNAL", str(exc), "")]
    payload = {"type": "error", "errors": problems} if problems else {"type": "plugin-sync", "inSync": True, "fixed": args.fix}
    print(json.dumps(payload, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
