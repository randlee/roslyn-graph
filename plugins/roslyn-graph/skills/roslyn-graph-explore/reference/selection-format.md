# Selection format (`roslyn-graph-selection/1`)

The explorer's **📋 Copy for Claude** button copies what is on the graph as JSON; **📋 Copy this type**
(details panel) copies the selected type; **⬇ JSON** downloads the same payload as a file. Users paste it
into a chat to start a deep dive ([../workflows/deep-dive.md](../workflows/deep-dive.md)).

```json
{
 "format": "roslyn-graph-selection/1",
 "note": "…",
 "scope": "graph",
 "context": {
  "format": "roslyn-graph-context/1",
  "createdUtc": "2026-09-24T03:10:00+00:00",
  "generator": "graph",
  "source": {
   "manifest": "F:\\.roslyn-graph\\views\\10302c19825782554a9b\\manifest.json",
   "store": "F:\\.roslyn-graph\\views\\10302c19825782554a9b\\store.oxigraph",
   "kind": "view", "artifactId": "10302c19…", "collection": "app_with_current_data", "profile": "app",
   "workspace": "F:\\work\\.roslyn-graph\\workspace.toml"
  },
  "definition": { "path": "…\\graphs\\repositories.graph.toml", "title": "…", "text": "schema_version = 1 …" },
  "result": { "seeds": ["Contoso.Data.IRepository"], "implementations": 4, "types": 37, "referenceEdges": 52,
              "truncated": false, "logical": true }
 },
 "view": {
  "visibleNamespaces": ["Contoso.Data"], "hiddenNamespaces": ["Contoso.Logging"],
  "search": "repo", "searchMatches": ["Contoso.Data.IRepository", "Contoso.Data.Repository"],
  "selectedType": "Contoso.Data.IRepository"
 },
 "summary": { "types": 37, "members": 164, "edges": 71 },
 "types": [
  {
   "fullName": "Contoso.Data.IRepository", "name": "IRepository", "kind": "interface",
   "namespace": "Contoso.Data", "inherits": [], "implements": ["IDisposable"],
   "members": [ { "kind": "method", "signature": "Task<Record> Load(Guid id, CancellationToken token)" } ],
   "iri": "urn:roslyn-graph:logical-type:…"
  }
 ],
 "edges": [ { "from": "Repository", "to": "IRepository", "kind": "implements" } ]
}
```

## Fields

| Field | Meaning |
|---|---|
| `scope` | `graph`: every type drawn (namespaces the user hid are excluded); `type`: only the selected type, with all its edges |
| `context.generator` | `graph` (from a `.graph.toml`, text in `context.definition`), `export` (from a CONSTRUCT, text and parameters in `context.query`), or `file` (loaded by hand; only `fileName`, no store) |
| `context.source` | the store to query: `manifest` and `store` paths, `kind` (solution or view), `artifactId`, `collection` |
| `view` | the filters applied in the explorer when copying; `searchMatches` are the types the search box highlights |
| `types[].fullName` | the stored `dt:fullName` (C# display name); the key for every follow-up query |
| `types[].iri` | the node's IRI: a physical type IRI (`http://dotnet.example/type/<assembly>/<version>/…`) or, in logical exports, `urn:roslyn-graph:logical-type:…` |
| `types[].members[].signature` | `ReturnType Name(ParamType param, …)` for methods, `Type Name` for properties and fields, `event Type Name`; type names are the explorer's display names (simple names for types outside the graph) |
| `edges[].kind` | `implements`, `inherits`, or `references` (a member or parameter type that pulled the target into the graph) |

Older pages without an embedded context (rendered before this format) give `context: null`; ask the user
which store the graph came from.
