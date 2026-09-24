"""Create assembly, solution and view artifacts from a plan.

Every artifact is built in staging, validated there, published atomically, then validated again at
its published path. Failed staging directories are kept for inspection and reported.
"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from . import artifacts, extractor, oxigraph, validate
from .plan import Component, Plan
from .result import RgError
from .util import DT, RDF_TYPE, RG, assembly_iri, nt_iri, nt_literal, sha256_file, sha256_text


def _workspace_block(plan: Plan, profile: str) -> dict[str, Any]:
    return {"path": str(plan.workspace.path), "sha256": plan.workspace.sha256, "profile": profile, "collection": plan.collection.name}


def _fail_staging(staging: Path, error: RgError) -> RgError:
    for problem in error.problems:
        problem.context.setdefault("staging", str(staging))
        if "staging" not in problem.hint:
            problem.hint = (problem.hint + " The staging directory was kept for inspection.").strip()
    return error


def _require(checks: validate.Checks, what: str, staging: Path | None = None) -> None:
    if not checks.passed:
        failed = [c.to_json() for c in checks.items if not c.passed]
        raise RgError.of(
            "VALIDATION_FAILED",
            f"{what} failed {len(failed)} validation check(s).",
            "See reference/validation.md for each check ID." + (" The staging directory was kept for inspection." if staging else ""),
            failed=failed,
            staging=str(staging) if staging else None,
        )


def unique_nt_lines(path: Path) -> int:
    seen: set[str] = set()
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line and not line.startswith("#"):
                seen.add(line)
    return len(seen)


# ---- assemblies -----------------------------------------------------------------------------


def snapshot(plan: Plan, c: Component) -> dict[str, Any]:
    if c.exists:
        return {"artifactId": c.artifact_id, "path": artifacts.relative(plan.root, c.destination), "status": "reused"}
    staging = artifacts.new_staging(plan.root, c.expected_name)
    art = staging / "artifact"
    ttl, nt, store = staging / "graph.ttl", staging / "graph.nt", art / "store.oxigraph"
    try:
        warnings = extractor.extract(plan.extractor, c.assembly_path, ttl, c.search_dirs)
        oxigraph.convert(ttl, nt)
        ttl_unique = unique_nt_lines(nt)
        oxigraph.load(store, ttl)
        count = oxigraph.default_graph_count(store)
        rows = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?a ?name ?version ?token WHERE {{ ?a a dt:Assembly ; dt:name ?name ; dt:version ?version . OPTIONAL {{ ?a dt:publicKeyToken ?token }} }}")
        if len(rows) != 1:
            raise RgError.of("ASSEMBLY_NODE_COUNT", f"{c.assembly_path.name}: expected one dt:Assembly, found {len(rows)}.", rows=rows[:5])
        m = dict(c.manifest)
        m["assembly"] = dict(m["assembly"], name=rows[0]["name"], version=rows[0]["version"], publicKeyToken=rows[0].get("token", ""))
        m["extraction"] = {
            "extractorId": plan.extractor.id,
            "extractor": plan.extractor.to_json(),
            "searchDirs": [str(d) for d in c.search_dirs],
            "ttlSha256": sha256_file(ttl),
            "ttlUniqueTriples": ttl_unique,
            "warnings": warnings,
        }
        identity = artifacts.assembly_identity(m)
        if artifacts.artifact_id(identity) != c.artifact_id:
            raise RgError.of("IDENTITY_DRIFT", f"{c.assembly_path.name}: identity changed between planning and extraction.", identity=identity)
        manifest = {
            "schemaVersion": artifacts.MANIFEST_SCHEMA, "kind": "assembly", "artifactId": c.artifact_id, "identity": identity,
            "graphIri": artifacts.graph_iri("assembly", c.artifact_id), "createdUtc": artifacts.utc_now(),
            "workspace": _workspace_block(plan, c.profile), **m,
            "store": {"format": "oxigraph", "oxigraphVersion": plan.oxigraph_version, "tripleCount": count},
        }
        checks = validate.assembly(art, manifest, published=False)
        _require(checks, f"Assembly {c.expected_name} (staging)", staging)
        manifest["validation"] = {"staging": checks.to_json()}
        artifacts.write_manifest(art, manifest)
        ttl.unlink()
        nt.unlink()
        published = artifacts.publish(plan.root, staging, c.destination, c.artifact_id)
    except RgError as exc:
        raise _fail_staging(staging, exc)
    _require(validate.assembly(c.destination, artifacts.read_manifest(c.destination / "manifest.json")), f"Assembly {c.expected_name} (published)")
    c.exists = True
    return {"artifactId": c.artifact_id, "path": artifacts.relative(plan.root, c.destination), "status": "created" if published else "reused", "triples": count}


def _component_entry(plan: Plan, c: Component) -> dict[str, Any]:
    m = artifacts.read_manifest(c.destination / "manifest.json")
    return {
        "artifactId": m["artifactId"], "graphIri": m["graphIri"], "profile": c.profile,
        "manifestPath": artifacts.relative(plan.root, c.destination / "manifest.json"),
        "origin": m["origin"], "package": m.get("package"),
        "assembly": {k: m["assembly"][k] for k in ("name", "version", "publicKeyToken", "sha256")},
        "tripleCount": m["store"]["tripleCount"],
    }


def _copy_component(component_store: Path, target: Path, graph: str, scratch: Path) -> None:
    dump = scratch / "component.nt"
    oxigraph.dump(component_store, dump, "nt", "default")
    oxigraph.load(target, dump, graph)
    dump.unlink()


# ---- solution -------------------------------------------------------------------------------


def compose(plan: Plan) -> dict[str, Any]:
    s = plan.solution
    destination = plan.root / s["destination"]
    if s["exists"]:
        return {"artifactId": s["artifactId"], "path": s["destination"], "status": "reused"}
    staging = artifacts.new_staging(plan.root, s["manifest"]["solution"]["name"])
    art = staging / "artifact"
    store = art / "store.oxigraph"
    try:
        components = [_component_entry(plan, c) for c in plan.base_components()]
        solution_iri = artifacts.graph_iri("solution", s["artifactId"])
        metadata_graph = f"{solution_iri}:metadata"
        for c in plan.base_components():
            _copy_component(c.destination / "store.oxigraph", store, artifacts.graph_iri("assembly", c.artifact_id), staging)
        fields = s["manifest"]["solution"]
        lines = [f"{nt_iri(solution_iri)} {nt_iri(RDF_TYPE)} {nt_iri(RG + 'SolutionBuild')} ."]
        for key, predicate in [("name", "name"), ("profile", "profile"), ("path", "solutionPath"), ("repository", "repository"),
                               ("branch", "branch"), ("commit", "commit"), ("fingerprint", "buildFingerprint"),
                               ("targetFramework", "targetFramework"), ("configuration", "configuration"), ("platform", "platform")]:
            if fields.get(key):
                lines.append(f"{nt_iri(solution_iri)} {nt_iri(RG + predicate)} {nt_literal(fields[key])} .")
        for entry in components:
            lines.append(f"{nt_iri(solution_iri)} {nt_iri(RG + 'includesGraph')} {nt_iri(entry['graphIri'])} .")
            lines.append(f"{nt_iri(solution_iri)} {nt_iri(RG + 'includesArtifact')} {nt_literal(entry['artifactId'])} .")
        metadata = staging / "metadata.nt"
        metadata.write_text("\n".join(lines) + "\n", encoding="utf-8")
        oxigraph.load(store, metadata, metadata_graph)
        oxigraph.optimize(store)
        graphs = oxigraph.graph_counts(store)
        manifest = {
            "schemaVersion": artifacts.MANIFEST_SCHEMA, "kind": "solution", "artifactId": s["artifactId"],
            "identity": artifacts.solution_identity(s["manifest"]), "solutionIri": solution_iri, "metadataGraphIri": metadata_graph,
            "createdUtc": artifacts.utc_now(), "workspace": _workspace_block(plan, plan.collection.base),
            "solution": fields, "components": components,
            "store": {"format": "oxigraph", "oxigraphVersion": plan.oxigraph_version, "tripleCount": sum(graphs.values()),
                      "namedGraphCount": len(graphs), "graphs": graphs},
        }
        checks = validate.solution(art, manifest, plan.root, published=False)
        _require(checks, "Solution store (staging)", staging)
        manifest["validation"] = {"staging": checks.to_json()}
        artifacts.write_manifest(art, manifest)
        metadata.unlink()
        created = artifacts.publish(plan.root, staging, destination, s["artifactId"])
    except RgError as exc:
        raise _fail_staging(staging, exc)
    _require(validate.solution(destination, artifacts.read_manifest(destination / "manifest.json"), plan.root, deep=True), "Solution store (published)")
    s["exists"] = True
    return {"artifactId": s["artifactId"], "path": s["destination"], "status": "created" if created else "reused",
            "triples": manifest["store"]["tripleCount"], "graphs": len(graphs)}


# ---- logical-type view ----------------------------------------------------------------------


def logical_iri(assembly_name: str, full_name: str) -> str:
    return f"urn:roslyn-graph:logical-type:{sha256_text(assembly_name + '|' + full_name)[:32]}"


def projection_lines(view_iri: str, solution_iri: str, policy: str, rows_by_component: list[tuple[str, list[dict[str, str]]]]) -> tuple[list[str], int, int]:
    """Build the logical-type graph. rows: (assemblyName, [{type, fullName, name}])."""
    lines = [
        f"{nt_iri(view_iri)} {nt_iri(RDF_TYPE)} {nt_iri(RG + 'LogicalTypeView')} .",
        f"{nt_iri(view_iri)} {nt_iri(RG + 'policy')} {nt_literal(policy)} .",
        f"{nt_iri(view_iri)} {nt_iri(RG + 'baseSolution')} {nt_iri(solution_iri)} .",
    ]
    physical: dict[str, str] = {}
    logical: set[str] = set()
    for assembly_name, rows in rows_by_component:
        for row in rows:
            if row["type"] in physical:
                raise RgError.of(
                    "PHYSICAL_IDENTITY_AMBIGUOUS",
                    f"{row['type']} is defined by more than one component ({physical[row['type']]} and {assembly_name}).",
                    "Two builds share an assembly name and version, so their type IRIs collide. Bump the assembly version of one of them.",
                )
            physical[row["type"]] = assembly_name
            target = logical_iri(assembly_name, row["fullName"])
            lines.append(f"{nt_iri(row['type'])} {nt_iri(RG + 'logicalType')} {nt_iri(target)} .")
            if target not in logical:
                logical.add(target)
                lines += [
                    f"{nt_iri(target)} {nt_iri(RDF_TYPE)} {nt_iri(RG + 'LogicalType')} .",
                    f"{nt_iri(target)} {nt_iri(RG + 'assemblyName')} {nt_literal(assembly_name)} .",
                    f"{nt_iri(target)} {nt_iri(DT + 'fullName')} {nt_literal(row['fullName'])} .",
                    f"{nt_iri(target)} {nt_iri(DT + 'name')} {nt_literal(row.get('name') or row['fullName'].rsplit('.', 1)[-1])} .",
                ]
    return lines, len(physical), len(logical)


def build_view(plan: Plan) -> dict[str, Any] | None:
    v = plan.view
    if v is None:
        return None
    destination = plan.root / v["destination"]
    if v["exists"]:
        return {"artifactId": v["artifactId"], "path": v["destination"], "status": "reused"}
    base_dir = plan.root / plan.solution["destination"]
    base = artifacts.read_manifest(base_dir / "manifest.json")
    staging = artifacts.new_staging(plan.root, "view")
    art = staging / "artifact"
    store = art / "store.oxigraph"
    try:
        dump = staging / "base.nq"
        oxigraph.dump(base_dir / "store.oxigraph", dump, "nq")
        oxigraph.load(store, dump)
        dump.unlink()
        overlays = [_component_entry(plan, c) for c in plan.overlay_components()]
        for c in plan.overlay_components():
            _copy_component(c.destination / "store.oxigraph", store, artifacts.graph_iri("assembly", c.artifact_id), staging)
        policy_assemblies = set(v["manifest"]["view"]["policyAssemblies"])
        projected = [e for e in base["components"] + overlays if e["assembly"]["name"] in policy_assemblies]
        projected.sort(key=lambda e: e["artifactId"])
        rows_by_component = []
        for entry in projected:
            asm = assembly_iri(entry["assembly"]["name"], entry["assembly"]["version"])
            rows = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?type ?fullName ?name WHERE {{ GRAPH <{entry['graphIri']}> {{ "
                                          f"?type a dt:Type ; dt:fullName ?fullName ; dt:definedInAssembly <{asm}> . OPTIONAL {{ ?type dt:name ?name }} }} }}")
            rows_by_component.append((entry["assembly"]["name"], sorted(rows, key=lambda r: r["type"])))
        view_iri = artifacts.graph_iri("view", v["artifactId"])
        logical_graph = f"{view_iri}:logical-types"
        lines, links, logical_count = projection_lines(view_iri, base["solutionIri"], plan.collection.policy, rows_by_component)
        mapping = staging / "logical-types.nt"
        mapping.write_text("\n".join(lines) + "\n", encoding="utf-8")
        oxigraph.load(store, mapping, logical_graph)
        mapping.unlink()
        oxigraph.optimize(store)
        graphs = oxigraph.graph_counts(store)
        manifest = {
            "schemaVersion": artifacts.MANIFEST_SCHEMA, "kind": "view", "artifactId": v["artifactId"],
            "identity": artifacts.view_identity(v["manifest"]), "viewIri": view_iri, "logicalGraphIri": logical_graph,
            "createdUtc": artifacts.utc_now(), "workspace": _workspace_block(plan, plan.collection.base),
            "view": v["manifest"]["view"],
            "baseSolution": {"artifactId": base["artifactId"], "manifestPath": artifacts.relative(plan.root, base_dir / "manifest.json"),
                             "solutionIri": base["solutionIri"], "graphs": base["store"]["graphs"]},
            "overlayComponents": overlays,
            "projection": {"physicalTypeLinks": links, "logicalTypes": logical_count,
                           "projectedComponents": [e["artifactId"] for e in projected]},
            "store": {"format": "oxigraph", "oxigraphVersion": plan.oxigraph_version, "tripleCount": sum(graphs.values()),
                      "namedGraphCount": len(graphs), "graphs": graphs},
        }
        checks = validate.view(art, manifest, plan.root, published=False)
        _require(checks, "Logical-type view (staging)", staging)
        manifest["validation"] = {"staging": checks.to_json()}
        artifacts.write_manifest(art, manifest)
        created = artifacts.publish(plan.root, staging, destination, v["artifactId"])
    except RgError as exc:
        raise _fail_staging(staging, exc)
    _require(validate.view(destination, artifacts.read_manifest(destination / "manifest.json"), plan.root, deep=True), "Logical-type view (published)")
    v["exists"] = True
    return {"artifactId": v["artifactId"], "path": v["destination"], "status": "created" if created else "reused",
            "triples": manifest["store"]["tripleCount"], "graphs": len(graphs), "physicalTypeLinks": links, "logicalTypes": logical_count}


def run_all(plan: Plan, progress=None) -> dict[str, Any]:
    results = []
    for index, component in enumerate(plan.components, 1):
        if progress:
            progress(f"[{index}/{len(plan.components)}] {component.expected_name}")
        results.append(snapshot(plan, component) | {"name": component.expected_name, "profile": component.profile, "role": component.role})
    if progress:
        progress("composing solution store")
    solution = compose(plan)
    if progress and plan.view:
        progress("building logical-type view")
    view_result = build_view(plan)
    return {"components": results, "solution": solution, "view": view_result}


def remove_tree(path: Path) -> None:
    shutil.rmtree(path)
