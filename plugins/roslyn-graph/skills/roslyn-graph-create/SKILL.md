---
name: roslyn-graph-create
description: Create or refresh immutable Roslyn Graph/Oxigraph assembly, solution, and overlay-view databases from a configured .NET workspace. Use when asked to build a configured solution into a graph database, capture a known successful build, snapshot selected assemblies or packages, compose a solution store, or create a logical dependency overlay.
---

# Roslyn Graph Create

Read `<workspace>/.roslyn-graph/workspace.toml` and select the requested profile or collection. Require an explicit collection scope for every profile.

Run the project-owned build command from the profile, or require the user to confirm a successful build and its exact outputs. Do not invent a command, reinterpret arbitrary MSBuild targets, or extract stale output after a failed build.

Capture the exact selected DLLs, repository commits, build command/result, and hashes of relevant target files. Use the Roslyn Graph extraction and Oxigraph artifact helpers to create immutable assembly stores, then compose a named-graph solution store. Validate every published store by reopening it and running a query.

For a collection with overlays, keep the base solution closure immutable. Build and snapshot overlay profiles independently, then create a new logical-type view with an explicit compatibility policy.

Report the manifest path, artifact ID, graph count, triple count, and any missing build/output prerequisite. Use `ROSLYN_GRAPH_DATA_ROOT` unless the workspace profile explicitly overrides it.
