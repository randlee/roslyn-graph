# Artifact layout and identity

## Directory layout

```
<data-root>/.roslyn-graph/
  assemblies/source/<repository>/<id>/           manifest.json + store.oxigraph/
  assemblies/nuget/<package id>/<version>/<id>/  manifest.json + store.oxigraph/
  solutions/<root folder>/<solution name>/<id>/  manifest.json + store.oxigraph/
  views/<id>/                                    manifest.json + store.oxigraph/
  cache/nuget/<hash>/                            isolated restores (safe to delete; recreated on demand)
  staging/<time>-<label>-<nonce>/                work in progress; left behind only by failed runs
  locks/                                         publish locks (empty when idle)
```

`<id>` is the first 20 hex characters of the artifact ID. If that directory already belongs to another
artifact, 32 and then all 64 characters are used; the manifest's `artifactId` decides ownership. A
directory without a manifest is never reused or deleted (`ARTIFACT_DIR_WITHOUT_MANIFEST`).

## Identity

The artifact ID is the SHA-256 of an identity string built only from manifest fields, so validation
recomputes it (check `M2`). Anything that can change the stored triples is part of it:

| Kind | Identity parts |
|---|---|
| source assembly | `assembly/v2 \| source \| repository \| commit \| dirty hash \| build fingerprint \| target framework \| DLL sha256 \| extractor id` |
| package assembly | `assembly/v2 \| nuget \| package id \| version \| nupkg sha256 \| asset path \| dependency-set hash \| restore target \| DLL sha256 \| extractor id` |
| solution | `solution/v2 \| profile \| root folder \| solution path \| commit \| dirty hash \| fingerprint \| framework \| configuration \| platform \| sorted component IDs` |
| view | `view/v2 \| base solution ID \| policy name \| sorted policy assemblies \| projection version \| sorted overlay IDs` |

Consequences:
- same inputs → same ID → `generate` reuses the artifact and writes nothing;
- a new commit, rebuilt DLL, different package bytes or dependencies, changed build files or a new
  extractor → new ID → a new artifact beside the old one; nothing is overwritten.

Graph IRIs are `urn:roslyn-graph:<kind>:<first 32 hex of the ID>`; solutions add `:metadata`, views add
`:logical-types`.

## Store contents

- **Assembly store**: the extractor's triples in the default graph; exactly one `dt:Assembly`.
- **Solution store**: each component in its own named graph (the component's graph IRI) plus the metadata
  graph describing the `rg:SolutionBuild` (profile, repository, branch, commit, fingerprint, framework,
  configuration, platform, `rg:includesGraph`, `rg:includesArtifact`). The default graph is empty.
- **View store**: an exact copy of the base solution's graphs, one graph per overlay component, and the
  logical-type graph: `rg:LogicalTypeView`, and for every own, fully extracted type of a policy assembly
  (projection domain v2: defined by the assembly, with `dt:accessibility`; constructed generics are not
  projected) `<physical type> rg:logicalType <logical type>`, with `rg:LogicalType`, `rg:assemblyName`,
  `dt:fullName` and `dt:name` on the logical node. The manifest records the domain size per component
  (`projection.domain`) and check V9 recounts it. `owl:sameAs` is never written.

## Manifests

All manifests have `schemaVersion: 2`, `kind`, `artifactId`, `identity`, `createdUtc`, `workspace`
(TOML path, TOML hash, profile, collection), `store` (Oxigraph version, triple count, per-graph counts)
and `validation.staging` (the checks that passed before publication). Component references use paths
relative to the artifact root, so a data root can be moved as a whole.

Manifests with `schemaVersion: 1`, or without one, are **legacy**: they come from the manual workflow
before this skill, use a different identity, and are reported by `inventory` as `legacy`.
