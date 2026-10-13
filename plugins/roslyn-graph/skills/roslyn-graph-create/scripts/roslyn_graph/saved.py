"""Saved queries (*.rq) and graph definitions (*.graph.toml) in a workspace's .roslyn-graph folder.

A saved .rq starts with a comment header:

    # Title: Implementers of an interface
    # Store: app_with_current_data
    # Parameters:
    #   INTERFACE  full name of the interface (example: Contoso.Data.IRecord)

`Store` names a workspace collection (its latest view, or solution when it has no overlays). Every
{{NAME}} placeholder must be declared under Parameters with an example, which `saved check` uses.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from . import artifacts, explore, traverse
from .result import RgError

_HEADER = re.compile(r"^#\s*(Title|Store|Description):\s*(.+?)\s*$")
_PARAM_LINE = re.compile(r"^#\s{2,}([A-Z][A-Z0-9_]*)\s+(.*?)\s*(?:\(example:\s*(.+?)\))?\s*$")


def folders(workspace: Path) -> tuple[Path, Path]:
    base = workspace.parent
    return base / "queries", base / "graphs"


def parse_header(text: str) -> dict[str, Any]:
    header: dict[str, Any] = {"title": "", "store": "", "description": "", "parameters": {}}
    in_params = False
    for line in text.splitlines():
        if not line.startswith("#"):
            if line.strip():
                break
            continue
        match = _HEADER.match(line)
        if match:
            header[match.group(1).lower()] = match.group(2)
            in_params = False
            continue
        if re.match(r"^#\s*Parameters:\s*$", line):
            in_params = True
            continue
        if in_params:
            param = _PARAM_LINE.match(line)
            if param:
                header["parameters"][param.group(1)] = {"description": param.group(2), "example": param.group(3) or ""}
    return header


def describe_query(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    header = parse_header(text)
    used = sorted(set(re.findall(r"\{\{([A-Z][A-Z0-9_]*)\}\}", text)))
    kind = "construct" if re.search(r"\bCONSTRUCT\b", text, re.IGNORECASE) else "select"
    problems = []
    if not header["title"]:
        problems.append("missing '# Title:' header")
    for name in used:
        if name not in header["parameters"]:
            problems.append(f"parameter {name} is not declared under '# Parameters:'")
        elif not header["parameters"][name]["example"]:
            problems.append(f"parameter {name} has no (example: ...) value")
    for name in header["parameters"]:
        if name not in used:
            problems.append(f"declared parameter {name} is not used")
    return {"path": str(path), "name": path.stem, "kind": kind, **header, "problems": problems}


def list_saved(workspace: Path) -> dict[str, Any]:
    queries_dir, graphs_dir = folders(workspace)
    queries = [describe_query(p) for p in sorted(queries_dir.glob("*.rq"))] if queries_dir.is_dir() else []
    graphs = []
    for path in sorted(graphs_dir.glob("*.graph.toml")) if graphs_dir.is_dir() else []:
        try:
            d = traverse.load_definition(path)
            graphs.append({"path": str(path), "name": path.name.removesuffix(".graph.toml"), "title": d.title,
                           "store": d.collection or d.manifest, "problems": []})
        except RgError as exc:
            graphs.append({"path": str(path), "name": path.name.removesuffix(".graph.toml"), "title": "", "store": "",
                           "problems": [p.message for p in exc.problems]})
    return {"type": "saved", "workspace": str(workspace), "queriesFolder": str(queries_dir), "graphsFolder": str(graphs_dir),
            "queries": queries, "graphs": graphs}


def check_saved(workspace: Path, data_root: str | None, out_dir: Path) -> dict[str, Any]:
    listing = list_saved(workspace)
    root = artifacts.artifact_root(data_root)
    results = []
    for q in listing["queries"]:
        entry: dict[str, Any] = {"path": q["path"], "kind": q["kind"]}
        if q["problems"]:
            entry.update(status="fail", problems=q["problems"])
        elif not q["store"]:
            entry.update(status="fail", problems=["missing '# Store:' header naming a workspace collection"])
        else:
            try:
                manifest = traverse.resolve_manifest(
                    traverse.Definition(Path(q["path"]), q["title"], workspace, q["store"], "", False, [], [], [], "none", [], True, 0, 0, ""), root)
                params = [f"{n}={v['example']}" for n, v in q["parameters"].items()]
                text = explore.read_query(None, q["path"], params)
                if q["kind"] == "construct":
                    result = explore.export(manifest, text, out_dir / f"{q['name']}.nt", union=False, logical=False)
                    entry.update(status="pass", triples=result["summary"]["triples"])
                else:
                    result = explore.query(manifest, text, union=False, limit=1)
                    entry.update(status="pass" if result["rowCount"] else "empty", rows=result["rowCount"])
            except RgError as exc:
                entry.update(status="fail", problems=[f"{p.code}: {p.message}" for p in exc.problems])
        results.append(entry)
    for g in listing["graphs"]:
        entry = {"path": g["path"], "kind": "graph"}
        if g["problems"]:
            entry.update(status="fail", problems=g["problems"])
        else:
            try:
                result = traverse.run(Path(g["path"]), data_root, out_dir, open_page=False)
                entry.update(status="pass", types=result["types"], truncated=result["truncated"])
            except RgError as exc:
                entry.update(status="fail", problems=[f"{p.code}: {p.message}" for p in exc.problems])
        results.append(entry)
    return {"type": "saved-check", "workspace": str(workspace), "passed": all(r["status"] != "fail" for r in results),
            "results": results}
