"""Schema-driven record export: one JSON object per type of a completed query graph.

Input is a graph (`rg.py graph` / `rg.py export` output, `.nt` with its `.context.json`) or an explorer selection
(`roslyn-graph-selection/2`). Filters narrow the types, a JSON Schema (a small 2020-12 subset whose properties
name registry fields with `x-rg-field`) says which fields each record carries, and only the bound fields are
queried. Records are validated against the schema and written as JSON Lines (or one JSON array), sorted by full
name, with a provenance sidecar. See the explore skill's reference/records.md.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import artifacts, explore, oxigraph, sources
from .result import ProblemList, RgError
from .traverse import BATCH, glob_regex
from .util import DT, RDF_TYPE, RG, nt_literal, resource, sha256_file

SELECTION_FORMAT = "roslyn-graph-selection/2"
MAX_VIOLATIONS = 20
ROOT_DIR = "./"  # projectDirs of a project at the repository root

# ---- field registry -------------------------------------------------------------------------


@dataclass(frozen=True)
class FieldSpec:
    name: str
    cardinality: str  # "scalar" or "list"
    json_type: str  # JSON Schema type of the value (of each item, for lists)
    nullable: bool = False
    needs: str = "store"  # store | manifest | graph | source
    doc: str = ""


REGISTRY: dict[str, FieldSpec] = {f.name: f for f in [
    FieldSpec("iri", "scalar", "string", needs="graph", doc="the type IRI as it appears in the input (logical or physical)"),
    FieldSpec("fullName", "scalar", "string", doc="`dt:fullName`"),
    FieldSpec("name", "scalar", "string", doc="`dt:name`"),
    FieldSpec("kind", "scalar", "string", doc="`dt:typeKind`"),
    FieldSpec("accessibility", "scalar", "string", doc="`dt:accessibility`"),
    FieldSpec("namespace", "scalar", "string", nullable=True, doc="full name of `dt:inNamespace`"),
    FieldSpec("isAbstract", "scalar", "boolean", doc="`dt:isAbstract` (false when absent)"),
    FieldSpec("isSealed", "scalar", "boolean", doc="`dt:isSealed` (false when absent)"),
    FieldSpec("isStatic", "scalar", "boolean", doc="`dt:isStatic` (false when absent)"),
    FieldSpec("isGeneric", "scalar", "boolean", doc="`dt:isGeneric` (false when absent)"),
    FieldSpec("assemblies", "list", "string", doc="names of the defining assemblies (several for a logical type)"),
    FieldSpec("origin", "scalar", "string", needs="manifest", doc="`source`, `nuget`, or `mixed` (a logical type with both)"),
    FieldSpec("repository", "scalar", "string", nullable=True, needs="manifest",
              doc="repository ID of the source project; null for NuGet. A type spanning repositories fails with `RECORD_AMBIGUOUS_FIELD`"),
    FieldSpec("repositories", "list", "string", needs="manifest", doc="repository IDs"),
    FieldSpec("projects", "list", "string", needs="manifest", doc="repository-relative project paths"),
    FieldSpec("projectDirs", "list", "string", needs="manifest", doc="directories of `projects`, with a trailing `/` (`./` for a project at the repository root)"),
    FieldSpec("files", "list", "string", needs="source", doc="repository-relative declaring files (source locator)"),
    FieldSpec("locationStatus", "scalar", "string", needs="source", doc="`found`, `compiler-generated`, `generated` or `nuget`"),
    FieldSpec("baseType", "scalar", "string", nullable=True, doc="full name of the base type's generic definition"),
    FieldSpec("interfaces", "list", "string", doc="full names of the implemented interfaces' generic definitions"),
    FieldSpec("referencesInGraph", "list", "string", needs="graph", doc="full names this type points to in the input graph"),
    FieldSpec("referencedByInGraph", "list", "string", needs="graph", doc="full names pointing to this type in the input graph"),
    FieldSpec("memberCount", "scalar", "integer", doc="number of `dt:hasMember` (the largest version for a logical type)"),
]}

# ---- schema ---------------------------------------------------------------------------------

ANNOTATIONS = {"$schema", "$id", "title", "description", "default", "examples"}
VALIDATION = {"type", "properties", "required", "additionalProperties", "items", "enum", "const", "minItems", "minLength"}
JSON_TYPES = {"string", "number", "integer", "boolean", "array", "object", "null"}


@dataclass
class Schema:
    name: str
    path: Path
    sha256: str
    data: dict[str, Any]
    bindings: list[tuple[str, str | None, Any]]  # (property, registry field or None, const value)

    def fields(self) -> set[str]:
        return {f for _, f, _ in self.bindings if f}


def _types(node: dict[str, Any]) -> set[str]:
    t = node.get("type")
    return set(t) if isinstance(t, list) else {t} if isinstance(t, str) else set()


def _check_node(node: Any, where: str, problems: ProblemList) -> None:
    if not isinstance(node, dict):
        problems.add("SCHEMA_INVALID", f"{where}: a schema must be an object.", where=where)
        return
    for key in node:
        if key not in ANNOTATIONS and key not in VALIDATION and not key.startswith("x-rg-"):
            problems.add("SCHEMA_UNSUPPORTED_KEYWORD", f"{where}: keyword {key!r} is not supported.",
                         f"Supported: {', '.join(sorted(VALIDATION))}; annotations {', '.join(sorted(ANNOTATIONS))} and x-rg-*.",
                         where=where, keyword=key)
    if "type" in node:
        t = node["type"]
        names = t if isinstance(t, list) else [t]
        if not names or not all(isinstance(n, str) and n in JSON_TYPES for n in names):
            problems.add("SCHEMA_INVALID", f"{where}: type must be one of {sorted(JSON_TYPES)} or a list of them.", where=where)
    if "enum" in node and (not isinstance(node["enum"], list) or not node["enum"]):
        problems.add("SCHEMA_INVALID", f"{where}: enum must be a non-empty array.", where=where)
    for key in ("minItems", "minLength"):
        if key in node and (not isinstance(node[key], int) or isinstance(node[key], bool) or node[key] < 0):
            problems.add("SCHEMA_INVALID", f"{where}: {key} must be a non-negative integer.", where=where)
    if "required" in node:
        req = node["required"]
        if not isinstance(req, list) or not all(isinstance(r, str) for r in req):
            problems.add("SCHEMA_INVALID", f"{where}: required must be an array of property names.", where=where)
        else:
            for name in req:
                if name not in (node.get("properties") or {}):
                    problems.add("SCHEMA_INVALID", f"{where}: required property {name!r} is not in properties.", where=where)
    if "properties" in node:
        if not isinstance(node["properties"], dict):
            problems.add("SCHEMA_INVALID", f"{where}: properties must be an object.", where=where)
        else:
            for name, sub in node["properties"].items():
                _check_node(sub, f"{where}/properties/{name}", problems)
    if "items" in node:
        _check_node(node["items"], f"{where}/items", problems)
    if "additionalProperties" in node and not isinstance(node["additionalProperties"], bool):
        _check_node(node["additionalProperties"], f"{where}/additionalProperties", problems)


def check_schema(data: Any, label: str = "schema") -> list[tuple[str, str | None, Any]]:
    """Validate a record schema and its field bindings; every problem is reported at once."""
    problems = ProblemList()
    _check_node(data, "#", problems)
    if not isinstance(data, dict):
        problems.raise_if_any()
    if data.get("type") != "object" or not isinstance(data.get("properties"), dict) or not data.get("properties"):
        problems.add("SCHEMA_INVALID", f"{label}: a record schema is an object schema with at least one property.")
    record = data.get("x-rg-record", "type")
    if record != "type":
        problems.add("SCHEMA_RECORD_UNSUPPORTED", f"{label}: x-rg-record {record!r} is not supported.", "Use \"type\" (one record per type).")
    bindings: list[tuple[str, str | None, Any]] = []
    for prop, node in (data.get("properties") or {}).items() if isinstance(data.get("properties"), dict) else []:
        if not isinstance(node, dict):
            continue
        where = f"#/properties/{prop}"
        bound, has_const = node.get("x-rg-field"), "const" in node
        if (bound is not None) == has_const:
            problems.add("SCHEMA_FIELD_MISSING", f"{where}: set exactly one of x-rg-field or const.",
                         f"Registry fields: {', '.join(REGISTRY)}.", where=where)
            continue
        if has_const:
            bindings.append((prop, None, node["const"]))
            continue
        spec = REGISTRY.get(bound) if isinstance(bound, str) else None
        if spec is None:
            problems.add("SCHEMA_FIELD_UNKNOWN", f"{where}: x-rg-field {bound!r} is not a registry field.",
                         f"Registry fields: {', '.join(REGISTRY)}.", where=where, field=bound)
            continue
        types = _types(node)
        if types and (spec.cardinality == "list") != ("array" in types):
            problems.add("SCHEMA_FIELD_CARDINALITY",
                         f"{where}: field {bound!r} is a {spec.cardinality} but the property type is {sorted(types)}.",
                         "Bind list fields to array properties and scalar fields to non-array properties.", where=where, field=bound)
            continue
        bindings.append((prop, bound, None))
    problems.raise_if_any()
    return bindings


def load_schema(name_or_path: str) -> Schema:
    """A built-in schema name (schemas/<name>.schema.json in the explore skill) or a path to a .json file."""
    if "/" in name_or_path or "\\" in name_or_path or name_or_path.endswith(".json"):
        path = Path(name_or_path)
    else:
        try:
            path = resource("schemas", f"{name_or_path}.schema.json")
        except RgError as exc:
            raise RgError.of("SCHEMA_NOT_FOUND", f"No built-in schema named {name_or_path!r}.",
                             "Pass a schema file path, or a name from the explore skill's schemas/ folder.") from exc
    if not path.is_file():
        raise RgError.of("SCHEMA_NOT_FOUND", f"{path} does not exist.")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RgError.of("SCHEMA_JSON", f"{path}: {exc}") from exc
    bindings = check_schema(data, str(path))
    return Schema(str(data.get("title") or path.name.removesuffix(".json").removesuffix(".schema")), path.resolve(),
                  sha256_file(path), data, bindings)


def _type_ok(value: Any, t: str) -> bool:
    if t == "null":
        return value is None
    if t == "boolean":
        return isinstance(value, bool)
    if t == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if t == "number":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    return isinstance(value, {"string": str, "array": list, "object": dict}[t])


def validate_value(value: Any, node: dict[str, Any], where: str = "") -> list[str]:
    """Violations of one value against a schema node (the supported keyword subset)."""
    out: list[str] = []
    here = where or "record"
    types = _types(node)
    if types and not any(_type_ok(value, t) for t in types):
        return [f"{here}: expected {'/'.join(sorted(types))}, got {type(value).__name__}"]
    if "const" in node and value != node["const"]:
        out.append(f"{here}: must be {node['const']!r}")
    if "enum" in node and value not in node["enum"]:
        out.append(f"{here}: {value!r} is not one of {node['enum']}")
    if isinstance(value, str) and len(value) < node.get("minLength", 0):
        out.append(f"{here}: shorter than minLength {node['minLength']}")
    if isinstance(value, list):
        if len(value) < node.get("minItems", 0):
            out.append(f"{here}: fewer than minItems {node['minItems']}")
        if isinstance(node.get("items"), dict):
            for i, item in enumerate(value):
                out += validate_value(item, node["items"], f"{here}[{i}]")
    if isinstance(value, dict):
        props = node.get("properties") or {}
        for name in node.get("required", []):
            if name not in value:
                out.append(f"{here}: missing required {name!r}")
        extra = node.get("additionalProperties", True)
        for name, item in value.items():
            if name in props:
                out += validate_value(item, props[name], f"{where}.{name}" if where else name)
            elif extra is False:
                out.append(f"{here}: unexpected property {name!r}")
            elif isinstance(extra, dict):
                out += validate_value(item, extra, f"{where}.{name}" if where else name)
    return out


# ---- inputs ---------------------------------------------------------------------------------

_LITERAL = re.compile(r'^"((?:[^"\\]|\\.)*)"(?:\^\^<[^>]*>|@[\w-]+)?$')
_ESCAPES = {"t": "\t", "n": "\n", "r": "\r", '"': '"', "\\": "\\", "b": "\b", "f": "\f", "'": "'"}
_NOT_TYPES = {DT + c for c in ("Namespace", "Assembly", "Member", "Method", "Constructor", "Property", "Field", "Event",
                               "Parameter", "TypeParameter", "Attribute", "UnsafeFact")}
_EDGE_PREDICATES = {DT + "inherits", DT + "implements", RG + "references"}


def _literal(token: str) -> str | None:
    match = _LITERAL.match(token)
    if not match:
        return None
    return re.sub(r"\\(u[0-9A-Fa-f]{4}|U[0-9A-Fa-f]{8}|.)",
                  lambda m: chr(int(m.group(1)[1:], 16)) if m.group(1)[0] in "uU" and len(m.group(1)) > 1 else _ESCAPES.get(m.group(1), m.group(1)),
                  match.group(1))


@dataclass
class GraphInput:
    kind: str  # "graph" or "selection"
    path: Path
    store_manifest: str | None
    names: dict[str, str] = field(default_factory=dict)  # graph: subject IRI -> full name; selection: name -> name
    edges: set[tuple[str, str]] = field(default_factory=set)  # graph subjects
    context: dict[str, Any] | None = None


def read_graph(path: Path) -> GraphInput:
    if not path.is_file():
        raise RgError.of("RECORDS_INPUT", f"{path} does not exist.")
    names: dict[str, str] = {}
    classes: dict[str, set[str]] = {}
    triples: list[tuple[str, str, str]] = []
    try:
        with open(path, encoding="utf-8") as handle:  # streamed: graphs can be large
            for line in handle:
                match = explore._NT_LINE.match(line.strip())
                if not match:
                    continue
                s, p, o = match.groups()
                if not s.startswith("<"):
                    continue
                s, p = s[1:-1], p[1:-1]
                if p == DT + "fullName":
                    value = _literal(o)
                    if value is not None:
                        names[s] = value
                elif p == RDF_TYPE and o.startswith("<"):
                    classes.setdefault(s, set()).add(o[1:-1])
                elif p in _EDGE_PREDICATES and o.startswith("<"):
                    triples.append((s, p, o[1:-1]))
    except (OSError, UnicodeDecodeError) as exc:
        raise RgError.of("RECORDS_INPUT", f"Cannot read {path} as UTF-8 N-Triples: {exc}",
                         "Pass a .nt file written by rg.py graph or rg.py export.", path=str(path)) from exc
    names = {s: n for s, n in names.items() if not classes.get(s, set()) & _NOT_TYPES}
    edges = {(s, o) for s, _, o in triples if s in names and o in names and s != o}
    sidecar = explore.context_path(path)
    try:
        context = json.loads(sidecar.read_text(encoding="utf-8")) if sidecar.is_file() else None
    except (OSError, ValueError) as exc:  # JSONDecodeError and UnicodeDecodeError
        raise RgError.of("RECORDS_INPUT", f"{sidecar} is not a readable context file: {exc}",
                         f"Regenerate {path.name} with rg.py graph or rg.py export, or delete the broken sidecar and pass --manifest.",
                         path=str(sidecar)) from exc
    manifest = ((context or {}).get("source") or {}).get("manifest")
    external = {entry["target"] for entry in (context or {}).get("externalReferences", [])}
    names = {key: name for key, name in names.items() if key not in external}
    edges = {(owner, target) for owner, target in edges if owner in names and target in names}
    return GraphInput("graph", path.resolve(), manifest, names, edges, context)


def read_selection(path: Path) -> GraphInput:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RgError.of("RECORDS_INPUT", f"{path} does not exist.") from exc
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise RgError.of("RECORDS_INPUT", f"{path} is not UTF-8 JSON: {exc}") from exc
    if not isinstance(data, dict) or data.get("format") != SELECTION_FORMAT or not isinstance(data.get("types"), list):
        raise RgError.of("RECORDS_INPUT", f"{path} is not a {SELECTION_FORMAT} payload.",
                         "Use the explorer's Copy for Claude or JSON download (reference/selection-format.md).")
    names = {n: n for n in data["types"] if isinstance(n, str) and n}
    return GraphInput("selection", path.resolve(), data.get("store"), names, set(), {k: v for k, v in data.items() if k != "types"})


# ---- store access ---------------------------------------------------------------------------


def _values(iris: list[str]) -> str:
    return " ".join(f"<{i}>" for i in iris)


def _batches(items: list[str]):
    for start in range(0, len(items), BATCH):
        yield items[start : start + BATCH]


_OWN = "?t dt:definedInAssembly ?asm ; dt:accessibility ?access . ?asm a dt:Assembly ."


def artifact_root_of(manifest_path: Path, relative: str) -> Path:
    """The artifact root a manifest's relative manifestPath values are resolved against."""
    for parent in manifest_path.resolve().parents:
        if (parent / relative).is_file():
            return parent
    raise RgError.of("RECORDS_MANIFEST_BROKEN", f"Cannot find {relative} above {manifest_path}.",
                     "The store's artifact root has moved or is incomplete; run validate on it.")


def project_path(component: dict[str, Any]) -> str:
    """Repository-relative project path of a source component manifest.

    assembly/v2 manifests record build.project relative to the profile root (B0 finding 0): the project is
    repository.parent/project when that file exists, else repository/project. Later identities are repository-relative.
    """
    project = component["build"]["project"]
    if not str(component.get("identity", "")).startswith("assembly/v2|"):
        return project
    repo = Path(component["origin"]["repository"])
    for candidate in (repo.parent / project, repo / project):
        if candidate.is_file():
            try:
                return candidate.resolve().relative_to(repo.resolve()).as_posix()
            except ValueError:
                break
    prefix = repo.name + "/"
    return project[len(prefix):] if project.lower().startswith(prefix.lower()) else project


class Store:
    """Batched, cached lookups over one solution or view store."""

    def __init__(self, manifest_path: Path, timeout: int | None, context: dict[str, Any] | None = None):
        self.manifest_path = manifest_path
        self.path, self.manifest = explore.store_for(manifest_path)
        self.timeout = timeout
        self._components: dict[str, dict[str, Any]] | None = None
        self._component_manifests: dict[str, dict[str, Any]] = {}
        self._root: Path | None = None
        self.context = context or {}
        self._additional: list[tuple[Path, dict[str, Any]]] = []
        seen: dict[str, dict[str, Any]] = {}
        for entry in self.context.get("additionalComponents", []):
            if not isinstance(entry, dict) or not all(isinstance(entry.get(key), str) and entry[key]
                                                    for key in ("artifactId", "graphIri", "manifestPath")):
                raise RgError.of("RECORDS_MANIFEST_BROKEN", "An additional component pin lacks its artifact ID, graph IRI or manifest path.")
            path = Path(entry["manifestPath"])
            if not path.is_absolute():
                path = self.root() / path
            pinned = artifacts.read_manifest(path)
            if (not isinstance(pinned, dict) or artifacts.manifest_kind(pinned) != "assembly"
                    or pinned.get("artifactId") != entry["artifactId"] or pinned.get("graphIri") != entry["graphIri"]):
                raise RgError.of("RECORDS_MANIFEST_BROKEN", f"{path} no longer matches its pinned assembly artifact.", pin=entry)
            if entry["artifactId"] in seen:
                if seen[entry["artifactId"]] != entry:
                    raise RgError.of("RECORDS_MANIFEST_BROKEN", f"Conflicting pins for {entry['artifactId']}.")
                continue
            seen[entry["artifactId"]] = entry
            store_path, _ = explore.store_for(path)
            self._additional.append((store_path, entry))
            self._component_manifests[entry["graphIri"]] = pinned

    def select(self, query: str) -> list[dict[str, str]]:
        return oxigraph.select(self.path, query, timeout=self.timeout)

    def _component_rows(self, variables: str, values: str, pattern: str) -> list[dict[str, str]]:
        prefix = f"PREFIX dt: <{DT}> PREFIX rg: <{RG}> SELECT DISTINCT {variables} WHERE {{ {values} "
        datasets = [(self.path, self.manifest if self.manifest.get("kind") == "assembly" else None)] + self._additional
        rows: list[dict[str, str]] = []
        for path, entry in datasets:
            body = f"{pattern} BIND(<{entry['graphIri']}> AS ?g)" if entry else f"GRAPH ?g {{ {pattern} }}"
            rows.extend(oxigraph.select(path, prefix + body + " }", timeout=self.timeout))
        return rows

    def pairs(self, subjects: list[str], pattern: str) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for batch in _batches(sorted(set(subjects))):
            rows = self._component_rows("?t ?r", f"VALUES ?t {{ {_values(batch)} }}", pattern)
            out += [(r["t"], r["r"]) for r in rows]
        return sorted(set(out))

    def own_graphs(self, iris: list[str]) -> dict[str, str]:
        """Component types among the IRIs, with the named graph (component) defining each."""
        out: dict[str, str] = {}
        for batch in _batches(sorted(set(iris))):
            rows = self._component_rows("?t ?g", f"VALUES ?t {{ {_values(batch)} }}", _OWN)
            out.update({r["t"]: r["g"] for r in rows})
        return out

    def own_by_name(self, names: list[str]) -> list[tuple[str, str, str]]:
        """(IRI, full name, graph) of every component type with one of the full names."""
        out: list[tuple[str, str, str]] = []
        for batch in _batches(sorted(set(names))):
            rows = self._component_rows("?t ?full ?g", f"VALUES ?full {{ {' '.join(nt_literal(n) for n in batch)} }}",
                                        f"?t dt:fullName ?full . {_OWN}")
            out += [(r["t"], r["full"], r["g"]) for r in rows]
        return sorted(set(out))

    def logical_types(self) -> dict[str, str]:
        """Physical IRI -> logical IRI; empty for solutions."""
        mapping = explore.logical_map(self.path, self.manifest) if self.manifest.get("kind") == "view" else {}
        mapping.update(self.context.get("logicalTypeMappings", {}))
        return mapping

    def root(self) -> Path:
        if self._root is None:
            m = self.manifest
            first = m["baseSolution"]["manifestPath"] if m.get("kind") == "view" else (m.get("components") or [{}])[0].get("manifestPath")
            self._root = artifact_root_of(self.manifest_path, first) if first else self.manifest_path.parent
        return self._root

    def components(self) -> dict[str, dict[str, Any]]:
        """graphIri -> component entry (origin, manifestPath) for every component of the store."""
        if self._components is None:
            m = self.manifest
            if m.get("kind") == "view":
                base = artifacts.read_manifest(self.root() / m["baseSolution"]["manifestPath"])
                entries = list(base.get("components", [])) + list(m.get("overlayComponents", []))
            elif m.get("kind") == "assembly":
                entries = [dict(m, manifestPath=str(self.manifest_path.resolve()))]
            else:
                entries = list(m.get("components", []))
            entries += [entry for _, entry in self._additional]
            self._components = {c["graphIri"]: c for c in entries}
        return self._components

    def component_manifest(self, graph: str) -> dict[str, Any]:
        if graph not in self._component_manifests:
            entry = self.components().get(graph)
            if entry is None:
                raise RgError.of("RECORDS_MANIFEST_BROKEN", f"Graph {graph} is not a component of {self.manifest_path}.")
            self._component_manifests[graph] = artifacts.read_manifest(self.root() / entry["manifestPath"])
        return self._component_manifests[graph]


# ---- types and fields -----------------------------------------------------------------------


@dataclass
class Unit:
    """One record: a type of the input (logical or physical) and the physical types behind it."""

    key: str
    full_name: str
    physicals: list[str]


class Fields:
    """Field values per unit, queried lazily and only for the fields asked for."""

    def __init__(self, store: Store, graph_of: dict[str, str], source: GraphInput):
        self.store, self.graph_of, self.source = store, graph_of, source
        self._physical: dict[str, dict[str, list[Any]]] = {}
        self.varies: Counter[str] = Counter()
        self.locations: dict[str, tuple[str, list[str]]] = {}
        self.projects: dict[str, sources.Project] = {}

    def resolve_sources(self, units: list[Unit], allow_drift: bool, repo_roots: dict[str, Path]) -> list[dict[str, Any]]:
        """Declaring files and locationStatus for every physical type of the units; returns drift warnings."""
        physicals = sorted({p for u in units for p in u.physicals})
        names = self._per_physical("fullName", physicals)
        for p in physicals:
            graph = self.graph_of[p]
            origin = (self.store.components().get(graph) or {}).get("origin") or {}
            if origin.get("kind") == "source" and graph not in self.projects:
                component = self.store.component_manifest(graph)
                # The path comes from the component as recorded: a moved checkout may have another folder name.
                self.projects[graph] = sources.project_for(graph, component, project_path(component), repo_roots)
        warnings = sources.index_all(list(self.projects.values()), self.store.root() / "cache" / "source-index", allow_drift)
        self.locations = {p: sources.locate(self.projects.get(self.graph_of[p]), names[p][0]) for p in physicals}
        return warnings

    def _per_physical(self, name: str, physicals: list[str]) -> dict[str, list[Any]]:
        if name not in self._physical:
            self._physical[name] = self._load(name, sorted(set(physicals)))
        return self._physical[name]

    def _load(self, name: str, iris: list[str]) -> dict[str, list[Any]]:
        out: dict[str, list[Any]] = {i: [] for i in iris}

        def put(pairs):
            for t, r in pairs:
                out.setdefault(t, []).append(r)

        literal = {"fullName": "fullName", "name": "name", "kind": "typeKind", "accessibility": "accessibility",
                   "isAbstract": "isAbstract", "isSealed": "isSealed", "isStatic": "isStatic", "isGeneric": "isGeneric"}
        if name in literal:
            put(self.store.pairs(iris, f"?t dt:{literal[name]} ?r"))
            if name.startswith("is"):
                out = {t: [v.lower() == "true" for v in vs] for t, vs in out.items()}
        elif name == "namespace":
            put(self.store.pairs(iris, "?t dt:inNamespace ?n . ?n dt:fullName ?r"))
        elif name == "assemblies":
            put(self.store.pairs(iris, "?t dt:definedInAssembly ?a . ?a a dt:Assembly ; dt:name ?r"))
        elif name in ("baseType", "interfaces"):
            refs = self.store.pairs(iris, "?t dt:inherits ?r" if name == "baseType" else "?t dt:implements ?r")
            definitions = dict(self.store.pairs([r for _, r in refs], "?t dt:genericDefinition ?r"))
            targets = {r: definitions.get(r, r) for _, r in refs}
            names = dict(self.store.pairs(list(set(targets.values())), "?t dt:fullName ?r"))
            put((t, names.get(targets[r], targets[r])) for t, r in refs)
        elif name == "memberCount":
            counts = Counter(t for t, _ in self.store.pairs(iris, "?t dt:hasMember ?r"))
            out = {t: [counts.get(t, 0)] for t in iris}
        elif name in ("origin", "repository", "repositories", "projects", "projectDirs"):
            for t in iris:
                graph = self.graph_of[t]
                entry = self.store.components().get(graph) or {}
                origin = entry.get("origin") or {}
                kind = origin.get("kind")
                if name == "origin":
                    out[t] = [kind] if kind else []
                elif kind != "source":
                    out[t] = []
                elif name in ("repository", "repositories"):
                    out[t] = [origin.get("id")]
                else:
                    project = project_path(self.store.component_manifest(graph))
                    out[t] = [project if name == "projects" else (project.rsplit("/", 1)[0] + "/" if "/" in project else ROOT_DIR)]
        else:
            raise AssertionError(name)
        return out

    def values(self, unit: Unit, name: str, units: list[Unit]) -> list[Any]:
        """Every distinct value of a field across a unit's physical types (store and manifest fields)."""
        data = self._per_physical(name, [p for u in units for p in u.physicals])
        seen: dict[Any, None] = {}
        for p in unit.physicals:
            for v in data.get(p, []):
                seen[v] = None
        return list(seen)

    def value(self, unit: Unit, name: str, units: list[Unit]) -> Any:
        spec = REGISTRY[name]
        if name == "iri":
            return unit.key
        if name in ("referencesInGraph", "referencedByInGraph"):
            out = {self.source.names[o if name == "referencesInGraph" else s]
                   for s, o in self.source.edges if (s if name == "referencesInGraph" else o) == unit.key}
            return sorted(out)
        if spec.needs == "source":
            found = [self.locations[p] for p in unit.physicals]
            if name == "files":
                return sorted({f for _, files in found for f in files})
            return min((status for status, _ in found), key=sources.STATUSES.index)
        values = self.values(unit, name, units)
        if name == "origin":
            kinds = set(values)
            return "mixed" if len(kinds) > 1 else (kinds.pop() if kinds else "nuget")
        if spec.cardinality == "list":
            return sorted(set(values))
        if name == "memberCount":
            return max(values, default=0)
        if name == "repository":
            if len(values) > 1:
                raise RgError.of("RECORD_AMBIGUOUS_FIELD", f"{unit.full_name} is built in several repositories: {sorted(values)}.",
                                 "Bind the repositories list field instead of repository.", type=unit.full_name, repositories=sorted(values))
            return values[0] if values else None
        if not values:
            return False if spec.json_type == "boolean" else None
        if len(values) > 1:
            self.varies[name] += 1
        return sorted(values, key=str)[0]


# ---- filters --------------------------------------------------------------------------------

FILTERS = [  # (option, registry field, matcher kind)
    ("include", "fullName", "glob"),
    ("kind", "kind", "exact"),
    ("namespace", "namespace", "glob"),
    ("assembly", "assemblies", "glob"),
    ("project", "projects", "glob"),
    ("accessibility", "accessibility", "exact"),
    ("origin", "origin", "exact"),
    ("exclude", "fullName", "glob"),  # applied last
]
ORIGINS = {"source", "nuget"}


def _matcher(kind: str, patterns: list[str]) -> Callable[[Any], bool]:
    if kind == "glob":
        regexes = [re.compile(glob_regex(p)) for p in patterns]
        return lambda v: isinstance(v, str) and any(rx.match(v) for rx in regexes)
    wanted = set(patterns)
    return lambda v: v in wanted


def apply_filters(units: list[Unit], fields: Fields, filters: dict[str, list[str]]) -> tuple[list[Unit], dict[str, int]]:
    """A repeated option ORs its values; different options AND; --exclude last. Returns (kept, removed per option)."""
    removed: dict[str, int] = {}
    current = list(units)
    for option, name, kind in FILTERS:
        patterns = filters.get(option) or []
        if not patterns:
            continue
        match = _matcher(kind, patterns)

        def hit(u: Unit) -> bool:
            if name == "fullName":
                return match(u.full_name)
            return any(match(v) for v in fields.values(u, name, current))

        kept = [u for u in current if (not hit(u)) == (option == "exclude")]
        removed[option] = len(current) - len(kept)
        current = kept
    return current, removed


# ---- command --------------------------------------------------------------------------------


def resolve_units(store: Store, source: GraphInput) -> tuple[list[Unit], dict[str, str]]:
    """Units for the input's types and the defining graph of every physical type; unknown types fail."""
    logical = store.logical_types()
    if source.kind == "graph":
        reverse: dict[str, list[str]] = {}
        for t, l in logical.items():
            reverse.setdefault(l, []).append(t)
        external = {entry["target"] for entry in (source.context or {}).get("externalReferences", [])}
        wanted = {s: sorted(reverse.get(s, [s])) for s in source.names if s not in external}
        graph_of = store.own_graphs([p for ps in wanted.values() for p in ps])
        units = [Unit(s, source.names[s], [p for p in ps if p in graph_of]) for s, ps in wanted.items()]
        missing = sorted(source.names[u.key] for u in units if not u.physicals)
    else:
        rows = store.own_by_name(list(source.names))
        graph_of = {t: g for t, _, g in rows}
        grouped: dict[str, Unit] = {}
        for t, full, _ in sorted(rows):
            key = logical.get(t, t)
            grouped.setdefault(key, Unit(key, full, [])).physicals.append(t)
        units = list(grouped.values())
        found = {u.full_name for u in units}
        missing = sorted(n for n in source.names if n not in found)
    if missing:
        raise RgError.of("RECORDS_TYPE_NOT_IN_STORE", f"{len(missing)} type(s) of the input are not component types of {store.manifest_path}.",
                         "The input was made from another store; pass that store's manifest with --manifest.",
                         missing=missing[:20], missingCount=len(missing))
    return sorted((u for u in units if u.physicals), key=lambda u: (u.full_name, u.key)), graph_of


def parse_repo_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for item in values or []:
        name, sep, path = item.partition("=")
        if not sep or not name or not path:
            raise RgError.of("USAGE", f"--repo-root {item!r} is not ID=PATH.", "Use the repository ID of the workspace profile, e.g. --repo-root p3=D:/work/p3.")
        roots[name] = Path(path)
    return roots


def run(graph: str | None, selection: str | None, manifest: str | None, schema_arg: str, output: Path, fmt: str,
        filters: dict[str, list[str]], timeout: int | None = explore.QUERY_TIMEOUT, allow_drift: bool = False,
        repo_roots: list[str] | None = None) -> dict[str, Any]:
    if bool(graph) == bool(selection):
        raise RgError.of("RECORDS_INPUT", "Pass exactly one of --graph or --selection.")
    source = read_graph(Path(graph)) if graph else read_selection(Path(selection))  # type: ignore[arg-type]
    store_manifest = manifest or source.store_manifest
    if not store_manifest:
        raise RgError.of("RECORDS_NO_STORE", f"{source.path} does not name its store.",
                         "Pass the solution or view manifest.json with --manifest.")
    for value in filters.get("origin") or []:
        if value not in ORIGINS:
            raise RgError.of("USAGE", f"--origin {value!r} must be one of {sorted(ORIGINS)}.")
    schema = load_schema(schema_arg)
    roots = parse_repo_roots(repo_roots or [])
    unavailable = sorted(f for f in schema.fields() if f in ("referencesInGraph", "referencedByInGraph")) if source.kind == "selection" else []
    if unavailable:
        raise RgError.of("RECORDS_FIELD_UNAVAILABLE", f"The schema binds {unavailable}, which a selection cannot fill.",
                         "Graph edge fields need --graph input; remove them from the schema.", fields=unavailable)
    manifest_path = Path(store_manifest)
    store = Store(manifest_path, timeout, source.context)
    units, graph_of = resolve_units(store, source)
    fields = Fields(store, graph_of, source)
    kept, removed = apply_filters(units, fields, filters)
    if not kept:
        worst = max(removed, key=removed.get) if removed else None
        raise RgError.of("RECORDS_EMPTY", f"No types are left of the input's {len(units)}.",
                         f"--{worst} removed the most ({removed[worst]})." if worst else "The input lists no types.", removed=removed)
    locations = None
    source_warnings: list[dict[str, Any]] = []
    if any(REGISTRY[f].needs == "source" for f in schema.fields()):
        source_warnings = fields.resolve_sources(kept, allow_drift, roots)
        statuses = Counter(min((fields.locations[p][0] for p in u.physicals), key=sources.STATUSES.index) for u in kept)
        locations = {"types": {s: statuses.get(s, 0) for s in sources.STATUSES}, "projects": len(fields.projects),
                     "cacheHits": sum(p.cached for p in fields.projects.values()),
                     "detail": [p.to_json() for p in sorted(fields.projects.values(), key=lambda p: (p.repository_id, p.relative))]}
    records: list[dict[str, Any]] = []
    for unit in kept:
        record: dict[str, Any] = {}
        for prop, name, const in schema.bindings:
            record[prop] = const if name is None else fields.value(unit, name, kept)
        records.append(record)
    violations = []
    for unit, record in zip(kept, records):
        problems = validate_value(record, schema.data)
        if problems:
            violations.append({"type": unit.full_name, "problems": problems})
    if violations:
        raise RgError.of("RECORD_SCHEMA_VIOLATION", f"{len(violations)} record(s) do not match {schema.name}.",
                         "Relax the schema (for example allow null) or narrow the input.", violations=violations[:MAX_VIOLATIONS],
                         violationCount=len(violations))
    output.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        output.write_text(json.dumps(records, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    else:
        output.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in records), encoding="utf-8", newline="\n")
    warnings = [{"code": "RECORD_FIELD_VARIES", "field": f, "types": n,
                 "message": f"{f} differs between versions of {n} type(s); the first value in sorted order was written."}
                for f, n in sorted(fields.varies.items())] + source_warnings
    repositories = {}
    for graph in sorted({graph_of[p] for u in kept for p in u.physicals}):
        origin = (store.components().get(graph) or {}).get("origin") or {}
        if origin.get("kind") == "source":
            project = fields.projects.get(graph)
            entry = repositories.setdefault(origin["id"], {"repository": origin.get("repository"), "commit": origin.get("commit"),
                                                           "dirtyHash": origin.get("dirtyHash", "")})
            if project:
                entry["checkout"] = str(project.repository)
                entry["drift"] = project.drift
    filter_summary = {"typesIn": len(units), "typesOut": len(kept), "removed": removed,
                      "options": {k: v for k, v in filters.items() if v}}
    explore.write_context(output, {
        "generator": "records",
        "source": explore.source_info(manifest_path, store.manifest),
        "input": {"kind": source.kind, "path": str(source.path), "context": source.context},
        "filters": filter_summary,
        "schema": {"name": schema.name, "path": str(schema.path), "sha256": schema.sha256},
        "recordFormat": fmt,
        "repositories": repositories,
        "count": len(records),
    })
    return {"type": "records", "output": str(output), "context": str(explore.context_path(output)), "count": len(records),
            "format": fmt, "schema": {"name": schema.name, "path": str(schema.path), "sha256": schema.sha256},
            "filters": filter_summary, "locations": locations, "warnings": warnings}
