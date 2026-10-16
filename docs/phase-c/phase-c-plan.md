# Phase C — Dependency-complete type graphs

Status: proposed implementation plan, not an implemented capability.

Date: 2026-10-15

Tracking: [#91 — Method-body dependency extraction oversight](https://github.com/randlee/roslyn-graph/issues/91).

## Objective and decisions

Extend the graph and its traversal to represent static type consumption, including method bodies, pointer targets, delegate signatures and function-pointer signatures. Resolve referenced library types into existing registered Roslyn Graph databases without exhaustively collecting external packages.

The following are requirements, not optional design alternatives:

- Method-body dependencies are part of dependency extraction, not merely signature metadata.
- Pointing to a type consumes that type. Pointer, array and generic wrappers must not hide dependencies.
- Delegate and function-pointer parameter and return types participate in traversal.
- When a referenced package has a matching registered database, traverse the referenced types in that database, recursively under the same policy and limits. Do not import every type in the package merely because the package is referenced.
- When no matching database is available, retain the referenced type and package/assembly identity as an external boundary. Do not download, extract or exhaustively traverse that package or its dependency tree.
- Attributes are opt-in, disabled by default for both extraction and dependency traversal.
- Missing references and unavailable dependency information are reported; default behavior continues with an explicitly incomplete result. Strict failure requires an explicit option.

This phase does not promise that an arbitrary selected type set can be rebuilt or executed. Static dependencies, build inputs and runtime dependencies are separate contracts. Reflection, dynamic loading, plugins, native libraries, resources and configuration need additional roots or future work.

## Current implementation and gaps

Paths below are repository-relative and describe the implementation reviewed for this plan.

| Area | Current implementation | Required change |
| --- | --- | --- |
| Method bodies | `AssemblyGraphExtractor.Members.cs` emits signatures and metadata; `UnsafeMethodAnalyzer.cs` only inspects unsafe facts | Semantic dependency extraction with ownership and evidence |
| DLL inputs | `AssemblyLoader.cs` loads metadata for Roslyn binding, not IL body dependencies | IL-backed dependency extraction or explicit unavailable/unsupported capability reporting; do not silently call metadata extraction complete |
| Reduction | `tools/rg/roslyn_graph/traverse.py` follows a fixed subset of signature relations | Add body, constraint, enclosing-type and callable-signature dependencies |
| Pointers | Extractor emits `pointerElementType`; reducer unwraps arrays/generics only | Traverse pointer targets recursively |
| Callables | Delegate invocation signatures and function-pointer constituent types are incomplete | Emit and traverse their signature types |
| Attributes | CLI currently defaults to inclusion through `--exclude-attributes`; traversal covers only type/member attributes | Positive opt-in, all supported attachment sites and typed arguments |
| Libraries | Reduction admits component-owned types only; external types are stubs | Resolve into pinned registered package databases, retaining provenance |

Related declaration gaps belong in this phase: generic constraints, nested-type enclosing types and enum underlying types. Capturing bodies alone would still leave a misleadingly incomplete static dependency closure.

## Graph and schema contract

Names in this section are proposed vocabulary, to be confirmed by the first ADR and schema tests. Reuse existing predicates where their meanings already match; do not create a second incompatible signature model.

### Dependency relationships and evidence

Retain existing declaration relationships (`returnType`, `parameterType`, `fieldType`, `propertyType`, `eventType`, `constrainedToType`, `pointerElementType`, and others). Add a member-to-type `usesType` relationship for executable-body dependencies. A derived type-to-type dependency projects through member ownership; it is not a replacement for the underlying facts.

Represent evidence separately so multiple uses of the same target are not lost through RDF triple deduplication:

| Proposed concept | Required data |
| --- | --- |
| Dependency evidence | Owning declaration, consumed type, reason, extraction mode and artifact identity |
| Source evidence | Repository-relative document identity and span when available; avoid machine-specific absolute paths |
| IL evidence | Module identity, method token and instruction offset when applicable |
| Usage reason | Construction, invocation, member access, local/signature type, conversion, pattern, exception, initialization, type token or implicit compiler-bound operation |
| Wrapper route | Ordered array/pointer/generic/function-pointer steps; preserve multiple routes to the same named type |

The dependency target for a member access includes the declaring type, constructed generic arguments and relevant bound signature types. Member-target evidence may support explanations, but a complete call graph or virtual-dispatch analysis is not a Phase C promise.

Initializers attach to their declared field/property/event or constructor as appropriate. Lambda and local-function evidence retains its lexical owner, and projects to the containing named type. Define stable ownership for top-level statements and compiler-generated members in the ADR. Repeated extraction must produce stable identities and deterministic evidence ordering.

### Recursive type shapes

- Follow arrays to their element types and pointers to their pointed-at types, including nested combinations.
- Follow constructed generics to the definition and each argument, preserving argument ordinals.
- Emit delegate invocation parameter/return relationships even though `DelegateInvoke` is not an ordinary method.
- Model function-pointer signatures with ordered parameters, return type, ref kinds and calling convention; recursively traverse constituent types.
- Follow declared generic constraints. A type parameter is not an external concrete type; preserve its owner and ordinal.
- Include enclosing types where required for nested declarations. Preserve identity across assemblies and versions; never resolve by full name alone.

### Capability and completeness metadata

Version the graph vocabulary/capability manifest and affected configuration schemas. Record extractor identity, source artifact hashes, selected dependency categories and per-input body coverage. Distinguish `source-semantic`, `il` and `metadata-only` modes.

Report method-level failures and aggregate them into the result. Abstract/interface declarations legitimately have no body; that is different from a missing body, unsupported construct or unresolved symbol. Native/extern bodies remain opaque. Legacy stores without coverage metadata are `unknown`, not complete.

Result status must distinguish:

1. Complete for the selected static relationship policy within the registered database universe.
2. Intentionally excluded categories, such as attributes when disabled.
3. External package boundaries with no registered database.
4. Missing/ambiguous reference bindings, unsupported bodies or incompatible database capabilities.
5. Truncation by depth, type count or another explicit budget.

An external boundary is not evidence that its outgoing dependencies are absent. A result must not claim complete build/runtime closure. Persist structured diagnostics in manifests/exports as well as reporting them to the caller.

## Method-body extraction

Implement semantic traversal for source inputs, using resolved symbols/operations rather than identifier spelling. Cover supported source languages explicitly; unsupported cases must be diagnosed.

Required cases:

- Explicit and inferred locals, object/array creation and generic instantiations.
- Calls, method groups, field/property/event accesses and their owning types.
- Casts/conversions, patterns/type tests, `typeof`, `sizeof`, `default`, catch and throw types.
- Constructor/base initializers, field/property/event initializers and static constructors.
- Lambda/local-function bodies and compiler-bound implicit dependencies such as enumeration, disposal and await operations.

For DLL inputs, add an IL reader that resolves referenced type/member tokens, generic instantiations, local signatures and exception handlers, plus dependencies in generated methods. Source and IL results need not be identical: compilation can erase source-only references. Publish and test the capability difference; IL output alone must not certify source-rebuild closure.

The first implementation ADR must settle IL library choice and source/IL ownership mapping before code is written. It must enumerate the minimum supported source-language and IL fixtures for every required category, including implicit enumeration, disposal and await. Those fixtures must emit the expected dependencies to pass; an unsupported diagnostic is acceptable only outside that agreed baseline. The phase cannot be declared complete for the existing assembly-backed pipeline with source-only support.

## Registered package database resolution

Introduce an explicit local registry of existing database manifests in workspace configuration, or extend existing collection/overlay configuration where it can satisfy the same contract. The registry is an allowlist of graph artifacts, not permission to crawl NuGet feeds or arbitrary local caches.

Resolution procedure:

1. Use the originating build's resolved reference identity, including package ID/version and target framework where available, assembly identity and artifact identity. Assembly version is not interchangeable with package version.
2. Locate a matching registered database and its authoritative type definition. Define explicit mappings for retargeting, type forwarding, and reference-versus-runtime assemblies; do not guess by simple type name or choose the newest package silently.
3. Pin the resolved manifest and content hash in the graph result. Expansion reuses these pins; refreshing databases is a separate explicit operation.
4. Admit the referenced type into the traversal universe and continue only through enabled dependency categories. A dependency on another registered database may be followed under the same rules.
5. If no match exists, retain an external boundary. If matches are ambiguous or incompatible, report the condition and do not select arbitrarily.

Keep package, assembly, graph artifact and physical type identities on nodes/edges. Link external reference identities to authoritative definitions without collapsing distinct versions. Cycles across databases terminate through a visited set keyed by resolved physical identity, not display name. Apply depth/type budgets globally across the traversal, not independently per database.

Graph access remains behind the `rg.py` layer. The workbench or viewer must not independently open package stores. A schema ADR must select bounded composition or a query abstraction across registered artifacts and test it without changing source databases.

Unregistered packages remain boundaries even if binaries happen to exist in a package cache. Existing restore needed to build/bind an explicitly configured input is distinct from graph expansion; this feature must not add package restore or extraction during traversal. A future explicit exhaustive-external option may be designed later; it is not implemented or enabled in Phase C.

## Attribute option and compatibility

Propose `--include-attributes`, default `false`, with matching persisted configuration. Apply the policy consistently to direct CLI extraction, the Python extraction wrapper, saved graph definitions and reduction of existing stores.

- With attributes disabled, do not collect or follow attribute-origin dependencies, including argument types. A type independently consumed by ordinary code remains a normal dependency.
- With attributes enabled, include assembly/module/type/member/return/parameter/type-parameter sites supported by the input, attribute classes, and typed constructor/named arguments such as `typeof(T)`, enum values and arrays of typed values.
- Preserve attachment site and argument position in evidence. Attribute arguments must not be only formatted strings.
- Retain `--exclude-attributes` temporarily as a deprecated explicit opt-out; reject contradictory include/exclude flags. Document the default change rather than silently retaining the old default.
- Include effective extraction flags in cache/artifact identity. Existing attribute-rich stores may be filtered at traversal; attribute-free stores cannot satisfy opt-in requests without regeneration. Report that capability mismatch.
- Version/migrate saved definitions: an explicit old `attributes` follow entry is an opt-in; absence is off. Do not reinterpret an explicit selection as a default.

## Delivery sequence and gates

Each implementation step starts with its ADR decisions and failing tests. Use isolated worktrees and reviewed stacked PRs off `develop` for dependent changes; this document does not authorize implementation or landing.

| Step | Deliverable | Gate |
| --- | --- | --- |
| C1 | Vocabulary, evidence, capabilities, registry identity and option contracts | Schema fixtures and migration tests reviewed before implementation |
| C2 | Source-semantic and IL body extraction | Body-only dependency fixtures; explicit source/IL capability differences; issue #91 acceptance |
| C3 | Pointer, delegate, function-pointer, constraint, enclosing-type and enum-underlying-type traversal | Exact expected closure and provenance on recursive signature fixtures |
| C4 | Registered package database resolution | Cross-store closure, pinned identities, cycles and external boundaries; no traversal-triggered acquisition |
| C5 | Attribute opt-in across extractor and reducer | Default-off, positive opt-in, all attachment sites, typed arguments, compatibility and cache tests |
| C6 | Integrated reduction, export and documentation | End-to-end regression fixtures, diagnostics, deterministic output and independent critical review |

## Acceptance matrix

| Scenario | Required result |
| --- | --- |
| `A.Run()` only uses `new B().Execute()` internally | Evidence links the body to B; recursive selection of A includes B |
| Dependency only in local/cast/catch/lambda/initializer/static constructor | Each dependency is emitted and followed; no signature reference masks a missing body edge |
| Implicit enumeration/disposal/await dependency | Required baseline fixtures emit bound dependencies; constructs outside the agreed baseline are specifically reported unsupported, never silently omitted |
| DLL-only fixture | IL-visible dependencies extracted; source-erased references not falsely claimed covered |
| `B*`, nested wrappers and constructed generic arguments | B and all relevant constituent types included, with distinct wrapper routes |
| Delegate/function-pointer parameter or return references B | B included without invoking the callable |
| Constraint-only or nested enclosing-type dependency | Required declaration types included |
| Enum with an explicit underlying type | Underlying-type relationship retained and traversed; external numeric types remain explicit boundaries where appropriate |
| Package P references Q; both databases registered | Only reachable types in P and Q enter the result, with pinned provenance |
| Referenced package Q has no database | Boundary and diagnostic retained; no download/extraction/recursive package crawl |
| Two package versions expose the same full type name | Correct resolved version selected; ambiguous bindings reported, never merged by name |
| Registered store is legacy or lacks body coverage | Traversal can use known facts but result explicitly reports incomplete coverage |
| Cross-database cycle or traversal budget hit | Cycle terminates; budget hit is reported as truncation, not closure |
| Attribute-only dependency, default settings | Attribute dependency is excluded; ordinary references to that same type still work |
| Attribute opt-in with `typeof(B)` and return/parameter attributes | Attribute classes and B included with typed argument/site evidence |
| Missing reference under default and strict modes | Default reports/continues; explicitly requested strict mode fails |
| Repeated extraction and pinned expansion | Stable identities, deterministic output, no silent database refresh |

Add a controlled source-export integration fixture that builds in isolation and runs a behavior test. Keep that evidence separate from graph completeness: general source reconstruction, generated files, resources, runtime discovery and deployment remain outside this phase.

## Required sample test solution and corner cases

Build a checked-in, documented `tests/fixtures/phase-c/DependencyCoverage.sln` (or the repository's equivalent solution format), not just synthetic RDF unit tests. It must contain small compilable projects that exercise extraction from real source and built assemblies, plus a local package feed and separate graph databases. Invalid/unresolved-input fixtures live outside the normal successful solution build. Integrate the runner with the existing .NET and Python test suites rather than introducing a separate test framework.

The fixture solution is a required Phase C deliverable. C1 defines its case manifest and expected results; C2-C5 add failing cases before each implementation; C6 runs the complete suite. A single happy-path application does not satisfy this gate.

### Project inventory

| Project or fixture group | Required corner cases |
| --- | --- |
| `BodyReferences.CSharp` | Body-only construction, explicit/inferred locals, array creation, casts and user-defined conversions, patterns, type tokens, catch filters/throws, static/instance member access, extension methods, generic invocations and method groups |
| `BodyReferences.VisualBasic` | Equivalent supported body cases using VB syntax, including inferred locals, casts, exception handling, delegates, lambdas and initializers; explicit language capability matrix for non-equivalent features |
| `InitializationAndGenerated` | Base/this constructor calls, field/property/event initializers, static constructors, partial types across files, top-level statements, nested local functions, captured lambdas, async and iterator state machines, and a small deterministic source generator |
| `ImplicitOperations` | Custom enumerable/enumerator, disposable and awaitable types consumed only by `foreach`, `using`, `await`, `await foreach` or `await using`; assert compiler-bound dependencies rather than only the visible operand type |
| `SignaturesAndUnsafe` | Pointer chains, array/pointer combinations allowed by the language, nested generics with repeated target arguments, constrained type/method parameters, nested types, enum underlying types, delegates and managed/unmanaged function pointers with parameter/return ref kinds |
| `IdentityAndDispatch` | Same full type name in separate assemblies, overloads, generic arity, nested generic ownership, ref/out/in/ref-readonly signatures, explicit/implicit interface implementations, override calls and static interface members; assert statically bound dependencies without promising every runtime dispatch target |
| `AttributeSites` | Assembly/module/type/member/return/parameter/type-parameter attributes, repeated attributes, constructor/named arguments, enum and array arguments, `typeof(T)`, and a target referenced both by an attribute and ordinary code |
| `PackageConsumer`, local packages P/Q/R | P and Q have registered databases; R does not. Include reachable and unreachable decoys, dependencies across databases, duplicate type names, package-version/assembly-version differences, type forwarding and reference/runtime assembly mappings |
| `CoverageAndFailures` | Missing references, ambiguous package mappings, legacy manifests, metadata-only/ref-only assemblies, abstract/interface members with no body, extern/native methods, malformed or unsupported input and partial extraction failures |
| `RunnableSubset` | A tiny executable with known output whose selected sources build and run in isolation; companion resource/reflection examples demonstrate reported limits or explicit roots, not automatic runtime discovery |

Use independently built versioned package projects where incompatible versions cannot coexist in one compilation. Build valid assembly fixtures first, then remove a dependency only inside an isolated test directory for missing-reference tests. Exercise cross-database cycles using valid assembly layouts or controlled graph fixtures; do not require an impossible circular project-reference build. Keep malformed binaries and unsupported-language examples out of the ordinary solution build.

### Independent expected-results manifest

Give every case a stable ID and a reviewed, hand-authored expectation containing:

- Input project, seed declaration, extraction mode, configuration and enabled categories.
- Expected consumed types and relationships, expected evidence owner/reason, and prohibited unrelated types.
- Expected wrapper routes and argument ordinals, including repeated routes to the same type.
- Expected package/assembly/artifact identity and boundary/completeness diagnostics.
- Source-versus-IL differences, with the reason for each difference (for example, optimized-away source constructs).

Expected results must not be generated by the production extractor or reducer. Each relationship case uses a uniquely named target that appears nowhere else in the seed's signatures, constraints or attributes unless that is the feature under test. Add disconnected decoy types so accidentally selecting the whole project or package fails the test. Use exact set equality for fixture-owned dependency types, not only checks that selected examples are present; separately account for compiler/framework dependencies.

### Execution matrix

1. Run applicable cases through source extraction and DLL extraction. Use Debug and Release builds for optimization-sensitive cases, and PDB-present/PDB-absent inputs to verify that missing source evidence does not hide IL dependencies.
2. Run attribute-sensitive cases with the default, explicit inclusion and explicit exclusion. Verify conflicting flags, saved-definition migration and cache/artifact invalidation.
3. Run registered-library cases with all databases present, one absent, incompatible or ambiguous identities, and a legacy metadata-only database. Include two pinned versions and an explicit refresh; expansion must not silently change the pin.
4. Run closure with sufficient budgets, exact boundary budgets, depth zero, and truncation. Verify shared dependencies, self-reference, cycles, diamonds, stable ordering and global limits across databases.
5. Run missing-reference cases in default continue/report mode and explicit strict mode. Verify structured diagnostics survive reduction and export, not only console output.
6. Build local packages and databases during fixture setup; after setup, run graph traversal offline with acquisition commands intercepted to fail. Verify no package restore, download or extraction occurs during traversal, even when an unregistered package exists in a populated local cache.
7. Re-extract and reduce identical inputs twice; compare normalized semantic facts, stable identities and diagnostics. Do not require source spans and IL offsets to match between configurations.

The ordinary suite runs a documented required matrix in CI; additional configuration combinations may run in an extended job. No required relationship category may be covered only by an optional/manual test. Fix the SDK/compiler inputs used by fixture builds, use temporary isolated outputs, and document prerequisite restore separately from network-free traversal.

### Assertions and completion gate

For each required case, assert extraction facts, evidence, reduced type closure, boundary status and exported explanations. Where output formats do not yet carry explanations, assert the underlying exported evidence contract rather than relying on a screenshot. Add bounded seeded graph fixtures to compare reduction against a deliberately simple independent reachability implementation, alongside the real compiler-built examples.

Demonstrate that the harness detects missing relationships: removing a required body/pointer/delegate edge from a fixture graph must fail the closure assertion; disabling registered-database resolution must fail the package case; enabling default attribute traversal or indiscriminately including package decoys must fail negative assertions. These checks test the test harness without adding production-only test switches.

The fixture README must provide one documented entry point to build the samples and run the required matrix, with commands for individual case IDs. Publish a coverage report mapping each Phase C requirement to its case IDs, extraction modes and passing assertions. C6 is blocked by uncovered requirements, unexplained source/IL differences, skipped required cases, or a runnable-subset fixture that fails its isolated build/behavior check. Generated-source/resource/reflection limitation cases must report limitations accurately; they do not expand the phase into a general source reconstruction or deployment tool.

## Review and completion

Run focused .NET extractor tests and Python reducer/configuration tests, then existing regression suites. Add viewer/export tests where new vocabulary or diagnostics affect their contracts. Use local deterministic fixtures; tests must not require downloading arbitrary packages.

An independent reviewer must verify that no incomplete input is reported as a closed dependency graph, unregistered packages are not crawled, attributes are off by default, and registered package definitions preserve identity. Close #91 only after its body-extraction acceptance criteria pass, not merely after this plan is approved.
