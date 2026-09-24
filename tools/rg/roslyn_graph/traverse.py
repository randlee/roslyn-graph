"""Saved graph definitions (*.graph.toml): seeds, implementations and recursive references.

A definition names seed types (full names or glob patterns), optionally adds every implementation of the
seed interfaces, then follows type references breadth-first until closure or a depth/size limit. Only
types defined by the store's component assemblies are expanded; framework types are never pulled in.
See the explore skill's reference/graph-definitions.md.
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import artifacts, config, explore, maintain, oxigraph
from .result import ProblemList, RgError
from .util import DT, RDF_TYPE, RG, full_path, nt_iri, nt_literal

SCHEMA_VERSION = 1
BATCH = 250
FOLLOW = {  # relation -> graph patterns binding ?t (the referencing type) and ?r (the referenced type)
    "base_types": ["?t dt:inherits ?r"],
    "interfaces": ["?t dt:implements ?r"],
    "member_types": ["?t dt:hasMember ?m . ?m dt:returnType|dt:propertyType|dt:fieldType|dt:eventType ?r"],
    "parameter_types": ["?t dt:hasMember ?m . ?m dt:hasParameter ?p . ?p dt:parameterType ?r"],
    "attributes": ["?t dt:hasAttribute ?at . ?at dt:attributeType ?r",
                   "?t dt:hasMember ?m . ?m dt:hasAttribute ?at . ?at dt:attributeType ?r"],
}
KINDS = {"Class", "Interface", "Struct", "Enum", "Delegate"}
IMPLEMENTATIONS = {"none", "direct", "transitive"}


@dataclass
class Definition:
    path: Path
    title: str
    workspace: Path
    collection: str
    manifest: str
    logical: bool
    seed_types: list[str]
    seed_patterns: list[str]
    seed_kinds: list[str]
    implementations: str
    follow: list[str]
    generic_arguments: bool
    max_depth: int
    max_types: int
    visualizer: str


def load_definition(path: Path) -> Definition:
    path = full_path(path)
    try:
        data = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RgError.of("GRAPH_DEFINITION_NOT_FOUND", f"{path} does not exist.") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RgError.of("TOML_SYNTAX", f"{path}: {exc}", "Fix the TOML syntax at the reported line and column.") from exc
    problems = ProblemList()

    def bad(key: str, message: str, hint: str = "") -> None:
        problems.add("GRAPH_DEFINITION_INVALID", f"{key}: {message}", hint, file=str(path), key=key)

    allowed = {"schema_version": None, "title": None, "source": {"workspace", "collection", "manifest", "logical"},
               "seeds": {"types", "patterns", "kinds", "implementations"},
               "expand": {"follow", "generic_arguments", "max_depth", "max_types"}, "output": {"visualizer"}}
    for key, value in data.items():
        if key not in allowed:
            bad(key, "unknown key", f"Allowed: {', '.join(allowed)}.")
        elif isinstance(allowed[key], set):
            if not isinstance(value, dict):
                bad(key, "must be a table")
            else:
                for sub in sorted(set(value) - allowed[key]):
                    bad(f"{key}.{sub}", "unknown key", f"Allowed: {', '.join(sorted(allowed[key]))}.")
    if data.get("schema_version") != SCHEMA_VERSION:
        bad("schema_version", f"must be {SCHEMA_VERSION}")
    source, seeds, expand, output = (data.get(k, {}) if isinstance(data.get(k, {}), dict) else {} for k in ("source", "seeds", "expand", "output"))

    def strings(table: dict, key: str, where: str) -> list[str]:
        value = table.get(key, [])
        if not isinstance(value, list) or not all(isinstance(v, str) and v for v in value):
            bad(f"{where}.{key}", "must be an array of non-empty strings")
            return []
        return value

    collection, manifest = source.get("collection", ""), source.get("manifest", "")
    if bool(collection) == bool(manifest):
        bad("source", "set exactly one of collection or manifest", "collection uses the latest artifact of a workspace collection.")
    types, patterns = strings(seeds, "types", "seeds"), strings(seeds, "patterns", "seeds")
    if not types and not patterns:
        bad("seeds", "list at least one full type name in types or one glob in patterns")
    kinds = strings(seeds, "kinds", "seeds")
    for kind in kinds:
        if kind not in KINDS:
            bad("seeds.kinds", f"unknown kind {kind!r}", f"Use {', '.join(sorted(KINDS))}.")
    implementations = seeds.get("implementations", "transitive")
    if implementations not in IMPLEMENTATIONS:
        bad("seeds.implementations", f"must be one of {sorted(IMPLEMENTATIONS)}")
    follow = strings(expand, "follow", "expand") if "follow" in expand else ["base_types", "interfaces", "member_types", "parameter_types"]
    for item in follow:
        if item not in FOLLOW:
            bad("expand.follow", f"unknown relation {item!r}", f"Use {', '.join(FOLLOW)}.")
    max_depth, max_types = expand.get("max_depth", 0), expand.get("max_types", 1500)
    for key, value in (("max_depth", max_depth), ("max_types", max_types)):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            bad(f"expand.{key}", "must be a non-negative integer (max_depth 0 = until closure)")
    problems.raise_if_any()
    return Definition(
        path=path, title=str(data.get("title") or path.stem.replace(".graph", "")),
        workspace=full_path(source.get("workspace", "../workspace.toml"), path.parent), collection=collection, manifest=manifest,
        logical=bool(source.get("logical", True)), seed_types=types, seed_patterns=patterns, seed_kinds=kinds,
        implementations=implementations, follow=follow, generic_arguments=bool(expand.get("generic_arguments", True)),
        max_depth=max_depth, max_types=max_types, visualizer=str(output.get("visualizer", "explorer")),
    )


def resolve_manifest(d: Definition, root: Path) -> Path:
    if d.manifest:
        path = root / d.manifest
        if not path.is_file():
            raise RgError.of("GRAPH_SOURCE_NOT_FOUND", f"{path} does not exist.")
        return path
    ws = config.load(d.workspace)
    collection = ws.collections.get(d.collection)
    if collection is None:
        raise RgError.of("COLLECTION_NOT_FOUND", f"Collection '{d.collection}' is not in {ws.path}.")
    kind, key = ("view", d.collection) if collection.overlays else ("solution", collection.base)
    found = maintain.previous(root, kind, key, exclude_id="")
    if not found:
        raise RgError.of("GRAPH_SOURCE_NOT_FOUND", f"No published {kind} for collection '{d.collection}'.",
                         "Generate the collection with the roslyn-graph-create skill first.")
    return found[0]


def glob_regex(pattern: str) -> str:
    """Glob over full type names: * matches any run of characters, ? one character."""
    return "^" + re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".") + "$"


def _values(iris: list[str]) -> str:
    return " ".join(f"<{i}>" for i in iris)


def _batches(items: list[str]):
    for start in range(0, len(items), BATCH):
        yield items[start : start + BATCH]


# A component's own, fully extracted type: defined by the graph's assembly and carrying dt:accessibility, which
# reference stubs and constructed generics never have. Positive patterns keep every query index-driven.
_OWN = "?asm a dt:Assembly . {t} dt:definedInAssembly ?asm ; dt:accessibility ?{v}Access ."


def _own(var: str) -> str:
    return _OWN.format(t=f"?{var}", v=var)


def find_seeds(store: Path, d: Definition) -> tuple[dict[str, str], list[str]]:
    """Physical IRIs of component types matching the seeds, with their full names; plus unmatched seeds."""
    rows = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT DISTINCT ?t ?full ?kind WHERE {{ GRAPH ?g {{ "
                                  f"{_own('t')} ?t dt:fullName ?full ; dt:typeKind ?kind . }} }}")
    matched: dict[str, str] = {}
    unmatched = []
    for name in d.seed_types:
        hits = {r["t"]: r["full"] for r in rows if r["full"] == name}
        if not hits:
            unmatched.append(name)
        matched.update(hits)
    for pattern in d.seed_patterns:
        rx = re.compile(glob_regex(pattern))
        hits = {r["t"]: r["full"] for r in rows if rx.match(r["full"]) and (not d.seed_kinds or r["kind"] in d.seed_kinds)}
        if not hits:
            unmatched.append(pattern)
        matched.update(hits)
    return matched, unmatched


def _pairs(store: Path, subjects: list[str], pattern: str) -> list[tuple[str, str]]:
    """(?t, ?r) for every subject ?t matching one graph pattern. One pattern per query: Oxigraph does not push
    an outer VALUES into UNION branches (a 60 ms lookup becomes 10 s), so relations are never UNIONed."""
    pairs: list[tuple[str, str]] = []
    for batch in _batches(sorted(subjects)):
        rows = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT DISTINCT ?t ?r WHERE {{ VALUES ?t {{ {_values(batch)} }} "
                                      f"GRAPH ?g {{ {pattern} }} }}")
        pairs += [(r["t"], r["r"]) for r in rows]
    return pairs


def _own_names(store: Path, iris: set[str]) -> dict[str, str]:
    """The subset of IRIs that are component types, with their full names."""
    names: dict[str, str] = {}
    for batch in _batches(sorted(iris)):
        rows = oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT DISTINCT ?t ?full WHERE {{ VALUES ?t {{ {_values(batch)} }} "
                                      f"GRAPH ?g {{ {_own('t')} ?t dt:fullName ?full . }} }}")
        names.update({r["t"]: r["full"] for r in rows})
    return names


def _underlying(store: Path, refs: set[str], generic_arguments: bool) -> dict[str, set[str]]:
    """Each referenced IRI mapped to itself plus the types inside it: generic definition, array element and
    (when enabled) type arguments, recursively."""
    patterns = ["?t dt:genericDefinition ?r", "?t dt:arrayElementType ?r"]
    if generic_arguments:
        patterns.append("?t dt:typeArgument ?a . ?a dt:type ?r")
    children: dict[str, set[str]] = {}
    frontier = set(refs)
    while frontier:
        found: dict[str, set[str]] = {t: set() for t in frontier}
        for pattern in patterns:
            for t, r in _pairs(store, list(frontier), pattern):
                found[t].add(r)
        children.update(found)
        frontier = {r for rs in found.values() for r in rs} - set(children)
    result: dict[str, set[str]] = {}
    for ref in refs:
        stack, reach = [ref], {ref}
        while stack:
            for child in children.get(stack.pop(), ()):
                if child not in reach:
                    reach.add(child)
                    stack.append(child)
        result[ref] = reach
    return result


def find_implementations(store: Path, targets: set[str], transitive: bool) -> dict[str, str]:
    """Component types that implement (or, transitively, extend/derive from) any target full name."""
    found: dict[str, str] = {}
    frontier = set(targets)
    names = set(targets)
    while frontier:
        # 1. every IRI naming a target: the type in any version, plus constructed generics of it
        literals = " ".join(nt_literal(n) for n in sorted(frontier))
        bases = {r["base"] for r in oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT DISTINCT ?base WHERE {{ "
                                                           f"VALUES ?target {{ {literals} }} GRAPH ?g {{ ?base dt:fullName ?target }} }}")}
        bases |= {r for _, r in _pairs(store, sorted(bases), "?r dt:genericDefinition ?t")}
        # 2. component types implementing or deriving from any of them
        candidates = {r for pattern in ("?r dt:implements ?t", "?r dt:inherits ?t") for _, r in _pairs(store, sorted(bases), pattern)}
        new = {iri: full for iri, full in _own_names(store, candidates - set(found)).items()}
        found.update(new)
        if not transitive:
            break
        frontier = set(new.values()) - names
        names |= frontier
    return found


def expand(store: Path, d: Definition, start: dict[str, str]) -> tuple[dict[str, str], list[tuple[str, str]], list[dict[str, Any]], bool]:
    """Breadth-first over references. Returns (types, reference edges, per-depth stats, truncated)."""
    seen = dict(start)
    edges: set[tuple[str, str]] = set()
    frontier = sorted(start)
    stats, depth, truncated = [], 0, False
    while frontier and (d.max_depth == 0 or depth < d.max_depth):
        depth += 1
        direct: set[tuple[str, str]] = set()
        for relation in d.follow:
            for pattern in FOLLOW[relation]:
                direct.update(_pairs(store, frontier, pattern))
        inside = _underlying(store, {r for _, r in direct}, d.generic_arguments)
        own = _own_names(store, {u for us in inside.values() for u in us})
        added: dict[str, str] = {}
        for t, r in direct:
            for u in inside[r]:
                if u in own and u != t:
                    edges.add((t, u))
                    if u not in seen:
                        added[u] = own[u]
        if len(seen) + len(added) > d.max_types:
            truncated = True
            stats.append({"depth": depth, "added": len(added), "stopped": f"would exceed max_types={d.max_types}"})
            break
        seen.update(added)
        stats.append({"depth": depth, "added": len(added), "total": len(seen)})
        frontier = sorted(added)
    return seen, sorted(edges), stats, truncated


def export_lines(store: Path, types: dict[str, str], edges: list[tuple[str, str]]) -> list[str]:
    """Viewer triples for the selected component types (IRI -> full name) and the edges between them."""
    lines: list[str] = []
    iris = sorted(types)
    for t, full in sorted(types.items()):
        lines.append(f"{nt_iri(t)} {nt_iri(DT + 'fullName')} {nt_literal(full)} .")
    for t, cls in _pairs(store, iris, "?t a ?r"):
        if cls != DT + "Type":
            lines.append(f"{nt_iri(t)} {nt_iri(RDF_TYPE)} {nt_iri(cls)} .")
    for t, name in _pairs(store, iris, "?t dt:name ?r"):
        lines.append(f"{nt_iri(t)} {nt_iri(DT + 'name')} {nt_literal(name)} .")
    namespaces = _pairs(store, iris, "?t dt:inNamespace ?r")
    for t, ns in namespaces:
        lines.append(f"{nt_iri(t)} {nt_iri(DT + 'inNamespace')} {nt_iri(ns)} .")
    for ns, ns_full in _pairs(store, sorted({ns for _, ns in namespaces}), "?t dt:fullName ?r"):
        lines.append(f"{nt_iri(ns)} {nt_iri(DT + 'name')} {nt_literal(ns_full)} .")
    wanted = set(types)
    structural: set[tuple[str, str]] = set()
    for predicate in ("implements", "inherits"):
        pairs = _pairs(store, iris, f"?t dt:{predicate} ?r")
        definitions = _underlying(store, {r for _, r in pairs}, generic_arguments=False)
        for t, r in pairs:
            for base in definitions[r]:
                if base in wanted and base != t:
                    lines.append(f"{nt_iri(t)} {nt_iri(DT + predicate)} {nt_iri(base)} .")
                    structural.add((t, base))
    for source, target in edges:
        if (source, target) not in structural and target in wanted:
            lines.append(f"{nt_iri(source)} {nt_iri(RG + 'references')} {nt_iri(target)} .")
    return list(dict.fromkeys(lines))


def run(definition_path: Path, data_root: str | None, output_dir: Path | None, open_page: bool) -> dict[str, Any]:
    d = load_definition(definition_path)
    root = artifacts.artifact_root(data_root)
    manifest_path = resolve_manifest(d, root)
    store, manifest = explore.store_for(manifest_path)
    if d.logical and manifest["kind"] != "view":
        d.logical = False
    seeds, unmatched = find_seeds(store, d)
    if unmatched:
        raise RgError.of("GRAPH_SEED_NOT_FOUND", f"No component type matches {unmatched}.",
                         "Seeds are full names as stored (C# display names, e.g. Contoso.IRepository<T>); "
                         "find them with the find-type query.", unmatched=unmatched)
    implementations: dict[str, str] = {}
    if d.implementations != "none":
        implementations = find_implementations(store, set(seeds.values()), transitive=d.implementations == "transitive")
    start = seeds | implementations
    types, edges, stats, truncated = expand(store, d, start)
    lines = export_lines(store, types, edges)
    collapsed = 0
    if d.logical:
        before = len(lines)
        lines = explore.collapse(lines, explore.logical_map(store, manifest))
        collapsed = before - len(lines)
    out_dir = output_dir or d.path.parent / "out"
    stem = d.path.name.removesuffix(".toml").removesuffix(".graph")
    data = out_dir / f"{stem}.nt"
    out_dir.mkdir(parents=True, exist_ok=True)
    data.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    page = explore.render(d.visualizer, data, out_dir / f"{stem}.html", d.title)
    if open_page:
        import webbrowser
        webbrowser.open(Path(page["output"]).resolve().as_uri())
    return {
        "type": "graph",
        "definition": str(d.path),
        "source": str(manifest_path),
        "logical": d.logical,
        "seeds": len(seeds),
        "implementations": len(implementations),
        "expansion": stats,
        "types": len(types),
        "referenceEdges": len(edges),
        "truncated": truncated,
        "duplicatesCollapsed": collapsed,
        "summary": explore.summarize(lines),
        "data": str(data),
        "page": page["output"],
        "opened": open_page,
    }
