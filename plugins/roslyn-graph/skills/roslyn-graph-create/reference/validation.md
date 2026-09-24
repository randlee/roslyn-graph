# Validation checks

`generate` runs these checks in staging (before publication, recorded in `validation.staging`) and again
on the published path. `rg.py validate` runs them on demand; `--deep` adds `D1`/`V8`. A store is valid only
when every applicable check passes.

## Every artifact

| ID | Check | A failure means |
|---|---|---|
| M1 | schemaVersion 2 and every required manifest field present | legacy or hand-edited manifest |
| M2 | the identity string recomputes from the manifest fields and hashes to `artifactId` | the manifest was edited or written by an incompatible version |
| M3 | the directory name is a prefix of `artifactId` (published only) | the directory was renamed or copied |
| P1 | `store.oxigraph/CURRENT` is at most 240 characters | the store cannot be reopened reliably on Windows |

## Assembly stores

| ID | Check | A failure means |
|---|---|---|
| S1 | the store reopens and holds the recorded triple count | corrupted or modified store |
| S2 | the extracted Turtle's unique triples equal the store's triples | the load dropped or added data |
| S3 | the store has no named graphs | unexpected content |
| S4 | exactly one `dt:Assembly`, whose IRI matches the manifest's name and version | wrong DLL or extractor output |
| S5 | the assembly's name equals the expected output name (project AssemblyName or package asset file name) | the DLL at that path is not the project's output |
| S6 | the assembly defines at least one type | empty or failed extraction |
| S7 | every type has exactly one `dt:fullName` | the extractor named one type two ways (for example with and without a nullable annotation); queries by name would return duplicates |

## Solution stores

| ID | Check | A failure means |
|---|---|---|
| S1 | the store reopens | corrupted store |
| G1 | named graphs are exactly the components plus the metadata graph | a component is missing or extra |
| G2 | each component graph holds its component's triple count | incomplete copy |
| G3 | the default graph is empty | stray triples |
| G4 | the total triple count matches the manifest | modified store |
| G5 | the metadata lists exactly the component graphs and artifact IDs | metadata out of sync |
| D1 | (`--deep`) every component artifact passes its own checks | a component store is damaged |

## View stores

| ID | Check | A failure means |
|---|---|---|
| S1 | the store reopens | corrupted store |
| V1 | named graphs are the base graphs, the overlay graphs and the logical-type graph | incomplete view |
| V2 | base and overlay graphs have exactly their source triple counts | the view modified or dropped physical data |
| V3 | the default graph is empty | stray triples |
| V4 | no `owl:sameAs` anywhere | forbidden merge semantics |
| V5 | every projected physical type has exactly one logical type | ambiguous projection |
| V6 | link and logical-type counts equal the manifest's projection | projection changed after creation |
| V7 | the total triple count matches the manifest | modified store |
| V8 | (`--deep`) the base solution manifest exists; with D1 for overlays | the base was removed |

## Run-level guarantees of `generate`

- Oxigraph reports parser problems on stderr while exiting 0; any stderr line other than its two
  advisories and progress lines fails the step (`OXIGRAPH_FAILED`).
- Every artifact is published by an atomic directory rename under a lock; a destination that already
  holds a different artifact is never written into.
- After publishing, the collection is planned again; any remaining work fails the run (`NOT_IDEMPOTENT`).
