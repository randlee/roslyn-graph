"""Mandatory real-store prerequisites for Phase C's existing-graph regression suite.

These tests intentionally do not use the optional ``requires_oxigraph`` marker: the C.1
acceptance scenarios exercise the built extractor and a real pinned store on every CI runner.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from roslyn_graph import explore, oxigraph, traverse
from roslyn_graph.result import RgError
from roslyn_graph.util import DT, RDF_TYPE, RG


@pytest.fixture(scope="session", autouse=True)
def require_real_store_tools():
    dotnet = shutil.which("dotnet")
    oxigraph = shutil.which("oxigraph")
    if not dotnet or not oxigraph:
        pytest.fail("Phase C existing-graph tests require dotnet and oxigraph on PATH.")
    version = subprocess.run([oxigraph, "--version"], check=True, capture_output=True, text=True).stdout
    if "0.5.8" not in version:
        pytest.fail(f"Phase C existing-graph tests require Oxigraph 0.5.8, got: {version.strip()}")


def test_real_store_pointer_constraint_and_enclosing_follow(tmp_path: Path):
    """Exercise the C.1 relations against a real named-graph Oxigraph store."""
    asm = "urn:assembly"
    s, p, iface, outer, inner, decoy = (f"urn:{name}" for name in ("S", "P", "IFoo", "Outer", "Outer.Inner", "Decoy"))
    lines = [f"<{asm}> <{RDF_TYPE}> <{DT}Assembly> ."]
    for iri, name in ((s, "S"), (p, "P"), (iface, "IFoo"), (outer, "Outer"), (inner, "Outer.Inner"), (decoy, "Decoy")):
        lines += [f"<{iri}> <{DT}definedInAssembly> <{asm}> .", f'<{iri}> <{DT}accessibility> "Public" .',
                  f'<{iri}> <{DT}fullName> "{name}" .']
    pointer, parameter = "urn:pointer", "urn:parameter"
    lines += [f"<{pointer}> <{DT}pointerElementType> <{p}> .", f"<{s}> <{DT}hasTypeParameter> <{parameter}> .",
              f"<{parameter}> <{DT}constrainedToType> <{iface}> .", f"<{inner}> <{DT}nestedIn> <{outer}> ."]
    nt, store = tmp_path / "fixture.nt", tmp_path / "store"
    nt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    oxigraph.load(store, nt, "urn:fixture")
    definition = SimpleNamespace(follow=["constraints", "enclosing_type"], max_depth=0, max_types=None, generic_arguments=False)
    types, _edges, _stats, truncated = traverse.expand(store, definition, {s: "S", inner: "Outer.Inner"})
    assert set(types) == {s, iface, inner, outer} and p not in types and decoy not in types and not truncated
    assert traverse._underlying(store, {pointer}, False)[pointer] == {pointer, p}


def test_unlimited_defaults_return_more_than_former_traversal_and_query_caps(tmp_path: Path, monkeypatch):
    """AC1: omitted caps must not quietly cut real Oxigraph results."""
    asm, graph = "urn:large-assembly", "urn:large-graph"
    types = [f"urn:type:{i}" for i in range(1_501)]
    lines = [f"<{asm}> <{RDF_TYPE}> <{DT}Assembly> ."]
    for index, iri in enumerate(types):
        lines.extend((f"<{iri}> <{DT}definedInAssembly> <{asm}> .", f'<{iri}> <{DT}accessibility> "Public" .',
                      f'<{iri}> <{DT}fullName> "Fixture.T{index}" .'))
        if index:
            lines.append(f"<{types[0]}> <{DT}inherits> <{iri}> .")
    for index in range(2_500):
        lines.append(f"<urn:row:{index}> <urn:predicate> <urn:object> .")
    nt, store = tmp_path / "large.nt", tmp_path / "store"
    nt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    oxigraph.load(store, nt, graph)
    definition = SimpleNamespace(follow=["base_types"], max_depth=0, max_types=None, generic_arguments=False)
    selected, _edges, _stats, truncated = traverse.expand(store, definition, {types[0]: "Fixture.T0"})
    assert len(selected) == 1_501 and not truncated
    monkeypatch.setattr(explore, "store_for", lambda _path: (store, {"kind": "solution"}))
    result = explore.query(tmp_path / "manifest.json", "SELECT ?s WHERE { GRAPH ?g { ?s <urn:predicate> <urn:object> } }", union=False)
    assert result["rowCount"] == 2_500 and len(result["rows"]) == 2_500 and not result["truncated"]


def test_unlimited_default_export_exceeds_former_triple_cap(tmp_path: Path, monkeypatch):
    """AC1: a default export returns every triple instead of silently capping at 500k."""
    count, graph = 600_001, "urn:export-graph"
    nt, store = tmp_path / "export.nt", tmp_path / "store"
    nt.write_text("".join(f"<urn:export:{i}> <urn:predicate> <urn:object> .\n" for i in range(count)), encoding="utf-8")
    oxigraph.load(store, nt, graph)
    monkeypatch.setattr(explore, "store_for", lambda _path: (store, {"kind": "solution"}))
    output = tmp_path / "export.nt"
    result = explore.export(tmp_path / "manifest.json", "CONSTRUCT { ?s ?p ?o } WHERE { GRAPH ?g { ?s ?p ?o } }", output,
                            union=False, logical=False)
    assert result["summary"]["triples"] == count
    assert sum(1 for _ in output.open(encoding="utf-8")) == count


def test_query_and_export_failures_never_return_partial_success(tmp_path: Path, monkeypatch):
    """AC1: backend failures propagate instead of producing a partial success result."""
    store = tmp_path / "store"
    monkeypatch.setattr(explore, "store_for", lambda _path: (store, {"kind": "solution"}))
    failure = RgError.of("OXIGRAPH_FAILED", "simulated backend failure")
    monkeypatch.setattr(explore.oxigraph, "select", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(RgError) as query_error:
        explore.query(tmp_path / "manifest.json", "SELECT ?s WHERE { ?s ?p ?o }", union=False)
    assert query_error.value.problems[0].code == "OXIGRAPH_FAILED"
    monkeypatch.setattr(explore.oxigraph, "construct", lambda *_args, **_kwargs: (_ for _ in ()).throw(failure))
    with pytest.raises(RgError) as export_error:
        explore.export(tmp_path / "manifest.json", "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", tmp_path / "out.nt", False, False)
    assert export_error.value.problems[0].code == "OXIGRAPH_FAILED" and not (tmp_path / "out.nt").exists()


def test_shipped_queries_are_not_limited_by_their_former_caps(tmp_path: Path):
    """AC1: every shipped query returns more matches than its removed LIMIT allowed."""
    graph, asm = "urn:queries", "urn:queries-assembly"
    lines = [f"<{asm}> <{RDF_TYPE}> <{DT}Assembly> .", f'<{asm}> <{DT}name> "Fixture" .', f'<{asm}> <{DT}version> "1.0" .']
    for index in range(2_001):
        type_iri, member, fact = f"urn:q-type:{index}", f"urn:q-member:{index}", f"urn:q-fact:{index}"
        lines += [f'<{type_iri}> <{DT}fullName> "Fixture.Repository{index}" .', f'<{type_iri}> <{DT}name> "Repository{index}" .',
                  f'<{type_iri}> <{DT}typeKind> "Class" .', f"<{type_iri}> <{DT}definedInAssembly> <{asm}> .",
                  f'<{type_iri}> <{DT}containsUnsafeCode> "true"^^<http://www.w3.org/2001/XMLSchema#boolean> .', f"<{type_iri}> <{DT}hasMember> <{member}> .",
                  f'<{member}> <{DT}containsUnsafeCode> "true"^^<http://www.w3.org/2001/XMLSchema#boolean> .', f"<{member}> <{DT}name> \"M{index}\" .",
                  f'<{member}> <{DT}requiresUnsafeCompilation> "true"^^<http://www.w3.org/2001/XMLSchema#boolean> .', f"<{member}> <{DT}hasUnsafeFact> <{fact}> .",
                  f'<{fact}> <{DT}unsafeReason> "Pointer" .', f'<{fact}> <{DT}unsafeLocation> "L{index}" .']
    for index in range(501):
        logical = f"urn:logical:{index}"
        for version in ("1", "2"):
            physical, version_asm = f"urn:physical:{index}:{version}", f"urn:logical-asm:{index}:{version}"
            lines += [f"<{physical}> <{RG}logicalType> <{logical}> .", f"<{logical}> <{RG}assemblyName> <urn:fixture:{index}> .",
                      f'<{logical}> <{DT}fullName> "Fixture.Logical{index}" .', f"<{physical}> <{DT}definedInAssembly> <{version_asm}> .",
                      f"<{version_asm}> <{RDF_TYPE}> <{DT}Assembly> .", f'<{version_asm}> <{DT}version> "{version}.0" .']
    nt, store = tmp_path / "queries.nt", tmp_path / "store"
    nt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    oxigraph.load(store, nt, graph)
    queries = Path(__file__).parents[3] / "plugins" / "roslyn-graph" / "skills" / "roslyn-graph-explore" / "queries"
    find_type = explore.read_query(None, str(queries / "find-type.rq"), ["NAME=Repository"])
    assert len(oxigraph.select(store, find_type)) == 2_001
    assert len(oxigraph.select(store, (queries / "logical-versions.rq").read_text(encoding="utf-8"))) == 501
    assert len(oxigraph.select(store, (queries / "unsafe-aggregates.rq").read_text(encoding="utf-8"))) == 2_001
    assert len(oxigraph.select(store, (queries / "unsafe-methods.rq").read_text(encoding="utf-8"))) == 2_001


def test_real_store_depth_bounds_distinguish_cuts_leaves_cycles_and_inverse(tmp_path: Path):
    """AC1-depth: bounded lookahead reports only real omissions in either direction."""
    asm, graph = "urn:depth-assembly", "urn:depth-graph"

    def store_for(name: str, edges: list[tuple[str, str]]):
        store, nt = tmp_path / name, tmp_path / f"{name}.nt"
        names = {node for edge in edges for node in edge}
        lines = [f"<{asm}> <{RDF_TYPE}> <{DT}Assembly> ."]
        for node in names:
            lines += [f"<urn:{node}> <{DT}definedInAssembly> <{asm}> .", f'<urn:{node}> <{DT}accessibility> "Public" .',
                      f'<urn:{node}> <{DT}fullName> "{node}" .']
        lines += [f"<urn:{source}> <{DT}inherits> <urn:{target}> ." for source, target in edges]
        nt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        oxigraph.load(store, nt, graph)
        return store

    direct = store_for("direct", [("A", "B"), ("B", "C")])
    limited = SimpleNamespace(follow=["base_types"], max_depth=1, max_types=None, generic_arguments=False)
    types, _edges, stats, truncated = traverse.expand(direct, limited, {"urn:A": "A"})
    assert set(types) == {"urn:A", "urn:B"} and truncated and stats[-1]["stopped"] == "max_depth=1"
    unlimited = SimpleNamespace(follow=["base_types"], max_depth=0, max_types=None, generic_arguments=False)
    assert set(traverse.expand(direct, unlimited, {"urn:A": "A"})[0]) == {"urn:A", "urn:B", "urn:C"}
    leaf = store_for("leaf", [("A", "B")])
    assert not traverse.expand(leaf, limited, {"urn:A": "A"})[3]
    cycle = store_for("cycle", [("A", "B"), ("B", "A")])
    cycle_types, cycle_edges, _stats, cycle_truncated = traverse.expand(cycle, limited, {"urn:A": "A"})
    assert set(cycle_types) == {"urn:A", "urn:B"} and ("urn:B", "urn:A") in cycle_edges and not cycle_truncated
    inverse = store_for("inverse", [("B", "A"), ("C", "B")])
    inverse_definition = SimpleNamespace(follow=["referenced_by"], max_depth=1, max_types=None, generic_arguments=False)
    inverse_types, _edges, inverse_stats, inverse_truncated = traverse.expand(inverse, inverse_definition, {"urn:A": "A"})
    assert set(inverse_types) == {"urn:A", "urn:B"} and inverse_truncated and inverse_stats[-1]["stopped"] == "max_depth=1"
