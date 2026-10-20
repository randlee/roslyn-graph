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

from roslyn_graph import oxigraph, traverse
from roslyn_graph.util import DT, RDF_TYPE


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
    lines += [f"<{s}> <{DT}pointerElementType> <{p}> .", f"<{s}> <{DT}hasTypeParameter> <{parameter}> .",
              f"<{parameter}> <{DT}constrainedToType> <{iface}> .", f"<{inner}> <{DT}nestedIn> <{outer}> ."]
    nt, store = tmp_path / "fixture.nt", tmp_path / "store"
    nt.write_text("\n".join(lines) + "\n", encoding="utf-8")
    oxigraph.load(store, nt, "urn:fixture")
    definition = SimpleNamespace(follow=["constraints", "enclosing_type"], max_depth=0, max_types=None, generic_arguments=False)
    types, _edges, _stats, truncated = traverse.expand(store, definition, {s: "S", inner: "Outer.Inner"})
    assert set(types) == {s, iface, inner, outer} and p not in types and decoy not in types and not truncated
    assert traverse._underlying(store, {pointer}, False)[pointer] == {pointer, p}
