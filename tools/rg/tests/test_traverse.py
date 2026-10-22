import re
import json
from pathlib import Path
from types import SimpleNamespace

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
    assert minimal.follow == ["base_types", "interfaces", "member_types", "parameter_types", "body_types", "constraints", "enclosing_type"]
    assert (minimal.implementations, minimal.max_depth, minimal.max_types, minimal.visualizer) == ("transitive", 0, None, "explorer")
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


def test_referenced_by_adds_component_consumers_with_edges_pointing_to_the_consumed_type(monkeypatch):
    definition = SimpleNamespace(follow=["referenced_by"], max_depth=1, max_types=10, generic_arguments=False)
    monkeypatch.setattr(traverse, "_inverse_pairs", lambda *_: [("seed", "consumer")])
    monkeypatch.setattr(traverse, "_underlying", lambda _store, refs, _generic: {ref: {ref} for ref in refs})
    monkeypatch.setattr(traverse, "_own_names", lambda _store, iris: {iri: iri.title() for iri in iris})

    types, edges, stats, truncated = traverse.expand(Path("store"), definition, {"seed": "Seed"})

    assert types == {"seed": "Seed", "consumer": "Consumer"}
    assert edges == [("consumer", "seed")]
    assert stats == [{"depth": 1, "added": 1, "total": 2}]
    assert truncated is False


def test_explicit_max_types_is_positive_and_omitted_is_unlimited(tmp_path):
    base = 'schema_version = 1\n[source]\nmanifest = "views/x/manifest.json"\n[seeds]\ntypes = ["A.B"]\n[expand]\n'
    assert traverse.load_definition(write(tmp_path / "unlimited", base)).max_types is None
    for value in ("0", "-1"):
        with pytest.raises(RgError) as info:
            traverse.load_definition(write(tmp_path / value, base + f"max_types = {value}\n"))
        assert any(p.context["key"] == "expand.max_types" for p in info.value.problems)


def test_depth_probe_reports_real_cut_and_preserves_cycle_edges(monkeypatch):
    graph = {"A": ["B"], "B": ["C"], "C": []}
    definition = SimpleNamespace(follow=["base_types"], max_depth=1, max_types=None, generic_arguments=False)
    monkeypatch.setattr(traverse, "_pairs", lambda _store, subjects, _pattern: [(t, r) for t in subjects for r in graph[t]])
    monkeypatch.setattr(traverse, "_underlying", lambda _store, refs, _generic: {ref: {ref} for ref in refs})
    monkeypatch.setattr(traverse, "_own_names", lambda _store, iris: {iri: iri for iri in iris})
    types, edges, stats, truncated = traverse.expand(Path("store"), definition, {"A": "A"})
    assert types == {"A": "A", "B": "B"} and edges == [("A", "B")]
    assert truncated is True and stats[-1]["stopped"] == "max_depth=1"

    graph["B"] = ["A"]
    types, edges, stats, truncated = traverse.expand(Path("store"), definition, {"A": "A"})
    assert types == {"A": "A", "B": "B"} and edges == [("A", "B"), ("B", "A")]
    assert truncated is False and "stopped" not in stats[-1]


def test_members_are_exported_by_default_and_can_be_turned_off(tmp_path):
    base = 'schema_version = 1\n[source]\nmanifest = "views/x/manifest.json"\n[seeds]\ntypes = ["A.B"]\n'
    assert traverse.load_definition(write(tmp_path / "on", base)).members is True
    assert traverse.load_definition(write(tmp_path / "off", base + "[output]\nmembers = false\n")).members is False


def test_callable_underlying_follows_signature_parameters_and_conventions(monkeypatch):
    relations = {
        "?t dt:signatureReturnType ?r": [("fp", "ret")],
        "?t dt:signatureParameter ?parameter . ?parameter dt:parameterType ?r": [("fp", "arg")],
        "?t dt:callingConventionType ?r": [("fp", "convention")],
        "?t dt:pointerElementType ?r": [("arg", "element")],
    }
    monkeypatch.setattr(traverse, "_pairs", lambda _store, subjects, pattern:
                        [(source, target) for source, target in relations.get(pattern, []) if source in subjects])
    assert traverse._underlying(Path("unused"), {"fp"}, False) == {"fp": {"fp", "ret", "arg", "element", "convention"}}


@pytest.mark.parametrize("attributes", [False, True])
def test_inverse_attributes_only_when_explicitly_enabled(monkeypatch, attributes):
    patterns = []
    definition = SimpleNamespace(follow=["referenced_by"] + (["attributes"] if attributes else []),
                                 max_depth=0, max_types=None, generic_arguments=False)
    monkeypatch.setattr(traverse, "_inverse_pairs", lambda _store, subjects, pattern: patterns.append(pattern) or [])
    monkeypatch.setattr(traverse, "_pairs", lambda *_: [])
    monkeypatch.setattr(traverse, "_own_names", lambda *_: {})
    traverse.expand(Path("unused"), definition, {"seed": "Seed"})
    assert any("dt:usesType" in pattern for pattern in patterns)
    assert any("dt:attributeType" in pattern for pattern in patterns) is attributes


def test_member_self_use_exports_original_edge(monkeypatch):
    relations = {"?t dt:hasMember ?r": [("root", "method")], "?t dt:usesType ?r": [("method", "root")]}
    monkeypatch.setattr(traverse, "_pairs", lambda _store, subjects, pattern:
                        [(source, target) for source, target in relations.get(pattern, []) if source in subjects])
    assert f"<method> <{traverse.DT}usesType> <root> ." in traverse.member_lines(Path("unused"), ["root"])


@pytest.fixture
def dependency_catalog(tmp_path):
    from roslyn_graph import oxigraph
    assert oxigraph.version() == "0.5.8"
    workspace = tmp_path / "workspace.toml"
    workspace.write_text("""
schema_version = 1
[tools]
oxigraph = "0.5.8"
[profiles.app]
kind = "solution"
root = "."
solution = "app.sln"
output_dir = "bin"
[profiles.app.build]
configuration = "Release"
target_framework = "net8.0"
[profiles.app.collect]
all_solution_projects = true
packages = ["p"]
[profiles.overlay]
kind = "solution"
root = "."
solution = "overlay.sln"
output_dir = "bin"
[profiles.overlay.build]
configuration = "Release"
target_framework = "net8.0"
[profiles.overlay.collect]
all_solution_projects = true
packages = ["q"]
[profiles.p]
kind = "nuget"
package = "Package.P"
version = "1.0.0"
target_framework = "net8.0"
source = "https://example.invalid/index.json"
[profiles.q]
kind = "nuget"
package = "Package.Q"
version = "1.0.0"
target_framework = "net8.0"
source = "https://example.invalid/index.json"
[profiles.external]
kind = "nuget"
package = "Package.E"
version = "1.0.0"
target_framework = "net8.0"
source = "https://example.invalid/index.json"
[policies.names]
assemblies = ["A", "P", "Q"]
[collections.app]
base = "app"
overlays = ["overlay"]
logical_type_policy = "names"
""", encoding="utf-8")
    root = tmp_path / "artifacts"
    root.mkdir()
    prefix = f"@prefix dt: <{traverse.DT}> .\n"

    def rdf(assembly, name, target=None, version="1.0.0.0", token="abc", decoy=True):
        lines = [f'<urn:asm:{assembly}> a dt:Assembly ; dt:name "{assembly}" ; dt:version "{version}" ; dt:publicKeyToken "{token}" .',
                 f'<urn:type:{name}> a dt:Class ; dt:name "{name}" ; dt:fullName "{name}" ; dt:typeKind "Class" ; '
                 f'dt:accessibility "Public" ; dt:definedInAssembly <urn:asm:{assembly}> .']
        if decoy:
            lines.append(f'<urn:type:{assembly}.Decoy> a dt:Class ; dt:fullName "{assembly}.Decoy" ; dt:typeKind "Class" ; '
                         f'dt:accessibility "Private" ; dt:definedInAssembly <urn:asm:{assembly}> .')
        if target:
            target_assembly = target.split(".")[0]
            lines += [f'<urn:type:{name}> dt:hasMember <urn:member:{name}> .',
                      f'<urn:member:{name}> a dt:Method ; dt:name "NeverCalled" ; dt:usesType <urn:type:{target}> .',
                      f'<urn:type:{target}> a dt:Class ; dt:fullName "{target}" ; dt:definedInAssembly <urn:asm:{target_assembly}> .',
                      f'<urn:asm:{target_assembly}> dt:name "{target_assembly}" ; dt:version "1.0.0.0" ; dt:publicKeyToken "abc" .']
        return prefix + "\n".join(lines)

    def publish(identifier, assembly, name, target=None, profile=None, **changes):
        directory = root / "assemblies" / identifier
        directory.mkdir(parents=True)
        data = directory / "input.ttl"
        data.write_text(rdf(assembly, name, target, version=changes.pop("version", "1.0.0.0"),
                            token=changes.pop("token", "abc")), encoding="utf-8")
        oxigraph.load(directory / "store.oxigraph", data)
        manifest = {"schemaVersion": 2, "kind": "assembly", "artifactId": identifier, "graphIri": f"urn:graph:{identifier}",
                    "workspace": {"path": str(workspace), "profile": profile or assembly.lower(), "collection": "app"},
                    "assembly": {"name": assembly, "version": "1.0.0.0"}, "origin": {"kind": "nuget"},
                    "package": {"id": f"Package.{assembly}", "version": "1.0.0", "targetFramework": "net8.0"}}
        manifest.update(changes)
        (directory / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        return directory / "manifest.json", manifest

    source = tmp_path / "source" / "store.oxigraph"
    source.parent.mkdir()
    data = tmp_path / "source.ttl"
    data.write_text(rdf("A", "A.Root", "P.Entry"), encoding="utf-8")
    oxigraph.load(source, data, "urn:graph:a")
    manifest = {"kind": "solution", "artifactId": "a", "workspace": {"path": str(workspace), "collection": "app"},
                "components": [{"artifactId": "a"}]}
    definition = SimpleNamespace(workspace=workspace, collection="app", follow=["body_types"], generic_arguments=True,
                                 max_depth=0, max_types=None)
    return SimpleNamespace(root=root, workspace=workspace, source=source, manifest=manifest,
                           definition=definition, publish=publish, rdf=rdf)


def test_registered_dependencies_follow_private_bodies_and_cycle_without_decoys(dependency_catalog):
    fixture = dependency_catalog
    fixture.publish("p-artifact", "P", "P.Entry", "Q.Leaf")
    fixture.publish("q-artifact", "Q", "Q.Leaf", "A.Root")
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, edges, _, truncated = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert set(types.values()) == {"A.Root", "P.Entry", "Q.Leaf"}
    assert len(edges) == 3 and truncated is False
    assert {pin["artifactId"] for pin in stores.additional_components} == {"p-artifact", "q-artifact"}
    assert all(Path(pin["manifestPath"]).is_absolute() for pin in stores.additional_components)
    assert {item["reason"] for item in stores.diagnostics} == {"body-coverage-unknown"}


def test_explicit_type_cap_reports_omitted_frontier(dependency_catalog):
    fixture = dependency_catalog
    fixture.publish("p-artifact", "P", "P.Entry", "Q.Leaf")
    fixture.publish("q-artifact", "Q", "Q.Leaf")
    fixture.definition.max_types = 2
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, edges, stats, truncated = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert types == {"urn:type:A.Root": "A.Root", "urn:type:P.Entry": "P.Entry"}
    assert len(types) <= fixture.definition.max_types
    assert truncated is True
    assert stats == [{"depth": 1, "added": 1, "total": 2},
                     {"depth": 2, "added": 1, "stopped": "would exceed max_types=2"}]
    assert edges == [("urn:type:A.Root", "urn:type:P.Entry"), ("urn:type:P.Entry", "urn:type:Q.Leaf")]
    traverse.evidence_lines(stores, types, fixture.definition)
    assert stores.external_references == [{"owner": "urn:member:P.Entry", "predicate": traverse.DT + "usesType",
                                          "target": "urn:type:Q.Leaf", "assembly": "urn:asm:Q",
                                          "reason": "selection-boundary"}]


def test_explicit_export_triple_cap_fails_without_output(dependency_catalog):
    import subprocess
    import sys

    fixture = dependency_catalog
    manifest = fixture.source.parent / "manifest.json"
    manifest.write_text(json.dumps(fixture.manifest | {"schemaVersion": 2}), encoding="utf-8")
    output = fixture.root / "limited.nt"
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] / "rg.py"), "export",
         "--manifest", str(manifest), "--query", "CONSTRUCT { ?s ?p ?o } WHERE { GRAPH ?g { ?s ?p ?o } }",
         "--output", str(output), "--max-triples", "1"],
        capture_output=True, text=True, encoding="utf-8")
    assert result.returncode == 1, result.stdout + result.stderr
    payload = json.loads(result.stdout)
    assert [problem["code"] for problem in payload["errors"]] == ["EXPORT_TOO_LARGE"]
    assert payload["errors"][0]["context"]["maxTriples"] == 1
    assert not output.exists()
    assert not output.with_suffix(".raw.nt").exists()
    assert not traverse.explore.context_path(output).exists()


def test_legacy_boundary_without_assembly_identity_is_reported(dependency_catalog):
    fixture = dependency_catalog
    data = fixture.root / "legacy.ttl"
    data.write_text(f'@prefix dt: <{traverse.DT}> .\n'
                    '<urn:member:A.Root> dt:usesType <urn:type:Legacy.External> .\n'
                    '<urn:type:Legacy.External> a dt:Class ; dt:fullName "Legacy.External" ; '
                    'dt:definedInAssembly <urn:asm:Legacy> .\n', encoding="utf-8")
    traverse.oxigraph.load(fixture.source, data, "urn:graph:a")
    manifest = fixture.source.parent / "manifest.json"
    manifest.write_text(json.dumps(fixture.manifest | {"schemaVersion": 2}), encoding="utf-8")
    definition = fixture.root / "legacy.graph.toml"
    definition.write_text(f'schema_version = 1\n[source]\nmanifest = "{manifest.as_posix()}"\nlogical = false\n'
                          '[seeds]\ntypes = ["A.Root"]\nimplementations = "none"\n'
                          '[expand]\nfollow = ["body_types"]\n', encoding="utf-8")
    result = traverse.run(definition, str(fixture.root), fixture.root / "out", False)
    output = Path(result["data"])
    context = json.loads(traverse.explore.context_path(output).read_text(encoding="utf-8"))
    lines = output.read_text(encoding="utf-8").splitlines()
    assert result["types"] == 1 and result["truncated"] is False
    assert f'<urn:member:A.Root> <{traverse.DT}usesType> <urn:type:Legacy.External> .' in lines
    assert f'<urn:type:Legacy.External> <{traverse.DT}definedInAssembly> <urn:asm:Legacy> .' in lines
    assert not any(line.startswith("<urn:asm:Legacy> ") for line in lines)
    diagnostic = {"reason": "external-identity-incomplete", "target": "urn:type:Legacy.External",
                  "assembly": "urn:asm:Legacy"}
    assert diagnostic in result["diagnostics"] and diagnostic in context["diagnostics"]
    assert {"owner": "urn:member:A.Root", "predicate": traverse.DT + "usesType",
            "target": "urn:type:Legacy.External", "assembly": "urn:asm:Legacy",
            "reason": "external-boundary"} in context["externalReferences"]
    assert context["coverage"] == result["coverage"]
    assert context["coverage"]["complete"] is False
    assert "external-identity-incomplete" in context["coverage"]["reasons"]


def test_catalog_corruption_does_not_hide_overlay_package(dependency_catalog):
    fixture = dependency_catalog
    fixture.publish("p-artifact", "P", "P.Entry", "Q.Leaf")
    fixture.publish("q-artifact", "Q", "Q.Leaf")
    for name, content in [("00-invalid-json", b"{"), ("01-invalid-utf8", b"\xff"), ("02-non-object", b"[]")]:
        path = fixture.root / "assemblies" / name / "manifest.json"
        path.parent.mkdir()
        path.write_bytes(content)
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert set(types.values()) == {"A.Root", "P.Entry", "Q.Leaf"}
    assert len([item for item in stores.diagnostics if item["reason"] in {"manifest-unreadable", "manifest-invalid"}]) == 3


@pytest.mark.parametrize("mismatch", ["version", "token", "framework", "workspace", "unregistered"])
def test_incompatible_artifact_never_substitutes(dependency_catalog, mismatch):
    fixture = dependency_catalog
    options = {"version": "2.0.0.0"} if mismatch == "version" else {"token": "def"} if mismatch == "token" else {}
    if mismatch == "framework":
        options["package"] = {"id": "Package.P", "targetFramework": "net9.0"}
    if mismatch == "workspace":
        options["workspace"] = {"path": str(fixture.root / "other.toml"), "profile": "p"}
    if mismatch == "unregistered":
        options["profile"] = "external"
    fixture.publish("bad-p", "P", "P.Entry", **options)
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert set(types.values()) == {"A.Root"}
    assert stores.additional_components == []


def test_ambiguous_artifacts_remain_boundary_and_known_facts_are_exported(dependency_catalog):
    fixture = dependency_catalog
    fixture.publish("p-one", "P", "P.Entry")
    fixture.publish("p-two", "P", "P.Entry")
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, edges, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    lines = traverse.evidence_lines(stores, types, fixture.definition)
    assert set(types.values()) == {"A.Root"} and not edges and not stores.additional_components
    assert any(item.get("candidateIds") == ["p-one", "p-two"] for item in stores.diagnostics)
    assert f'<urn:member:A.Root> <{traverse.DT}usesType> <urn:type:P.Entry> .' in lines
    assert f'<urn:type:P.Entry> <{traverse.DT}definedInAssembly> <urn:asm:P> .' in lines
    assert stores.external_references == [{"owner": "urn:member:A.Root", "predicate": traverse.DT + "usesType",
                                          "target": "urn:type:P.Entry", "assembly": "urn:asm:P", "reason": "ambiguous-artifacts"}]


def test_dependency_query_failure_propagates_without_partial_success(dependency_catalog, monkeypatch):
    fixture = dependency_catalog
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    def fail(*args, **kwargs):
        raise RgError.of("OXIGRAPH_FAILED", "simulated resource failure")
    monkeypatch.setattr(traverse.oxigraph, "select", fail)
    with pytest.raises(RgError, match="simulated resource failure"):
        traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})


@pytest.mark.parametrize("change", ["unsigned-reference", "culture"])
def test_same_physical_iri_cannot_hide_assembly_identity_mismatch(dependency_catalog, change):
    from roslyn_graph import oxigraph
    fixture = dependency_catalog
    fixture.publish("p", "P", "P.Entry")
    source = fixture.root / "identity-source"
    content = fixture.rdf("A", "A.Root", "P.Entry")
    if change == "unsigned-reference":
        content = content.replace('; dt:publicKeyToken "abc"', "")
    else:
        content += '\n<urn:asm:P> dt:culture "fr-FR" .'
    path = fixture.root / "identity.ttl"
    path.write_text(content, encoding="utf-8")
    oxigraph.load(source, path, "urn:graph:identity")
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert set(types.values()) == {"A.Root"}
    assert any(item["reason"] == "identity-incompatible" for item in stores.diagnostics)


def test_malformed_nested_manifest_continues_to_valid_registered_definition(dependency_catalog):
    fixture = dependency_catalog
    fixture.publish("z-valid-p", "P", "P.Entry")
    for identifier, field in [("00-build", "build"), ("01-package", "package"), ("02-assembly", "assembly"),
                              ("03-artifact", "artifactId"), ("04-graph", "graphIri")]:
        path, manifest = fixture.publish(identifier, "P", "P.Entry")
        manifest[field] = "" if field in {"artifactId", "graphIri"} else ["invalid"]
        path.write_text(json.dumps(manifest), encoding="utf-8")
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert set(types.values()) == {"A.Root", "P.Entry"}
    assert [pin["artifactId"] for pin in stores.additional_components] == ["z-valid-p"]
    assert len([item for item in stores.diagnostics if item["reason"] == "manifest-invalid"]) == 5


def test_explicit_manifest_never_falls_back_to_nearby_workspace(dependency_catalog, monkeypatch):
    fixture = dependency_catalog
    fixture.definition.manifest = "explicit/manifest.json"
    manifest = {key: value for key, value in fixture.manifest.items() if key != "workspace"}
    def unexpected(*args):
        pytest.fail("explicit manifest without recorded registration must not load a fallback workspace")
    monkeypatch.setattr(traverse.config, "load", unexpected)
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, manifest, fixture.source)
    assert not stores.candidates
    assert any(item["reason"] == "registration-unavailable" for item in stores.diagnostics)


@pytest.mark.parametrize("members", [False, True])
def test_external_boundary_witnesses_survive_member_detail_preference(dependency_catalog, members, monkeypatch):
    fixture = dependency_catalog
    fixture.definition.members = members
    path, manifest = fixture.publish("cached-but-unregistered", "P", "P.Entry", profile="external")
    manifest["assembly"]["publicKeyToken"] = "abc"
    path.write_text(json.dumps(manifest), encoding="utf-8")
    original = traverse.oxigraph.select
    def never_open_unregistered(store, *args, **kwargs):
        assert store != path.parent / "store.oxigraph"
        return original(store, *args, **kwargs)
    monkeypatch.setattr(traverse.oxigraph, "select", never_open_unregistered)
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    lines = traverse.evidence_lines(stores, types, fixture.definition)
    assert set(types.values()) == {"A.Root"}
    assert not stores.additional_components
    assert f'<urn:type:A.Root> <{traverse.DT}hasMember> <urn:member:A.Root> .' in lines
    assert f'<urn:member:A.Root> <{traverse.DT}usesType> <urn:type:P.Entry> .' in lines
    assert f'<urn:type:P.Entry> <{traverse.DT}definedInAssembly> <urn:asm:P> .' in lines
    assert not any("<urn:member:A.Root>" in line and f"<{traverse.DT}name>" in line for line in lines)
    assert stores.external_references[0]["target"] == "urn:type:P.Entry"
    assert stores.external_references[0]["reason"] == "external-boundary"
    assert stores.external_references[0]["package"] == manifest["package"]


def test_members_false_without_boundaries_keeps_existing_export_exactly(dependency_catalog):
    fixture = dependency_catalog
    fixture.definition.members = False
    fixture.publish("p", "P", "P.Entry")
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, edges, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    before = traverse.export_lines(stores, types, edges)
    assert traverse.evidence_lines(stores, types, fixture.definition) == []
    assert traverse.export_lines(stores, types, edges) == before


def test_boundary_attribute_is_opt_in_and_preserves_original_owner(dependency_catalog):
    from roslyn_graph import oxigraph
    fixture = dependency_catalog
    data = fixture.root / "attributes.ttl"
    data.write_text(f'@prefix dt: <{traverse.DT}> .\n'
                    '<urn:type:A.Root> dt:hasAttribute <urn:attr:one> .\n'
                    '<urn:attr:one> dt:attributeType <urn:type:E.Attribute> .\n'
                    '<urn:type:E.Attribute> a dt:Class ; dt:fullName "E.Attribute" ; dt:definedInAssembly <urn:asm:E> .\n'
                    '<urn:asm:E> dt:name "E" ; dt:version "1.0.0.0" .\n', encoding="utf-8")
    oxigraph.load(fixture.source, data, "urn:graph:a")
    fixture.definition.follow = []
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    assert not any("urn:type:E.Attribute" in line for line in traverse.evidence_lines(stores, {"urn:type:A.Root": "A.Root"}, fixture.definition))
    fixture.definition.follow = ["attributes"]
    lines = traverse.evidence_lines(stores, {"urn:type:A.Root": "A.Root"}, fixture.definition)
    assert f'<urn:attr:one> <{traverse.DT}attributeType> <urn:type:E.Attribute> .' in lines
    assert stores.external_references[-1]["owner"] == "urn:attr:one"


def test_boundary_wrapper_positions_and_reference_kinds_are_retained(dependency_catalog):
    from roslyn_graph import oxigraph
    fixture = dependency_catalog
    data = fixture.root / "wrappers.ttl"
    data.write_text(f'@prefix dt: <{traverse.DT}> .\n'
                    '<urn:type:A.Root> dt:hasMember <urn:member:pointer> .\n'
                    '<urn:member:pointer> dt:fieldType <urn:fp> .\n'
                    '<urn:fp> a dt:Type ; dt:typeKind "FunctionPointer" ; dt:signatureParameter <urn:param:0>, <urn:param:1> ; '
                    'dt:callingConvention "Unmanaged" ; dt:signatureReturnRefKind "Ref" .\n'
                    '<urn:param:0> a dt:Parameter ; dt:ordinal 0 ; dt:refKind "In" ; dt:parameterType <urn:array> .\n'
                    '<urn:param:1> a dt:Parameter ; dt:ordinal 1 ; dt:refKind "Out" ; dt:parameterType <urn:generic> .\n'
                    '<urn:array> dt:arrayElementType <urn:type:E.Type> ; dt:arrayRank 2 .\n'
                    '<urn:generic> dt:typeArgument <urn:arg:0>, <urn:arg:1> .\n'
                    '<urn:arg:0> dt:index 0 ; dt:type <urn:type:E.Type> .\n'
                    '<urn:arg:1> dt:index 1 ; dt:type <urn:type:E.Type> .\n'
                    '<urn:type:E.Type> a dt:Class ; dt:fullName "E.Type" ; dt:definedInAssembly <urn:asm:E> .\n'
                    '<urn:asm:E> dt:name "E" ; dt:version "1.0.0.0" .', encoding="utf-8")
    oxigraph.load(fixture.source, data, "urn:graph:a")
    fixture.definition.follow = ["member_types"]
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    lines = traverse.evidence_lines(stores, {"urn:type:A.Root": "A.Root"}, fixture.definition)
    for subject, predicate, value in [("urn:arg:0", "index", 0), ("urn:arg:1", "index", 1),
                                      ("urn:param:0", "ordinal", 0), ("urn:param:1", "ordinal", 1), ("urn:array", "arrayRank", 2)]:
        assert f'<{subject}> <{traverse.DT + predicate}> "{value}"^^<{traverse.XSD_INTEGER}> .' in lines
    assert f'<urn:param:1> <{traverse.DT}refKind> "Out" .' in lines
    assert f'<urn:fp> <{traverse.DT}callingConvention> "Unmanaged" .' in lines


def test_logical_cut_boundary_context_uses_emitted_key(dependency_catalog, monkeypatch):
    from roslyn_graph import oxigraph
    fixture = dependency_catalog
    content = fixture.rdf("P", "P.Entry", "Q.Leaf") + fixture.rdf("Q", "Q.Leaf")
    data = fixture.root / "composed.ttl"
    data.write_text(content, encoding="utf-8")
    oxigraph.load(fixture.source, data, "urn:graph:composed")
    mapping = fixture.root / "logical.ttl"
    mapping.write_text(f'<urn:type:A.Root> <{traverse.RG}logicalType> <urn:logical:A> .\n'
                       f'<urn:type:P.Entry> <{traverse.RG}logicalType> <urn:logical:P> .\n'
                       f'<urn:type:Q.Leaf> <{traverse.RG}logicalType> <urn:logical:Q> .\n', encoding="utf-8")
    oxigraph.load(fixture.source, mapping, "urn:graph:logical")
    manifest = fixture.manifest | {"schemaVersion": 2, "kind": "view", "logicalGraphIri": "urn:graph:logical",
                                   "view": {"policyAssemblies": ["A", "P", "Q"]}}
    manifest_path = fixture.source.parent / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    definition = fixture.root / "cut.graph.toml"
    definition.write_text(f'schema_version = 1\n[source]\nmanifest = "{manifest_path.as_posix()}"\nlogical = true\n'
                          '[seeds]\ntypes = ["A.Root"]\nimplementations = "none"\n'
                          '[expand]\nfollow = ["body_types"]\nmax_depth = 1\n', encoding="utf-8")
    monkeypatch.setattr(traverse.artifacts, "artifact_root", lambda _: fixture.root)
    monkeypatch.setattr(traverse.explore, "render", lambda *_: {"output": "unused.html"})
    result = traverse.run(definition, None, fixture.root / "out", False)
    output = Path(result["data"])
    context = json.loads(traverse.explore.context_path(output).read_text(encoding="utf-8"))
    assert result["types"] == 2 and result["truncated"] is True
    assert "<urn:logical:Q>" in output.read_text(encoding="utf-8")
    assert context["externalReferences"] == [{"owner": "urn:member:P.Entry", "predicate": traverse.DT + "usesType",
                                              "target": "urn:logical:Q", "assembly": "urn:asm:Q", "reason": "selection-boundary"}]


def test_admission_does_not_hide_later_type_ambiguity(dependency_catalog):
    from roslyn_graph import oxigraph
    fixture = dependency_catalog
    path, _ = fixture.publish("p-one", "P", "P.Entry", "P.Shared")
    fixture.publish("p-two", "P", "P.Shared")
    data = fixture.root / "shared.ttl"
    data.write_text(fixture.rdf("P", "P.Shared"), encoding="utf-8")
    oxigraph.load(path.parent / "store.oxigraph", data)
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert set(types.values()) == {"A.Root", "P.Entry"}
    assert any(item.get("target") == "urn:type:P.Shared" and item.get("candidateIds") == ["p-one", "p-two"]
               for item in stores.diagnostics)


def test_corrupt_candidate_store_does_not_hide_readable_registered_artifact(dependency_catalog):
    fixture = dependency_catalog
    corrupt_path, _ = fixture.publish("00-corrupt-p", "P", "P.Entry")
    (corrupt_path.parent / "store.oxigraph" / "CURRENT").write_text("not-a-manifest\n", encoding="utf-8")
    fixture.publish("valid-p", "P", "P.Entry")
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    assert set(types.values()) == {"A.Root", "P.Entry"}
    assert [pin["artifactId"] for pin in stores.additional_components] == ["valid-p"]
    assert any(item["reason"] == "store-unavailable" for item in stores.diagnostics)


def test_candidate_query_resource_failure_is_not_reported_as_ignorable_corruption(dependency_catalog, monkeypatch):
    fixture = dependency_catalog
    path, _ = fixture.publish("p", "P", "P.Entry")
    original = traverse.oxigraph.select
    def fail_candidate(store, *args, **kwargs):
        if store == path.parent / "store.oxigraph":
            raise RgError.of("OXIGRAPH_FAILED", "out of memory", stderr=["Error: Memory limit exceeded"])
        return original(store, *args, **kwargs)
    monkeypatch.setattr(traverse.oxigraph, "select", fail_candidate)
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    with pytest.raises(RgError, match="out of memory"):
        traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})


def test_generic_wrapper_is_evidence_not_movable_record(dependency_catalog):
    from roslyn_graph import oxigraph, records
    fixture = dependency_catalog
    data = fixture.root / "generic.ttl"
    data.write_text(f'@prefix dt: <{traverse.DT}> .\n'
                    '<urn:type:A.Root> dt:hasMember <urn:member:field> .\n'
                    '<urn:member:field> dt:fieldType <urn:constructed> .\n'
                    '<urn:constructed> a dt:Type ; dt:fullName "Box<A.Root>" ; dt:definedInAssembly <urn:asm:A> ; '
                    'dt:genericDefinition <urn:type:A.Box> ; dt:typeArgument <urn:arg:0> .\n'
                    '<urn:arg:0> dt:index 0 ; dt:type <urn:type:A.Root> .\n'
                    '<urn:type:A.Box> a dt:Class ; dt:fullName "A.Box<T>" ; dt:typeKind "Class" ; '
                    'dt:accessibility "Public" ; dt:definedInAssembly <urn:asm:A> .', encoding="utf-8")
    oxigraph.load(fixture.source, data, "urn:graph:a")
    fixture.definition.follow = ["member_types"]
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, edges, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    lines = traverse.export_lines(stores, types, edges) + traverse.evidence_lines(stores, types, fixture.definition)
    output = fixture.root / "generic.nt"
    output.write_text("\n".join(lines) + "\n", encoding="utf-8")
    traverse.explore.write_context(output, {"externalReferences": stores.external_references})
    graph = records.read_graph(output)
    assert graph.names == {"urn:type:A.Root": "A.Root", "urn:type:A.Box": "A.Box<T>"}
    assert any(item["target"] == "urn:constructed" for item in graph.context["externalReferences"])


@pytest.mark.parametrize("source_owns_shared", [False, True])
def test_admitted_artifact_does_not_bypass_later_identity_rejection(dependency_catalog, source_owns_shared):
    from roslyn_graph import oxigraph
    fixture = dependency_catalog
    path, _ = fixture.publish("p", "P", "P.Entry", "Q.Leaf")
    shared = fixture.root / "shared.ttl"
    shared.write_text(fixture.rdf("P", "P.Shared"), encoding="utf-8")
    oxigraph.load(path.parent / "store.oxigraph", shared)
    if source_owns_shared:
        oxigraph.load(fixture.source, shared, "urn:graph:original-own")
    path, _ = fixture.publish("q", "Q", "Q.Leaf", "P.Shared")
    conflict = fixture.root / "culture.ttl"
    conflict.write_text(f'<urn:asm:P> <{traverse.DT}culture> "fr-FR" .', encoding="utf-8")
    oxigraph.load(path.parent / "store.oxigraph", conflict)
    stores = traverse.DependencyStores.registered(fixture.root, fixture.definition, fixture.manifest, fixture.source)
    types, _, _, _ = traverse.expand(stores, fixture.definition, {"urn:type:A.Root": "A.Root"})
    expected = {"A.Root", "P.Entry", "Q.Leaf"} | ({"P.Shared"} if source_owns_shared else set())
    assert set(types.values()) == expected
    lines = traverse.evidence_lines(stores, types, fixture.definition)
    if source_owns_shared:
        assert not any(item["target"] == "urn:type:P.Shared" for item in stores.external_references)
    else:
        assert stores.reasons["urn:type:P.Shared"] == "registered-definition-unavailable"
        assert any(item["target"] == "urn:type:P.Shared" and item["reason"] == "registered-definition-unavailable"
                   for item in stores.external_references)
        assert f'<urn:member:Q.Leaf> <{traverse.DT}usesType> <urn:type:P.Shared> .' in lines
