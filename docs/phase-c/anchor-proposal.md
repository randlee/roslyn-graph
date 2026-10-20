# Phase C intent and anchor proposal

Status: the no-silent-truncation directive below is explicitly user-approved. The remaining candidate statements and fixtures are not locked or gate-ready. Fixture approval and the skill's validation remain required before automated gates. Existing TX IDs are authoritative requirement references, not new duplicate ANC IDs. This document is a capture packet, not a second implementation-status ledger.

## Approved directive: no silent truncation

Approved by Rand Lee on 2026-10-16 with the instruction: "anchor this".

Verbatim provenance:

> it doesn' tmatter, as long as I see everything I ask for in the future.  if I ask for 11m things I don't care if my computer runs out of ram and crashes, I want it to try.  (might be an exageration, but silently dropping a query from a tool I am planning a 1m LOC migration with is NOT acceptable.

Approved constraint: Roslyn Graph queries, traversal and exports return the complete requested result by default, with no implicit type, row, edge or depth limits.

- Limits apply only when explicitly requested by the user, including explicit saved configuration.
- Any result cut by an explicitly requested limit is clearly identified as partial.
- Resource exhaustion or another execution failure is reported as failure; partial output is never presented as complete.
- Batching and paging may control resource use but must drain the requested result rather than reduce it.

Scope: all query, traversal and export entry points, defaults, saved configuration and result reporting. This broadens candidate 5 beyond traversal; do not create overlapping independently counted requirements for the same default-limit constraint. It does not remove the user's explicit query filters or requested limits, and does not require a redesign of working paths.

User approval records the directive, not a claim that implementation or automated gate validation has passed. Tuning must preserve this meaning and may split independent checks without weakening it.

## Intent

### Approved plan-shape constraints

User provenance:
- "nothing in the plan that is not specific code change."
- "don't fucking redesign anything that isn't broken."
- "I don't know if this is an actual problem, I wnat the plan this fucking specific."
- "not long verbose code, but the literal roslyn call and what it lands in."
- "I expect code that if very similar from both of them"
- "make it so."

Every implementation item identifies a verified defect and the exact file/symbol, decisive API/property, emitted RDF subject/predicate/object, traversal query change where applicable, and concrete expected test result. Use short code fragments rather than broad task descriptions or full implementations. Resolve semantic choices so two independent developers produce very similar code. Examples of desired specificity are not evidence of defects. Preserve working behavior; no unrelated redesign or refactoring. These constraints govern the plan, not a claim that the current draft already passes them.

Produce a thorough, ontology-defined static inventory for deciding what code moves from A to B. Inventory all types and members in selected libraries and reachable dependencies in already-analyzed libraries. Analyze source or compiled libraries without executing them; include allocations and other statically bound body relationships. Preserve the resulting typed relationships, ownership and provenance through export. Do not infer runtime-only targets or reconstruct an executable deployment.

Authority: the user's planning conversation and corrections. Implementation requirements remain in ../requirements.md; the implementation plan remains phase-c-plan.md. The user requested independent tuning by tebo, with background agents permitted. Ontology research is a separate task and is not input authority for changing these constraints.

## Candidates and draft fixtures

### 1. Full inventory (TX-G02, TX-G29)

Quote: "yes, so w want a thorough inventory of the libraries analyzed including dependencies which we have already analyzed."

Statement: Full-library selection must inventory every type and member in each selected library, including non-public and uncalled members.

Scope: library roots, member enumeration and inventory selection.

Pass fixture: Selecting library A includes its internal types and an uncalled private method's dependency.

Fail fixture: Selecting library A inventories only public types or methods reached from an entry point.

### 2. Static type relationships (TX-G05 through TX-G15 and applicable TX-C requirements)

Quote: "I just want all types including generics, unsafe, method bodies, func to be analyzed for relationships."

Statement: Roslyn Graph must extract the required static type relationships in declarations, signatures and executable bodies, including generic, unsafe and callable type constituents.

Scope: source/assembly extraction and constituent-type traversal. Use the referenced TX cases for precise coverage; do not replace them with this summary.

Pass fixture: A type used only in a method-body allocation, generic argument or function-pointer signature appears with its relationship.

Fail fixture: Declaration extraction succeeds but method bodies or function-pointer constituents are skipped.

### 3. Existing analyzed dependencies (TX-G16)

Quote: "i.e. if we reference nuget package and we have a database for the package, it should be included in the type graph we are creating."

Statement: Selection must follow referenced type definitions and their dependencies into compatible registered library databases.

Scope: cross-database resolution and traversal.

Pass fixture: A references P.T; P's registered database supplies T and its reachable dependencies, excluding disconnected package types.

Fail fixture: P.T remains an unresolved stub despite an explicitly registered compatible database with the bound definition.

### 4. External package boundary (TX-G17, TX-O05)

Quote: "for a 'package reference' we externally reference, this is not something we want to exhaustively collect today."

Statement: Phase C traversal must leave packages without admitted databases as external references rather than acquiring or extracting their contents.

Scope: external package resolution and acquisition.

Pass fixture: An unregistered package remains an identified external boundary; traversal performs no restore, download or extraction.

Fail fixture: Traversal downloads or extracts an unregistered dependency package to extend closure.

### 5. Unlimited defaults (TX-G19)

Quote: "we do not want default limits.  it's fine to have an optional limit as an arg."

Statement: Roslyn Graph traversal must apply no depth or type-count limit unless the caller explicitly supplies one.

Scope: traversal defaults, limit arguments and saved selection definitions. Explicit saved finite limits remain explicit choices; max_depth=0 retains unlimited semantics.

Pass fixture: Omitted limits return the full reachable graph, including more than 1,500 types; explicit positive limits report truncation.

Fail fixture: Omitted limits silently stop selection at 1,500 types.

### 6. Cycle-safe traversal (requirements scope and TX-G19)

Quote: "you should detect cycles and not do amature queries and avoid recursion, but this is just intelligent design, not only showing partial information"

Statement: Dependency traversal must reach closure using iterative cycle-safe expansion and batched adjacency queries, without cutting results to handle cycles.

Scope: dependency and wrapper traversal algorithms. The tuner must flag if separate atomic statements are required; it must not drop batching or cycle-edge preservation.

Pass fixture: A deep cyclic graph is fully traversed with each physical definition expanded once and every batch drained.

Fail fixture: Traversal handles cycles by returning a depth-limited partial inventory or recursively revisits dependencies.

### 7. Attributes opt-in (TX-O01)

Quote: "attributes should be an --option and not enabled by default."

Statement: Attribute-origin dependency extraction and traversal must be disabled by default and enabled only by explicit opt-in.

Scope: attribute options, extraction, reduction and saved policy. Reading compiler-semantic metadata does not itself authorize attribute-origin dependency edges.

Pass fixture: An attribute-only target is absent by default and present with explicit inclusion; an ordinary body use remains present in either mode.

Fail fixture: Default extraction includes attribute-only dependencies.

### 8. Missing references and --strict (TX-G20, TX-O04)

Quotes:
- "#1 if reference is missing, this should be flagged and reported, we should not fast-fail unless this is specified (no default)."
- "I like the 'optional --strict flag'"

Statement: Missing references must produce reported incomplete coverage while extraction continues by default; explicit --strict makes missing-reference resolution fail the operation.

Scope: recoverable missing-reference handling and CLI policy. This is not a requirement to continue after malformed requests or unusable inputs; intentional unregistered package boundaries are not strict-resolution failures.

Pass fixture: A missing bound dependency produces retained known facts and diagnostics by default; the same input fails with --strict.

Fail fixture: A missing bound dependency aborts ordinary extraction without --strict, or is silently omitted from coverage reporting.

### 9. Non-running-library analysis (scope boundary and TX-G09 through TX-G14)

Quotes:
- "we are not doing runtime inference, we aren't supporting com or 'special' types."
- "confirming `9. Static-only scope:` means analysis on non-running libraries.  (i.e. we don't skip dynamically allocated types)."

Statement: Static analysis must retain statically identifiable allocated types without executing the analyzed libraries or inferring runtime-only targets.

Scope: source/IL body analysis, allocations, reflection and dynamic binding boundaries. Normal built-in types remain supported; the exclusion concerns special interoperability expansion, not ordinary primitive types.

Pass fixture: A never-executed method's new Foo() contributes Foo; an externally supplied reflection type name does not invent a target.

Fail fixture: The analyzer excludes new Foo() because allocation occurs at runtime, or requires executing the library to discover Foo.

### 10. Full VB.NET parity (TX-G01)

Quote: "#10 - change to we fully support vb.net with parity to c#."

Statement: Roslyn Graph must support VB.NET with C# parity for applicable language features in source-semantic and compiled-assembly analysis.

Scope: language capability, extraction and fixtures. Parity concerns equivalent semantics, not C#-only syntax. This is a delivery requirement, not a statement of present implementation completeness.

Pass fixture: Equivalent C# and VB body-only dependencies are extracted in source and DLL modes with corresponding relationship semantics.

Fail fixture: VB declaration indexing passes while equivalent VB body relationships remain unsupported.

### 11. Ontology-defined inventory (TX-G04, TX-G30)

Quote: "#11 is defined by the ontology, not prose."

Statement: Inventory relationships, categories, ownership and provenance must be ontology-defined graph facts preserved through export, not substitutes expressed only in prose.

Scope: ontology, emitted relationship/evidence facts and export. Reuse existing terms; extend the ontology when required facts cannot be represented. Predicate names and shape proposals from independent research require review rather than automatic adoption.

Pass fixture: Exported ontology-defined facts identify the consuming member, target type, relationship category and originating artifact.

Fail fixture: A textual explanation names the dependency's reason but no queryable graph relationship represents that reason.

### 12. Real sample verification (TX-V01 through TX-V07)

Quote: "make sure the plan includes extensive sample test project to verify corner cases."

Statement: Phase C must include real C#/VB sample inputs verifying general and required corner-case type relationships against explicit expected results and negative controls.

Scope: sample projects and executable acceptance tests. Preserve required coverage using existing test tooling; no fixed project count or full option Cartesian product is required.

Pass fixture: Built source/DLL samples assert body-only dependencies and exclude disconnected decoys, using hand-authored expected sets.

Fail fixture: Tests contain only synthetic triples or compare the extractor against expected results generated by that same extractor.

## Tuning authority and state

Remote TypeSafe evaluation is user-approved for this workflow only. No credentials belong in this packet or run artifacts. The prior capture produced one testable unlimited-default candidate and seven inconclusive candidates; that is not a passing gate or authorization to weaken requirements.

The tuner must distinguish direct user directives from technical detail derived from the existing requirement register. Keep TX identity where a requirement already exists. Before tuning, freeze the approved authority and independent expected outcomes according to the skill. Draft fixtures here are not yet user-approved. Report any missing authority, compound constraints or semantic ambiguity; do not silently lock or revise scope. Rubric calibration may proceed independently using the skill's prescribed corpus.
