#!/usr/bin/env python3
"""Guarantee the roslyn-graph plugin carries exactly the repository's ontology and viewer.

The plugin must be self-contained, so it holds copies of files that are authored elsewhere in this
repository. This check fails when a copy differs from its source (compared as git blobs, so line-ending
conversion does not matter), when the generated ontology reference is stale, or when the extractor emits
an ontology term the ontology does not declare.

    python scripts/check_plugin_sync.py          # check (CI and the pre-commit hook)
    python scripts/check_plugin_sync.py --fix    # copy sources into the plugin and regenerate the reference

Prints one JSON object: {"type": "plugin-sync", "inSync": true} or {"type": "error", "errors": [...]}.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PLUGIN = REPO / "plugins" / "roslyn-graph"
COPIES = {
    "ontology/dotnet-types.ttl": "plugins/roslyn-graph/ontology/dotnet-types.ttl",
    "ontology/roslyn-graph.ttl": "plugins/roslyn-graph/ontology/roslyn-graph.ttl",
    "viewer/explorer.html": "plugins/roslyn-graph/visualizers/explorer/explorer.html",
    "viewer/rdf-graph-parser.js": "plugins/roslyn-graph/visualizers/explorer/rdf-graph-parser.js",
}
EXTRACTOR_SOURCES = ["src/RoslynToRdf.Core/Model/DotNetOntology.cs", "src/RoslynToRdf.Core/Extraction"]
_STANDARD_PREFIXES = {"dt", "http"}


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


def check(fix: bool) -> list[dict]:
    problems = []
    for source, copy in COPIES.items():
        src, dst = REPO / source, REPO / copy
        if not src.is_file():
            problems.append({"code": "SYNC_SOURCE_MISSING", "message": f"{source} does not exist", "hint": "", "context": {}})
            continue
        if not dst.is_file() or blob(src) != blob(dst):
            if fix:
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
            else:
                problems.append({"code": "SYNC_COPY_DIFFERS", "message": f"{copy} differs from {source}",
                                 "hint": "Run: python scripts/check_plugin_sync.py --fix", "context": {"source": source, "copy": copy}})

    sys.path.insert(0, str(PLUGIN / "scripts"))
    from roslyn_graph import ontology  # noqa: E402  (after the copies are fixed)

    declared = ontology.declared()
    undeclared = sorted(emitted_terms() - declared)
    if undeclared:
        problems.append({"code": "ONTOLOGY_TERM_UNDECLARED", "message": f"the extractor emits undeclared dt: terms: {undeclared}",
                         "hint": "Declare them in ontology/dotnet-types.ttl, then run with --fix.", "context": {"terms": undeclared}})

    reference = PLUGIN / "skills" / "roslyn-graph-explore" / "reference" / "ontology.md"
    generated = ontology.markdown()
    current = reference.read_text(encoding="utf-8").replace("\r\n", "\n") if reference.is_file() else ""
    if current != generated:
        if fix:
            reference.write_text(generated, encoding="utf-8", newline="\n")
        else:
            problems.append({"code": "SYNC_ONTOLOGY_DOC_STALE", "message": f"{reference.relative_to(REPO).as_posix()} is out of date",
                             "hint": "Run: python scripts/check_plugin_sync.py --fix", "context": {}})
    return problems


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fix", action="store_true")
    args = parser.parse_args()
    try:
        problems = check(args.fix)
    except Exception as exc:  # noqa: BLE001 - always one JSON object
        problems = [{"code": "SYNC_INTERNAL", "message": str(exc), "hint": "", "context": {}}]
    payload = {"type": "error", "errors": problems} if problems else {"type": "plugin-sync", "inSync": True, "fixed": args.fix}
    print(json.dumps(payload, indent=2))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
