# Visualize workflow

Example requests:
- "visualize all interfaces in the solution plus the current Data and Annotations builds" — a scoped
  CONSTRUCT (steps 1–4 below);
- "graph the measurement-database interfaces, all their implementations and everything those reference"
  — a traversal graph (next section).

## Traversal graphs (seeds → implementations → recursive references)

Use a `.graph.toml` definition ([../reference/graph-definitions.md](../reference/graph-definitions.md)):

1. Look for an existing definition in `<workspace>/.roslyn-graph/graphs/`. Otherwise write one there:
   seeds as full names or globs (find names with `queries/find-type.rq`), `implementations`, the
   `follow` relations the user means by "references", and limits.
2. Run it:

   ```
   python <plugin>/scripts/rg.py graph --definition <workspace>/.roslyn-graph/graphs/<name>.graph.toml --open
   ```

3. Report from the `type: "graph"` result: seeds, implementations, growth per depth (`expansion`), total
   types, and whether `truncated` stopped it (then offer to narrow it). The page shows `inherits`,
   `implements` and dotted `references` edges.

## Scoped CONSTRUCT

## 1. Choose the store and the visualizer

- Store: the view that combines the solution with the overlays (or the solution when no overlays are
  involved). See the query workflow, step 1.
- Visualizer: run `python <plugin>/scripts/rg.py visualizers` and pick the one whose description fits; read
  its entry in [../reference/visualizers.md](../reference/visualizers.md) for the input it needs
  (for `explorer`: typed nodes with `dt:name`, namespaces with `dt:name`, `dt:implements`/`dt:inherits`
  edges) and its size limit.

## 2. Design a CONSTRUCT query

Start from [../queries/](../queries/): `interfaces.rq`, `implementers.rq` and `namespace-hierarchy.rq`
are viewer-ready. A viewer-ready CONSTRUCT emits, for every node:
`a <dt class>`, `dt:name`, `dt:fullName`, `dt:inNamespace ?ns`, and `?ns dt:name <full namespace>` (use
the namespace's `dt:fullName` as its label). Follow [../reference/query-design.md](../reference/query-design.md).

## 3. Export

```
python <plugin>/scripts/rg.py export --manifest <manifest.json> --query-file <file.rq> [--param NAME=VALUE ...] --output <out>.nt [--logical]
```

- `--logical` (views only) merges physical versions of policy assemblies into one node per logical type,
  so a type present in both the packaged and the current source build is drawn once. Use it when the user
  asks about the combined solution; omit it to compare versions side by side.
- Check `summary.nodesByKind` and `summary.edges` against the visualizer's limit (explorer: about 1,500
  type nodes). If it is larger, narrow the query (a namespace, an assembly, one interface's implementers)
  and tell the user what was left out.

## 4. Render and open

```
python <plugin>/scripts/rg.py render --visualizer explorer --data <out>.nt --output <out>.html --title "<what it shows>" --open
```

The page is self-contained apart from the libraries it loads from public CDNs. Tell the user the file
path, what the graph contains (counts from the export summary), and what was excluded.

## Reference result

On a 61-assembly view (57 solution projects, two packages and their two newer source builds, about 2.8
million triples), `interfaces.rq` with `--logical` exported 1,386 interfaces with 3,354 inheritance edges
in under a second. That is at the explorer's size limit; narrow by namespace for a readable picture.
A traversal graph seeded with 5 interfaces added 10 implementations and closed after 6 levels at 193 types
(170 drawn after merging versions) in about 3 seconds.
