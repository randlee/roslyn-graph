# Phase A implementation plan: skill first

## Decision

Do not build a generalized .NET build/configuration engine. Projects own their build rules, imports, generators, and conditions. The `roslyn-graph` skill must run a known project build, use the outputs that build produced, and preserve the evidence of that execution.

The durable data operations remain small and deterministic: extract one DLL, load an Oxigraph store, compose named graphs, and create an optional logical view. They may remain scripts initially. Promote only repeatedly stable, mechanical operations to .NET code.

Code is appropriate for interpreting and validating the workspace contract. It is not appropriate for guessing how an arbitrary solution ought to build.

## Inputs

The workspace provides `F:\_r2609\.roslyn-graph\workspace.toml`:

- named profiles identify a repository root, solution, explicit collection scope, and minimal build selectors;
- P3 explicitly selects every solution project;
- Data and Annotations explicitly select one project each; and
- collections describe an exact P3 build and an optional current-dependency overlay.

The workspace omits `data_root`, so `ROSLYN_GRAPH_DATA_ROOT` resolves durable storage. A profile may later carry a project-specific build command override when `dotnet build` with the stated selectors is not sufficient. The skill executes that command; it does not try to infer or synthesize an equivalent command.

## Skill workflow

1. Read the selected workspace profile and validate that its explicit project selection is unambiguous.
2. Run the profile's known build command (or the documented default) against its `.sln`. Stop on a failed build; do not extract stale binaries.
3. Record the command, exit result, solution/profile values, selected output DLL paths, repository commits, and hashes of relevant target files such as `.build\tt3\Common.targets`.
4. For every selected output, run the existing `roslyn2rdf` CLI and import the temporary RDF into an immutable per-assembly Oxigraph store with a manifest.
5. Compose the selected assembly stores into an immutable solution store with one named graph per assembly plus a metadata graph.
6. When a workspace collection names overlays, build their selected projects separately, preserve them as distinct source artifacts, and derive an immutable logical-type view from the exact base solution. Never mutate the base solution store.
7. Run validation queries, report artifact paths/IDs, and optionally `CONSTRUCT` a small, deduplicated graph payload for the viewer.

For P3, the skill runs the configured P3 solution build, records the effective TT3 target evidence, snapshots all 57 selected P3 outputs and the exact restored package assets, and then may create the Data/Annotations overlay view.

## Small implementation surface

### Workspace-profile code

Add a small .NET `WorkspaceProfile` library and CLI surface. It should:

- parse `workspace.toml` with a maintained TOML parser;
- validate the schema and mutually exclusive collection modes;
- resolve repository, solution, and selected-project paths relative to the workspace file;
- resolve `dataRoot` using explicit option → TOML override → `ROSLYN_GRAPH_DATA_ROOT`;
- select a named profile or collection and return a typed, serializable execution plan; and
- reject missing paths, duplicate selections, or an unspecified collection scope before a build starts.

It must not inspect arbitrary `.targets` files to invent a build, mutate profile settings, or substitute its own project selection. This code gives the skill a reliable typed contract and makes profile validation unit-testable.

### Skill

Create a concise `roslyn-graph` skill after the workspace TOML and reference workflow are accepted. It should contain only:

- profile and collection selection rules;
- build/run/stop-on-failure rules;
- provenance and validation requirements;
- paths to the artifact scripts and query templates; and
- a reference for the workspace TOML schema and P3-specific evidence.

Do not embed project-specific build logic in the skill. The workspace profile or an explicit user-provided command supplies it.

### Scripts now

Keep and harden the three reference operations:

- `Invoke-AssemblySnapshot.ps1`;
- `Invoke-SolutionComposition.ps1`; and
- `Invoke-LogicalTypeView.ps1`.

They need only accept already-built assembly paths/manifests, enforce immutable short-path publication, and validate their own output. They do not evaluate MSBuild, discover arbitrary package layouts, or decide which projects matter.

Add a thin skill-owned orchestrator script only if the repeated shell plumbing becomes error-prone. It should obtain the typed profile plan from the profile CLI, invoke the build command, and pass explicit paths to the three operations.

### Existing .NET code

Continue using the existing `Roslyn2Rdf.Cli` for DLL-to-RDF extraction. Add the small TOML profile library/CLI, but no .NET build-evaluation framework is required for Phase A.

Later, add .NET code only for a proven need—for example, a stable manifest library, a fast local query service, or a viewer API. Such code must not take ownership of building arbitrary customer solutions.

## Required validation

- The configured build succeeds in the current workspace before any extraction.
- Every configured selected project has exactly one recorded output DLL for the requested build.
- Every artifact has a manifest and passes a reopen/query check.
- The solution metadata graph has the same membership as the configured selected outputs.
- An overlay is visibly distinct from the base build and uses an explicit logical-type policy.
- Interface graph export uses distinct node/edge identities before viewer rendering.
- Repeating the same successful profile/build produces the same artifact IDs and does not overwrite data.

## Delivery sequence

1. Finalize and validate `workspace.toml` against the P3, Data, and Annotations reference builds.
2. Create the skill and use the current scripts beneath it for one complete P3 reference run.
3. Add unit tests for workspace profile parsing/path resolution and only the tests needed for scripts and P3 workflow failure boundaries.
4. Improve or replace a helper with .NET code only after real repeated use demonstrates the need.
