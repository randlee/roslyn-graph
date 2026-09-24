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
follow = ["base_types", "interfaces", "member_types", "parameter_types"]   # default
generic_arguments = true                       # default: List<Foo> and Foo[] reference Foo
max_depth = 0                                  # 0 = until closure (default)
max_types = 1500                               # stop before exceeding this many types (default)

[output]
visualizer = "explorer"                        # default
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
| `attributes` | attribute classes applied to it or its members |

With `generic_arguments`, constructed generics contribute their definition and every type argument, and
arrays their element type. Only component types are added; references to framework types end there.

### Output

`rg.py graph --definition <file> [--output-dir <dir>] [--open]` writes `<name>.nt` and `<name>.html`
(default folder: `out/` next to the definition) and returns a `type: "graph"` result with the seed and
implementation counts, per-depth growth (`expansion`), the total, `truncated` when `max_types` stopped
it, and the export summary.

Edges drawn: `dt:inherits`, `dt:implements` between exported types, plus `rg:references` for every other
reference that pulled a type in, drawn as dotted grey lines.

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
follow = ["base_types", "interfaces", "member_types", "parameter_types"]
max_depth = 0
max_types = 1500
```

When the result is `truncated`, narrow the seeds, drop `parameter_types`, or set `max_depth`, and tell
the user what the limit cut.
