"""CLI contract (always one JSON object) and Oxigraph integration."""

import json
import subprocess
import sys
from types import SimpleNamespace
from pathlib import Path

import pytest

from conftest import SCRIPTS, requires_oxigraph
from roslyn_graph import artifacts, build, oxigraph
from roslyn_graph.result import RgError


def rg(*args: str) -> tuple[int, dict]:
    proc = subprocess.run([sys.executable, str(SCRIPTS / "rg.py"), *args], capture_output=True, text=True, encoding="utf-8")
    return proc.returncode, json.loads(proc.stdout)


def test_usage_errors_are_json():
    code, payload = rg("generate", "--workspace", "x")
    assert code == 1 and payload["type"] == "error" and payload["errors"][0]["code"] == "USAGE"


def test_unknown_command_is_json():
    code, payload = rg("bogus")
    assert code == 1 and payload["errors"][0]["hint"] == "Run: python rg.py --help"


def test_domain_errors_are_json(tmp_path):
    code, payload = rg("check-workspace", "--workspace", str(tmp_path / "missing.toml"))
    assert code == 1 and payload["errors"][0]["code"] == "WORKSPACE_NOT_FOUND"


def test_visualizers_lists_the_explorer():
    code, payload = rg("visualizers")
    assert code == 0 and payload["type"] == "visualizers" and "explorer" in payload["visualizers"]


def test_ontology_doc_is_current():
    code, payload = rg("ontology-doc", "--check")
    assert code == 0 and payload["upToDate"] is True, payload


@requires_oxigraph
def test_load_select_and_graph_counts(tmp_path):
    ttl = tmp_path / "a.ttl"
    ttl.write_text("@prefix ex: <http://e/> . ex:a ex:b ex:c . ex:a ex:b ex:c . ex:a ex:b ex:d .\n")
    store = tmp_path / "store"
    oxigraph.load(store, ttl)
    assert oxigraph.default_graph_count(store) == 2
    nt = tmp_path / "b.nt"
    nt.write_text("<http://e/x> <http://e/y> <http://e/z> .\n")
    oxigraph.load(store, nt, "urn:g")
    assert oxigraph.graph_counts(store) == {"urn:g": 1}
    assert oxigraph.scalar(store, "SELECT (COUNT(*) AS ?n) WHERE { ?s ?p ?o }", union=True) == 3


@requires_oxigraph
def test_parse_errors_fail_even_though_oxigraph_exits_zero(tmp_path):
    bad = tmp_path / "bad.ttl"
    bad.write_text("garbage <<\n")
    with pytest.raises(RgError) as info:
        oxigraph.load(tmp_path / "store", bad)
    assert info.value.problems[0].code == "OXIGRAPH_FAILED"
    assert "Parser error" in " ".join(info.value.problems[0].context["stderr"])


@requires_oxigraph
def test_missing_input_fails(tmp_path):
    with pytest.raises(RgError):
        oxigraph.load(tmp_path / "store", tmp_path / "nope.nt")


def test_bounded_select_wraps_after_the_prologue():
    from roslyn_graph import explore
    text = "# comment\nPREFIX dt: <http://dotnet.example/ontology/>\nSELECT ?s WHERE { ?s ?p ?o } ORDER BY ?s"
    wrapped = explore.bounded_select(text, 5)
    assert wrapped.startswith("# comment\nPREFIX dt: <http://dotnet.example/ontology/>\nSELECT * WHERE {\nSELECT ?s")
    assert wrapped.rstrip().endswith("LIMIT 6")
    with pytest.raises(RgError) as info:
        explore.bounded_select("CONSTRUCT { ?s ?p ?o } WHERE { ?s ?p ?o }", 5)
    assert info.value.problems[0].code == "QUERY_NOT_SELECT"


def test_timeouts_become_query_timeout(monkeypatch):
    import subprocess as sp

    def slow(args, **kwargs):
        raise sp.TimeoutExpired(args, kwargs.get("timeout"))

    monkeypatch.setattr(oxigraph, "run", slow)
    with pytest.raises(RgError) as info:
        oxigraph.invoke(["query", "--location", "s"], "running a SELECT query", trace="SELECT *", timeout=3)
    assert info.value.problems[0].code == "QUERY_TIMEOUT"


@requires_oxigraph
def test_bounded_select_limits_in_the_engine(tmp_path):
    from roslyn_graph import explore
    nt = tmp_path / "a.nt"
    nt.write_text("".join(f"<http://e/s{i}> <http://e/p> <http://e/o> .\n" for i in range(50)))
    store = tmp_path / "store"
    oxigraph.load(store, nt)
    rows = oxigraph.select(store, explore.bounded_select("SELECT ?s WHERE { ?s ?p ?o } ORDER BY ?s", 10))
    assert len(rows) == 11 and rows[0]["s"] == "http://e/s0"


@requires_oxigraph
def test_s8_rejects_an_own_type_written_only_as_a_stub(tmp_path):
    from roslyn_graph import validate
    asm = "http://dotnet.example/assembly/Lib/1.0.0.0"
    good, stub = "http://dotnet.example/type/Lib/1.0.0.0/Lib.Good", "http://dotnet.example/type/Lib/1.0.0.0/Lib.Stub"
    dt = "http://dotnet.example/ontology/"
    lines = [f"<{asm}> <http://www.w3.org/1999/02/22-rdf-syntax-ns#type> <{dt}Assembly> .", f'<{asm}> <{dt}name> "Lib" .',
             f'<{asm}> <{dt}version> "1.0.0.0" .']
    for t in (good, stub):
        lines += [f"<{t}> <{dt}definedInAssembly> <{asm}> .", f'<{t}> <{dt}fullName> "{t.rsplit("/", 1)[1]}" .', f'<{t}> <{dt}typeKind> "Class" .']
    lines.append(f'<{good}> <{dt}accessibility> "Public" .')
    nt = tmp_path / "a.nt"
    nt.write_text("\n".join(lines) + "\n")
    store = tmp_path / "artifact" / "store.oxigraph"
    store.parent.mkdir()
    oxigraph.load(store, nt)
    m = {"assembly": {"name": "Lib", "version": "1.0.0.0"}, "store": {"tripleCount": len(lines)},
         "extraction": {"ttlUniqueTriples": len(lines)}}
    checks = {c.id: c for c in validate.assembly(tmp_path / "artifact", m, published=False).items}
    assert checks["S7"].passed and not checks["S8"].passed


@requires_oxigraph
def test_type_to_project_provenance_query_returns_repo_and_relative_path(tmp_path):
    from roslyn_graph.util import assembly_iri, nt_iri, project_iri, RDF_TYPE, RG

    assembly = assembly_iri("PixelMeasurement", "1.0.0.0")
    type_iri = "http://dotnet.example/type/PixelMeasurement/1.0.0.0/MeasurementFilter"
    manifest = {
        "origin": {"kind": "source", "id": "TrueTestCore"},
        "build": {"project": "TrueTest_Analyses/PixelMeasurement/MeasurementFilter/MeasurementFilter.vbproj"},
    }
    lines = [
        f"{nt_iri(type_iri)} {nt_iri(RDF_TYPE)} {nt_iri('http://dotnet.example/ontology/Type')} .",
        f"{nt_iri(type_iri)} {nt_iri('http://dotnet.example/ontology/definedInAssembly')} {nt_iri(assembly)} .",
        *build.project_provenance_lines(manifest, assembly),
    ]
    nt = tmp_path / "provenance.nt"
    nt.write_text("\n".join(lines) + "\n")
    store = tmp_path / "store"
    oxigraph.load(store, nt)

    rows = oxigraph.select(store, f"""PREFIX dt: <http://dotnet.example/ontology/> PREFIX rg: <{RG}>
      SELECT ?repository ?path WHERE {{
        <{type_iri}> dt:definedInAssembly ?assembly .
        ?assembly rg:builtFromProject ?project .
        ?project a rg:Project ; rg:projectRepository ?repository ; rg:projectRelativePath ?path .
      }}""")
    assert rows == [{"repository": "TrueTestCore", "path": "TrueTest_Analyses/PixelMeasurement/MeasurementFilter/MeasurementFilter.vbproj"}]
    assert project_iri("TrueTestCore", manifest["build"]["project"]) in "\n".join(lines)


@requires_oxigraph
def test_snapshot_publishes_validated_type_to_project_provenance(tmp_path, monkeypatch):
    from roslyn_graph.plan import Component
    from roslyn_graph.util import RG, sha256_file

    dll = tmp_path / "Lib.dll"
    dll.write_bytes(b"test assembly bytes")
    project_path = tmp_path / "Lib.csproj"
    project_path.write_text("<Project />")
    assembly = "http://dotnet.example/assembly/Lib/1.0.0.0"
    type_iri = "http://dotnet.example/type/Lib/1.0.0.0/Lib.Widget"
    source_manifest = {
        "origin": {"kind": "source", "id": "Repo", "repository": str(tmp_path / "Repo"), "commit": "c1", "dirtyHash": ""},
        "build": {"fingerprint": "debug-net10.0-test", "targetFramework": "net10.0", "project": "src/Lib.csproj"},
        "assembly": {"sha256": sha256_file(dll), "expectedName": "Lib", "inputPath": str(dll)},
        "extraction": {"extractorId": "e1", "inputKind": "source-project"},
    }
    component = Component("p", "base", dll, "Lib", [], source_manifest, project_path)
    component.artifact_id = artifacts.artifact_id(artifacts.assembly_identity(source_manifest))
    base = artifacts.base_dir(tmp_path / ".roslyn-graph", "assembly-source", origin="Repo")
    component.destination, component.exists = artifacts.resolve_destination(base, component.artifact_id)

    class FakeExtractor:
        id = "e1"

        def to_json(self):
            return {"id": self.id}

    fake_plan = SimpleNamespace(
        root=tmp_path / ".roslyn-graph",
        extractor=FakeExtractor(),
        oxigraph_version="test",
        workspace=SimpleNamespace(path=tmp_path / "workspace.toml", sha256="workspace-hash"),
        collection=SimpleNamespace(name="test-collection"),
    )

    extracted_from = []

    def fake_extract(_extractor, extraction_path, output, _search_dirs):
        extracted_from.append(extraction_path)
        output.write_text(f"""@prefix dt: <http://dotnet.example/ontology/> .
<{assembly}> a dt:Assembly ; dt:name "Lib" ; dt:version "1.0.0.0" .
<{type_iri}> a dt:Type, dt:Class ; dt:name "Widget" ; dt:fullName "Lib.Widget" ;
  dt:typeKind "Class" ; dt:accessibility "Public" ; dt:definedInAssembly <{assembly}> .
<{type_iri}/M> dt:unsafeReason "PointerType" .
""")
        return []

    monkeypatch.setattr(build.extractor, "extract", fake_extract)
    result = build.snapshot(fake_plan, component)
    manifest = artifacts.read_manifest(component.destination / "manifest.json")
    assert result["status"] == "created"
    assert extracted_from == [project_path]
    assert manifest["assembly"]["sha256"] == sha256_file(dll)
    assert manifest["assembly"]["inputPath"] == str(dll)
    assert manifest["extraction"]["inputKind"] == "source-project"
    assert {c["id"]: c["status"] for c in manifest["validation"]["staging"]}["S9"] == "pass"
    rows = oxigraph.select(component.destination / "store.oxigraph", f"""PREFIX dt: <http://dotnet.example/ontology/> PREFIX rg: <{RG}>
      SELECT ?repository ?path WHERE {{
        <{type_iri}> dt:definedInAssembly ?assembly .
        ?assembly rg:builtFromProject ?project .
        ?project rg:projectRepository ?repository ; rg:projectRelativePath ?path .
      }}""")
    assert rows == [{"repository": "Repo", "path": "src/Lib.csproj"}]
    assert oxigraph.select(component.destination / "store.oxigraph", f"SELECT ?reason WHERE {{ <{type_iri}/M> <http://dotnet.example/ontology/unsafeReason> ?reason }}") == [
        {"reason": "PointerType"}
    ]
