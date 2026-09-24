from pathlib import Path

from roslyn_graph import saved

GOOD = """# Title: Implementers of an interface
# Store: app_with_current_data
# Description: every implementer, all versions.
# Parameters:
#   INTERFACE  full name of the interface (example: Contoso.Data.IRecord)
PREFIX dt: <http://dotnet.example/ontology/>
CONSTRUCT { ?t dt:implements ?i } WHERE { GRAPH ?g { ?t dt:implements ?i . ?i dt:fullName "{{INTERFACE}}" } }
"""


def workspace(tmp_path: Path) -> Path:
    ws = tmp_path / ".roslyn-graph" / "workspace.toml"
    (ws.parent / "queries").mkdir(parents=True)
    (ws.parent / "graphs").mkdir()
    ws.write_text("schema_version = 1\n", encoding="utf-8")
    return ws


def test_header_is_parsed():
    header = saved.parse_header(GOOD)
    assert header["title"] == "Implementers of an interface"
    assert header["store"] == "app_with_current_data"
    assert header["parameters"] == {"INTERFACE": {"description": "full name of the interface", "example": "Contoso.Data.IRecord"}}


def test_list_reports_queries_graphs_and_problems(tmp_path):
    ws = workspace(tmp_path)
    (ws.parent / "queries" / "implementers.rq").write_text(GOOD, encoding="utf-8")
    (ws.parent / "queries" / "broken.rq").write_text('SELECT * WHERE { ?t ?p "{{TYPE}}" }\n', encoding="utf-8")
    (ws.parent / "graphs" / "repo.graph.toml").write_text(
        'schema_version = 1\ntitle = "Repo"\n[source]\ncollection = "c"\n[seeds]\ntypes = ["A.B"]\n', encoding="utf-8")
    (ws.parent / "graphs" / "bad.graph.toml").write_text("schema_version = 1\n", encoding="utf-8")
    listing = saved.list_saved(ws)
    assert listing["type"] == "saved"
    queries = {q["name"]: q for q in listing["queries"]}
    assert queries["implementers"]["kind"] == "construct" and queries["implementers"]["problems"] == []
    assert "missing '# Title:' header" in queries["broken"]["problems"]
    assert any("TYPE is not declared" in p for p in queries["broken"]["problems"])
    graphs = {g["name"]: g for g in listing["graphs"]}
    assert graphs["repo"]["title"] == "Repo" and graphs["repo"]["store"] == "c" and not graphs["repo"]["problems"]
    assert graphs["bad"]["problems"]


def test_unused_and_example_less_parameters_are_problems(tmp_path):
    query = tmp_path / "q.rq"
    query.write_text("# Title: t\n# Parameters:\n#   A  used without example\n#   B  never used (example: x)\n"
                     'SELECT * WHERE { ?s ?p "{{A}}" }\n', encoding="utf-8")
    assert saved.describe_query(query)["problems"] == [
        "parameter A has no (example: ...) value",
        "declared parameter B is not used",
    ]


def test_missing_folders_list_nothing(tmp_path):
    ws = tmp_path / "workspace.toml"
    ws.write_text("", encoding="utf-8")
    listing = saved.list_saved(ws)
    assert listing["queries"] == [] and listing["graphs"] == []
