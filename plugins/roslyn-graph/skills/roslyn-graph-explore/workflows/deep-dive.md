# Deep dive from a pasted selection

Trigger: the user pastes JSON whose `format` is `roslyn-graph-selection/2` (copied from the explorer), or
attaches a `*.selection.json` file, and asks about those types. Format:
[../reference/selection-format.md](../reference/selection-format.md).

## 1. Orient

- `types` lists the full names the user is looking at. Answer from that list when the question needs
  nothing more; do not query just to restate it.
- Take the database from `store` (a `manifest.json`; `store.oxigraph` sits beside it). Confirm it still
  exists; if it was removed or superseded (`rg.py inventory` from the create skill), tell the user and use
  the latest artifact of `collection` instead, noting that versions may differ.
- `query` says how the graph was made, for reference: read `query.definition` (graph) or `query.file` with
  `query.params` (export) when you need to extend or re-run it.
- No `store` (`query.kind` is `file`, or no `query` at all): ask which store the graph came from before
  querying.

## 2. Look up only what the question needs

Members, signatures and edges are not in the payload. Fetch them from the store when the question calls
for them, for the types it is about, rather than for the whole list up front.

## 3. Go deeper with queries

Key every query on the names in `types` (they match `dt:fullName` in every version).

| Question | How |
|---|---|
| Members and signatures of a type, or all versions side by side | `queries/type-members.rq --param TYPE=<fullName>` |
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
