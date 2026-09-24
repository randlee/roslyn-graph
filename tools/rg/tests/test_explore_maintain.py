import json
from pathlib import Path

import pytest

from roslyn_graph import artifacts, build, discover, explore, maintain, ontology
from roslyn_graph.result import RgError
from roslyn_graph.util import DT, RDF_TYPE, RG

P1, P2 = "http://dotnet.example/type/Lib/1.0.0.0/Lib.IThing", "http://dotnet.example/type/Lib/2.0.0.0/Lib.IThing"


# ---- projection -----------------------------------------------------------------------------

def test_projection_links_versions_to_one_logical_type():
    rows = [("Lib", [{"type": P1, "fullName": "Lib.IThing", "name": "IThing"}]),
            ("Lib", [{"type": P2, "fullName": "Lib.IThing", "name": "IThing"}])]
    lines, links, logical = build.projection_lines("urn:v", "urn:s", "policy", rows)
    assert (links, logical) == (2, 1)
    target = build.logical_iri("Lib", "Lib.IThing")
    assert f"<{P1}> <{RG}logicalType> <{target}> ." in lines and f"<{P2}> <{RG}logicalType> <{target}> ." in lines
    assert not any("sameAs" in line for line in lines)


def test_projection_refuses_ambiguous_physical_types():
    rows = [("Lib", [{"type": P1, "fullName": "Lib.IThing"}]), ("Lib", [{"type": P1, "fullName": "Lib.IThing"}])]
    with pytest.raises(RgError) as info:
        build.projection_lines("urn:v", "urn:s", "p", rows)
    assert info.value.problems[0].code == "PHYSICAL_IDENTITY_AMBIGUOUS"


def test_unique_nt_lines(tmp_path):
    nt = tmp_path / "a.nt"
    nt.write_text("<a> <b> <c> .\n<a> <b> <c> .\n\n# comment\n<a> <b> \"d\" .\n")
    assert build.unique_nt_lines(nt) == 2


# ---- explore --------------------------------------------------------------------------------

def test_collapse_rewrites_subjects_and_objects_and_dedupes():
    lines = [
        f"<{P1}> <{RDF_TYPE}> <{DT}Interface> .",
        f"<{P2}> <{RDF_TYPE}> <{DT}Interface> .",
        f'<{P2}> <{DT}name> "IThing" .',
        f"<http://x/Impl> <{DT}implements> <{P1}> .",
    ]
    out = explore.collapse(lines, {P1: "urn:l", P2: "urn:l"})
    assert out == [f"<urn:l> <{RDF_TYPE}> <{DT}Interface> .", '<urn:l> <http://dotnet.example/ontology/name> "IThing" .',
                   f"<http://x/Impl> <{DT}implements> <urn:l> ."]


def test_summarize_counts_kinds_and_edges():
    lines = [f"<a> <{RDF_TYPE}> <{DT}Interface> .", f"<b> <{RDF_TYPE}> <{DT}Class> .", f"<b> <{DT}implements> <a> ."]
    assert explore.summarize(lines) == {"triples": 3, "nodesByKind": {"Interface": 1, "Class": 1}, "edges": {"implements": 1, "inherits": 0}}


def test_render_builds_a_self_contained_explorer_page(tmp_path):
    data = tmp_path / "g.nt"
    data.write_text(f"<a> <{RDF_TYPE}> <{DT}Interface> .\n")
    result = explore.render("explorer", data, tmp_path / "g.html", 'Interfaces "P3"')
    page = (tmp_path / "g.html").read_text(encoding="utf-8")
    assert result["type"] == "page" and result["dataTriples"] == 1
    assert '<script src="rdf-graph-parser.js">' not in page and "RdfGraphParser" in page
    assert 'id="roslyn-graph-data" data-title="Interfaces &quot;P3&quot;"' in page
    assert "loadEmbeddedGraph" in page


def test_render_rejects_unknown_visualizers_and_unsafe_data(tmp_path):
    data = tmp_path / "g.nt"
    data.write_text('<a> <b> "</script>" .\n')
    with pytest.raises(RgError):
        explore.render("nope", data, tmp_path / "x.html", "t")
    with pytest.raises(RgError) as info:
        explore.render("explorer", data, tmp_path / "x.html", "t")
    assert info.value.problems[0].code == "EXPORT_UNSAFE"


def test_every_registered_visualizer_has_its_files():
    for name, entry in explore.registry().items():
        folder = explore.resource("visualizers", name)
        assert (folder / entry["template"]).is_file()
        for script in entry.get("inlineScripts", []):
            assert (folder / script).is_file()


def test_export_requires_construct(tmp_path):
    with pytest.raises(RgError) as info:
        explore.export(tmp_path / "manifest.json", "SELECT * WHERE {}", tmp_path / "o.nt", True, False)
    assert info.value.problems[0].code == "EXPORT_NEEDS_CONSTRUCT"


def test_read_query_needs_exactly_one_source(tmp_path):
    with pytest.raises(RgError):
        explore.read_query(None, None)
    q = tmp_path / "q.rq"
    q.write_text("SELECT 1")
    assert explore.read_query(None, str(q)) == "SELECT 1"


# ---- maintain -------------------------------------------------------------------------------

def put(root: Path, rel: str, manifest: dict) -> Path:
    directory = root / rel
    directory.mkdir(parents=True)
    (directory / "manifest.json").write_text(json.dumps(manifest))
    return directory


def component(artifact_id: str, name: str, version: str, triples: int, commit: str = "c1", manifest_path: str = "") -> dict:
    return {"artifactId": artifact_id, "manifestPath": manifest_path, "origin": {"kind": "source", "id": "Repo", "commit": commit},
            "assembly": {"name": name, "version": version}, "tripleCount": triples}


def test_compare_reports_added_removed_and_changed():
    old = {"artifactId": "o", "solution": {"commit": "c1"}, "store": {"tripleCount": 100},
           "components": [component("1", "A", "1.0", 10), component("2", "B", "1.0", 20)]}
    new = {"artifactId": "n", "solution": {"commit": "c2"}, "store": {"tripleCount": 130},
           "components": [component("1", "A", "1.0", 10), component("3", "B", "1.1", 25, "c2"), component("4", "C", "1.0", 5)]}
    diff = maintain.compare(old, new)
    assert [a["assembly"] for a in diff["added"]] == ["C"] and diff["removed"] == []
    assert diff["changed"][0]["tripleDelta"] == 5 and diff["unchanged"] == 1 and diff["tripleDelta"] == 30


def test_inventory_statuses_and_reference_checked_removal(tmp_path):
    root = tmp_path / ".roslyn-graph"
    v2 = {"schemaVersion": 2}
    put(root, "assemblies/source/Repo/aaaa", v2 | {"kind": "assembly", "artifactId": "a" * 64, "createdUtc": "1"})
    put(root, "assemblies/source/Repo/bbbb", v2 | {"kind": "assembly", "artifactId": "b" * 64, "createdUtc": "1"})
    old = v2 | {"kind": "solution", "artifactId": "o" * 64, "createdUtc": "2", "workspace": {"profile": "p", "collection": "c"},
                "components": [{"manifestPath": "assemblies/source/Repo/bbbb/manifest.json"}]}
    new = v2 | {"kind": "solution", "artifactId": "n" * 64, "createdUtc": "3", "workspace": {"profile": "p", "collection": "c"},
                "components": [{"manifestPath": "assemblies/source/Repo/aaaa/manifest.json"}]}
    put(root, "solutions/r/s/oooo", old)
    put(root, "solutions/r/s/nnnn", new)
    put(root, "views/legacy", {"schemaVersion": 1, "artifactId": "l" * 64})
    status = {e["path"]: e["status"] for e in maintain.inventory(root)["artifacts"]}
    assert status == {"assemblies/source/Repo/aaaa": "in-use", "assemblies/source/Repo/bbbb": "in-use",
                      "solutions/r/s/nnnn": "latest", "solutions/r/s/oooo": "superseded", "views/legacy": "legacy"}
    with pytest.raises(RgError) as info:
        maintain.remove(root, "assemblies/source/Repo/bbbb", confirm=True)
    assert info.value.problems[0].code == "REMOVE_REFERENCED"
    assert maintain.remove(root, "solutions/r/s/oooo", confirm=False)["removed"] is False
    assert maintain.remove(root, "solutions/r/s/oooo", confirm=True)["removed"] is True
    assert maintain.remove(root, "assemblies/source/Repo/bbbb", confirm=True)["removed"] is True
    assert maintain.previous(root, "solution", "p", "x" * 64)[1]["artifactId"] == "n" * 64


def test_remove_only_touches_artifacts(tmp_path):
    root = tmp_path / ".roslyn-graph"
    (root / "staging" / "x").mkdir(parents=True)
    with pytest.raises(RgError) as info:
        maintain.remove(root, "staging/x", confirm=True)
    assert info.value.problems[0].code == "REMOVE_OUTSIDE_ARTIFACTS"


# ---- ontology and discovery -----------------------------------------------------------------

def test_ontology_parses_and_generates_every_term():
    prefixes, terms = ontology.load()
    assert prefixes["dt"] == DT and prefixes["rg"] == RG
    text = ontology.markdown()
    for term in terms:
        if term.kind in {"class", "property"}:
            assert f"`{term.curie}`" in text


def test_ontology_parser_rejects_unterminated_statements():
    with pytest.raises(RgError):
        ontology.parse("@prefix dt: <http://x/> .\ndt:A a rdfs:Class ;\n", "bad.ttl")


def test_import_chain_honors_empty_guards(tmp_path):
    sln = tmp_path / "Sln"
    sln.mkdir()
    (sln / "Common.targets").write_text('<Project><Import Project="$(MSBuildThisFileDirectory)..\\Shared\\Real.targets" /></Project>')
    (tmp_path / "Shared").mkdir()
    (tmp_path / "Shared" / "Real.targets").write_text("<Project />")
    (tmp_path / ".build").mkdir()
    (tmp_path / ".build" / "Common.targets").write_text("<Project />")
    project = tmp_path / "Proj" / "P.csproj"
    project.parent.mkdir()
    project.write_text(
        "<Project><PropertyGroup Condition=\"'$(SolutionDir)' == ''\"><SolutionDir>$(MSBuildThisFileDirectory)..\\.build\\</SolutionDir>"
        '</PropertyGroup><Import Project="$(SolutionDir)Common.targets" /><Import Project="$(Unknown)X.targets" /></Project>'
    )
    found, unresolved = discover.import_chain(project, sln)
    assert found == [(sln / "Common.targets").resolve(), (tmp_path / "Shared" / "Real.targets").resolve()]
    assert unresolved == {"$(Unknown)X.targets"}


def test_collapse_merges_members_of_a_type_across_versions():
    m1, m2 = f"{P1}/member/Run%28%29", f"{P2}/member/Run%28%29"
    lines = [f"<{P1}> <{DT}hasMember> <{m1}> .", f"<{P2}> <{DT}hasMember> <{m2}> .",
             f'<{m1}> <{DT}name> "Run" .', f'<{m2}> <{DT}name> "Run" .',
             f"<{m1}/param/0> <{DT}parameterType> <{P2}> ."]
    out = explore.collapse(lines, {P1: "urn:l", P2: "urn:l"})
    assert out == [f"<urn:l> <{DT}hasMember> <urn:l/member/Run%28%29> .",
                   '<urn:l/member/Run%28%29> <http://dotnet.example/ontology/name> "Run" .',
                   f"<urn:l/member/Run%28%29/param/0> <{DT}parameterType> <urn:l> ."]


def test_render_embeds_the_context_sidecar_safely(tmp_path):
    data = tmp_path / "g.nt"
    data.write_text(f"<a> <{RDF_TYPE}> <{DT}Interface> .\n")
    explore.write_context(data, {"generator": "export", "query": {"text": 'CONSTRUCT {} WHERE { FILTER("</script>" != "") }'}})
    result = explore.render("explorer", data, tmp_path / "g.html", "t")
    page = (tmp_path / "g.html").read_text(encoding="utf-8")
    block = page.split('<script type="application/json" id="roslyn-graph-context">\n', 1)[1].split("\n</script>", 1)[0]
    assert "</script" not in block
    context = json.loads(block.replace("<\/", "</"))
    assert context["format"] == "roslyn-graph-context/1" and context["query"]["text"].count("</script>") == 1
    assert result["context"] == str(explore.context_path(data))
    assert page.index('id="roslyn-graph-context"') < page.index('id="roslyn-graph-data"')


def test_source_info_names_the_store(tmp_path):
    manifest = tmp_path / "views" / "abc" / "manifest.json"
    info = explore.source_info(manifest, {"kind": "view", "artifactId": "a" * 64, "workspace": {"collection": "c", "profile": "p"}})
    assert info["kind"] == "view" and info["collection"] == "c" and info["store"].endswith("store.oxigraph")
