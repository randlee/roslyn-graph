"""records: schema subset, validator, filters, inputs and output against a small view store."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import SCRIPTS, requires_oxigraph
from roslyn_graph import oxigraph, records
from roslyn_graph.result import RgError
from roslyn_graph.util import DT, RDF_TYPE, RG, sha256_file


def codes(exc: pytest.ExceptionInfo) -> list[str]:
    return [p.code for p in exc.value.problems]


def schema(**properties) -> dict:
    return {"type": "object", "properties": properties or {"name": {"type": "string", "x-rg-field": "fullName"}}}


# ---- schema loader --------------------------------------------------------------------------


@pytest.mark.parametrize("keyword", ["pattern", "oneOf", "$ref", "maxItems", "format"])
def test_unsupported_keywords_fail(keyword):
    data = schema(name={"type": "string", "x-rg-field": "fullName", keyword: "x"})
    with pytest.raises(RgError) as info:
        records.check_schema(data)
    assert codes(info) == ["SCHEMA_UNSUPPORTED_KEYWORD"]
    assert info.value.problems[0].context["keyword"] == keyword


def test_annotations_and_x_rg_keywords_are_accepted():
    data = schema(name={"type": "string", "x-rg-field": "fullName", "description": "d", "default": "", "examples": ["A"], "x-rg-note": 1})
    data |= {"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": "x", "title": "t", "x-rg-record": "type"}
    assert records.check_schema(data) == [("name", "fullName", None)]


def test_missing_unknown_and_conflicting_bindings():
    data = schema(a={"type": "string"}, b={"type": "string", "x-rg-field": "nope"},
                  c={"const": 1, "x-rg-field": "kind"}, d={"const": "fixed"})
    with pytest.raises(RgError) as info:
        records.check_schema(data)
    assert codes(info) == ["SCHEMA_FIELD_MISSING", "SCHEMA_FIELD_UNKNOWN", "SCHEMA_FIELD_MISSING"]


@pytest.mark.parametrize("prop", [{"type": "string", "x-rg-field": "assemblies"},
                                  {"type": "array", "x-rg-field": "kind"},
                                  {"type": ["string", "null"], "x-rg-field": "projects"}])
def test_cardinality_mismatch_fails_at_load(prop):
    with pytest.raises(RgError) as info:
        records.check_schema(schema(x=prop))
    assert codes(info) == ["SCHEMA_FIELD_CARDINALITY"]


def test_several_problems_are_reported_together():
    data = {"type": "object", "x-rg-record": "member", "properties": {
        "a": {"type": "strng", "x-rg-field": "fullName"}, "b": {"x-rg-field": "files", "type": "string", "anyOf": []}},
        "required": ["zzz"]}
    with pytest.raises(RgError) as info:
        records.check_schema(data)
    assert set(codes(info)) == {"SCHEMA_INVALID", "SCHEMA_UNSUPPORTED_KEYWORD", "SCHEMA_RECORD_UNSUPPORTED", "SCHEMA_FIELD_CARDINALITY"}
    assert len(info.value.problems) >= 4


def test_record_schema_must_be_an_object_with_properties():
    with pytest.raises(RgError) as info:
        records.check_schema({"type": "array"})
    assert "SCHEMA_INVALID" in codes(info)


def test_load_schema_by_path_name_and_errors(tmp_path):
    path = tmp_path / "mine.schema.json"
    path.write_text(json.dumps(schema()))
    loaded = records.load_schema(str(path))
    assert loaded.name == "mine" and loaded.sha256 == sha256_file(path) and loaded.fields() == {"fullName"}
    with pytest.raises(RgError) as info:
        records.load_schema("no-such-built-in")
    assert codes(info) == ["SCHEMA_NOT_FOUND"]
    bad = tmp_path / "bad.json"
    bad.write_text("{")
    with pytest.raises(RgError) as info:
        records.load_schema(str(bad))
    assert codes(info) == ["SCHEMA_JSON"]


def test_every_registry_field_can_be_bound():
    props = {}
    for name, spec in records.REGISTRY.items():
        item = {"string": "string", "boolean": "boolean", "integer": "integer"}[spec.json_type]
        props[name] = ({"type": "array", "items": {"type": item}} if spec.cardinality == "list"
                       else {"type": [item, "null"] if spec.nullable else item}) | {"x-rg-field": name}
    assert [f for _, f, _ in records.check_schema(schema(**props))] == list(records.REGISTRY)


# ---- validator ------------------------------------------------------------------------------


@pytest.mark.parametrize("node, good, bad", [
    ({"type": "string"}, "a", 1),
    ({"type": "integer"}, 3, True),
    ({"type": "number"}, 1.5, "1"),
    ({"type": "boolean"}, False, 0),
    ({"type": "null"}, None, ""),
    ({"type": ["string", "null"]}, None, []),
    ({"type": "array"}, [], {}),
    ({"type": "object"}, {}, []),
    ({"enum": ["a", "b"]}, "b", "c"),
    ({"const": 7}, 7, 8),
    ({"minLength": 2}, "ab", "a"),
    ({"minItems": 1}, ["x"], []),
    ({"type": "array", "items": {"type": "string"}}, ["x"], ["x", 1]),
    ({"type": "object", "required": ["a"]}, {"a": 1}, {"b": 1}),
    ({"type": "object", "properties": {"a": {"type": "string"}}, "additionalProperties": False}, {"a": "x"}, {"a": "x", "b": 1}),
    ({"type": "object", "properties": {"a": {"type": "string"}}}, {"a": "x", "b": 1}, {"a": 1}),
    ({"type": "object", "additionalProperties": {"type": "integer"}}, {"a": 1}, {"a": "x"}),
])
def test_validator_keywords(node, good, bad):
    assert records.validate_value(good, node) == []
    assert records.validate_value(bad, node) != []


# ---- filters --------------------------------------------------------------------------------


class FakeFields:
    def __init__(self, data):
        self.data = data

    def values(self, unit, name, units):
        value = self.data[unit.key].get(name)
        return value if isinstance(value, list) else [] if value is None else [value]


UNITS = [records.Unit(k, n, [k]) for k, n in [("a", "App.Orders.Order"), ("b", "App.Orders.IOrder"), ("c", "App.Util"), ("d", "Lib.Money")]]
DATA = {
    "a": {"kind": "Class", "namespace": "App.Orders", "assemblies": ["App"], "projects": ["src/App/App.csproj"], "accessibility": "Public", "origin": "source"},
    "b": {"kind": "Interface", "namespace": "App.Orders", "assemblies": ["App"], "projects": ["src/App/App.csproj"], "accessibility": "Public", "origin": "source"},
    "c": {"kind": "Class", "namespace": "App", "assemblies": ["App"], "projects": ["src/App/App.csproj"], "accessibility": "Internal", "origin": "source"},
    "d": {"kind": "Struct", "namespace": "Lib", "assemblies": ["Lib", "Lib.Old"], "projects": [], "accessibility": "Public", "origin": "nuget"},
}


def run_filters(**filters):
    kept, removed = records.apply_filters(UNITS, FakeFields(DATA), filters)
    return [u.key for u in kept], removed


def test_repeated_values_or_and_options_and():
    assert run_filters(kind=["Class", "Struct"])[0] == ["a", "c", "d"]
    assert run_filters(kind=["Class", "Struct"], accessibility=["Public"]) == (["a", "d"], {"kind": 1, "accessibility": 1})


def test_exclude_is_applied_last_and_counted():
    kept, removed = run_filters(exclude=["*.Order"], include=["App.*"])
    assert kept == ["b", "c"] and list(removed) == ["include", "exclude"] and removed == {"include": 1, "exclude": 1}


def test_list_fields_match_any_value_and_globs_span_segments():
    assert run_filters(assembly=["Lib.Old"])[0] == ["d"]
    assert run_filters(project=["src/**"])[0] == ["a", "b", "c"]
    assert run_filters(namespace=["App"])[0] == ["c"]
    assert run_filters(origin=["nuget"])[0] == ["d"]


# ---- store fixture --------------------------------------------------------------------------

GA, GB, GN = "urn:roslyn-graph:assembly:a", "urn:roslyn-graph:assembly:b", "urn:roslyn-graph:assembly:n"
LOGICAL_GRAPH = "urn:roslyn-graph:view:v:logical-types"
T = "http://dotnet.example/type"
ORDER, BASE, BASE_OF_ORDER = f"{T}/Billing/1/Billing.Orders.Order", f"{T}/Billing/1/Billing.Orders.EntityBase%601", f"{T}/Billing/1/Billing.Orders.EntityBase%601%5BBilling.Orders.Order%5D"
MONEY_A, MONEY_B = f"{T}/Billing/1/Contoso.Shared.Money", f"{T}/Lib/2/Contoso.Shared.Money"
UTIL_B, UTIL_N = f"{T}/Lib/2/Lib.Util", f"{T}/Contoso.Lib/3/Lib.Util"
ENTITY = f"{T}/Contoso.Lib/3/Contoso.IEntity"
L_MONEY, L_UTIL = "urn:roslyn-graph:logical-type:money", "urn:roslyn-graph:logical-type:util"


def iri(v):
    return f"<{v}>"


def lit(v):
    return json.dumps(v)


def type_lines(t, asm, full, kind, ns, access="Public", **flags):
    name = full.rsplit(".", 1)[-1]
    out = [f"{iri(t)} {iri(RDF_TYPE)} {iri(DT + 'Type')} .", f"{iri(t)} {iri(RDF_TYPE)} {iri(DT + kind)} .",
           f"{iri(t)} {iri(DT + 'definedInAssembly')} {iri(asm)} .", f"{iri(t)} {iri(DT + 'fullName')} {lit(full)} .",
           f"{iri(t)} {iri(DT + 'name')} {lit(name)} .", f"{iri(t)} {iri(DT + 'typeKind')} {lit(kind)} .",
           f"{iri(t)} {iri(DT + 'accessibility')} {lit(access)} .", f"{iri(t)} {iri(DT + 'inNamespace')} {iri(ns)} ."]
    out += [f'{iri(t)} {iri(DT + k)} "{str(v).lower()}"^^<http://www.w3.org/2001/XMLSchema#boolean> .' for k, v in flags.items()]
    return out


def asm_lines(asm, name, namespaces):
    out = [f"{iri(asm)} {iri(RDF_TYPE)} {iri(DT + 'Assembly')} .", f"{iri(asm)} {iri(DT + 'name')} {lit(name)} ."]
    for ns in namespaces:
        out += [f"{iri(asm + '/ns/' + ns)} {iri(RDF_TYPE)} {iri(DT + 'Namespace')} .", f"{iri(asm + '/ns/' + ns)} {iri(DT + 'fullName')} {lit(ns)} ."]
    return out


@pytest.fixture
def view(tmp_path):
    """A view: base solution with App (source, v3) and Contoso.Lib (nuget), overlay Lib (source, v2 manifest)."""
    root = tmp_path / ".roslyn-graph"
    asm_a, asm_b, asm_n = "http://dotnet.example/assembly/Billing/1", "http://dotnet.example/assembly/Lib/2", "http://dotnet.example/assembly/Contoso.Lib/3"
    ns = lambda asm, n: f"{asm}/ns/{n}"  # noqa: E731
    graphs = {
        GA: asm_lines(asm_a, "Billing", ["Billing.Orders", "Contoso.Shared"])
        + type_lines(ORDER, asm_a, "Billing.Orders.Order", "Class", ns(asm_a, "Billing.Orders"), isSealed=True)
        + type_lines(BASE, asm_a, "Billing.Orders.EntityBase<T>", "Class", ns(asm_a, "Billing.Orders"), isAbstract=True, isGeneric=True)
        + type_lines(MONEY_A, asm_a, "Contoso.Shared.Money", "Struct", ns(asm_a, "Contoso.Shared"))
        + [f"{iri(ORDER)} {iri(DT + 'inherits')} {iri(BASE_OF_ORDER)} .", f"{iri(BASE_OF_ORDER)} {iri(DT + 'genericDefinition')} {iri(BASE)} .",
           f"{iri(BASE_OF_ORDER)} {iri(DT + 'fullName')} {lit('Billing.Orders.EntityBase<Billing.Orders.Order>')} .",
           f"{iri(ORDER)} {iri(DT + 'implements')} {iri(ENTITY)} .", f"{iri(ENTITY)} {iri(DT + 'fullName')} {lit('Contoso.IEntity')} .",
           f"{iri(ORDER)} {iri(DT + 'hasMember')} {iri(ORDER + '/member/Id')} .", f"{iri(ORDER)} {iri(DT + 'hasMember')} {iri(ORDER + '/member/Total')} ."],
        GB: asm_lines(asm_b, "Lib", ["Contoso.Shared", "Lib"])
        + type_lines(MONEY_B, asm_b, "Contoso.Shared.Money", "Struct", ns(asm_b, "Contoso.Shared"), access="Internal")
        + type_lines(UTIL_B, asm_b, "Lib.Util", "Class", ns(asm_b, "Lib"), isStatic=True),
        GN: asm_lines(asm_n, "Contoso.Lib", ["Contoso", "Lib"])
        + type_lines(ENTITY, asm_n, "Contoso.IEntity", "Interface", ns(asm_n, "Contoso"))
        + type_lines(UTIL_N, asm_n, "Lib.Util", "Class", ns(asm_n, "Lib"), isStatic=True),
        LOGICAL_GRAPH: [f"{iri(p)} {iri(RG + 'logicalType')} {iri(l)} ." for p, l in
                        [(MONEY_A, L_MONEY), (MONEY_B, L_MONEY), (UTIL_B, L_UTIL), (UTIL_N, L_UTIL)]],
    }
    store = root / "views" / "v" / "store.oxigraph"
    store.parent.mkdir(parents=True)
    for i, (graph, lines) in enumerate(graphs.items()):
        nt = tmp_path / f"g{i}.nt"
        nt.write_text("\n".join(lines) + "\n", encoding="utf-8")
        oxigraph.load(store, nt, graph)

    work = tmp_path / "work"
    (work / "Lib" / "src").mkdir(parents=True)
    (work / "Lib" / "src" / "Lib.csproj").write_text("<Project />")

    def component(graph, rel, manifest):
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        (root / rel).write_text(json.dumps(manifest))
        return {"graphIri": graph, "manifestPath": rel, "origin": manifest["origin"]}

    app = component(GA, "assemblies/source/App/a/manifest.json", {
        "identity": "assembly/v3|source|App", "origin": {"kind": "source", "id": "App", "repository": str(work / "App"), "commit": "c1", "dirtyHash": ""},
        "build": {"project": "src/Billing/Billing.csproj"}})
    nuget = component(GN, "assemblies/nuget/contoso.lib/n/manifest.json", {"identity": "assembly/v2|nuget|contoso.lib", "origin": {"kind": "nuget", "id": "Contoso.Lib"}})
    lib = component(GB, "assemblies/source/Lib/b/manifest.json", {
        "identity": "assembly/v2|source|Lib", "origin": {"kind": "source", "id": "Lib", "repository": str(work / "Lib"), "commit": "c2", "dirtyHash": ""},
        "build": {"project": "Lib/src/Lib.csproj"}})
    solution = root / "solutions" / "app" / "s" / "manifest.json"
    solution.parent.mkdir(parents=True)
    solution.write_text(json.dumps({"schemaVersion": 2, "kind": "solution", "components": [app, nuget]}))
    manifest = store.parent / "manifest.json"
    manifest.write_text(json.dumps({"schemaVersion": 2, "kind": "view", "artifactId": "v", "logicalGraphIri": LOGICAL_GRAPH,
                                    "workspace": {"collection": "app_with_lib", "profile": "app"},
                                    "baseSolution": {"manifestPath": "solutions/app/s/manifest.json"}, "overlayComponents": [lib]}))
    return manifest


def write_graph(tmp_path, manifest, context=True) -> Path:
    """A logical graph: Order, EntityBase, IEntity, and the logical Money and Util, plus a namespace node."""
    names = {ORDER: "Billing.Orders.Order", BASE: "Billing.Orders.EntityBase<T>", ENTITY: "Contoso.IEntity",
             L_MONEY: "Contoso.Shared.Money", L_UTIL: "Lib.Util"}
    lines = [f"{iri(t)} {iri(DT + 'fullName')} {lit(n)} ." for t, n in names.items()]
    lines += [f"{iri('urn:ns:Billing.Orders')} {iri(RDF_TYPE)} {iri(DT + 'Namespace')} .", f"{iri('urn:ns:Billing.Orders')} {iri(DT + 'fullName')} {lit('Billing.Orders')} .",
              f"{iri(ORDER)} {iri(DT + 'inherits')} {iri(BASE)} .", f"{iri(ORDER)} {iri(DT + 'implements')} {iri(ENTITY)} .",
              f"{iri(ORDER)} {iri(RG + 'references')} {iri(L_MONEY)} ."]
    graph = tmp_path / "out" / "billing.nt"
    graph.parent.mkdir(exist_ok=True)
    graph.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if context:
        (tmp_path / "out" / "billing.context.json").write_text(json.dumps({"format": "roslyn-graph-context/1", "generator": "graph",
                                                                           "source": {"manifest": str(manifest)}}))
    return graph


STORE_FIELDS = {"iri": "string", "fullName": "string", "name": "string", "kind": "string", "accessibility": "string",
                "namespace": ["string", "null"], "isAbstract": "boolean", "isSealed": "boolean", "isStatic": "boolean",
                "isGeneric": "boolean", "assemblies": "array", "origin": "string", "repositories": "array", "projects": "array",
                "projectDirs": "array", "baseType": ["string", "null"], "interfaces": "array", "referencesInGraph": "array",
                "referencedByInGraph": "array", "memberCount": "integer"}


def write_schema(tmp_path, fields=STORE_FIELDS, extra=None, name="test") -> Path:
    props = {f: {"type": t, "x-rg-field": f} for f, t in fields.items()} | (extra or {})
    path = tmp_path / f"{name}.schema.json"
    path.write_text(json.dumps({"type": "object", "properties": props, "required": list(props), "additionalProperties": False}))
    return path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@requires_oxigraph
def test_graph_export_of_every_store_field(tmp_path, view):
    graph = write_graph(tmp_path, view)
    out = tmp_path / "records" / "billing.jsonl"
    result = records.run(str(graph), None, None, str(write_schema(tmp_path)), out, "jsonl", {})
    assert result["count"] == 5 and result["filters"]["typesIn"] == 5
    rows = {r["fullName"]: r for r in read_jsonl(out)}
    assert list(rows) == sorted(rows)
    order = rows["Billing.Orders.Order"]
    assert list(order) == list(STORE_FIELDS)
    assert order | {} == {
        "iri": ORDER, "fullName": "Billing.Orders.Order", "name": "Order", "kind": "Class", "accessibility": "Public",
        "namespace": "Billing.Orders", "isAbstract": False, "isSealed": True, "isStatic": False, "isGeneric": False,
        "assemblies": ["Billing"], "origin": "source", "repositories": ["App"], "projects": ["src/Billing/Billing.csproj"],
        "projectDirs": ["src/Billing/"], "baseType": "Billing.Orders.EntityBase<T>", "interfaces": ["Contoso.IEntity"],
        "referencesInGraph": ["Billing.Orders.EntityBase<T>", "Contoso.IEntity", "Contoso.Shared.Money"], "referencedByInGraph": [],
        "memberCount": 2}
    # a logical type with two physical versions in two projects of two repositories
    money = rows["Contoso.Shared.Money"]
    assert money["iri"] == L_MONEY and money["assemblies"] == ["Billing", "Lib"] and money["repositories"] == ["App", "Lib"]
    assert money["projects"] == ["src/Billing/Billing.csproj", "src/Lib.csproj"]  # v2 path made repository-relative
    assert money["referencedByInGraph"] == ["Billing.Orders.Order"]
    assert rows["Lib.Util"]["origin"] == "mixed" and rows["Lib.Util"]["isStatic"] is True
    assert rows["Contoso.IEntity"]["origin"] == "nuget" and rows["Contoso.IEntity"]["repositories"] == []
    assert result["warnings"] == [{"code": "RECORD_FIELD_VARIES", "field": "accessibility", "types": 1,
                                   "message": "accessibility differs between versions of 1 type(s); the first value in sorted order was written."}]


@requires_oxigraph
def test_repository_is_ambiguous_for_a_type_in_two_repositories(tmp_path, view):
    graph = write_graph(tmp_path, view)
    with pytest.raises(RgError) as info:
        records.run(str(graph), None, None, str(write_schema(tmp_path, {"repository": ["string", "null"]})), tmp_path / "r.jsonl", "jsonl", {})
    assert codes(info) == ["RECORD_AMBIGUOUS_FIELD"]
    out = tmp_path / "r.jsonl"
    records.run(str(graph), None, None, str(write_schema(tmp_path, {"fullName": "string", "repository": ["string", "null"]})), out, "jsonl",
                {"exclude": ["Contoso.Shared.*"]})
    assert {r["fullName"]: r["repository"] for r in read_jsonl(out)}["Lib.Util"] == "Lib"


@requires_oxigraph
def test_filters_on_the_store_and_the_empty_hint(tmp_path, view):
    graph = write_graph(tmp_path, view)
    schema_path = str(write_schema(tmp_path, {"fullName": "string"}))
    out = tmp_path / "r.jsonl"
    result = records.run(str(graph), None, None, schema_path, out, "jsonl", {"origin": ["source"], "kind": ["Class", "Struct"], "project": ["src/**"]})
    assert [r["fullName"] for r in read_jsonl(out)] == ["Billing.Orders.EntityBase<T>", "Billing.Orders.Order", "Contoso.Shared.Money", "Lib.Util"]
    assert result["filters"]["removed"] == {"kind": 1, "project": 0, "origin": 0}
    with pytest.raises(RgError) as info:
        records.run(str(graph), None, None, schema_path, out, "jsonl", {"namespace": ["Billing.*"], "exclude": ["*"]})
    assert codes(info) == ["RECORDS_EMPTY"] and info.value.problems[0].hint.startswith("--namespace removed the most (3)")


@requires_oxigraph
def test_inputs_context_manifest_override_and_selection(tmp_path, view):
    schema_path = str(write_schema(tmp_path, {"fullName": "string", "iri": "string"}))
    bare = write_graph(tmp_path, view, context=False)
    with pytest.raises(RgError) as info:
        records.run(str(bare), None, None, schema_path, tmp_path / "r.jsonl", "jsonl", {})
    assert codes(info) == ["RECORDS_NO_STORE"]
    assert records.run(str(bare), None, str(view), schema_path, tmp_path / "r.jsonl", "jsonl", {})["count"] == 5
    with pytest.raises(RgError) as info:
        records.run(None, None, None, schema_path, tmp_path / "r.jsonl", "jsonl", {})
    assert codes(info) == ["RECORDS_INPUT"]

    selection = tmp_path / "sel.json"
    selection.write_text(json.dumps({"format": "roslyn-graph-selection/2", "store": str(view), "types": ["Contoso.Shared.Money", "Billing.Orders.Order"]}))
    out = tmp_path / "sel.jsonl"
    assert records.run(None, str(selection), None, schema_path, out, "jsonl", {})["count"] == 2
    assert read_jsonl(out) == [{"fullName": "Billing.Orders.Order", "iri": ORDER}, {"fullName": "Contoso.Shared.Money", "iri": L_MONEY}]
    with pytest.raises(RgError) as info:
        records.run(None, str(selection), None, str(write_schema(tmp_path, {"referencesInGraph": "array"}, name="edges")), out, "jsonl", {})
    assert codes(info) == ["RECORDS_FIELD_UNAVAILABLE"]
    selection.write_text(json.dumps({"format": "roslyn-graph-selection/2", "store": str(view), "types": ["Nope.Missing"]}))
    with pytest.raises(RgError) as info:
        records.run(None, str(selection), None, schema_path, out, "jsonl", {})
    assert codes(info) == ["RECORDS_TYPE_NOT_IN_STORE"] and info.value.problems[0].context["missing"] == ["Nope.Missing"]


@requires_oxigraph
def test_source_fields_are_unavailable_and_violations_fail(tmp_path, view):
    graph = write_graph(tmp_path, view)
    with pytest.raises(RgError) as info:
        records.run(str(graph), None, None, str(write_schema(tmp_path, {"files": "array", "locationStatus": "string"})), tmp_path / "r.jsonl", "jsonl", {})
    assert codes(info) == ["RECORDS_FIELD_UNAVAILABLE"] and info.value.problems[0].context["fields"] == ["files", "locationStatus"]
    with pytest.raises(RgError) as info:
        records.run(str(graph), None, None, str(write_schema(tmp_path, {"namespace": "string", "baseType": "string"})), tmp_path / "r.jsonl", "jsonl", {})
    assert codes(info) == ["RECORD_SCHEMA_VIOLATION"]
    assert info.value.problems[0].context["violationCount"] == 4  # every type but Order has no base type
    assert not (tmp_path / "r.jsonl").exists()


@requires_oxigraph
def test_json_format_sidecar_and_cli(tmp_path, view):
    graph = write_graph(tmp_path, view)
    schema_path = write_schema(tmp_path, {"fullName": "string"}, extra={"source": {"const": "roslyn-graph"}})
    out = tmp_path / "r.json"
    proc = subprocess.run([sys.executable, str(SCRIPTS / "rg.py"), "records", "--graph", str(graph), "--schema", str(schema_path),
                           "--output", str(out), "--format", "json", "--kind", "Class", "--kind", "Interface"],
                          capture_output=True, text=True, encoding="utf-8")
    result = json.loads(proc.stdout)
    assert proc.returncode == 0 and result["type"] == "records" and result["count"] == 4, result
    assert json.loads(out.read_text(encoding="utf-8")) == [{"fullName": n, "source": "roslyn-graph"} for n in
                                                          ["Billing.Orders.EntityBase<T>", "Billing.Orders.Order", "Contoso.IEntity", "Lib.Util"]]
    context = json.loads((tmp_path / "r.context.json").read_text(encoding="utf-8"))
    assert context["format"] == "roslyn-graph-context/1" and context["generator"] == "records" and context["recordFormat"] == "json"
    assert context["schema"] == {"name": "test", "path": str(schema_path.resolve()), "sha256": sha256_file(schema_path)}
    assert context["filters"]["options"] == {"kind": ["Class", "Interface"]} and context["filters"]["removed"] == {"kind": 1}
    assert context["input"]["kind"] == "graph" and context["source"]["manifest"] == str(view.resolve())
    assert context["repositories"] == {"App": {"repository": str(tmp_path / "work" / "App"), "commit": "c1", "dirtyHash": ""},
                                       "Lib": {"repository": str(tmp_path / "work" / "Lib"), "commit": "c2", "dirtyHash": ""}}
    again = tmp_path / "again.json"
    records.run(str(graph), None, None, str(schema_path), again, "json", {"kind": ["Class", "Interface"]})
    assert again.read_bytes() == out.read_bytes()


def test_project_path_rules(tmp_path):
    repo = tmp_path / "work" / "Repo"
    (repo / "src").mkdir(parents=True)
    (repo / "src" / "A.csproj").write_text("")
    v2 = {"identity": "assembly/v2|source|Repo", "origin": {"repository": str(repo)}}
    assert records.project_path(v2 | {"build": {"project": "Repo/src/A.csproj"}}) == "src/A.csproj"  # profile-root-relative
    assert records.project_path(v2 | {"build": {"project": "src/A.csproj"}}) == "src/A.csproj"  # profile root is the repository
    assert records.project_path(v2 | {"build": {"project": "Repo/gone/B.csproj"}}) == "gone/B.csproj"  # checkout missing the file
    assert records.project_path({"identity": "assembly/v3|source|Repo", "origin": {"repository": str(repo)},
                                 "build": {"project": "Repo/x.csproj"}}) == "Repo/x.csproj"


def test_nt_literals_are_unescaped():
    assert records._literal('"A\\"B\\u0043\\\\"') == 'A"BC\\'
    assert records._literal('"x"^^<http://www.w3.org/2001/XMLSchema#string>') == "x"
    assert records._literal("<http://e/x>") is None
