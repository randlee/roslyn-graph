"""Keep the skill documents honest: every error code, check ID and query parameter is documented."""

import ast
import re
from pathlib import Path

import pytest

from conftest import PLUGIN, SCRIPTS
from roslyn_graph import explore
from roslyn_graph.result import RgError

CREATE = PLUGIN / "skills" / "roslyn-graph-create"
EXPLORE = PLUGIN / "skills" / "roslyn-graph-explore"
SOURCES = sorted((SCRIPTS / "roslyn_graph").glob("*.py")) + [SCRIPTS / "rg.py"]
_CODE = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+|INTERNAL|USAGE")


def error_codes() -> set[str]:
    codes: set[str] = set()
    for path in SOURCES:
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                if name in {"of", "add", "Problem"} and node.args:
                    first = node.args[0]
                    candidates = [first] if isinstance(first, ast.Constant) else [first.body, first.orelse] if isinstance(first, ast.IfExp) else []
                    codes.update(c.value for c in candidates if isinstance(c, ast.Constant) and isinstance(c.value, str) and _CODE.fullmatch(c.value))
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values):
                    if isinstance(key, ast.Constant) and key.value == "code" and isinstance(value, ast.Constant):
                        codes.add(value.value)
    text = (SCRIPTS / "rg.py").read_text(encoding="utf-8")
    codes.update(re.findall(r'\\?"code\\?": \\?"([A-Z_]+)\\?"', text))
    return codes


def test_every_error_code_is_documented():
    documented = set(re.findall(r"`([A-Z][A-Z0-9_]+)`", (CREATE / "reference" / "troubleshooting.md").read_text(encoding="utf-8")))
    codes = error_codes()
    assert len(codes) > 70
    assert not codes - documented, f"undocumented error codes: {sorted(codes - documented)}"


def test_every_check_id_is_documented():
    source = (SCRIPTS / "roslyn_graph" / "validate.py").read_text(encoding="utf-8")
    ids = set(re.findall(r'(?:add|run)\("([A-Z]\d)"', source))
    documented = set(re.findall(r"^\| ([A-Z]\d) \|", (CREATE / "reference" / "validation.md").read_text(encoding="utf-8"), re.MULTILINE))
    assert ids and not ids - documented, f"undocumented checks: {sorted(ids - documented)}"


def test_workflow_and_reference_links_resolve():
    for md in list(CREATE.rglob("*.md")) + list(EXPLORE.rglob("*.md")):
        for target in re.findall(r"\]\(([^)#]+)\)", md.read_text(encoding="utf-8")):
            if not target.startswith("http"):
                assert (md.parent / target).exists(), f"{md.relative_to(PLUGIN)} links to missing {target}"


@pytest.mark.parametrize("query", sorted((EXPLORE / "queries").glob("*.rq")), ids=lambda p: p.name)
def test_library_queries_use_the_saved_query_header(query):
    from roslyn_graph import saved

    described = saved.describe_query(query)
    assert re.search(r"^\s*(CONSTRUCT|SELECT)\b", query.read_text(encoding="utf-8"), re.MULTILINE | re.IGNORECASE)
    assert described["title"] and described["problems"] == [], described["problems"]


def test_graph_definition_docs_match_unlimited_defaults_and_export_options():
    from roslyn_graph import traverse

    doc = (EXPLORE / "reference" / "graph-definitions.md").read_text(encoding="utf-8")
    assert "omitted = until closure" in doc
    assert "`--max-triples`" in doc and "`--unbounded`" in doc
    for relation in ("constraints", "enclosing_type", "body_types"):
        assert relation in traverse.FOLLOW and f"`{relation}`" in doc


def test_graph_and_records_docs_describe_pinned_components_and_external_evidence():
    for name in ("graph-definitions.md", "records.md"):
        doc = (EXPLORE / "reference" / name).read_text(encoding="utf-8")
        for field in ("additionalComponents", "artifactId", "graphIri", "manifestPath", "externalReferences"):
            assert f"`{field}`" in doc, f"{name} omits {field}"
        assert "incomplete" in doc


def test_params_are_substituted_and_escaped():
    text = explore.read_query('SELECT * WHERE { ?t <p> "{{TYPE}}" . ?u <q> "{{TYPE}}" }', None, ['TYPE=A"B\\C'])
    assert text == 'SELECT * WHERE { ?t <p> "A\\"B\\\\C" . ?u <q> "A\\"B\\\\C" }'


def test_missing_and_malformed_params():
    with pytest.raises(RgError) as info:
        explore.read_query('"{{A}}" "{{B}}"', None, ["A=1"])
    assert info.value.problems[0].code == "QUERY_PARAM_MISSING" and info.value.problems[0].context["missing"] == ["B"]
    with pytest.raises(RgError) as info:
        explore.read_query("x", None, ["lower=1"])
    assert info.value.problems[0].code == "QUERY_PARAM_INVALID"


def test_records_reference_matches_the_field_registry_and_filters():
    from roslyn_graph import records

    doc = (EXPLORE / "reference" / "records.md").read_text(encoding="utf-8")
    table = doc.split("## Field registry", 1)[1].split("\n## ", 1)[0]
    rows = {m[0]: (m[1], m[2]) for m in re.findall(r"^\| `(\w+)` \| ([a-z ]+) \| (\w+) \|", table, re.MULTILINE)}
    expected = {}
    for f in records.REGISTRY.values():
        value_type = f"list of {f.json_type}" if f.cardinality == "list" else f.json_type + (" or null" if f.nullable else "")
        expected[f.name] = (value_type, f.needs)
    assert rows == expected
    for option, _, _ in records.FILTERS:
        assert f"`--{option} " in doc, f"--{option} is not documented"


@pytest.mark.parametrize("schema", sorted((EXPLORE / "schemas").glob("*.schema.json")), ids=lambda p: p.name)
def test_built_in_schemas_load(schema):
    from roslyn_graph import records

    loaded = records.load_schema(schema.name.removesuffix(".schema.json"))
    assert loaded.name == schema.name.removesuffix(".schema.json") and loaded.fields() <= set(records.REGISTRY)
