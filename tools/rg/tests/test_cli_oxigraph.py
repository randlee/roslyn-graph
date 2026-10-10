"""CLI contract (always one JSON object) and Oxigraph integration."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPTS, requires_oxigraph
from roslyn_graph import oxigraph
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
