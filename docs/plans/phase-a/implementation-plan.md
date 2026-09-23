# Phase A minimal code backlog

The database-creation and database-exploration workflows are implemented and reviewed as plugin skills under [`plugins/roslyn-graph`](../../../plugins/roslyn-graph). This document deliberately contains only code that should exist outside those skills.

1. Add a small .NET workspace-profile library and CLI that parses `workspace.toml`, validates explicit collection scope, resolves relative paths, resolves the data root, and returns a typed execution plan. It must not attempt to infer arbitrary MSBuild build logic.
2. Add unit tests for TOML parsing, profile/collection selection, path resolution, data-root precedence, and invalid/missing project selections.
3. Harden or replace the existing deterministic artifact helpers only where repeated use proves a need: immutable manifest publication, short-ID collision handling, and store reopen/query validation.

Do not add a generalized build engine, automatic project discovery, or an alternate implementation of the plugin workflows.
