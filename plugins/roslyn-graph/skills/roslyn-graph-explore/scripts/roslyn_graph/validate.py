"""Artifact validation. The same checks run in staging before publication and on the published path.

Each check has a stable ID documented in reference/validation.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import artifacts, oxigraph
from .result import RgError
from .util import DT, OWL_SAME_AS, RG, assembly_iri


@dataclass
class Check:
    id: str
    name: str
    passed: bool
    detail: str = ""

    def to_json(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "status": "pass" if self.passed else "fail", "detail": self.detail}


class Checks:
    def __init__(self) -> None:
        self.items: list[Check] = []

    def add(self, id_: str, name: str, passed: bool, detail: str = "") -> bool:
        self.items.append(Check(id_, name, bool(passed), detail))
        return bool(passed)

    def run(self, id_: str, name: str, body: Callable[[], tuple[bool, str]]) -> bool:
        try:
            passed, detail = body()
        except RgError as exc:
            passed, detail = False, str(exc)
        return self.add(id_, name, passed, detail)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.items)

    def to_json(self) -> list[dict[str, Any]]:
        return [c.to_json() for c in self.items]


REQUIRED = {
    "assembly": ["artifactId", "identity", "graphIri", "createdUtc", "origin", "assembly", "extraction", "store"],
    "solution": ["artifactId", "identity", "solutionIri", "metadataGraphIri", "solution", "components", "store"],
    "view": ["artifactId", "identity", "viewIri", "logicalGraphIri", "view", "baseSolution", "overlayComponents", "projection", "store"],
}


def _common(checks: Checks, directory: Path, m: dict[str, Any], kind: str, published: bool) -> None:
    missing = [k for k in REQUIRED[kind] if k not in m]
    checks.add("M1", "manifest has every required field", m.get("schemaVersion") == artifacts.MANIFEST_SCHEMA and not missing,
               f"schemaVersion={m.get('schemaVersion')} missing={missing}")
    if missing:
        return
    recomputed = artifacts.IDENTITY[kind](m)
    checks.add("M2", "artifact ID recomputes from manifest fields",
               recomputed == m["identity"] and artifacts.artifact_id(recomputed) == m["artifactId"],
               "" if recomputed == m["identity"] else f"recomputed identity {recomputed!r}")
    if published:
        checks.add("M3", "directory name is a prefix of the artifact ID", m["artifactId"].startswith(directory.name), directory.name)
    checks.add("P1", "store path is short enough to reopen on Windows",
               len(str(directory / "store.oxigraph" / "CURRENT")) <= artifacts.MAX_CURRENT_PATH)


def assembly(directory: Path, m: dict[str, Any], published: bool = True) -> Checks:
    checks = Checks()
    _common(checks, directory, m, "assembly", published)
    store = directory / "store.oxigraph"
    if not checks.run("S1", "store reopens and holds the recorded triple count",
                      lambda: _eq(oxigraph.default_graph_count(store), m["store"]["tripleCount"])):
        return checks
    checks.add("S2", "extracted Turtle and store hold the same unique triples",
               m["extraction"].get("ttlUniqueTriples") == m["store"]["tripleCount"],
               f"ttl={m['extraction'].get('ttlUniqueTriples')} store={m['store']['tripleCount']}")
    checks.run("S3", "store has no named graphs", lambda: _eq(len(oxigraph.graph_counts(store)), 0))
    iri = assembly_iri(m["assembly"]["name"], m["assembly"]["version"])
    checks.run("S4", "exactly one dt:Assembly, matching the manifest", lambda: _assembly_node(store, iri))
    checks.add("S5", "assembly name matches the expected output name",
               m["assembly"]["name"] == m["assembly"].get("expectedName", m["assembly"]["name"]),
               f"{m['assembly']['name']} vs {m['assembly'].get('expectedName')}")
    checks.run("S6", "the assembly defines at least one type", lambda: _positive(
        oxigraph.scalar(store, f"PREFIX dt: <{DT}> SELECT (COUNT(DISTINCT ?t) AS ?n) WHERE {{ ?t dt:definedInAssembly <{iri}> }}")))
    checks.run("S7", "every type has exactly one full name", lambda: _eq(oxigraph.scalar(
        store, f"PREFIX dt: <{DT}> SELECT (COUNT(*) AS ?n) WHERE {{ {{ SELECT ?t WHERE {{ ?t dt:fullName ?f }} GROUP BY ?t HAVING (COUNT(DISTINCT ?f) > 1) }} }}"), 0))
    checks.run("S8", "every own type is fully extracted (one full name, kind and accessibility)", lambda: _eq(oxigraph.scalar(
        store, f"""PREFIX dt: <{DT}> SELECT (COUNT(*) AS ?n) WHERE {{
          {{ SELECT ?t (COUNT(DISTINCT ?f) AS ?fc) (COUNT(DISTINCT ?k) AS ?kc) (COUNT(DISTINCT ?a) AS ?ac) WHERE {{
               ?t dt:definedInAssembly <{iri}> . FILTER NOT EXISTS {{ ?t dt:genericDefinition ?d }}
               OPTIONAL {{ ?t dt:fullName ?f }} OPTIONAL {{ ?t dt:typeKind ?k }} OPTIONAL {{ ?t dt:accessibility ?a }}
             }} GROUP BY ?t }}
          FILTER(?fc != 1 || ?kc != 1 || ?ac != 1) }}"""), 0))
    return checks


def solution(directory: Path, m: dict[str, Any], root: Path, published: bool = True, deep: bool = False) -> Checks:
    checks = Checks()
    _common(checks, directory, m, "solution", published)
    store = directory / "store.oxigraph"
    expected = {c["graphIri"]: c["tripleCount"] for c in m["components"]}
    if not checks.run("S1", "store reopens", lambda: (True, f"{len(graphs := oxigraph.graph_counts(store))} graphs")):
        return checks
    graphs = oxigraph.graph_counts(store)
    checks.add("G1", "named graphs are exactly the components plus metadata",
               set(graphs) == set(expected) | {m["metadataGraphIri"]}, _set_diff(set(graphs), set(expected) | {m["metadataGraphIri"]}))
    wrong = {g: (graphs.get(g), n) for g, n in expected.items() if graphs.get(g) != n}
    checks.add("G2", "each component graph holds its component's triple count", not wrong, f"mismatches={dict(list(wrong.items())[:5])}")
    checks.run("G3", "default graph is empty", lambda: _eq(oxigraph.default_graph_count(store), 0))
    checks.add("G4", "store triple count matches the manifest", sum(graphs.values()) == m["store"]["tripleCount"])
    meta = oxigraph.select(store, f"PREFIX rg: <{RG}> SELECT ?g ?a WHERE {{ GRAPH <{m['metadataGraphIri']}> {{ "
                                  f"{{ <{m['solutionIri']}> rg:includesGraph ?g }} UNION {{ <{m['solutionIri']}> rg:includesArtifact ?a }} }} }}")
    listed_graphs = {r["g"] for r in meta if "g" in r}
    listed_ids = {r["a"] for r in meta if "a" in r}
    checks.add("G5", "metadata membership equals the component list",
               listed_graphs == set(expected) and listed_ids == {c["artifactId"] for c in m["components"]},
               _set_diff(listed_graphs, set(expected)))
    if deep:
        _deep_components(checks, root, m["components"])
    return checks


def view(directory: Path, m: dict[str, Any], root: Path, published: bool = True, deep: bool = False) -> Checks:
    checks = Checks()
    _common(checks, directory, m, "view", published)
    store = directory / "store.oxigraph"
    if not checks.run("S1", "store reopens", lambda: (True, "")):
        return checks
    graphs = oxigraph.graph_counts(store)
    base_graphs = m["baseSolution"]["graphs"]
    overlay = {c["graphIri"]: c["tripleCount"] for c in m["overlayComponents"]}
    expected = set(base_graphs) | set(overlay) | {m["logicalGraphIri"]}
    checks.add("V1", "named graphs are base + overlays + logical projection", set(graphs) == expected, _set_diff(set(graphs), expected))
    wrong = {g: (graphs.get(g), n) for g, n in (base_graphs | overlay).items() if graphs.get(g) != n}
    checks.add("V2", "base and overlay graphs are unchanged copies", not wrong, f"mismatches={dict(list(wrong.items())[:5])}")
    checks.run("V3", "default graph is empty", lambda: _eq(oxigraph.default_graph_count(store), 0))
    checks.run("V4", "no owl:sameAs anywhere", lambda: _eq(oxigraph.scalar(
        store, f"SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH ?g {{ ?s <{OWL_SAME_AS}> ?o }} }}"), 0))
    lg = m["logicalGraphIri"]
    checks.run("V5", "every projected physical type has exactly one logical type", lambda: _eq(oxigraph.scalar(
        store, f"PREFIX rg: <{RG}> SELECT (COUNT(*) AS ?n) WHERE {{ {{ SELECT ?t (COUNT(?l) AS ?c) WHERE {{ GRAPH <{lg}> {{ ?t rg:logicalType ?l }} }} GROUP BY ?t }} FILTER(?c != 1) }}"), 0))
    checks.run("V6", "projection counts match the manifest", lambda: _eq(
        (oxigraph.scalar(store, f"PREFIX rg: <{RG}> SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{lg}> {{ ?t rg:logicalType ?l }} }}"),
         oxigraph.scalar(store, f"PREFIX rg: <{RG}> SELECT (COUNT(*) AS ?n) WHERE {{ GRAPH <{lg}> {{ ?l a rg:LogicalType }} }}")),
        (m["projection"]["physicalTypeLinks"], m["projection"]["logicalTypes"])))
    checks.add("V7", "store triple count matches the manifest", sum(graphs.values()) == m["store"]["tripleCount"])
    checks.run("V9", "every own type of every projected component is linked", lambda: _projection_domain(store, lg, m["projection"].get("domain")))
    if deep:
        base_manifest = root / m["baseSolution"]["manifestPath"]
        checks.add("V8", "base solution manifest exists", base_manifest.is_file(), str(base_manifest))
        _deep_components(checks, root, m["overlayComponents"])
    return checks


def validate_path(manifest_path: Path, root: Path, deep: bool = False) -> dict[str, Any]:
    m = artifacts.read_manifest(manifest_path)
    kind = artifacts.manifest_kind(m)
    directory = manifest_path.parent
    if kind == "assembly":
        checks = assembly(directory, m)
    elif kind == "solution":
        checks = solution(directory, m, root, deep=deep)
    elif kind == "view":
        checks = view(directory, m, root, deep=deep)
    else:
        raise RgError.of(
            "MANIFEST_UNSUPPORTED",
            f"{manifest_path} is a {kind} manifest (schemaVersion {m.get('schemaVersion')}).",
            "Legacy artifacts predate this skill and cannot be validated; regenerate them with generate-initial.",
        )
    return {"manifest": str(manifest_path), "kind": kind, "artifactId": m.get("artifactId"), "passed": checks.passed, "checks": checks.to_json()}


def _deep_components(checks: Checks, root: Path, components: list[dict[str, Any]]) -> None:
    failed = []
    for component in components:
        path = root / component["manifestPath"]
        result = assembly(path.parent, artifacts.read_manifest(path)) if path.is_file() else None
        if result is None or not result.passed:
            failed.append(component["manifestPath"])
    checks.add("D1", "every component artifact validates", not failed, f"failed={failed[:10]}")


def _projection_domain(store: Path, logical_graph: str, domain: list[dict[str, Any]] | None) -> tuple[bool, str]:
    """Count each projected component's own types in the store (independently of the manifest) and require
    that the manifest recorded the same number and that every one of them carries a logical link."""
    if not domain:
        return False, "manifest has no projection.domain (created before projection v2); regenerate the view"
    wrong = []
    for entry in domain:
        asm = assembly_iri(entry["assembly"], entry["version"])
        own = f"GRAPH <{entry['graphIri']}> {{ ?t dt:definedInAssembly <{asm}> ; dt:accessibility ?a }}"
        total = oxigraph.scalar(store, f"PREFIX dt: <{DT}> SELECT (COUNT(DISTINCT ?t) AS ?n) WHERE {{ {own} }}")
        linked = oxigraph.scalar(store, f"PREFIX dt: <{DT}> PREFIX rg: <{RG}> SELECT (COUNT(DISTINCT ?t) AS ?n) WHERE {{ {own} "
                                        f"GRAPH <{logical_graph}> {{ ?t rg:logicalType ?l }} }}")
        if total != entry["types"] or linked != total:
            wrong.append(f"{entry['assembly']} {entry['version']}: own={total} recorded={entry['types']} linked={linked}")
    return not wrong, "; ".join(wrong[:5])


def _assembly_node(store: Path, iri: str) -> tuple[bool, str]:
    rows = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?a WHERE {{ ?a a dt:Assembly }}")
    found = [r["a"] for r in rows]
    return found == [iri], f"found={found} expected={iri}"


def _eq(actual: Any, expected: Any) -> tuple[bool, str]:
    return actual == expected, f"actual={actual} expected={expected}"


def _positive(value: int) -> tuple[bool, str]:
    return value > 0, f"count={value}"


def _set_diff(actual: set, expected: set) -> str:
    return f"missing={sorted(expected - actual)[:5]} extra={sorted(actual - expected)[:5]}"
