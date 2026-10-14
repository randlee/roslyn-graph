"""B0 experiment 2: declaration-scan accuracy against every component type of a store, and a graph's types."""

from __future__ import annotations

import argparse
import collections
import json
import random
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4] / "tools" / "rg"))
from roslyn_graph import oxigraph  # noqa: E402

from csharp_scan import declarations  # noqa: E402

DT = "http://dotnet.example/ontology/"
RG = "http://roslyn-graph.example/ontology/"
GENERATED = re.compile(r"(^|\.)<")


def compiler_generated(full: str) -> bool:
    """A name segment starting with '<' (display classes, state machines, <PrivateImplementationDetails>)."""
    return any(seg.startswith("<") for seg in _segments(full))


def _segments(full: str) -> list[str]:
    out, depth, cur = [], 0, ""
    for ch in full:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth -= 1
        if ch == "." and depth == 0:
            out.append(cur); cur = ""
        else:
            cur += ch
    out.append(cur)
    return out


def source_owner(full: str) -> str:
    """The outermost-to-innermost prefix of segments before the first compiler-generated segment."""
    segs = _segments(full)
    keep = []
    for s in segs:
        if s.startswith("<"):
            break
        keep.append(s)
    return ".".join(keep)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--store", required=True)
    ap.add_argument("--manifest", required=True)
    ap.add_argument("--compile-items", required=True)
    ap.add_argument("--graph-nt", required=True)
    ap.add_argument("--output", required=True)
    a = ap.parse_args()
    data_root = Path(a.manifest).parents[2]
    view = json.loads(Path(a.manifest).read_text(encoding="utf-8"))
    solution = json.loads((data_root / view["baseSolution"]["manifestPath"]).read_text(encoding="utf-8"))
    comps = solution["components"] + view["overlayComponents"]
    graph_to_comp = {c["graphIri"]: json.loads((data_root / c["manifestPath"]).read_text(encoding="utf-8")) for c in comps}
    items = {(r["repository"], r["project"]): r for r in json.loads(Path(a.compile_items).read_text(encoding="utf-8"))}

    rows = oxigraph.select(Path(a.store), f"PREFIX dt: <{DT}> SELECT ?g ?t ?full ?kind WHERE {{ GRAPH ?g {{ ?asm a dt:Assembly . "
                                           f"?t dt:definedInAssembly ?asm ; dt:accessibility ?acc ; dt:fullName ?full ; dt:typeKind ?kind . }} }}")
    logical = {r["t"]: r["l"] for r in oxigraph.select(Path(a.store), f"PREFIX rg: <{RG}> SELECT ?t ?l WHERE {{ GRAPH <{view['logicalGraphIri']}> {{ ?t rg:logicalType ?l }} }}")}

    started = time.monotonic()
    index: dict[tuple[str, str], dict[str, set[str]]] = {}
    scanned = 0
    for key, r in items.items():
        decl: dict[str, set[str]] = collections.defaultdict(set)
        repo = Path(next(m for m in graph_to_comp.values() if m["origin"]["id"] == key[0])["origin"]["repository"]).resolve()
        defines = set(r.get("defineConstants", []))
        for f in [f for f in r.get("files", []) if Path(f).resolve().is_relative_to(repo)]:
            p = Path(f)
            for name, _line in declarations(p.read_text(encoding="utf-8-sig", errors="replace"), defines):
                decl[name].add(p.resolve().relative_to(repo).as_posix())
            scanned += 1
        index[key] = decl
    scan_seconds = round(time.monotonic() - started, 1)

    results = []
    for row in rows:
        m = graph_to_comp.get(row["g"])
        if m is None:
            continue
        if m["origin"]["kind"] != "source":
            status, files = "nuget", []
        else:
            repo = Path(m["origin"]["repository"])
            project = m["build"]["project"]
            absolute = repo / project if m["identity"].startswith("assembly/v3|") else next(
                (c for c in (repo.parent / project, repo / project) if c.is_file()), repo / project)
            rel = absolute.resolve().relative_to(repo.resolve()).as_posix()
            decl = index.get((m["origin"]["id"], rel), {})
            name = row["full"]
            if compiler_generated(name):
                owner = source_owner(name)
                files = sorted(decl.get(owner, ())) if owner else []
                status = "compiler-generated" if files else "compiler-generated-unowned"
            else:
                files = sorted(decl.get(name, ()))
                status = "found" if files else "not-found"
        results.append({"iri": row["t"], "logical": logical.get(row["t"]), "fullName": row["full"], "kind": row["kind"],
                        "repository": m["origin"]["id"], "status": status, "files": files})

    graph_logical = set()
    for line in Path(a.graph_nt).read_text(encoding="utf-8").splitlines():
        if line.split(" ", 2)[1:2] == [f"<{DT}fullName>"]:
            graph_logical.add(line.split(" ", 1)[0][1:-1])
    in_graph = [r for r in results if (r["logical"] or r["iri"]) in graph_logical]

    random.seed(20261013)
    source_rows = [r for r in results if r["status"] != "nuget"]
    sample = random.sample(source_rows, min(300, len(source_rows)))

    def summary(rs):
        c = collections.Counter(r["status"] for r in rs)
        return {"types": len(rs), **dict(c), "multiFile": sum(1 for r in rs if len(r["files"]) > 1)}

    out = {"type": "scan-accuracy", "filesScanned": scanned, "scanSeconds": scan_seconds,
           "all": summary(results), "graph": summary(in_graph), "graphLogicalTypes": len(graph_logical), "sample300": summary(sample),
           "graphTypes": sorted(in_graph, key=lambda r: r["fullName"]),
           "notFoundAll": sorted({(r["repository"], r["fullName"], r["kind"]) for r in results if r["status"] in ("not-found", "compiler-generated-unowned")})}
    Path(a.output).write_text(json.dumps(out, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k not in ("notFoundAll", "graphTypes")}, indent=1))
    print("not-found (first 40):")
    for x in out["notFoundAll"][:40]:
        print("  ", x)
    return 0


if __name__ == "__main__":
    sys.exit(main())
