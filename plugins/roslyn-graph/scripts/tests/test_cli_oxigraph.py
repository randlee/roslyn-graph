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
