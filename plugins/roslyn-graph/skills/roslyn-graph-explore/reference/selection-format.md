# Selection format (`roslyn-graph-selection/2`)

The explorer's **📋 Copy for Claude** button copies the types on the graph and a pointer to where they came
from; **📋 Copy this type** (details panel) copies the selected type the same way; **⬇ JSON** downloads the
payload as a file. Users paste it into a chat to start a deep dive
([../workflows/deep-dive.md](../workflows/deep-dive.md)).

The payload is deliberately small: it names the types and says which database and query produced them.
Everything else (members, signatures, edges) is looked up from that database.

```json
{
 "format": "roslyn-graph-selection/2",
 "store": "F:\\.roslyn-graph\\views\\10302c19825782554a9b\\manifest.json",
 "collection": "app_with_current_data",
 "query": { "kind": "graph", "title": "Repositories", "definition": "F:\\work\\.roslyn-graph\\graphs\\repositories.graph.toml" },
 "types": ["Contoso.Data.IRepository", "Contoso.Data.Repository"]
}
```

## Fields

| Field | Meaning |
|---|---|
| `store` | the artifact's `manifest.json`; its directory holds `store.oxigraph`. Absent for a hand-loaded file |
| `collection` | the workspace collection the artifact belongs to, for finding its latest version if `store` is gone |
| `query.kind` | `graph`: made from the `.graph.toml` at `query.definition` (`query.title` is its title). `export`: made from the CONSTRUCT at `query.file` with `query.params` (`logical: true` when exported with `--logical`), or the inline `query.text` when there was no file. `file`: loaded by hand from `query.fileName`; no store is known |
| `types` | the `dt:fullName` of each copied type, sorted: every type drawn (hidden namespaces excluded), or just the selected one. The key for every follow-up query |

`query` is absent for pages rendered before the page carried its context; ask the user which store and
query the graph came from.
