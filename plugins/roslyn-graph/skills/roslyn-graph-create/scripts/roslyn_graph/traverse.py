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

from . import artifacts, build, config, explore, maintain, oxigraph
from .result import ProblemList, RgError
from .util import DT, RDF_TYPE, RG, full_path, nt_iri, nt_literal

SCHEMA_VERSION = 1
BATCH = 250
_ADMISSION_FAILURES = {"ambiguous-artifacts", "registered-definition-unavailable", "external-boundary"}
FOLLOW = {  # relation -> graph patterns binding ?t (the referencing type) and ?r (the referenced type)
    "base_types": ["?t dt:inherits ?r"],
    "interfaces": ["?t dt:implements ?r"],
    "member_types": ["?t dt:hasMember ?m . ?m dt:returnType|dt:propertyType|dt:fieldType|dt:eventType ?r"],
    "parameter_types": ["?t dt:hasMember ?m . ?m dt:hasParameter ?p . ?p dt:parameterType ?r"],
    "body_types": ["?t dt:hasMember ?member . ?member dt:usesType ?r"],
    "constraints": ["?t dt:hasTypeParameter ?parameter . ?parameter dt:constrainedToType ?r",
                    "?t dt:hasMember ?method . ?method dt:hasTypeParameter ?parameter . ?parameter dt:constrainedToType ?r"],
    "enclosing_type": ["?t dt:nestedIn ?r"],
    "attributes": ["?t dt:hasAttribute ?at . ?at dt:attributeType ?r",
                   "?t dt:hasMember ?m . ?m dt:hasAttribute ?at . ?at dt:attributeType ?r"],
}
INVERSE_FOLLOW = {  # relation -> patterns binding ?t (the consumed type) and ?r (its component consumer)
    "referenced_by": [
        "?r dt:inherits ?t",
        "?r dt:implements ?t",
        "?r dt:hasMember ?m . ?m dt:returnType|dt:propertyType|dt:fieldType|dt:eventType ?t",
        "?r dt:hasMember ?m . ?m dt:hasParameter ?p . ?p dt:parameterType ?t",
        "?r dt:hasMember ?member . ?member dt:usesType ?t",
        "?r dt:hasTypeParameter ?parameter . ?parameter dt:constrainedToType ?t",
        "?r dt:hasMember ?method . ?method dt:hasTypeParameter ?parameter . ?parameter dt:constrainedToType ?t",
        "?r dt:hasAttribute ?at . ?at dt:attributeType ?t",
        "?r dt:hasMember ?m . ?m dt:hasAttribute ?at . ?at dt:attributeType ?t",
    ],
}
FOLLOW = FOLLOW | INVERSE_FOLLOW
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
    max_types: int | None
    visualizer: str
    members: bool = True


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
               "expand": {"follow", "generic_arguments", "max_depth", "max_types"}, "output": {"visualizer", "members"}}
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
    follow = strings(expand, "follow", "expand") if "follow" in expand else ["base_types", "interfaces", "member_types", "parameter_types", "body_types", "constraints", "enclosing_type"]
    for item in follow:
        if item not in FOLLOW:
            bad("expand.follow", f"unknown relation {item!r}", f"Use {', '.join(FOLLOW)}.")
    max_depth, max_types = expand.get("max_depth", 0), expand.get("max_types")
    for key, value in (("max_depth", max_depth),):
        if not isinstance(value, int) or isinstance(value, bool) or value < 0:
            bad(f"expand.{key}", "must be a non-negative integer (max_depth 0 = until closure)")
    if max_types is not None and (not isinstance(max_types, int) or isinstance(max_types, bool) or max_types <= 0):
        bad("expand.max_types", "must be a positive integer when set (omitted = until closure)")
    problems.raise_if_any()
    return Definition(
        path=path, title=str(data.get("title") or path.stem.replace(".graph", "")),
        workspace=full_path(source.get("workspace", "../workspace.toml"), path.parent), collection=collection, manifest=manifest,
        logical=bool(source.get("logical", True)), seed_types=types, seed_patterns=patterns, seed_kinds=kinds,
        implementations=implementations, follow=follow, generic_arguments=bool(expand.get("generic_arguments", True)),
        max_depth=max_depth, max_types=max_types, visualizer=str(output.get("visualizer", "explorer")),
        members=bool(output.get("members", True)),
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


class DependencyStores:
    def __init__(self, store: Path, manifest: dict):
        self.sources = [(store, manifest.get("kind") != "assembly")]
        self.manifest = manifest
        self.candidates: list[tuple[Path, dict]] = []
        self.known_components: list[dict] = []
        self.additional_components: list[dict] = []
        self.diagnostics: list[dict] = []
        self.resolved: set[str] = set()
        self.reasons: dict[str, str] = {}
        self.external_references: list[dict] = []
        self.packages: dict[str, dict] = {}

    def report(self, reason: str, **details):
        item = {"reason": reason, **details}
        if item not in self.diagnostics:
            self.diagnostics.append(item)

    @classmethod
    def registered(cls, root: Path, definition: Definition, manifest: dict, store: Path | None = None):
        result = cls(store or root / "store.oxigraph", manifest)
        result.report("body-coverage-unknown", artifactId=manifest.get("artifactId"))
        recorded = manifest.get("workspace", {})
        if not isinstance(recorded, dict):
            result.report("registration-unavailable", message="The source manifest has invalid workspace provenance.")
            return result
        if getattr(definition, "manifest", "") and (not recorded.get("path") or not recorded.get("collection")):
            result.report("registration-unavailable", message="The source manifest has no recorded workspace and collection.")
            return result
        if getattr(definition, "manifest", "") and (not isinstance(recorded["path"], str) or not isinstance(recorded["collection"], str)):
            result.report("registration-unavailable", message="The source manifest has invalid workspace provenance.")
            return result
        workspace_path = Path(recorded["path"]) if getattr(definition, "manifest", "") else definition.workspace
        collection_name = recorded["collection"] if getattr(definition, "manifest", "") else definition.collection
        try:
            workspace = config.load(workspace_path)
            collection = workspace.collections.get(collection_name)
            if collection is None:
                result.report("registration-unavailable", workspace=str(workspace_path), collection=collection_name)
                return result
        except (RgError, UnicodeError, OSError) as exc:
            result.report("registration-unavailable", workspace=str(workspace_path), message=str(exc))
            return result
        profiles = {collection.base, *collection.overlays}
        for name in list(profiles):
            profiles.update(getattr(workspace.profiles[name], "packages", []))
        present = {manifest.get("artifactId")}
        for key in ("components", "baseComponents", "overlayComponents"):
            present.update(item["artifactId"] for item in manifest.get(key, []))
        for path in sorted((root / "assemblies").rglob("manifest.json")):
            try:
                candidate = artifacts.read_manifest(path)
            except (RgError, UnicodeError) as exc:
                result.report("manifest-unreadable", manifestPath=str(path), message=str(exc))
                continue
            if not isinstance(candidate, dict):
                result.report("manifest-invalid", manifestPath=str(path))
                continue
            registration = candidate.get("workspace", {})
            if (not isinstance(registration, dict) or not isinstance(registration.get("path"), str)
                    or not isinstance(registration.get("profile"), str)
                    or not isinstance(candidate.get("build", {}), dict)
                    or not isinstance(candidate.get("package") or {}, dict)
                    or not isinstance(candidate.get("assembly", {}), dict)):
                result.report("manifest-invalid", manifestPath=str(path))
                continue
            if Path(registration["path"]).resolve() != workspace.path.resolve():
                continue
            if candidate.get("schemaVersion") != 2 or candidate.get("kind") != "assembly":
                result.report("manifest-unsupported", manifestPath=str(path))
                continue
            if (not isinstance(candidate.get("artifactId"), str) or not candidate["artifactId"]
                    or not isinstance(candidate.get("graphIri"), str) or not candidate["graphIri"]):
                result.report("manifest-invalid", manifestPath=str(path))
                continue
            result.known_components.append(candidate)
            if registration["profile"] not in profiles:
                continue
            if candidate.get("artifactId") in present:
                continue
            profile = workspace.profiles[registration["profile"]]
            framework = candidate.get("build", {}).get("targetFramework") or (candidate.get("package") or {}).get("targetFramework")
            if framework != profile.target_framework:
                result.report("framework-incompatible", manifestPath=str(path), targetFramework=framework)
                continue
            result.candidates.append((path, candidate))
        return result

    def select(self, columns: str, pattern: str, values: str = "") -> list[dict]:
        rows = []
        for path, named in self.sources:
            scoped = f"GRAPH ?g {{ {pattern} }}" if named else pattern
            rows.extend(oxigraph.select(path, f"PREFIX dt: <{DT}> SELECT DISTINCT {columns} WHERE {{ {values} {scoped} }}"))
        return [dict(row) for row in {tuple(sorted(row.items())) for row in rows}]

    def resolve(self, refs: set[str]):
        unresolved = refs - self.resolved
        self.resolved.update(unresolved)
        if not unresolved:
            return
        source_path, source_named = self.sources[0]
        own_pattern = f"GRAPH ?g {{ {_own('t')} }}" if source_named else _own("t")
        existing = {row["t"] for batch in _batches(sorted(unresolved))
                    for row in oxigraph.select(source_path, f"PREFIX dt: <{DT}> SELECT DISTINCT ?t WHERE {{ "
                                               f"VALUES ?t {{ {_values(batch)} }} {own_pattern} }}")}
        unresolved -= existing
        bound = {}
        for batch in _batches(sorted(unresolved)):
            for row in self.select("?t ?asm ?name ?version ?culture ?token",
                                   "?t dt:definedInAssembly ?asm . ?asm dt:name ?name ; dt:version ?version . "
                                   "OPTIONAL { ?asm dt:culture ?culture } OPTIONAL { ?asm dt:publicKeyToken ?token }",
                                   f"VALUES ?t {{ {_values(batch)} }}"):
                bound.setdefault(row["t"], []).append(row)
        for ref, references in bound.items():
            packages = [component["package"] for component in self.known_components if component.get("package") and
                        all(all(component.get("assembly", {}).get(field, "") == reference.get(variable, "")
                                for field, variable in (("name", "name"), ("version", "version"), ("culture", "culture"),
                                                        ("publicKeyToken", "token"))) for reference in references)]
            if packages and all(package == packages[0] for package in packages):
                self.packages[ref] = packages[0]
        matches: dict[str, dict[str, tuple[Path, dict]]] = {}
        for path, manifest in self.candidates:
            candidate_store = path.parent / "store.oxigraph"
            if not candidate_store.is_dir():
                self.report("store-unavailable", manifestPath=str(path))
                continue
            for batch in _batches(sorted(unresolved)):
                try:
                    rows = oxigraph.select(candidate_store, f"PREFIX dt: <{DT}> SELECT DISTINCT ?t ?asm ?name ?version ?culture ?token WHERE {{ "
                                           f"VALUES ?t {{ {_values(batch)} }} {_own('t')} ?t dt:definedInAssembly ?asm ; dt:fullName ?full . "
                                           "?asm dt:name ?name ; dt:version ?version . OPTIONAL { ?asm dt:culture ?culture } "
                                           "OPTIONAL { ?asm dt:publicKeyToken ?token } }")
                except RgError as exc:
                    corrupt = all(problem.code == "OXIGRAPH_FAILED" and
                                  any(re.match(r"^\s*(?:Error: )?Corruption:", line)
                                      for line in problem.context.get("stderr", []))
                                  for problem in exc.problems)
                    if not corrupt:
                        raise
                    self.report("store-unavailable", manifestPath=str(path), message=str(exc))
                    for options in matches.values():
                        options.pop(manifest["artifactId"], None)
                    break
                for row in rows:
                    references = bound.get(row["t"], [])
                    if references and all(all(row.get(key, "") == reference.get(key, "") for key in ("asm", "name", "version", "culture", "token"))
                                          for reference in references):
                        matches.setdefault(row["t"], {})[manifest["artifactId"]] = (path, manifest)
                    else:
                        self.report("identity-incompatible", target=row["t"], artifactId=manifest.get("artifactId"))
        for ref in sorted(unresolved):
            options = matches.get(ref, {})
            if len(options) == 1:
                path, manifest = next(iter(options.values()))
                if not any(pin["artifactId"] == manifest["artifactId"] for pin in self.additional_components):
                    self.sources.append((path.parent / "store.oxigraph", False))
                    self.additional_components.append({key: manifest.get(key) for key in ("artifactId", "graphIri", "origin", "package", "assembly")} |
                                                      {"manifestPath": str(path.resolve())})
                    self.report("body-coverage-unknown", artifactId=manifest["artifactId"])
            elif len(options) > 1:
                self.reasons[ref] = "ambiguous-artifacts"
                self.report("ambiguous-artifacts", target=ref, candidateIds=sorted(options))
            else:
                bound_names = {row["name"] for row in bound.get(ref, [])}
                registered = [manifest for _, manifest in self.candidates if manifest.get("assembly", {}).get("name") in bound_names]
                self.reasons[ref] = "registered-definition-unavailable" if registered else "external-boundary"
                if registered:
                    self.report("registered-definition-unavailable", target=ref, candidateIds=sorted({item["artifactId"] for item in registered}))


def _select(store: Path | DependencyStores, columns: str, pattern: str, values: str = "") -> list[dict]:
    if isinstance(store, DependencyStores):
        return store.select(columns, pattern, values)
    return oxigraph.select(store, f"PREFIX dt: <{DT}> SELECT DISTINCT {columns} WHERE {{ {values} GRAPH ?g {{ {pattern} }} }}")


def find_seeds(store: Path, d: Definition) -> tuple[dict[str, str], list[str]]:
    """Physical IRIs of component types matching the seeds, with their full names; plus unmatched seeds."""
    rows = _select(store, "?t ?full ?kind", f"{_own('t')} ?t dt:fullName ?full ; dt:typeKind ?kind .")
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
        rows = _select(store, "?t ?r", pattern, f"VALUES ?t {{ {_values(batch)} }}")
        pairs += [(r["t"], r["r"]) for r in rows]
    return sorted(set(pairs))


def _inverse_pairs(store: Path, targets: list[str], pattern: str) -> list[tuple[str, str]]:
    """Return (consumed target, component consumer) pairs for an inverse follow pattern."""
    pairs: list[tuple[str, str]] = []
    for batch in _batches(sorted(targets)):
        rows = _select(store, "?t ?r", pattern, f"VALUES ?t {{ {_values(batch)} }}")
        pairs += [(r["t"], r["r"]) for r in rows]
    return pairs


def _own_names(store: Path, iris: set[str]) -> dict[str, str]:
    """The subset of IRIs that are component types, with their full names."""
    names: dict[str, str] = {}
    if isinstance(store, DependencyStores):
        store.resolve(iris)
    for batch in _batches(sorted(iris)):
        rows = _select(store, "?t ?full", f"{_own('t')} ?t dt:fullName ?full .", f"VALUES ?t {{ {_values(batch)} }}")
        names.update({r["t"]: r["full"] for r in rows})
    if isinstance(store, DependencyStores):
        names = {key: value for key, value in names.items() if store.reasons.get(key) not in _ADMISSION_FAILURES}
    return names


def _underlying(store: Path, refs: set[str], generic_arguments: bool) -> dict[str, set[str]]:
    """Each referenced IRI mapped to itself plus the types inside it: generic definition, array element and
    (when enabled) type arguments, recursively."""
    patterns = ["?t dt:genericDefinition ?r", "?t dt:arrayElementType ?r", "?t dt:pointerElementType ?r",
                "?t dt:signatureReturnType ?r", "?t dt:signatureParameter ?parameter . ?parameter dt:parameterType ?r",
                "?t dt:callingConventionType ?r"]
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
        bases = {r["base"] for r in _select(store, "?base", "?base dt:fullName ?target", f"VALUES ?target {{ {literals} }}")}
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
        inverse: set[tuple[str, str]] = set()
        for relation in d.follow:
            if relation in INVERSE_FOLLOW:
                for pattern in INVERSE_FOLLOW[relation]:
                    if "dt:attributeType" in pattern and "attributes" not in d.follow:
                        continue
                    inverse.update(_inverse_pairs(store, frontier, pattern))
            else:
                for pattern in FOLLOW[relation]:
                    direct.update(_pairs(store, frontier, pattern))
        inside = _underlying(store, {r for _, r in direct}, d.generic_arguments)
        inverse_inside = _underlying(store, {r for _, r in inverse}, d.generic_arguments)
        own = _own_names(store, {u for us in inside.values() for u in us})
        own.update(_own_names(store, {u for us in inverse_inside.values() for u in us}))
        added: dict[str, str] = {}
        for t, r in direct:
            for u in inside[r]:
                if u in own and u != t:
                    edges.add((t, u))
                    if u not in seen:
                        added[u] = own[u]
        for target, consumer in inverse:
            for u in inverse_inside[consumer]:
                if u in own and u != target:
                    edges.add((u, target))
                    if u not in seen:
                        added[u] = own[u]
        if d.max_types is not None and len(seen) + len(added) > d.max_types:
            truncated = True
            stats.append({"depth": depth, "added": len(added), "stopped": f"would exceed max_types={d.max_types}"})
            break
        seen.update(added)
        stats.append({"depth": depth, "added": len(added), "total": len(seen)})
        frontier = sorted(added)
    if frontier and d.max_depth and depth == d.max_depth and not truncated:
        # One bounded lookahead distinguishes a real depth cut from a leaf frontier.  It deliberately
        # does not expand the frontier or add new types, but preserves edges wholly within the selection.
        direct: set[tuple[str, str]] = set()
        inverse: set[tuple[str, str]] = set()
        for relation in d.follow:
            if relation in INVERSE_FOLLOW:
                for pattern in INVERSE_FOLLOW[relation]:
                    if "dt:attributeType" in pattern and "attributes" not in d.follow:
                        continue
                    inverse.update(_inverse_pairs(store, frontier, pattern))
            else:
                for pattern in FOLLOW[relation]:
                    direct.update(_pairs(store, frontier, pattern))
        inside = _underlying(store, {r for _, r in direct}, d.generic_arguments)
        inverse_inside = _underlying(store, {r for _, r in inverse}, d.generic_arguments)
        own = _own_names(store, {u for us in inside.values() for u in us})
        own.update(_own_names(store, {u for us in inverse_inside.values() for u in us}))
        omitted = False
        for t, r in direct:
            for u in inside[r]:
                if u in own and u != t:
                    if u in seen:
                        edges.add((t, u))
                    else:
                        omitted = True
        for target, consumer in inverse:
            for u in inverse_inside[consumer]:
                if u in own and u != target:
                    if u in seen:
                        edges.add((u, target))
                    else:
                        omitted = True
        if omitted:
            truncated = True
            stats[-1]["stopped"] = f"max_depth={d.max_depth}"
    return seen, sorted(edges), stats, truncated


MEMBER_TYPE_PREDICATES = ("returnType", "propertyType", "fieldType", "eventType")
XSD_INTEGER = "http://www.w3.org/2001/XMLSchema#integer"


def member_lines(store: Path, types: list[str]) -> list[str]:
    """Members of the selected types for the viewer's details panel: kind, name, type and parameters."""
    lines: list[str] = []
    memberships = _pairs(store, types, "?t dt:hasMember ?r")
    members = sorted({m for _, m in memberships})
    lines += [f"{nt_iri(t)} {nt_iri(DT + 'hasMember')} {nt_iri(m)} ." for t, m in memberships]
    for m, cls in _pairs(store, members, "?t a ?r"):
        if cls != DT + "Member":
            lines.append(f"{nt_iri(m)} {nt_iri(RDF_TYPE)} {nt_iri(cls)} .")
    lines += [f"{nt_iri(m)} {nt_iri(DT + 'name')} {nt_literal(n)} ." for m, n in _pairs(store, members, "?t dt:name ?r")]
    for predicate in MEMBER_TYPE_PREDICATES:
        lines += [f"{nt_iri(m)} {nt_iri(DT + predicate)} {nt_iri(t)} ." for m, t in _pairs(store, members, f"?t dt:{predicate} ?r")]
    lines += [f"{nt_iri(m)} {nt_iri(DT + 'usesType')} {nt_iri(t)} ." for m, t in _pairs(store, members, "?t dt:usesType ?r")]
    parameters = _pairs(store, members, "?t dt:hasParameter ?r")
    params = sorted({p for _, p in parameters})
    lines += [f"{nt_iri(m)} {nt_iri(DT + 'hasParameter')} {nt_iri(p)} ." for m, p in parameters]
    lines += [f"{nt_iri(p)} {nt_iri(RDF_TYPE)} {nt_iri(DT + 'Parameter')} ." for p in params]
    lines += [f"{nt_iri(p)} {nt_iri(DT + 'name')} {nt_literal(n)} ." for p, n in _pairs(store, params, "?t dt:name ?r")]
    lines += [f'{nt_iri(p)} {nt_iri(DT + "ordinal")} "{int(o)}"^^{nt_iri(XSD_INTEGER)} .' for p, o in _pairs(store, params, "?t dt:ordinal ?r")]
    lines += [f"{nt_iri(p)} {nt_iri(DT + 'parameterType')} {nt_iri(t)} ." for p, t in _pairs(store, params, "?t dt:parameterType ?r")]
    return lines


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


def evidence_lines(store: DependencyStores, types: dict[str, str], definition: Definition) -> list[str]:
    selected = sorted(types)
    references = {target for relation in definition.follow if relation not in INVERSE_FOLLOW
                  for pattern in FOLLOW[relation] for _, target in _pairs(store, selected, pattern)}
    underlying = _underlying(store, references, definition.generic_arguments)
    reachable = references | {target for targets in underlying.values() for target in targets}
    identities = _pairs(store, sorted(reachable | set(selected)), "?t dt:definedInAssembly ?r")
    boundary = {target for target, _ in identities if target not in types and target in reachable}
    for batch in _batches(sorted(boundary)):
        for row in _select(store, "?t", _own("t"), f"VALUES ?t {{ {_values(batch)} }}"):
            if store.reasons.get(row["t"]) not in _ADMISSION_FAILURES:
                store.reasons[row["t"]] = "selection-boundary"
    memberships = _pairs(store, selected, "?t dt:hasMember ?r")
    members = {member for _, member in memberships}
    parameters = _pairs(store, sorted(members), "?t dt:hasParameter ?r")
    owners = set(selected) | members | {parameter for _, parameter in parameters}
    links: set[tuple[str, str, str]] = set()
    predicates = []
    for relation, names in (
        ("base_types", ["inherits"]), ("interfaces", ["implements"]),
        ("enclosing_type", ["nestedIn"]), ("body_types", ["usesType"]),
        ("member_types", list(MEMBER_TYPE_PREDICATES)), ("parameter_types", ["parameterType"]),
        ("constraints", ["constrainedToType"]),
    ):
        if relation in definition.follow:
            predicates.extend(names)
    for predicate in predicates:
        for owner, target in _pairs(store, sorted(owners), f"?t dt:{predicate} ?r"):
            links.add((owner, predicate, target))
    if "parameter_types" in definition.follow:
        links.update((owner, "hasParameter", target) for owner, target in parameters)
    if "constraints" in definition.follow:
        constraints = _pairs(store, sorted(owners), "?t dt:hasTypeParameter ?r")
        links.update((owner, "hasTypeParameter", target) for owner, target in constraints)
        links.update((owner, "constrainedToType", target) for owner, target in
                     _pairs(store, sorted({target for _, target in constraints}), "?t dt:constrainedToType ?r"))
    if "attributes" in definition.follow:
        attributes = _pairs(store, sorted(owners), "?t dt:hasAttribute ?r")
        links.update((owner, "hasAttribute", target) for owner, target in attributes)
        links.update((owner, "attributeType", target) for owner, target in
                     _pairs(store, sorted({target for _, target in attributes}), "?t dt:attributeType ?r"))
    links.update((owner, "hasMember", member) for owner, member in memberships)
    wrapper_nodes = set(reachable)
    for predicate in ("genericDefinition", "arrayElementType", "pointerElementType", "signatureReturnType",
                      "signatureParameter", "callingConventionType"):
        pairs = _pairs(store, sorted(reachable), f"?t dt:{predicate} ?r")
        links.update((owner, predicate, target) for owner, target in pairs)
        wrapper_nodes.update(target for _, target in pairs)
    if definition.generic_arguments:
        arguments = _pairs(store, sorted(reachable), "?t dt:typeArgument ?r")
        links.update((owner, "typeArgument", target) for owner, target in arguments)
        wrapper_nodes.update(target for _, target in arguments)
        links.update((owner, "type", target) for owner, target in
                     _pairs(store, sorted({target for _, target in arguments}), "?t dt:type ?r"))
    links.update((owner, "parameterType", target) for owner, target in
                 _pairs(store, sorted(wrapper_nodes), "?t dt:parameterType ?r"))
    if not getattr(definition, "members", True):
        if not boundary:
            return []
        required = set(boundary)
        witness_links = set()
        frontier = set(boundary)
        while frontier:
            incoming = {link for link in links if link[2] in frontier}
            witness_links.update(incoming)
            frontier = {owner for owner, _, _ in incoming} - required - set(selected)
            required.update(frontier)
        links = witness_links
        wrapper_nodes &= required
        identities = [(subject, assembly) for subject, assembly in identities if subject in boundary]
    lines = [f"{nt_iri(owner)} {nt_iri(DT + predicate)} {nt_iri(target)} ." for owner, predicate, target in sorted(links)]
    identity_nodes = boundary | wrapper_nodes
    if getattr(definition, "members", True):
        identity_nodes.update(selected)
    assembly_by_type = dict(identities)
    for subject, assembly in identities:
        lines.append(f"{nt_iri(subject)} {nt_iri(DT + 'definedInAssembly')} {nt_iri(assembly)} .")
    for subject, kind in _pairs(store, sorted(identity_nodes), "?t a ?r"):
        lines.append(f"{nt_iri(subject)} {nt_iri(RDF_TYPE)} {nt_iri(kind)} .")
    for predicate in ("name", "fullName", "typeKind", "refKind", "signatureReturnRefKind", "callingConvention"):
        lines.extend(f"{nt_iri(subject)} {nt_iri(DT + predicate)} {nt_literal(value)} ."
                     for subject, value in _pairs(store, sorted(identity_nodes), f"?t dt:{predicate} ?r"))
    for predicate in ("ordinal", "index", "arrayRank"):
        for subject, ordinal in _pairs(store, sorted(identity_nodes), f"?t dt:{predicate} ?r"):
            lines.append(f'{nt_iri(subject)} {nt_iri(DT + predicate)} "{int(ordinal)}"^^{nt_iri(XSD_INTEGER)} .')
    assembly_values: dict[str, dict[str, str]] = {}
    for predicate in ("name", "version", "culture", "publicKeyToken"):
        for assembly, value in _pairs(store, sorted(set(assembly_by_type.values())), f"?t dt:{predicate} ?r"):
            assembly_values.setdefault(assembly, {})[predicate] = value
            lines.append(f"{nt_iri(assembly)} {nt_iri(DT + predicate)} {nt_literal(value)} .")
    for owner, predicate, target in sorted(links):
        if target not in boundary:
            continue
        assembly = assembly_by_type[target]
        evidence = {"owner": owner, "predicate": DT + predicate, "target": target, "assembly": assembly,
                    "reason": store.reasons.get(target, "external-boundary")}
        if target in store.packages:
            evidence["package"] = store.packages[target]
        store.external_references.append(evidence)
        if not {"name", "version"} <= set(assembly_values.get(assembly, {})):
            store.report("external-identity-incomplete", target=target, assembly=assembly)
    return list(dict.fromkeys(lines))


def run(definition_path: Path, data_root: str | None, output_dir: Path | None, open_page: bool) -> dict[str, Any]:
    d = load_definition(definition_path)
    root = artifacts.artifact_root(data_root)
    manifest_path = resolve_manifest(d, root)
    source_store, manifest = explore.store_for(manifest_path)
    store = DependencyStores.registered(root, d, manifest, source_store)
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
    if d.members:
        lines += member_lines(store, sorted(types))
    lines += evidence_lines(store, types, d)
    lines = list(dict.fromkeys(lines))
    collapsed = 0
    mapping = {}
    if d.logical:
        before = len(lines)
        mapping = explore.logical_map(source_store, manifest)
        for path, named in store.sources[1:]:
            for row in oxigraph.select(path, f"PREFIX dt: <{DT}> SELECT ?t ?full ?name WHERE {{ {_own('t')} "
                                            "?t dt:fullName ?full ; dt:definedInAssembly ?asm . ?asm dt:name ?name . }"):
                if row["t"] in types and row["name"] in manifest.get("view", {}).get("policyAssemblies", []):
                    mapping[row["t"]] = build.logical_iri(row["name"], row["full"])
        lines = explore.collapse(lines, mapping)
        for reference in store.external_references:
            rewritten = explore.collapse([f"{nt_iri(reference['owner'])} {nt_iri(reference['predicate'])} {nt_iri(reference['target'])} ."], mapping)[0]
            reference["owner"] = explore._NT_LINE.match(rewritten).group(1)[1:-1]
            reference["target"] = mapping.get(reference["target"], reference["target"])
        collapsed = before - len(lines)
    out_dir = output_dir or d.path.parent / "out"
    stem = d.path.name.removesuffix(".toml").removesuffix(".graph")
    data = out_dir / f"{stem}.nt"
    out_dir.mkdir(parents=True, exist_ok=True)
    data.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    explore.write_context(data, {
        "generator": "graph",
        "source": explore.source_info(manifest_path, manifest),
        "definition": {"path": str(d.path), "title": d.title, "text": d.path.read_text(encoding="utf-8")},
        "result": {"seeds": sorted(set(seeds.values())), "implementations": len(implementations), "types": len(types),
                   "referenceEdges": len(edges), "truncated": truncated, "logical": d.logical},
        "additionalComponents": store.additional_components,
        "externalReferences": store.external_references,
        "logicalTypeMappings": mapping,
        "diagnostics": store.diagnostics,
        "coverage": {"complete": not store.diagnostics, "reasons": sorted({item["reason"] for item in store.diagnostics})},
    })
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
        "diagnostics": store.diagnostics,
        "coverage": {"complete": not store.diagnostics, "reasons": sorted({item["reason"] for item in store.diagnostics})},
    }
