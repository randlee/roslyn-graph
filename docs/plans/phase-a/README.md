# Phase A: Manual artifact and solution-store workflow

Status: reference run completed 2026-09-23

## Objective

Establish and record a repeatable manual workflow for turning a successful .NET build into durable Roslyn Graph artifacts:

1. immutable Oxigraph stores for individual built assemblies;
2. an immutable Oxigraph store for one solution build; and
3. a solution-facing logical-type view that can reconcile compatible package versions without losing physical-build provenance.

This record is the reference implementation for later commands, tests, and the `roslyn-graph` skill. Do not automate a step until it has been performed, evidenced, and accepted here.

## Agreed data model

- An assembly artifact is immutable evidence of one compiled assembly under one build context.
- A solution is a configured build, not merely a `.sln` filename. Its identity includes source revision, target framework, configuration, platform, effective MSBuild properties, and compile conditions.
- Source-built artifacts use repository branch and commit provenance.
- NuGet-built artifacts use package ID, package release version, package hash, feed, selected target-framework asset, and contained assembly identity.
- A temporary TTL is an interchange/import artifact. The durable artifact is an Oxigraph store plus a manifest.
- Physical type identities retain their assembly version. A later logical-type projection provides one display/query node per compatible logical type; it does not use `owl:sameAs`.

## Data-root contract

Resolve the artifact root in this precedence order:

1. `--data-root`
2. `ROSLYN_GRAPH_DATA_ROOT`
3. application-defined default location

All durable artifacts reside beneath `<data-root>\.roslyn-graph`. The source checkout is not the default data root.

Phase A uses the persistent user environment variable `ROSLYN_GRAPH_DATA_ROOT=F:\`, which resolves the artifact root to `F:\.roslyn-graph`. New shells inherit this setting; reference commands in an existing shell pass `-DataRoot F:\` explicitly.

## Workspace analysis profile

Build selection belongs in one small workspace-local TOML file, not in the data root and not in an invocation full of copied command-line properties. The P3, Data, and Annotations profiles plus their collection relationship are in [`F:\_r2609\.roslyn-graph\workspace.toml`](F:\_r2609\.roslyn-graph\workspace.toml). Each `profiles.<name>.collect` table belongs unambiguously to its named profile: P3 selects all solution projects, while Data and Annotations select only their respective `Radiant.Data.csproj` and `Radiant.Annotations.csproj` outputs.

There is deliberately no output-root field: this workspace uses `ROSLYN_GRAPH_DATA_ROOT`. The product command resolves paths relative to the workspace file, evaluates MSBuild with the selected profile, and records the resulting effective configuration and symbols. For P3, `.build\tt3\Common.targets` makes the effective configuration `Debug-Net10-TT3X`; the profile does not duplicate derived constants such as `TRUETEST3X`.

```text
<data-root>\.roslyn-graph\
  assemblies\
    source\<repository>\<artifact-id-prefix>\
        manifest.json
        store.oxigraph\
    nuget\<package-id>\<package-version>\<artifact-id-prefix>\
        manifest.json
        store.oxigraph\
  solutions\<repository>\<solution-name>\<artifact-id-prefix>\
      manifest.json
      store.oxigraph\
  views\<artifact-id-prefix>\
    manifest.json
    store.oxigraph\
  staging\
  locks\
```

Branch is navigational metadata. Commit, build fingerprint, and package hash are immutable identity inputs.

Every `<artifact-id-prefix>` begins as the first 20 hexadecimal characters (80 bits) of the full SHA-256 artifact identity. If that directory already belongs to another full ID, the resolver tries 32 characters and then the complete ID; a remaining collision is an error. This avoids collision-based overwrites without carrying every provenance value in the filesystem path. Oxigraph must reopen RocksDB files under the path on Windows, and full provenance is immutable in the manifest. Published `store.oxigraph\CURRENT` paths must be at most 240 characters; the reference helpers reject longer paths before publication.

## Manual reference workflow

### 0. Capture build evidence

Before extraction, record:

- source repository location, branch, and commit;
- `.sln` path and all repositories/projects participating in the build;
- target framework, configuration, platform, and supplied MSBuild properties;
- the effective condition file(s), including a content hash for generated files such as `Common.targets`;
- a successful build result and, when available, the build binlog;
- exact output DLL paths selected by the build.

Do not infer the assembly list by scanning directories. Derive it from the successful build and its solution/project outputs.

### 1. Snapshot a source-built assembly

1. Build the selected project with the recorded build context.
2. Create a staging directory under the data root.
3. Run `roslyn2rdf` for the exact output DLL, with dependency search paths from that build.
4. Load the emitted TTL into a new Oxigraph store in staging.
5. Record the triple count, store content/hash evidence, assembly identity, and build provenance in `manifest.json`.
6. Validate representative SPARQL queries against the store.
7. Atomically move the complete store and manifest into its immutable assembly location.
8. Remove the staging TTL only after validation succeeds.

### 2. Snapshot a NuGet package assembly

1. Resolve the package from the successful restore/build assets, not from a source checkout.
2. Record package ID, release version, feed, `.nupkg` SHA-256, selected TFM asset, and assembly identity.
3. Extract the selected DLL to staging without modifying the package cache.
4. Follow the source-assembly snapshot procedure from step 3 onward.

Source clones may be snapshot separately as source artifacts. They must not be labeled as NuGet artifacts merely because they produce a package-named assembly.

### 3. Compose a solution store

1. Use the `.sln`, build evidence, and effective build properties to resolve the exact participating assembly artifacts.
2. Write a solution manifest listing every assembly-store identity and the complete build context.
3. Create a new Oxigraph store in staging.
4. Load each assembly artifact into a deterministic named graph.
5. Add a solution metadata graph that records membership, build inputs, package provenance, and timestamps.
6. Validate graph membership, assembly counts, and representative cross-assembly queries.
7. Atomically publish the solution store and manifest to the immutable solution location.

### 4. Build the logical-type projection

1. Preserve each physical versioned type node in the component named graphs.
2. Generate a solution-level logical type resource for compatible versions using a stable key: publisher/assembly identity plus full metadata type name, without package release version.
3. Link physical nodes with a project-specific relation such as `dt:logicalType` and record source/version provenance.
4. Direct visualization and logical API queries to this projection so a compatible type appears once.
5. Keep policy and evidence explicit for renamed, removed, or otherwise incompatible types; do not silently merge them.

## Phase A acceptance checks

- Every published assembly store has a complete manifest and passes a basic SPARQL query.
- No failed or partial staging store is published as an artifact.
- A solution manifest exactly lists the project assemblies selected by the successful build.
- Named graph count matches solution membership.
- A cross-assembly query returns expected P3-to-dependency relationships.
- The logical projection links compatible package versions while preserving each physical source/version identity.
- Repeating the same snapshot inputs yields the same artifact identity and does not overwrite immutable data.

## Completed P3 reference run

The full evidence, commands, artifacts, and validation queries are recorded in [reference-run-2026-09-23.md](reference-run-2026-09-23.md). The reviewable workflow source is the [`roslyn-graph` plugin](../../../plugins/roslyn-graph); [implementation-plan.md](implementation-plan.md) is restricted to the small code backlog outside the plugin.

The PowerShell files under `scripts/` are executable reference aids, not the production interface. The plugin skills invoke the workspace's known build and these small deterministic artifact operations. They must not attempt to become a universal .NET build engine.

## Change record

| Date | Activity | Result |
|---|---|---|
| 2026-09-23 | Created Phase A reference record | In progress |
| 2026-09-23 | Captured 57 exact P3 build outputs and 2 exact NuGet assemblies | Published immutable build-closure solution store |
| 2026-09-23 | Captured current Radiant.Data and Radiant.Annotations source builds | Published a derived logical-type analysis view without mutating the build closure |
