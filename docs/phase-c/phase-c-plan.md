# Phase c - Specific fixes, sprint index

| Sprint | Authoritative plan | Tracker | Relation | Closure |
| --- | --- | --- | --- | --- |
| c-1 | [Existing graph completeness](sprint-c-1-existing-graph-completeness.md) | none | parallel_safe c-2 | integration |
| c-2 | [Extraction facts](sprint-c-2-extraction-facts.md) | none | parallel_safe c-1 | boundary |
| c-3 | [New fact integration](sprint-c-3-new-fact-integration.md) | none | must_follow c-1, c-2 | integration |

The sprint documents replace the former nine-item implementation list as the authoritative implementation scope. They retain its API/RDF/query choices and add two code-verified omissions found during anchoring: admission of registered analyzed dependencies and preservation of external boundary identity. Requirements remain in [requirements.md](../requirements.md); user provenance remains in [anchor-proposal.md](anchor-proposal.md). This index is scheduling/ownership metadata, not an additional implementation checklist.

## Boundary map

This repository is .NET/Python, not Rust: no crate boundary manifests or `allowed_dependencies` registries exist. The contracts below come from project references, imports and emitted RDF; do not add a new boundary framework.

| Boundary | Existing implementation and dependency edge | Contract change | Owner |
| --- | --- | --- | --- |
| rg-query-and-existing-graph | tools/rg/rg.py imports roslyn_graph; reads existing RDF via Oxigraph | Optional unbounded result limits; existing pointer/constraint/enclosing follow patterns | c-1 |
| dotnet-extraction-cli | RoslynToRdf.Cli references Core; Core writes dt: triples | Delegate Invoke, function-pointer constituent properties, usesType; source/DLL behavior; attribute opt-in and strict alias | c-2 |
| rdf-to-reduction-export | Python reduction reads Core's artifact RDF; exporters preserve member facts | New-fact consumers; attribute inverse filtering; registered artifact admission and typed boundary/provenance export | c-3 |

Shared registry/schema ownership: c-2 owns DotNetOntology, dotnet-types.ttl and the VB Workspaces project reference; c-3 owns the rg:references derivation comment. Each sprint owns only its changed packaged copies. No contract-only sprint: the RDF changes have one producer and one consumer, and a separate stub/schema phase adds no useful parallel implementation.

## Waves and contracts

| Wave | Track | Sprint | target_boundary | owned_paths summary |
| --- | --- | --- | --- | --- |
| 1 | existing graph | c-1 | rg-query-and-existing-graph | Python CLI/query/traversal, shipped queries, their tests/copies and graph-definitions.md |
| 1 | extraction | c-2 | dotnet-extraction-cli | .NET extractor/CLI/tests/fixtures, dt: ontology and generated ontology reference |
| 2 | integration | c-3 | rdf-to-reduction-export | Python traversal/records export/tests, registered-store context, rg: comment, CI and generated copies |

Critical path: **2 sprints**. Width: **2**. Sprint count: **3**.

c-3 consumes c-1's unbounded `Definition.max_types`/query/export behavior and c-2's concrete signature/usesType RDF. These are completed behaviors rather than declarations that can be hoisted into a thin contract sprint. Repeated ownership of traverse.py and ontology.md is across waves only, never parallel. The named contracts, not file overlap, require c-3 to follow both parents.

## Original item ownership

| Reviewed item | Producer/implementation | Feature acceptance owner |
| --- | --- | --- |
| 1 limits; 2 pointers; 5 constraints; 6 enclosing types | c-1 | c-1 |
| 3 delegates; 4 function pointers | c-2 | c-3 |
| 7 attribute option / inverse policy | c-2 / c-3 | c-3 |
| 8 strict alias | c-2 | c-3 |
| 9 body extraction / query-export wiring | c-2 / c-3 | c-3 |
| Registered analyzed dependencies absent from selected store | c-3 | c-3 |
| External identity and source-artifact evidence dropped by export | c-2 stub metadata / c-3 export | c-3 |

No sprint claims that all broader TX requirements are new development or completed by this fix set. Existing working functionality remains unchanged; no unverified cross-database redesign or workbench is added.

## Branch declarations

Retain the existing Phase C directory/name as the guidelines' legacy-phase exception; do not rename the already-published plan history. Proposed implementation branches are declared in `.sprints/c-1.yaml`, `.sprints/c-2.yaml`, `.sprints/c-3.yaml`; none is created by this documentation change. Use `integrate/phase-c` as the phase base, c-1/c-2 as parallel tracks, and c-3 after both contract parents are incorporated. Parent development being pushed triggers merge-forward before a child dev/fix round; parent PRs merge first. Plan/final phase PR targets develop; sprint PRs target the phase or their stack parent.

## Plan verification

Guideline source: the installed `plan-hardening/sprint-planning-guidelines.md` (no exact `sprint-plan-guidelines.md` was found). Use native .NET/Python validation, not nonexistent cargo/just commands. There is no repository developer roster; the docs name a workhorse developer role rather than invent a named assignment.

Deterministic anchoring checks: each sprint has one scope, deliverables, rooted acceptance, validation and non-closure list; each item above has one feature-acceptance owner; same-wave owned paths do not intersect; every deliverable names code/API/RDF/query choices or explicitly says no RDF/query change; no product redesign or speculative example task appears. Source discovery/shape and live gate results are required before reporting plan-anchoring PASS. Hardening readiness is not claimed by writing this index.
