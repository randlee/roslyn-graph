# Phase A implementation plan

## Outcome to implement

`roslyn-graph` will maintain immutable assembly/package Oxigraph artifacts and immutable solution and analysis-view artifacts at the configured data root. On this machine, the persistent setting is `ROSLYN_GRAPH_DATA_ROOT=F:\`, so the root is `F:\.roslyn-graph`.

The system must answer both questions without conflating them:

- **Build truth:** what exact types and relationships were present in a particular configured solution build?
- **Analysis truth:** how do explicitly compatible physical package/source versions present as one logical type to queries and visualization?

## Product work

1. **Storage library and schema.** Add a tested .NET storage layer for root resolution, SHA-256 artifact identity, filesystem-safe path layout, manifests, staging, locks, atomic publication, integrity reopening, and retention/cleanup. Use a 20-hex identity prefix that expands to 32 then 64 on a detected manifest-ID collision; keep all full provenance in the manifest. Require a path budget before any Oxigraph write.
2. **Workspace profile resolver.** Add a versioned TOML workspace file at `<workspace>\.roslyn-graph\workspace.toml`. Each named profile requires a repository-relative root, solution, explicit collection scope (`all_solution_projects` or a project list), and minimal build selectors. Collections refer to profiles by name to describe exact builds and optional overlays. Make `dataRoot` optional and default to `ROSLYN_GRAPH_DATA_ROOT`. Validate requested settings against evaluated MSBuild results rather than copying all derived constants into TOML.
3. **Assembly and package snapshot commands.** Productize the reference PowerShell behavior as CLI commands. Accept exact DLL input plus build provenance; resolve NuGet package/asset provenance from restore assets and lock files; emit a manifest and Oxigraph store without retaining TTL by default.
4. **Build capture.** Add an MSBuild logger/binlog reader that captures solution membership, output DLL path, evaluated target framework/configuration/platform/properties, imported condition files and hashes, dependency search paths, and project/repository provenance. Do not derive project membership by directory scanning.
5. **Solution snapshot command.** Resolve the captured assembly artifact IDs, validate completeness, load each into its deterministic named graph, add a metadata graph, optimize, reopen/validate the published database, and expose the resulting solution artifact ID.
6. **Derived analysis views.** Implement a policy-driven overlay command. It must declare the base solution artifact, additional artifacts, compatibility policy/version, logical-key algorithm, and generated graph. It must never alter the base solution store.
7. **Logical-type policy.** Start with a reviewed allowlist for Radiant.Data and Radiant.Annotations. Compatibility must be an input and an auditable result, not an assumption from matching package names. Record unmatched, added, removed, and incompatible types in the view manifest.
8. **Query and extraction API.** Add parameterized query templates and `CONSTRUCT` export for a viewer: graph membership, type/interface graph, inheritance, implementation, callers, and logical type projection. Return a filtered Turtle/N-Quads subgraph only after selecting distinct node/edge identities.
9. **Viewer integration.** Make the HTML viewer consume N-Quads/Turtle through the already corrected N3 parser; add deterministic client-side deduplication and a graph-selection/filter model. The interface graph query must use the logical projection where selected, retain physical-version drill-down, and avoid duplicate cross-graph edges.
10. **Skill and scripts.** Once commands and evidence formats are stable, create/update the `roslyn-graph` skill with the exact workflow: resolve profile → capture build → snapshot closure → compose solution → optionally derive view → query/export/view. The skill should be thin orchestration over the CLI, not a second implementation.

## Required test coverage

- Unit: root precedence, path budget, deterministic identity, manifest validation, N-Triples escaping, package asset selection, and compatibility-key generation.
- Integration: a fixture solution with conditional compile symbols and multiple projects; verify its captured outputs are exactly the composed named graphs.
- Failure/recovery: malformed Turtle, failed loader, interrupted stage, duplicate immutable destination, long destination path, and lock contention. Verify no partial publication.
- Versioning: two compatible assembly versions produce distinct physical nodes and one logical node; an incompatible or unapproved version is not merged.
- Query/viewer: interface query returns distinct edge identities; generated RDF parses in the viewer; physical provenance drill-down remains available.
- Regression: Roslyn member/indexer IRI escaping and multi-assembly CLI aggregation already added on `develop` remain covered.

## Delivery sequence

1. Land storage/manifests/path guard and tests.
2. Land assembly/package snapshot with fixture tests.
3. Land build capture and solution composition with an end-to-end fixture.
4. Land logical view policy and version tests.
5. Land query/export endpoints and viewer tests.
6. Write the skill from the stabilized commands, then run this same P3 reference workflow through it.

## Completion criteria

- A new P3 build can be captured without manually preparing a DLL list.
- Repeating identical inputs returns the same immutable artifact; changed build/package/source inputs produce new IDs.
- The exact solution closure, all provenance, and an optimized/reopenable Oxigraph store are published under the configured root.
- The logical view exposes one display/query resource per approved logical type while preserving every physical source/package version.
- A query can generate a compact interface graph payload that the viewer renders without duplicate nodes or edges.
