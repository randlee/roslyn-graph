#!/usr/bin/env python3
"""Roslyn Graph command line used by the roslyn-graph plugin skills.

Every command prints exactly one JSON object to stdout. Its "type" field discriminates the result:
a command-specific success type, or "error" with a list of {code, message, hint, context}.
Progress goes to stderr. Exit status: 0 success, 1 error or failed validation.

Requires Python 3.11+. Run `python rg.py <command> --help` for arguments.
"""

from __future__ import annotations

import argparse
import sys
import traceback
import webbrowser
from pathlib import Path

if sys.version_info < (3, 11):
    sys.stdout.write('{"type": "error", "errors": [{"code": "PYTHON_TOO_OLD", "message": "rg.py needs Python 3.11 or newer.", '
                     '"hint": "Install Python 3.11+ and run it with that interpreter.", "context": {}}]}\n')
    sys.exit(1)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from roslyn_graph import artifacts, build, config, discover, explore, maintain, ontology, plan, saved, traverse, validate  # noqa: E402
from roslyn_graph.result import Problem, RgError, emit, error_payload  # noqa: E402


def _progress(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def cmd_discover(a) -> dict:
    return discover.solution(Path(a.solution), Path(a.root) if a.root else None, a.tfm)


def cmd_check_workspace(a) -> dict:
    ws = config.load(Path(a.workspace))
    return {
        "type": "workspace",
        "path": str(ws.path),
        "sha256": ws.sha256,
        "profiles": {n: {"kind": p.kind} for n, p in ws.profiles.items()},
        "collections": {n: {"base": c.base, "overlays": c.overlays, "policy": c.policy} for n, c in ws.collections.items()},
    }


def cmd_plan(a) -> dict:
    return plan.build_plan(config.load(Path(a.workspace)), a.collection, a.data_root, a.allow_dirty).to_json()


def cmd_generate(a) -> dict:
    ws = config.load(Path(a.workspace))
    p = plan.build_plan(ws, a.collection, a.data_root, a.allow_dirty)
    _progress(f"plan: {len(p.components)} components, {sum(not c.exists for c in p.components)} new")
    results = build.run_all(p, _progress)
    _progress("re-planning to confirm the run is idempotent")
    again = plan.build_plan(config.load(Path(a.workspace)), a.collection, a.data_root, a.allow_dirty)
    pending = [c.expected_name for c in again.components if not c.exists]
    if pending or not again.solution["exists"] or (again.view and not again.view["exists"]):
        raise RgError.of("NOT_IDEMPOTENT", "Re-planning after generation still finds work to do.",
                         "Inputs changed during the run (for example a rebuild); run generate again.", pending=pending)
    solution_manifest = artifacts.read_manifest(p.root / p.solution["destination"] / "manifest.json")
    prior = maintain.previous(p.root, "solution", ws.collections[a.collection].base, p.solution["artifactId"])
    pins = [{"profile": pkg.profile, "sha256": pkg.nupkg_sha256} for pkg in p.packages if not ws.profiles[pkg.profile].sha256]
    return {
        "type": "generate",
        "collection": a.collection,
        "artifactRoot": str(p.root),
        "summary": {
            "components": len(results["components"]),
            "created": sum(r["status"] == "created" for r in results["components"]),
            "reused": sum(r["status"] == "reused" for r in results["components"]),
            "solution": results["solution"],
            "view": results["view"],
            "idempotent": True,
        },
        "solutionManifest": str(p.root / p.solution["destination"] / "manifest.json"),
        "viewManifest": str(p.root / p.view["destination"] / "manifest.json") if p.view else None,
        "diffFromPrevious": maintain.compare(prior[1], solution_manifest) if prior else None,
        "pinsToRecord": pins,
        "warnings": p.warnings,
        "components": results["components"],
    }


def cmd_validate(a) -> dict:
    root = artifacts.artifact_root(a.data_root)
    targets = [Path(m) for m in a.manifest] if a.manifest else [
        path for path, m in artifacts.iter_manifests(root) if artifacts.manifest_kind(m) in {"assembly", "solution", "view"}
    ]
    reports = [validate.validate_path(t, root, deep=a.deep) for t in targets]
    return {"type": "validation", "passed": all(r["passed"] for r in reports), "count": len(reports),
            "failed": [r for r in reports if not r["passed"]], "reports": reports if a.verbose else []}


def cmd_inventory(a) -> dict:
    inv = maintain.inventory(artifacts.artifact_root(a.data_root))
    inv["cleanupCandidates"] = [{"path": e["path"], "kind": e["kind"], "status": e["status"]} for e in maintain.cleanup_candidates(inv)]
    return inv


def cmd_diff(a) -> dict:
    return maintain.compare(artifacts.read_manifest(Path(a.old)), artifacts.read_manifest(Path(a.new)))


def cmd_remove(a) -> dict:
    return maintain.remove(artifacts.artifact_root(a.data_root), a.path, a.confirm)


def cmd_query(a) -> dict:
    return explore.query(Path(a.manifest), explore.read_query(a.query, a.query_file, a.param), union=a.union, limit=a.limit, timeout=a.timeout)


def cmd_export(a) -> dict:
    return explore.export(Path(a.manifest), explore.read_query(a.query, a.query_file, a.param), Path(a.output), union=a.union, logical=a.logical, unbounded=a.unbounded, timeout=a.timeout)


def cmd_render(a) -> dict:
    result = explore.render(a.visualizer, Path(a.data), Path(a.output), a.title or Path(a.output).stem)
    if a.open:
        webbrowser.open(Path(a.output).resolve().as_uri())
        result["opened"] = True
    return result


def cmd_graph(a) -> dict:
    return traverse.run(Path(a.definition), a.data_root, Path(a.output_dir) if a.output_dir else None, a.open)


def cmd_saved(a) -> dict:
    workspace = Path(a.workspace).resolve()
    if a.action == "list":
        return saved.list_saved(workspace)
    out = Path(a.output_dir) if a.output_dir else workspace.parent / "graphs" / "out" / "check"
    return saved.check_saved(workspace, a.data_root, out)


def cmd_visualizers(a) -> dict:
    return {"type": "visualizers", "visualizers": explore.registry()}


def cmd_ontology_doc(a) -> dict:
    text = ontology.markdown()
    target = Path(a.output)
    if a.check:
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
        if current.replace("\r\n", "\n") != text:
            raise RgError.of("ONTOLOGY_DOC_STALE", f"{target} does not match the ontology.", "Run: python scripts/rg.py ontology-doc")
        return {"type": "ontology-doc", "output": str(target), "upToDate": True}
    target.write_text(text, encoding="utf-8", newline="\n")
    return {"type": "ontology-doc", "output": str(target), "written": True}


class JsonArgumentParser(argparse.ArgumentParser):
    """Usage errors become JSON errors too, so callers only ever parse one shape."""

    def error(self, message: str):  # type: ignore[override]
        raise RgError.of("USAGE", f"{self.prog}: {message}", "Run: python rg.py " + (self.prog.split()[-1] + " " if " " in self.prog else "") + "--help")


def parser() -> argparse.ArgumentParser:
    root = JsonArgumentParser(prog="rg.py", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = root.add_subparsers(dest="command", required=True, parser_class=JsonArgumentParser)

    def add(name: str, fn, help_: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, help=help_, description=help_)
        p.set_defaults(fn=fn)
        return p

    def data_root(p: argparse.ArgumentParser) -> None:
        p.add_argument("--data-root", help="Parent of .roslyn-graph; defaults to ROSLYN_GRAPH_DATA_ROOT.")

    p = add("discover", cmd_discover, "Inspect a built .sln and suggest workspace.toml values (design-toml).")
    p.add_argument("--solution", required=True)
    p.add_argument("--root", help="Profile root; defaults to the common ancestor of the solution and its projects.")
    p.add_argument("--tfm", help="Target framework used by the build.")

    p = add("check-workspace", cmd_check_workspace, "Validate workspace.toml without touching any build output.")
    p.add_argument("--workspace", required=True)

    for name, fn, help_ in [("plan", cmd_plan, "Resolve a collection into an exact plan; writes only the NuGet restore cache."),
                            ("generate", cmd_generate, "Create and validate every artifact of a collection; reuses what already exists.")]:
        p = add(name, fn, help_)
        p.add_argument("--workspace", required=True)
        p.add_argument("--collection", required=True)
        p.add_argument("--allow-dirty", action="store_true", help="Snapshot repositories with uncommitted changes (recorded in the identity).")
        data_root(p)

    p = add("validate", cmd_validate, "Validate published artifacts (all of them when no --manifest is given).")
    p.add_argument("--manifest", action="append")
    p.add_argument("--deep", action="store_true", help="Also validate every component of solutions and views.")
    p.add_argument("--verbose", action="store_true", help="Include passing reports.")
    data_root(p)

    p = add("inventory", cmd_inventory, "List artifacts with status (latest, in-use, superseded, unreferenced, legacy).")
    data_root(p)

    p = add("diff", cmd_diff, "Compare two solution manifests.")
    p.add_argument("--old", required=True)
    p.add_argument("--new", required=True)

    p = add("remove", cmd_remove, "Remove one unreferenced artifact directory. Without --confirm it only reports.")
    p.add_argument("--path", required=True, help="Artifact directory or manifest.json, absolute or relative to the artifact root.")
    p.add_argument("--confirm", action="store_true")
    data_root(p)

    for name, fn, help_ in [("query", cmd_query, "Run a SELECT query against a solution or view store."),
                            ("export", cmd_export, "Run a CONSTRUCT query and write a viewer-ready N-Triples subgraph.")]:
        p = add(name, fn, help_)
        p.add_argument("--manifest", required=True)
        p.add_argument("--query")
        p.add_argument("--query-file")
        p.add_argument("--param", action="append", default=[], help="NAME=VALUE for a {{NAME}} placeholder in the query; repeatable.")
        p.add_argument("--timeout", type=int, default=explore.QUERY_TIMEOUT, help="Seconds before the query is stopped (default %(default)s).")
        p.add_argument("--union", action="store_true",
                       help="Treat the union of all named graphs as the default graph (slow on large stores; prefer GRAPH ?g).")
        if name == "query":
            p.add_argument("--limit", type=int, default=explore.MAX_ROWS)
        else:
            p.add_argument("--output", required=True)
            p.add_argument("--logical", action="store_true", help="Collapse physical type versions to logical types (views only).")
            p.add_argument("--unbounded", action="store_true", help="Deliberate full export: no timeout and no triple cap.")

    p = add("render", cmd_render, "Build a self-contained page for a registered visualizer.")
    p.add_argument("--visualizer", default="explorer")
    p.add_argument("--data", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--title")
    p.add_argument("--open", action="store_true")

    p = add("graph", cmd_graph, "Build and render a saved graph definition (*.graph.toml): seeds, implementations, recursive references.")
    p.add_argument("--definition", required=True)
    p.add_argument("--output-dir", help="Defaults to an out/ folder next to the definition.")
    p.add_argument("--open", action="store_true")
    data_root(p)

    p = add("saved", cmd_saved, "List or check the workspace's saved queries (.roslyn-graph/queries/*.rq) and graphs (graphs/*.graph.toml).")
    p.add_argument("action", choices=["list", "check"])
    p.add_argument("--workspace", required=True, help="workspace.toml; saved files live in queries/ and graphs/ beside it.")
    p.add_argument("--output-dir", help="check: where test outputs go (default graphs/out/check).")
    data_root(p)

    add("visualizers", cmd_visualizers, "List registered visualizers and their input contracts.")

    p = add("ontology-doc", cmd_ontology_doc, "Regenerate the ontology reference from the plugin ontology files.")
    p.add_argument("--output", default=str(explore.PLUGIN_ROOT / "skills" / "roslyn-graph-explore" / "reference" / "ontology.md"))
    p.add_argument("--check", action="store_true")
    return root


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    try:
        args = parser().parse_args(argv)
        payload = args.fn(args)
    except RgError as exc:
        emit(error_payload(exc))
        return 1
    except Exception as exc:  # noqa: BLE001 - every failure must still be one JSON object
        emit(error_payload(RgError(Problem("INTERNAL", f"{type(exc).__name__}: {exc}", "This is a bug in rg.py; report it with the context.",
                                           {"traceback": traceback.format_exc().splitlines()[-12:]}))))
        return 1
    emit(payload)
    return 0 if payload.get("passed", True) else 1  # validation, saved-check


if __name__ == "__main__":
    sys.exit(main())
