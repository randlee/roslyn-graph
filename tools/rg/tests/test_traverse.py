import re
from pathlib import Path

import pytest

from roslyn_graph import traverse
from roslyn_graph.result import RgError

VALID = """
schema_version = 1
title = "Repository types"

[source]
collection = "app_with_current_data"

[seeds]
types = ["Contoso.Data.IRepository"]
patterns = ["Contoso.Data.I*Store*"]
kinds = ["Interface"]
implementations = "transitive"

[expand]
follow = ["base_types", "member_types"]
max_depth = 3
max_types = 200

[output]
visualizer = "explorer"
"""


def write(tmp_path: Path, text: str) -> Path:
    path = tmp_path / ".roslyn-graph" / "graphs" / "repo.graph.toml"
    path.parent.mkdir(parents=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_valid_definition_and_defaults(tmp_path):
    d = traverse.load_definition(write(tmp_path, VALID))
    assert d.title == "Repository types"
    assert d.workspace == (tmp_path / ".roslyn-graph" / "workspace.toml").resolve()
    assert (d.collection, d.logical, d.implementations, d.max_depth, d.max_types) == ("app_with_current_data", True, "transitive", 3, 200)
    assert d.follow == ["base_types", "member_types"] and d.generic_arguments is True

    minimal = traverse.load_definition(write(tmp_path / "m", 'schema_version = 1\n[source]\nmanifest = "views/x/manifest.json"\n[seeds]\ntypes = ["A.B"]\n'))
    assert minimal.follow == ["base_types", "interfaces", "member_types", "parameter_types"]
    assert (minimal.implementations, minimal.max_depth, minimal.max_types, minimal.visualizer) == ("transitive", 0, 1500, "explorer")
    assert minimal.title == "repo"


def test_every_problem_is_reported(tmp_path):
    text = VALID.replace('implementations = "transitive"', 'implementations = "all"').replace(
        'follow = ["base_types", "member_types"]', 'follow = ["callers"]').replace("max_depth = 3", "max_depth = -1").replace(
        'kinds = ["Interface"]', 'kinds = ["Widget"]') + '\n[extra]\nx = 1\n'
    with pytest.raises(RgError) as info:
        traverse.load_definition(write(tmp_path, text))
    keys = {p.context["key"] for p in info.value.problems}
    assert {"seeds.implementations", "expand.follow", "expand.max_depth", "seeds.kinds", "extra"} <= keys
    assert all(p.code == "GRAPH_DEFINITION_INVALID" for p in info.value.problems)


def test_source_and_seeds_are_required(tmp_path):
    with pytest.raises(RgError) as info:
        traverse.load_definition(write(tmp_path, "schema_version = 1\n[source]\n[seeds]\n"))
    keys = {p.context["key"] for p in info.value.problems}
    assert keys == {"source", "seeds"}


def test_missing_definition(tmp_path):
    with pytest.raises(RgError) as info:
        traverse.load_definition(tmp_path / "nope.graph.toml")
    assert info.value.problems[0].code == "GRAPH_DEFINITION_NOT_FOUND"


@pytest.mark.parametrize("pattern,name,matches", [
    ("Contoso.Data.I*Store*", "Contoso.Data.IRecordStore<T>", True),
    ("Contoso.Data.I*Store*", "Contoso.Data.Store", False),
    ("Contoso.?Data", "Contoso.XData", True),
    ("Contoso.Data.IRepository", "Contoso.Data.IRepositoryFactory", False),
    ("A(B)*", "A(B)x", True),
])
def test_glob_regex(pattern, name, matches):
    assert bool(re.match(traverse.glob_regex(pattern), name)) is matches


def test_every_follow_relation_is_documented():
    from conftest import EXPLORE_SKILL
    doc = (EXPLORE_SKILL / "reference" / "graph-definitions.md").read_text(encoding="utf-8")
    for relation in traverse.FOLLOW:
        assert f"`{relation}`" in doc
