import json
from pathlib import Path

import pytest

from roslyn_graph import artifacts
from roslyn_graph.result import RgError


def source_manifest(**overrides):
    m = {
        "origin": {"kind": "source", "id": "Repo", "commit": "c1", "dirtyHash": ""},
        "build": {"fingerprint": "debug-net10.0-abc", "targetFramework": "net10.0"},
        "assembly": {"sha256": "d" * 64},
        "extraction": {"extractorId": "e1"},
    }
    for key, value in overrides.items():
        m[key] = {**m[key], **value}
    return m


def test_assembly_identity_changes_with_commit_dll_and_extractor():
    base = artifacts.assembly_identity(source_manifest())
    assert artifacts.assembly_identity(source_manifest(origin={"commit": "c2"})) != base
    assert artifacts.assembly_identity(source_manifest(assembly={"sha256": "e" * 64})) != base
    assert artifacts.assembly_identity(source_manifest(extraction={"extractorId": "e2"})) != base
    assert artifacts.assembly_identity(source_manifest(origin={"dirtyHash": "x"})) != base


def test_nuget_identity_uses_package_fields():
    m = {
        "origin": {"kind": "nuget", "id": "Lib"},
        "package": {"id": "Lib", "version": "1.0.0", "nupkgSha256": "a", "asset": "lib/net10.0/Lib.dll",
                    "dependenciesHash": "h", "targetFramework": "net10.0"},
        "assembly": {"sha256": "d"}, "extraction": {"extractorId": "e"},
    }
    first = artifacts.assembly_identity(m)
    m["package"]["dependenciesHash"] = "h2"
    assert artifacts.assembly_identity(m) != first
    assert first.startswith("assembly/v2|nuget|lib|1.0.0|")


def test_solution_identity_ignores_component_order():
    fields = {"profile": "p", "repository": "r", "relativePath": "a.sln", "commit": "c", "dirtyHash": "", "fingerprint": "f",
              "targetFramework": "t", "configuration": "Debug", "platform": ""}
    a = artifacts.solution_identity({"solution": fields, "components": [{"artifactId": "1"}, {"artifactId": "2"}]})
    b = artifacts.solution_identity({"solution": fields, "components": [{"artifactId": "2"}, {"artifactId": "1"}]})
    assert a == b


def test_resolve_destination_moves_past_foreign_prefixes(tmp_path):
    full = "a" * 20 + "b" * 44
    other = "a" * 20 + "c" * 44
    (tmp_path / full[:20]).mkdir()
    (tmp_path / full[:20] / "manifest.json").write_text(json.dumps({"artifactId": other}))
    assert artifacts.resolve_destination(tmp_path, full) == (tmp_path / full[:32], False)
    (tmp_path / full[:32]).mkdir()
    (tmp_path / full[:32] / "manifest.json").write_text(json.dumps({"artifactId": full}))
    assert artifacts.resolve_destination(tmp_path, full) == (tmp_path / full[:32], True)


def test_resolve_destination_refuses_unknown_directories(tmp_path):
    (tmp_path / ("a" * 20)).mkdir()
    with pytest.raises(RgError) as info:
        artifacts.resolve_destination(tmp_path, "a" * 64)
    assert info.value.problems[0].code == "ARTIFACT_DIR_WITHOUT_MANIFEST"


def staged(root: Path, artifact_id: str) -> Path:
    staging = artifacts.new_staging(root, "x")
    (staging / "artifact" / "manifest.json").write_text(json.dumps({"artifactId": artifact_id}))
    return staging


def test_publish_moves_atomically_and_cleans_staging(tmp_path):
    root = tmp_path / ".roslyn-graph"
    staging = staged(root, "f" * 64)
    destination = root / "views" / ("f" * 20)
    assert artifacts.publish(root, staging, destination, "f" * 64) is True
    assert (destination / "manifest.json").is_file() and not staging.exists()
    assert not list((root / "locks").iterdir())


def test_publish_treats_an_identical_winner_as_reuse(tmp_path):
    root = tmp_path / ".roslyn-graph"
    destination = root / "views" / ("f" * 20)
    artifacts.publish(root, staged(root, "f" * 64), destination, "f" * 64)
    loser = staged(root, "f" * 64)
    assert artifacts.publish(root, loser, destination, "f" * 64) is False
    assert not loser.exists()


def test_publish_never_writes_into_a_foreign_destination(tmp_path):
    root = tmp_path / ".roslyn-graph"
    destination = root / "views" / ("f" * 20)
    destination.mkdir(parents=True)
    (destination / "manifest.json").write_text(json.dumps({"artifactId": "0" * 64}))
    with pytest.raises(RgError) as info:
        artifacts.publish(root, staged(root, "f" * 64), destination, "f" * 64)
    assert info.value.problems[0].code == "ARTIFACT_DESTINATION_TAKEN"
    assert sorted(p.name for p in destination.iterdir()) == ["manifest.json"]


def test_publish_reports_a_held_lock(tmp_path):
    root = tmp_path / ".roslyn-graph"
    (root / "locks").mkdir(parents=True)
    (root / "locks" / ("f" * 64 + ".lock")).write_text("123")
    with pytest.raises(RgError) as info:
        artifacts.publish(root, staged(root, "f" * 64), root / "views" / "x", "f" * 64)
    assert info.value.problems[0].code == "ARTIFACT_LOCKED"


def test_segment_and_path_length(tmp_path):
    assert artifacts.segment("Integration/annotations-only") == "Integration_annotations-only"
    with pytest.raises(RgError):
        artifacts.check_path_length(tmp_path / ("x" * 250))


def test_artifact_root_requires_a_value(monkeypatch):
    monkeypatch.delenv("ROSLYN_GRAPH_DATA_ROOT", raising=False)
    with pytest.raises(RgError) as info:
        artifacts.artifact_root(None)
    assert info.value.problems[0].code == "DATA_ROOT_MISSING"
    monkeypatch.setenv("ROSLYN_GRAPH_DATA_ROOT", "/data")
    assert artifacts.artifact_root(None).name == ".roslyn-graph"
