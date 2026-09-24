# Visualizers

Visualizers live in `<plugin>/visualizers/<name>/` and are declared in `<plugin>/visualizers/registry.json`.
`rg.py visualizers` prints the registry; `rg.py render --visualizer <name>` builds a page for one.

## explorer

Interactive type graph (Cytoscape): nodes are types coloured by kind and grouped by namespace, edges are
`implements` and `inherits`; clicking a node shows its members and signatures; namespaces can be toggled
and types searched.

| | |
|---|---|
| Render mode | `embed-rdf`: the exported N-Triples are embedded in a copy of `explorer.html`, with its parser inlined |
| Draws | subjects typed `dt:Class`, `dt:Interface`, `dt:Struct` or `dt:Enum` that have a `dt:name` (records are typed `dt:Class` too) |
| Groups by | `dt:inNamespace` → namespace `dt:name` (export the namespace's full name as `dt:name`) |
| Edges | `dt:implements`, `dt:inherits` — only between drawn types |
| Details panel | `dt:hasMember` with member `dt:name`, `dt:returnType`, `dt:hasParameter`, `dt:parameterType`, `dt:ordinal` |
| Size | responsive to roughly 1,500 type nodes |
| Needs | a browser with network access to cdnjs and unpkg (Cytoscape, N3) |

To include member details, add to the CONSTRUCT template
`?t dt:hasMember ?m . ?m a ?memberClass ; dt:name ?memberName .` (and return/parameter types as needed);
this grows the export quickly, so do it only for small type sets.

## Adding a visualizer

1. Create `<plugin>/visualizers/<name>/` with its page and scripts.
2. Add an entry to `registry.json`: `description`, `render` (a mode `rg.py render` supports; today
   `embed-rdf`), `template`, `inlineScripts`, `input`, `reads`, `limits`, `requiresNetwork`.
3. A template for `embed-rdf` must reference each inline script as `<script src="<file>"></script>` and
   load the graph from `<script type="text/turtle" id="roslyn-graph-data">` when present.
4. Document it in this file; the plugin tests check every registered visualizer's files exist.

A visualizer that needs another input shape (for example JSON nodes and edges) needs a new render mode in
`scripts/roslyn_graph/explore.py`, with tests.
