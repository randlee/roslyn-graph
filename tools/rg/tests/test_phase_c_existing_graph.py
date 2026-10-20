"""Mandatory real-store prerequisites for Phase C's existing-graph regression suite.

These tests intentionally do not use the optional ``requires_oxigraph`` marker: the C.1
acceptance scenarios exercise the built extractor and a real pinned store on every CI runner.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

from roslyn_graph import explore, oxigraph, traverse
from roslyn_graph.result import RgError
from roslyn_graph.util import DT, RDF_TYPE, RG


REPO = Path(__file__).parents[3]
BUILT_EXTRACTOR = REPO / "src" / "RoslynToRdf.Cli" / "bin" / "Release" / "net8.0" / "RoslynToRdf.Cli.dll"


def extract_source_with_core_harness(tmp_path: Path, language: str, source: str) -> Path:
    """Test-local Core harness required by C.1 source acceptance fixtures."""
    harness = tmp_path / "core-harness"
    harness.mkdir()
    core = REPO / "src" / "RoslynToRdf.Core" / "RoslynToRdf.Core.csproj"
    (harness / "Harness.csproj").write_text(f'''<Project Sdk="Microsoft.NET.Sdk"><PropertyGroup><TargetFramework>net8.0</TargetFramework><OutputType>Exe</OutputType><ImplicitUsings>enable</ImplicitUsings><EnableDefaultCompileItems>false</EnableDefaultCompileItems></PropertyGroup><ItemGroup><Compile Include="Program.cs" /><ProjectReference Include="{core}" /><PackageReference Include="Microsoft.CodeAnalysis.CSharp" Version="4.9.2" /><PackageReference Include="Microsoft.CodeAnalysis.VisualBasic" Version="4.9.2" /></ItemGroup></Project>''')
    (harness / "Program.cs").write_text('''using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.VisualBasic;
using RoslynToRdf.Core.Emitters;
using RoslynToRdf.Core.Extraction;
var language = args[0]; var source = File.ReadAllText(args[1]); var output = args[2];
var references = new[] { MetadataReference.CreateFromFile(typeof(object).Assembly.Location) };
Compilation compilation = language == "vb"
 ? VisualBasicCompilation.Create("Fixture", new[] { VisualBasicSyntaxTree.ParseText(source) }, references, new VisualBasicCompilationOptions(OutputKind.DynamicallyLinkedLibrary))
 : CSharpCompilation.Create("Fixture", new[] { CSharpSyntaxTree.ParseText(source) }, references, new CSharpCompilationOptions(OutputKind.DynamicallyLinkedLibrary, allowUnsafe: true));
if (compilation.GetDiagnostics().Any(d => d.Severity == DiagnosticSeverity.Error)) throw new Exception(string.Join("\\n", compilation.GetDiagnostics()));
using var stream = File.Create(output); using var emitter = new TurtleEmitter(stream);
new AssemblyGraphExtractor(emitter, new ExtractionOptions { IncludePrivate = true }).Extract(compilation, compilation.Assembly);
''')
    source_path, output = harness / f"Fixture.{language}", harness / "fixture.ttl"
    source_path.write_text(source)
    completed = subprocess.run(["dotnet", "run", "--project", str(harness / "Harness.csproj"), "--", language, str(source_path), str(output)], capture_output=True, text=True)
    assert completed.returncode == 0 and output.is_file(), completed.stdout + completed.stderr
    return output


def extract_compiled_fixture(tmp_path: Path, language: str, source: str) -> Path:
    """DLL-mode companion: compile the fixture, then use the shipped extractor CLI."""
    if not BUILT_EXTRACTOR.is_file():
        pytest.fail("Phase C fixture requires the Release RoslynToRdf CLI built by authoritative validation.")
    extension = "cs" if language == "cs" else "vb"
    project = tmp_path / f"Fixture.{extension}proj"
    unsafe = "<AllowUnsafeBlocks>true</AllowUnsafeBlocks>" if language == "cs" else ""
    root_namespace = "<RootNamespace></RootNamespace>" if language == "vb" else ""
    project.write_text(f"<Project Sdk=\"Microsoft.NET.Sdk\"><PropertyGroup><TargetFramework>net8.0</TargetFramework>{unsafe}{root_namespace}</PropertyGroup></Project>")
    (tmp_path / f"Fixture.{extension}").write_text(source)
    build = subprocess.run(["dotnet", "build", str(project), "--configuration", "Release"], capture_output=True, text=True)
    assert build.returncode == 0, build.stderr
    ttl = tmp_path / "fixture.ttl"
    completed = subprocess.run(["dotnet", str(BUILT_EXTRACTOR), str(tmp_path / "bin" / "Release" / "net8.0" / "Fixture.dll"),
                                "--output", str(ttl), "--format", "Turtle", "--include-private", "--quiet"], capture_output=True, text=True)
    assert completed.returncode == 0 and ttl.is_file(), completed.stderr
    return ttl


def selected_names(store: Path, seed: str, follow: list[str]) -> set[str]:
    """Run graph reduction from a real extracted type and return its exact component names."""
    definition = SimpleNamespace(follow=follow, max_depth=0, max_types=None, generic_arguments=False)
    rows = oxigraph.select(store, f'PREFIX dt: <{DT}> SELECT ?t WHERE {{ GRAPH ?g {{ ?t dt:fullName "{seed}" }} }}')
    assert len(rows) == 1, f"expected exactly one extracted seed named {seed}, got {rows}"
    types, _edges, _stats, truncated = traverse.expand(store, definition, {rows[0]["t"]: seed})
    assert not truncated
    return set(types.values())


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


def test_real_csharp_pointer_fixture_extracts_and_reduces_without_decoy(tmp_path: Path):
    """AC2 source evidence must construct a Compilation and call Core directly."""
    ttl = extract_source_with_core_harness(tmp_path, "cs", "public unsafe struct S { public P** F; } public struct P {} public struct Decoy {}")
    store = tmp_path / "store"
    oxigraph.load(store, ttl, "urn:fixture")
    rows = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?pointer ?p WHERE {{ GRAPH ?g {{ ?pointer dt:pointerElementType ?p . ?p dt:fullName \"P\" }} }}")
    assert rows, "unsafe pointer fixture must emit dt:pointerElementType"
    assert selected_names(store, "S", ["member_types"]) == {"S", "P"}


def test_real_compiled_pointer_fixture_emits_pointer_constituent(tmp_path: Path):
    """AC2 DLL-mode evidence uses the extractor CLI on the compiled assembly."""
    ttl = extract_compiled_fixture(tmp_path, "cs", "public unsafe struct S { public P** F; } public struct P {} public struct Decoy {}")
    store = tmp_path / "store"
    oxigraph.load(store, ttl, "urn:fixture")
    assert oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?pointer WHERE {{ GRAPH ?g {{ ?pointer dt:pointerElementType ?p . }} }}")
    assert selected_names(store, "S", ["member_types"]) == {"S", "P"}


@pytest.mark.parametrize(("language", "source"), [
    ("cs", "public interface IFoo {} public interface IBar {} public class S<T> where T : IFoo {} public class H { public void M<U>() where U : IBar {} } public class Outer { public class Inner {} } public class Decoy {}"),
    ("vb", "Public Interface IFoo\nEnd Interface\nPublic Interface IBar\nEnd Interface\nPublic Class S(Of T As IFoo)\nEnd Class\nPublic Class H\nPublic Sub M(Of U As IBar)()\nEnd Sub\nEnd Class\nPublic Class Outer\nPublic Class Inner\nEnd Class\nEnd Class\nPublic Class Decoy\nEnd Class"),
])
@pytest.mark.parametrize("mode", ["source", "dll"])
def test_real_constraints_and_nested_fixtures_reduce_exactly(tmp_path: Path, language: str, source: str, mode: str):
    """AC3/AC4: C#/VB source harness and compiled DLL select only the intended facts."""
    ttl = extract_source_with_core_harness(tmp_path, language, source) if mode == "source" else extract_compiled_fixture(tmp_path, language, source)
    store = tmp_path / "store"
    oxigraph.load(store, ttl, "urn:fixture")
    generic_seed = "S(Of T)" if language == "vb" and mode == "source" else "S<T>"
    assert selected_names(store, generic_seed, ["constraints"]) == {generic_seed, "IFoo"}
    assert selected_names(store, "H", ["constraints"]) == {"H", "IBar"}
    assert selected_names(store, "Outer.Inner", ["enclosing_type"]) == {"Outer.Inner", "Outer"}


@pytest.mark.parametrize(("language", "source"), [
    ("cs", "public interface IFoo {} public class S<T> where T : IFoo {} public class Outer { public class Inner {} }"),
    ("vb", "Public Interface IFoo\nEnd Interface\nPublic Class S(Of T As IFoo)\nEnd Class\nPublic Class Outer\nPublic Class Inner\nEnd Class\nEnd Class"),
])
def test_core_harness_extracts_csharp_and_vb_source_fixtures(tmp_path: Path, language: str, source: str):
    """C.1 source fixtures use Compilation.Create and AssemblyGraphExtractor directly."""
    ttl = extract_source_with_core_harness(tmp_path, language, source)
    store = tmp_path / "store"
    oxigraph.load(store, ttl, "urn:fixture")
    assert oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?p WHERE {{ GRAPH ?g {{ ?owner dt:hasTypeParameter ?p . ?p dt:constrainedToType ?c . }} }}")
    assert oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?inner WHERE {{ GRAPH ?g {{ ?inner dt:nestedIn ?outer . }} }}")


def test_export_preserves_full_real_source_rdf_and_context(tmp_path: Path, monkeypatch):
    """AC5: export every fact from a Core-extracted source fixture and identify its source separately."""
    ttl = extract_source_with_core_harness(
        tmp_path, "cs",
        "public interface IFoo {} public unsafe class Outer { public class Inner {} public P* F; public P M<U>() where U : IFoo => default; } public struct P {}")
    store = tmp_path / "store"
    oxigraph.load(store, ttl, "urn:fixture")
    assembly = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT ?assembly WHERE {{ GRAPH ?g {{ ?assembly a dt:Assembly }} }}")
    assert len(assembly) == 1
    provenance = tmp_path / "provenance.nt"
    provenance.write_text(f"<{assembly[0]['assembly']}> <{RG}builtFromProject> <urn:fixture-project> .\n")
    oxigraph.load(store, provenance, "urn:fixture")
    manifest_path = tmp_path / "artifact.json"
    manifest_path.write_text(json.dumps({"kind": "solution", "artifactId": "fixture-artifact", "workspace": {"collection": "fixture"}}))
    manifest = json.loads(manifest_path.read_text())
    monkeypatch.setattr(explore, "store_for", lambda _path: (store, manifest))
    query = "CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }"
    output = tmp_path / "fixture.nt"
    result = explore.export(manifest_path, query, output, union=True, logical=False)
    expected = tmp_path / "expected.nt"
    oxigraph.construct(store, query, expected, union=True)
    assert set(output.read_text().splitlines()) == set(expected.read_text().splitlines())
    rdf = output.read_text()
    for term in (RDF_TYPE, DT + "hasMember", DT + "memberOf", DT + "returnType", DT + "fieldType",
                 DT + "definedInAssembly", RG + "builtFromProject", DT + "constrainedToType",
                 DT + "pointerElementType", DT + "nestedIn"):
        assert f"<{term}>" in rdf
    context = json.loads(Path(result["context"]).read_text())
    assert context["source"]["manifest"] == str(manifest_path.resolve())
    assert context["source"]["store"] == str((manifest_path.parent / "store.oxigraph").resolve())
    assert context["source"]["artifactId"] == "fixture-artifact"


def test_private_library_inventory_has_every_type_and_private_member(tmp_path: Path):
    """AC6: the >1500-type fixture is a real private-inclusive library, not entry-point reachability."""
    public_types = {f"T{index}" for index in range(1_501)}
    source = "\n".join([*(f"public class {name} {{ }}" for name in sorted(public_types)),
                        "internal class Hidden { private void Uncalled() {} }",
                        "public class Outer { private class Inner { private void InnerUncalled() {} } }"])
    ttl = extract_compiled_fixture(tmp_path, "cs", source)
    store = tmp_path / "store"
    oxigraph.load(store, ttl, "urn:fixture")
    definition = SimpleNamespace(seed_types=[], seed_patterns=["*"], seed_kinds=[])
    types, unmatched = traverse.find_seeds(store, definition)
    expected = public_types | {"<Module>", "Hidden", "Outer", "Outer.Inner"}
    assert not unmatched and set(types.values()) == expected
    members = "\n".join(traverse.member_lines(store, sorted(types)))
    assert '"Uncalled"' in members and '"InnerUncalled"' in members


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
