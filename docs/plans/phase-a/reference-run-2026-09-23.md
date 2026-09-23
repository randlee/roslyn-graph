# P3ImagerCli Phase A reference run — 2026-09-23

## Result

The reference run produced two durable, queryable databases beneath `F:\.roslyn-graph`:

| Artifact | Purpose | Components / graphs | Triples |
|---|---:|---:|---:|
| P3 build closure | Exact successful P3 build, including the precise NuGet assemblies it consumed | 59 / 60 | 2,259,287 |
| Logical dependency view | Immutable derived view that adds the current Data and Annotations source builds and reconciles their compatible type versions | 61 physical components plus projection / 63 | 2,475,851 |

The P3 build-closure artifact is the authoritative answer to “what was built.” The logical view is a separate artifact that never mutates the closure.

## Global storage configuration

The persistent user environment variable was configured as:

```text
ROSLYN_GRAPH_DATA_ROOT=F:\
```

Therefore every artifact root in this run is `F:\.roslyn-graph`. Existing shells passed `-DataRoot F:\` explicitly; new shells inherit the variable. The setting is intentionally a data-root parent, not the final artifact directory, so another machine can choose a different drive while preserving the layout.

## Build contract captured

| Input | Value |
|---|---|
| Solution | `F:\_r2609\p3-cli\P3ImagerCli\P3ImagerCli.sln` |
| Build configuration | `Debug` |
| Target framework | `net10.0` |
| TT3 platform / conditions | `TT3X` using `F:\_r2609\p3-cli\.build\tt3\Common.targets` |
| Common.targets SHA-256 prefix | `33666cef169bcee6` |
| Build fingerprint | `tt3-net10-debug-33666cef169bcee6` |
| Exact selected project outputs | 57 entries in `F:\.roslyn-graph\reference-p3-build-inputs.json` |

The assembly list was captured from the successful solution build, not inferred by scanning folders. It includes the project test output where it is a solution output.

### Source provenance

| Repository | Branch | Commit |
|---|---|---|
| P3ImagerCli | `Integration/annotations-only` | `e44954121463dc0416dfbde4aa969f5c6defa529` |
| XCore | `Integration/annotations-only` | `b5b818a7b953344a99983880f8bff01c4826e30d` |
| CameraXCore | `Integration/annotations-only` | `f00bf091aeaede49b84796084971ed6193cc5c9a` |
| CalibrationXCore | `Integration/annotations-only` | `a4fe2d8cba617b9917a856916b05a6184bbd4280` |
| DatabaseXCore | `Integration/annotations-only` | `f65c042f73580194be4ce18a10aff3d5cabe40b9` |
| RScripting | `Integration/annotations-only` | `067f76591f79c25d00e6c47ea1f97390df876737` |
| CommonTargets | `Integration/annotations-only` | `c056eea704c65e161f8a563d09658cafea59e402` |
| SharedBuildHelpers | `Integration/annotations-only` | `cbaeb609fb144edb038ad3075c22957ed4cac35e` |

### Exact package provenance

The closure contains the DLL assets restored by P3, rather than the newer source clones.

| Package | Version / selected asset | `.nupkg` SHA-256 | Feed |
|---|---|---|---|
| Radiant.Data | `0.50.0`, `lib\\net10.0\\Radiant.Data.dll` | `997EBB0656E1BF8548AFC78DEFF688C39004121D3D333ACEC2A2518E752D86E2` | `https://nuget.pkg.github.com/Radiant-Vision-Systems/index.json` |
| Radiant.Annotations | `0.55.0`, `lib\\net10.0\\Radiant.Annotations.dll` | `078CB7917036D6C4FDBC8E808BF010C4F78B740AFFCF20E26930B0CB75996F06` | `https://nuget.pkg.github.com/Radiant-Vision-Systems/index.json` |

The newer source artifacts were deliberately captured independently:

| Assembly | Source commit | Assembly version | Graph IRI |
|---|---|---:|---|
| Radiant.Data | `343cd634404347be87540154056110dff46f034a` | `0.51.0.0` | `urn:roslyn-graph:assembly:24773c7ce30ba2229304712be542bbac` |
| Radiant.Annotations | `7b12af4275318da73a4ca2474a6db36bb575320a` | `0.56.2.0` | `urn:roslyn-graph:assembly:e3f66bfa5e71147f6a2a390ac27cf7d0` |

They are unsigned source-build evidence and are not mislabeled as package artifacts.

## Executed workflow

### 1. Assembly snapshots

For each exact built DLL, `scripts/Invoke-AssemblySnapshot.ps1` performed this sequence:

1. resolve and validate the exact input DLL;
2. run `Roslyn2Rdf.Cli` with `--include-private` and the build’s dependency search paths;
3. load its temporary Turtle output into a fresh staged Oxigraph store;
4. run a triple-count query and write a manifest containing build, assembly, extraction, and origin provenance;
5. delete only the temporary Turtle interchange file; and
6. publish the complete store and manifest together to its immutable location.

The source layout groups by repository and the NuGet layout by package ID/version; the final folder is a collision-safe, initially 20-hex artifact-ID prefix. If occupied by another full SHA-256 identity, it expands to 32 characters and then the full hash. Branch, commit, build fingerprint, package SHA-256, target framework, assembly name, and assembly version remain complete immutable manifest fields.

### 2. Exact solution composition

`scripts/Invoke-SolutionComposition.ps1` selected the 57 manifests whose `assembly.inputPath` matches `reference-p3-build-inputs.json`, added the two exact package manifests, and loaded every component store into its manifest-defined named graph. It added one solution metadata graph containing the build contract and all membership edges.

Published artifact:

```text
F:\.roslyn-graph\solutions\p3-cli\P3ImagerCli\feabe34877ee97e1a5a4\
```

Identity and metadata graph:

```text
solution artifact ID: feabe34877ee97e1a5a49a573f625a01f7ddd741f11a29969967d5b628fc34a2
solution IRI:         urn:roslyn-graph:solution:feabe34877ee97e1a5a49a573f625a01
metadata graph:       urn:roslyn-graph:solution:feabe34877ee97e1a5a49a573f625a01:metadata
```

The store was optimized before publication. This validation returned the expected membership:

```sparql
PREFIX rg: <http://roslyn-graph.example/ontology/>
SELECT ?name ?configuration ?platform (COUNT(?g) AS ?graphs) WHERE {
  GRAPH ?metadata {
    ?solution rg:name ?name; rg:configuration ?configuration;
              rg:platform ?platform; rg:includesGraph ?g
  }
}
GROUP BY ?name ?configuration ?platform
```

Result: `P3ImagerCli, Debug, TT3X, 59`.

### 3. Derived logical-type view

`scripts/Invoke-LogicalTypeView.ps1` copied the immutable base solution into a fresh staged store, added the two source artifact graphs, and wrote a new named graph with this policy:

```text
logical key = assembly name + full metadata type name
only explicitly listed additive-compatible assembly versions are linked
physical identities are retained
owl:sameAs is not emitted
```

The policy is deliberately explicit because the current source builds are not byte-identical or strong-name-identical to P3’s package assets. It is valid only for the stated additive-compatible package versions; a future breaking release must opt in through an evaluated compatibility policy.

Published view:

```text
F:\.roslyn-graph\views\3f0e290093d2b17b30b9\
```

It contains 2,548 `dt:logicalType` physical links and 1,307 logical resources. A validation query found two physical versions for types such as `Radiant.Annotations.<Module>` while exposing one logical node. The store has no `owl:sameAs` triples.

## Query examples proven against the final view

Use this store path:

```text
F:\.roslyn-graph\views\3f0e290093d2b17b30b9\store.oxigraph
```

Logical version reconciliation:

```sparql
PREFIX dt: <http://dotnet.example/ontology/>
SELECT ?assembly ?fullName (COUNT(?physical) AS ?versions) WHERE {
  GRAPH <urn:roslyn-graph:view:3f0e290093d2b17b30b9f50e0f7c28df:logical-types> {
    ?physical dt:logicalType ?logical .
    ?logical dt:assemblyName ?assembly; dt:fullName ?fullName
  }
}
GROUP BY ?assembly ?fullName
HAVING (COUNT(?physical) > 1)
ORDER BY ?assembly ?fullName
```

Interface graph seed (the visualization query should select `DISTINCT` pairs before constructing nodes and edges, because an entity can be described in more than one component graph):

```sparql
PREFIX dt: <http://dotnet.example/ontology/>
SELECT DISTINCT ?implementer ?interface WHERE {
  GRAPH ?implementationGraph {
    ?implementation dt:implements ?interfaceType; dt:fullName ?implementer
  }
  GRAPH ?interfaceGraph {
    ?interfaceType dt:fullName ?interface; dt:typeKind "Interface"
  }
}
ORDER BY ?interface ?implementer
LIMIT 500
```

The non-distinct relationship probe returned 159,264 graph-level matches, confirming why the viewer must deduplicate the logical display edge set.

## Defects found by the run

1. The first solution composition attempt rejected its metadata N-Triples because the reference encoder did not escape Windows path backslashes. The failure stayed in staging; no solution artifact was published. The encoder now emits `\\` correctly.
2. A first logical view used a provenance-heavy filesystem path that Oxigraph could create but could not reopen on Windows. The new `views\\<view-artifact-id>` layout is short, and all reference helpers reject a published `store.oxigraph\\CURRENT` path longer than 240 characters. Full provenance remains in the manifest.
3. Oxigraph emits generic “Wikidata / --lenient” and optimization advice on each load. In this run they were informational output with exit code zero; the product command should classify or suppress this noise while preserving genuine parser errors.

The failed staging directories are intentionally retained for forensic inspection. Earlier long-path trials are not valid artifacts and are not referenced by the canonical short-path stores; a production cleanup command should remove them by explicit manifest/status, never by broad path deletion.
