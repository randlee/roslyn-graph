# Deep dive from a pasted selection

Trigger: the user pastes JSON whose `format` is `roslyn-graph-selection/1` (copied from the explorer), or
attaches a `*.selection.json` file, and asks about those types. Format:
[../reference/selection-format.md](../reference/selection-format.md).

## 1. Orient

- Read `summary`, `scope`, `view` (what the user filtered to, searched for and selected) and `types`.
  `view.selectedType` and `view.searchMatches` usually say where the user's attention is; start there.
- Take the store from `context.source.manifest`. Confirm it still exists; if it was removed or superseded
  (`rg.py inventory` from the create skill), tell the user and use the latest artifact of
  `context.source.collection` instead, noting that versions may differ.
- `context.generator` tells you how the graph was made: re-read `context.definition.text` (graph) or
  `context.query.text` with `context.query.params` (export) before extending it.
- `context: null` (hand-loaded file): ask which store the graph came from before querying.

## 2. Answer from the payload first

Signatures, inheritance and the edges between the copied types are already in the JSON. Answer questions
about them directly and quote signatures verbatim; do not re-query what the payload already states.

## 3. Go deeper with queries

Use the store for everything the payload does not contain. Key every query on `types[].fullName`
(it matches `dt:fullName` in every version); use `types[].iri` only for physical IRIs.

| Question | How |
|---|---|
| Members of a type not in the payload, or all versions side by side | `queries/type-members.rq --param TYPE=<fullName>` |
| Who implements an interface (beyond this graph) | `queries/implementers.rq --param INTERFACE=<fullName>` (`export` + `render` to draw it) |
| What a type depends on, recursively | a `.graph.toml` seeded with the type, `implementations = "none"` ([../reference/graph-definitions.md](../reference/graph-definitions.md)) |
| Everything built around an interface | a `.graph.toml` seeded with it, `implementations = "transitive"` |
| Which version introduced or changed a type | `queries/logical-versions.rq` (views), then `type-members.rq` for both versions |
| Where a type is used as a member or parameter type | a SELECT over `dt:returnType`/`dt:propertyType`/`dt:fieldType`/`dt:parameterType` pointing at the type, scoped with `GRAPH ?g` ([../reference/query-design.md](../reference/query-design.md)) |

The ontology describes declarations and relationships (types, members, signatures, inheritance,
attributes, XML-doc `throws`/`seealso`); it has no method bodies or call graph. Say so when a question
needs runtime behaviour, and offer to read the source repository instead (the component's
`origin.repository` and `build.project` are in its assembly manifest).

## 4. Hand back something reusable

When the investigation should be repeatable, offer to save the query or graph definition in the user's
workspace ([saved-queries.md](saved-queries.md)); when a new graph helps, render it so the user can
explore it and copy a refined selection back.
