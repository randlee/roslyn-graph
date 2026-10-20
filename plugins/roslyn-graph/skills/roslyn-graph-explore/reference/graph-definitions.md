# Saved graph definitions

Two kinds of saved exploration files live in the workspace, next to `workspace.toml`:

```
<workspace>/.roslyn-graph/
  workspace.toml
  queries/<name>.rq            SPARQL queries (SELECT or CONSTRUCT), with {{PARAM}} placeholders
  graphs/<name>.graph.toml     traversal graphs built by `rg.py graph`
  graphs/out/                  generated .nt and .html (derived; add to .gitignore)
```

- **`.rq`** is the standard SPARQL query extension (editors highlight it). Use it for questions a single
  query answers well, and run it with `rg.py query` or `rg.py export`. Saved `.rq` files carry a header
  (title, store collection, parameters with examples); see [../workflows/saved-queries.md](../workflows/saved-queries.md).
- **`.graph.toml`** is for graphs that grow from seeds, such as "these interfaces, all their
  implementations, and everything those reference, recursively". A single SPARQL query cannot express
  that with depth limits and stay fast across many assembly graphs; `rg.py graph` expands it level by
  level with graph-scoped, batched queries.

## Format (schema version 1)

```toml
schema_version = 1
title = "Repository layer"                     # page title; defaults to the file name

[source]                                       # exactly one of collection / manifest
workspace = "../workspace.toml"                # default: the workspace.toml beside the graphs folder
collection = "app_with_current_data"           # latest view (collections with overlays) or solution
# manifest = "views/<id>/manifest.json"         # or a specific artifact, relative to the artifact root
logical = true                                 # views: one node per type across versions (default true)

[seeds]                                        # at least one of types / patterns
types = ["Contoso.Data.IRepository"]           # full names exactly as stored (C# display names)
patterns = ["Contoso.Data.I*Store*"]           # globs over full names: * any run, ? one character
kinds = ["Interface"]                          # optional filter for pattern matches: Class Interface Struct Enum Delegate
implementations = "transitive"                 # none | direct | transitive (default)

[expand]
follow = ["base_types", "interfaces", "member_types", "parameter_types", "constraints", "enclosing_type", "body_types"]   # default
generic_arguments = true                       # default: List<Foo> and Foo[] reference Foo
max_depth = 0                                  # 0 = until closure (default)
# max_types = 1500                             # optional positive cap; omitted = until closure (default)

[output]
visualizer = "explorer"                        # default
members = true                                 # default: export each type's members for the details panel
```

### Seeds and implementations

Seeds are matched against the store's **component** types (types defined by the solution's own
assemblies and packages, never framework stubs), in every physical version. A seed that matches nothing
is an error (`GRAPH_SEED_NOT_FOUND`); find exact names with `queries/find-type.rq`.

- `direct`: types whose `dt:implements` or `dt:inherits` names a seed (including constructed generics
  such as `IStore<Order>` for a seed `IStore<T>`).
- `transitive`: repeat with the types found until nothing new appears: interfaces extending a seed,
  their implementers, and subclasses of implementers.

### Expansion relations

| `follow` value | A type references |
|---|---|
| `base_types` | its base class (`dt:inherits`) |
| `interfaces` | the interfaces it implements or extends (`dt:implements`) |
| `member_types` | return, property, field and event types of its members |
| `parameter_types` | parameter types of its methods, constructors and indexers |
| `constraints` | constraints on its type or method type parameters |
| `enclosing_type` | its containing type when it is nested |
| `body_types` | statically bound types used by its members (`dt:hasMember` / `dt:usesType`), including uncalled private bodies |
| `attributes` | attribute classes applied to it or its members |
| `referenced_by` | component types that consume it through inheritance, interfaces, member/parameter/body types or constraints; attribute consumers only when `attributes` is also enabled |

With `generic_arguments`, constructed generics contribute their definition and every type argument, and
arrays and pointers their element type. Function pointers contribute `dt:signatureReturnType`,
`dt:signatureParameter` / `dt:parameterType`, and `dt:callingConventionType` targets. Delegate Invoke
signatures use the existing member/parameter relations. Saved explicit follow lists are preserved:
`body_types` is a default for omitted lists, not an automatic addition to a saved list.

Only component definitions enter the traversal frontier. Registered, already-analyzed dependencies
may supply a reached definition by exact bound assembly/type identity and configured TFM. Reduction
never downloads packages, restores, executes the build plan or regenerates artifacts. Unregistered
dependencies remain external boundaries, not extra movable types.

### Output

`rg.py graph --definition <file> [--output-dir <dir>] [--open]` writes `<name>.nt` and `<name>.html`
(default folder: `out/` next to the definition) and returns a `type: "graph"` result with the seed and
implementation counts, per-depth growth (`expansion`), the total, `truncated` when an explicit `max_types`
or positive `max_depth` stopped expansion, and the export summary.

Edges drawn: `dt:inherits`, `dt:implements` between exported types, plus `rg:references` for every other
reference that pulled a type in, drawn as dotted grey lines.

With `members = true` (the default) every exported type also carries its members: kind, name, type
(`dt:returnType`, `dt:propertyType`, `dt:fieldType`, `dt:eventType`) and parameters (name, ordinal,
type), plus original `dt:usesType` body edges. Self-use facts remain even though projected
`rg:references` self-edges are omitted. With `logical = true` the members of a type present in
several versions are merged with the type. Set `members = false` for very large graphs.

### Dependency context and boundaries

The adjacent context pins admitted artifacts in `additionalComponents`. Each entry records
`artifactId`, `graphIri`, `manifestPath`, `origin`, `package` and `assembly`; the source manifest is
not modified. `logicalTypeMappings` preserves physical-to-logical identities for newly admitted
types when the source view uses logical output. Reopening uses these pins, not a newer catalog.

`externalReferences` records unresolved boundary evidence: owner, predicate, target, assembly,
reason and known manifest package identity. Boundary types retain their available RDF identity and
connecting wrapper/signature edges, but do not enter the frontier or count as selected components.
Package identity is never inferred from an assembly name. Attribute-only boundaries require
`attributes` in the follow list.

Missing, unreadable, incompatible or ambiguous registered artifacts are diagnosed as incomplete
coverage while independent branches continue. Ambiguity reports candidate artifact IDs and admits
neither; there is no newest-version fallback. An unregistered package is an intentional boundary.
Legacy missing identity fields are reported, not invented. Published manifests lack affirmative
body-coverage certification, so known facts remain usable but missing coverage evidence is
unknown/incomplete; even existing `dt:usesType` triples do not certify completeness.
Store/query/resource failures remain errors, not complete partial results.

## Example

```toml
schema_version = 1
title = "Repositories: interfaces, implementations and what they use"

[source]
collection = "app_with_current_data"

[seeds]
patterns = ["Contoso.Data.I*Repository*"]
kinds = ["Interface"]
implementations = "transitive"

[expand]
follow = ["base_types", "interfaces", "member_types", "parameter_types", "constraints", "enclosing_type", "body_types"]
max_depth = 0
# max_types = 1500  # optional cap
```

When the result is `truncated`, an explicit type cap or depth bound cut the traversal; tell the user which
limit cut it. `rg.py export` accepts optional `--max-triples N`, which sets a positive export cap and fails loudly
when reached. `--max-triples` cannot be combined with `--unbounded`, which preserves the compatibility mode that disables
the export timeout. Explicit `LIMIT` clauses in saved queries are preserved.
