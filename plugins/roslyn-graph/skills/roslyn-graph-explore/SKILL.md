---
name: roslyn-graph-explore
description: Query and visualize published Roslyn Graph (Oxigraph) solution and view databases using the .NET type ontology. Use when asked about types, interfaces, inheritance, implementers, members, namespaces, assemblies or package versions in a Roslyn Graph database, to compare physical and logical versions, or to draw/visualize any part of it (for example "visualize all interfaces in the solution").
---

# Roslyn Graph Explore

Answers questions about .NET code captured by the roslyn-graph-create skill, and draws the answer in a
visualizer. The work is always: **understand the store → design a query against the ontology → run it →
(optionally) export a bounded subgraph and open it in a visualizer.**

## The one command

```
python <skill>/scripts/rg.py <command> ...
```

`<skill>` is this skill's folder (the one containing this SKILL.md); it carries its own copy of the CLI in
`<skill>/scripts/`, plus the ontology (`<skill>/ontology/`) and visualizers (`<skill>/visualizers/`). Every
command prints one JSON object whose `type` is the
result or `"error"` (with `code`, `message`, `hint`).

## Starting point

A **solution** or **view** `manifest.json` under `<data-root>/.roslyn-graph/` (the create skill reports
them; `rg.py inventory` lists them with status `latest`). Prefer the view when the user asks about the
solution *together with* newer builds of some assemblies; prefer the solution for "what was built".
Read the manifest first: `components` / `overlayComponents` say which assemblies and versions are in it.

## Pick a workflow

| Request | Workflow |
|---|---|
| A question with a textual answer (which types, how many, where defined, what changed between versions) | [query](workflows/query.md) |
| "Show", "draw", "visualize", "graph" anything, including graphs grown from seeds ("these interfaces, their implementations and everything they reference") | [visualize](workflows/visualize.md) |
| List, run, save, update or check the user's saved queries and graphs | [saved-queries](workflows/saved-queries.md) |

References, loaded when a workflow step needs them:
- [reference/ontology.md](reference/ontology.md): every class and predicate (generated from the plugin ontology);
- [reference/query-design.md](reference/query-design.md): store structure, the rules that keep queries fast, patterns;
- [reference/graph-definitions.md](reference/graph-definitions.md): saved `.rq` queries and `.graph.toml` traversal graphs in the workspace;
- [reference/visualizers.md](reference/visualizers.md): available visualizers and what each needs;
- [queries/](queries/): tested queries to copy or adapt (parameters are `{{NAME}}`, passed with `--param NAME=VALUE`).

Users keep their own queries and graph definitions in the workspace: `<workspace>/.roslyn-graph/queries/*.rq`
and `<workspace>/.roslyn-graph/graphs/*.graph.toml`. Check there first (`rg.py saved list`); offer to save
a new one when a request is likely to be repeated ([saved-queries](workflows/saved-queries.md)).

## Rules

- Physical assembly graphs are the truth about what was built. Use the logical projection (`--logical`,
  views only) only when the user wants versions reconciled, and say so in the answer.
- Never dump or draw the whole database. Scope every export; check the export `summary` against the
  visualizer's limits before rendering.
- Stores are read-only artifacts. Write query files and outputs outside `<data-root>/.roslyn-graph`.
