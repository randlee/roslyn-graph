---
name: roslyn-graph-create
description: Design workspace.toml for .NET solutions and NuGet packages, generate immutable validated Roslyn Graph (Oxigraph) databases from it, and maintain them when sources or packages change. Use when asked to set up Roslyn Graph for a solution or package, build or rebuild its graph databases, capture a new version, check that stores are valid, or clean up old artifacts.
---

# Roslyn Graph Create

Turns `.NET` build outputs and NuGet packages into immutable Oxigraph stores: one per assembly, one per
solution build, and optional logical-type views that reconcile compatible versions. Everything is driven
by one `workspace.toml`; every store is validated before and after it is published.

## The one command

All work goes through the plugin CLI (Python 3.11+, standard library only):

```
python <skill>/scripts/rg.py <command> ...
```

`<skill>` is this skill's folder (the one containing this SKILL.md); the skill carries its own copy of the
CLI in `<skill>/scripts/`, so it works however it was installed. Every command prints exactly one
JSON object whose `type` is the result type or `"error"`. On `"error"`, read each entry's `code`,
`message` and `hint`; the hint says what to change. Never parse progress text on stderr.

## Preconditions

- **Solution profiles** need a successful build that *you* produce first, with exactly the settings the
  profile records. Building a solution is outside this skill: follow the repository's own build
  instructions. The skill checks that outputs exist, are fresh and come from committed sources; it cannot
  prove they were built with the recorded configuration or platform. That is your responsibility.
- **NuGet profiles** need nothing: the TOML plus this skill hold everything required.
- Tools: see [reference/setup.md](reference/setup.md) (Oxigraph, the RoslynToRdf extractor, .NET SDK,
  `ROSLYN_GRAPH_DATA_ROOT`).

## Pick a workflow

| Situation | Workflow |
|---|---|
| No `workspace.toml`, or a solution/package must be added to it | [a) design-toml](workflows/design-toml.md) |
| `workspace.toml` exists and the collection has never been generated | [b) generate-initial](workflows/generate-initial.md) |
| Databases exist and sources, packages, the extractor or the TOML changed; or validation/cleanup is requested | [c) maintain](workflows/maintain.md) |

Load only the workflow you need; each one links the reference pages it uses at the step that needs them.

## Rules

- Never hand-edit or delete anything under `<data-root>/.roslyn-graph` except through `rg.py remove`,
  and only after the user approves the specific paths.
- Never publish a store that has not passed validation; `generate` enforces this. Report failures with
  their check IDs ([reference/validation.md](reference/validation.md)).
- Never put secrets in `workspace.toml`. Feeds that need credentials name an environment variable.
